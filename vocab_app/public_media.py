"""Public pronunciation lookups and Commons images; no model credentials."""
import hashlib
import html
import json
import re
import time
from pathlib import Path
from urllib.parse import urlencode, quote, urlparse
from urllib.request import Request, urlopen
from .media import MediaResult, MediaRegistry

AGENT = "VocabularyCardPrototype/0.2 (personal vocabulary study; low volume)"

def fetch(url, binary=False):
    if urlparse(url).scheme != "https":
        raise ValueError("媒体仅允许 HTTPS。")
    for attempt in range(2):
        try:
            with urlopen(Request(url, headers={"User-Agent": AGENT}), timeout=30) as response:
                content = response.read(12_000_001)
            break
        except Exception:
            if attempt:
                raise
            time.sleep(1)
    if len(content) > 12_000_000:
        raise ValueError("媒体文件过大。")
    return content if binary else content.decode("utf-8")

def api(host, **params):
    return json.loads(fetch("https://" + host + "/w/api.php?" + urlencode({"format":"json", **params})))

def plain(text):
    return html.unescape(re.sub("<[^>]+>", "", text)).strip()

def commons_metadata(title):
    data = api("commons.wikimedia.org", action="query", titles=title,
               prop="imageinfo", iiprop="url|size|extmetadata", iiurlwidth=900)
    page = next(iter(data["query"]["pages"].values()))
    info = page["imageinfo"][0]
    meta = info.get("extmetadata", {})
    return {
        "url": info.get("thumburl") or info["url"], "source_page": info["descriptionurl"],
        "attribution": plain(meta.get("Artist", {}).get("value", "")),
        "license": plain(meta.get("LicenseShortName", {}).get("value", "")),
        "license_url": meta.get("LicenseUrl", {}).get("value", ""),
        "description": plain(meta.get("ImageDescription", {}).get("value", "")),
        "title": title, "width": info.get("width", 0), "height": info.get("height", 0),
    }

class PublicMediaRegistry(MediaRegistry):
    def lookup(self, source, language, word):
        if language not in ("en", "ja", "ko"):
            raise ValueError("不支持当前语言。")
        if source == "commons":
            return self.search_image(word)
        if source in ("cambridge", "oxford", "longman", "free_dictionary"):
            if language != "en":raise ValueError("该英语发音来源仅支持英语。")
            from .english_media import lookup
            return lookup(self, word, sources=(source,))
        if source == "daum":
            if language != "ko":raise ValueError("Daum 韩语发音仅支持韩语。")
            from .korean_media import daum
            return daum(word)
        if source in ("kanjium", "ojad", "ubiq"):
            if language != "ja":
                raise ValueError("该声调来源仅支持日语。")
            return self.japanese_accent(word, source=source)
        if source == "auto":
            from .expanded_media import lookup_expanded
            return lookup_expanded(self, language, word)
        if source not in ("wiktionary", "krdict"):
            return super().lookup(source, language, word)
        if source == "krdict" and language != "ko":
            raise ValueError("韩国语词典仅支持韩语。")
        try:
            if source == "krdict":
                return self.korean(word)
            return self.wiktionary(word, language)
        except Exception:
            return MediaResult(warnings=[source + " 媒体查询失败；未用 AI 编造或合成发音替代。"])

    def japanese_accent(self, word, reading="", source="auto"):
        from .japanese_pitch import lookup, PRIORITY
        return lookup(word, reading, PRIORITY if source == "auto" else (source,))

    def english_audio(self, word, directory=None, sources=None):
        from .english_media import lookup
        return lookup(self, word, directory, sources)

    def wiktionary(self, word, language, host="en.wiktionary.org"):
        name = {"en":"English","ja":"Japanese","ko":"Korean"}[language]
        if host == "ja.wiktionary.org":
            name = "日本語"
        sections = api(host, action="parse", page=word, prop="sections")["parse"]["sections"]
        index = next(s["index"] for s in sections if s["line"] == name and s["level"] == "2")
        markup = api(host, action="parse", page=word, section=index, prop="text")["parse"]["text"]["*"]
        ipas = [plain(s) for s in re.findall(r'<span[^>]*class="[^"]*\bIPA\b[^"]*"[^>]*>(.*?)</span>', markup, re.S)]
        # Dialect selection is tied to a labelled pronunciation item, not a
        # global first-IPA guess. Keep the source label in metadata.
        ipa = ""
        if language == "en":
            for item in re.findall(r"<li\b[^>]*>.*?</li>", markup, re.S):
                if re.search(r"General American|GenAm|US", plain(item)):
                    # Qualifier text may itself contain IPA (/æ/ raising).
                    # The word transcription follows the IPA-key superscript.
                    transcription = item.split("</sup>", 1)[-1]
                    candidate = re.findall(r'<span[^>]*class="[^"]*\bIPA\b[^"]*"[^>]*>(.*?)</span>', transcription, re.S)
                    if candidate:
                        ipa = plain(candidate[0])
                        break
        elif ipas:
            ipa = ipas[0]
        titles = re.findall(r'<audio[^>]*data-mwtitle="([^"]+)"', markup)
        if language == "en":
            titles = [t for t in titles if re.search(r"(?:en[-_]us|en[-_]US)", t, re.I)]
        elif language == "ja":
            titles = [t for t in titles if t.lower().startswith("ja") or "(jpn)" in t.lower()]
        elif language == "ko":
            titles = [t for t in titles if t.lower().startswith("ko") or "(kor)" in t.lower()]
        assets, warnings = [], []
        if titles:
            asset = commons_metadata("File:" + html.unescape(titles[0]))
            # Use the directly linked MP3 transcode, if present, else the original.
            matching = re.search(r'<audio[^>]*data-mwtitle="' + re.escape(titles[0]) + r'".*?</audio>', markup, re.S)
            if matching:
                source = re.search(r'<source[^>]*src="([^"]+)"[^>]*type="audio/mpeg"', matching.group(0))
                if source:
                    asset["url"] = "https:" + html.unescape(source[1]) if source[1].startswith("//") else html.unescape(source[1])
            asset.update(kind="audio", variety="US" if language == "en" else name)
            assets.append(asset)
        else:
            warnings.append("未找到符合目标语言／美式筛选条件的真人录音。")
        if not ipa:
            warnings.append("未找到可匹配的音标；保留来源链接供复核。")
        result = MediaResult(ipa, "IPA", assets, warnings)
        if language == "ko":
            for item in re.findall(r'<li\b[^>]*>.*?</li>', markup, re.S):
                if "Phonetic hangul:" not in item:
                    continue
                text = plain(item).split("Phonetic hangul:", 1)[1].strip()
                for reading in re.findall(r'\[[가-힣ː: ̚.]+\]', text):
                    result.phonetic_hangul.append({"text": reading, "source": "Wiktionary · Phonetic Hangul", "source_page": "https://" + host + "/wiki/" + quote(word, safe="") + "#Korean"})
        if language == "ja":
            text = plain(markup)
            patterns = re.findall(r'\(Tokyo\)[^\n]{0,180}?\((Heiban|Atamadaka|Nakadaka|Odaka)[^\n]{0,30}?\[(\d+)\]', text)
            for kind, number in patterns:
                label = {"Heiban":"平板型","Atamadaka":"頭高型","Nakadaka":"中高型","Odaka":"尾高型"}[kind]
                result.pitch_accents.append({"label":"東京式 ["+number+"] "+label,"source_page":"https://"+host+"/wiki/"+quote(word,safe=""),"reading_scope":word})
        return result

    def korean(self, word):
        from .korean_media import krdict
        return krdict(word)

    def image_candidates(self, query, limit=5):
        data = api("commons.wikimedia.org", action="query", generator="search",
                   gsrsearch=query, gsrnamespace=6, gsrlimit=limit)
        return [p["title"] for p in sorted(data.get("query", {}).get("pages", {}).values(),
                                         key=lambda p:p.get("index",0))]

    def image_search(self, query, limit=6):
        """Fetch a small search result AND ranking/credit metadata in one API call."""
        data = api('commons.wikimedia.org', action='query', generator='search',
                   gsrsearch=query, gsrnamespace=6, gsrlimit=min(limit, 6),
                   prop='imageinfo', iiprop='url|size|mime|extmetadata', iiurlwidth=900,
                   iiextmetadatafilter='Artist|LicenseShortName|LicenseUrl|ImageDescription',
                   iiextmetadatalanguage='en')
        assets = []
        for page in sorted(data.get('query', {}).get('pages', {}).values(), key=lambda p: p.get('index', 0)):
            info = (page.get('imageinfo') or [{}])[0]
            meta = info.get('extmetadata', {})
            assets.append({'kind': 'image', 'title': page.get('title', ''),
                           'url': info.get('thumburl') or info.get('url', ''),
                           'source_page': info.get('descriptionurl', ''),
                           'width': info.get('width', 0), 'height': info.get('height', 0),
                           'attribution': plain(meta.get('Artist', {}).get('value', '')),
                           'license': plain(meta.get('LicenseShortName', {}).get('value', '')),
                           'license_url': meta.get('LicenseUrl', {}).get('value', ''),
                           'description': plain(meta.get('ImageDescription', {}).get('value', ''))[:2400]})
        return assets

    def select_image(self, word, language, senses, plan):
        from .image_selection import select_image
        return select_image(self, word, language, senses, plan)

    def representative_image(self, topic):
        """Exact Wikipedia article representative, with Commons license metadata."""
        data = api('en.wikipedia.org', action='query', titles=topic, redirects=1,
                   prop='pageimages|extracts|pageprops', piprop='name', pilicense='free',
                   exintro=1, explaintext=1, exsentences=2, ppprop='disambiguation')
        page = next(iter(data.get('query', {}).get('pages', {}).values()), {})
        if 'disambiguation' in page.get('pageprops', {}) or not page.get('pageimage') or page.get('missing') is not None:
            return []
        # Require Commons attribution even if Wikipedia also has local files.
        asset = self.image('File:' + page['pageimage'])
        asset.assets[0]['representative_article'] = {'title':page['title'], 'extract':page.get('extract', '')[:1200],
                                                  'url':'https://en.wikipedia.org/wiki/' + quote(page['title'].replace(' ', '_'), safe='')}
        return asset.assets

    def image(self, title):
        asset = commons_metadata(title)
        if not asset["license"] or not asset["attribution"]:
            raise ValueError("图片缺少许可或作者元数据。")
        asset["kind"] = "image"
        return MediaResult(assets=[asset])

    def search_image(self, word):
        """Use Commons relevance order; no model calls or manual image curation."""
        result = MediaResult(selection={"source": "commons", "query": word,
                             "strategy": "first_available", "candidate_titles": [],
                             "selected_title": None})
        try:
            titles = self.image_candidates(word, limit=5)
            result.selection["candidate_titles"] = titles
            for title in titles:
                try:
                    candidate = self.image(title)
                    url = candidate.assets[0]["url"]
                    if Path(urlparse(url).path).suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                        raise ValueError("不是支持的静态图片。")
                    result.assets = candidate.assets
                    result.selection["selected_title"] = title
                    result.lookup_attempts.append({"title": title, "status": "selected"})
                    break
                except Exception:
                    result.lookup_attempts.append({"title": title, "status": "unavailable"})
            if not result.assets:
                result.warnings.append("Commons 未找到可用图片；本词卡不配图。")
        except Exception:
            result.warnings.append("Commons 图片搜索失败；本词卡不配图。")
        return result

def download_assets(result, directory, relative_prefix="media"):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    kept = []
    for asset in result.assets:
        try:
            url = asset["url"]
            host = urlparse(url).hostname
            if host not in ("upload.wikimedia.org", "thumb.wikimedia.org", "krdicmedia.korean.go.kr", "t1.daumcdn.net", "api.dictionaryapi.dev", "ssl.gstatic.com", "www.gavo.t.u-tokyo.ac.jp", "gavo.t.u-tokyo.ac.jp", "dictionary.cambridge.org", "www.oxfordlearnersdictionaries.com", "www.ldoceonline.com"):
                raise ValueError("不支持此媒体主机。")
            ext = Path(urlparse(url).path).suffix.lower()
            extensionless_audio = host == "t1.daumcdn.net" and asset.get("kind") == "audio" and not ext
            if extensionless_audio:ext = ".mp3"
            if ext not in (".mp3",".ogg",".wav",".jpg",".jpeg",".png",".webp"):
                raise ValueError("不支持此媒体格式。")
            filename = hashlib.sha256(url.encode()).hexdigest()[:20] + ext
            target = directory / filename
            if not target.exists():
                content = fetch(url, binary=True)
                if asset.get("kind") == "audio" and not (content.startswith(b"ID3") or content.startswith(b"OggS") or (content.startswith(b"RIFF") and content[8:12]==b"WAVE") or (len(content)>1 and content[0]==255 and content[1]&224==224)):
                    raise ValueError("响应不是支持的音频文件。")
                if extensionless_audio and not (content.startswith(b"ID3") or (len(content)>1 and content[0]==255 and content[1]&224==224)):
                    raise ValueError("Daum 响应不是 MP3 录音。")
                if asset.get("kind") == "image" and not (
                    content.startswith(b"\xff\xd8\xff") or content.startswith(b"\x89PNG\r\n\x1a\n") or
                    (content.startswith(b"RIFF") and content[8:12] == b"WEBP")
                ):
                    raise ValueError("响应不是支持的图片文件。")
                target.write_bytes(content)
            asset["local_path"] = relative_prefix + "/" + filename
            kept.append(asset)
        except Exception:
            result.warnings.append("一个媒体文件下载失败；未使用无效链接替代。")
    result.assets = kept
    if result.selection.get('strategy') == 'sense_metadata_v1':
        selected = result.selection.get('selected_title')
        if kept:
            result.selection['status'] = 'downloaded'
            result.lookup_attempts.append({'title': selected, 'status': 'downloaded'})
        elif selected:
            # Only previously approved candidates may be used after a failed
            # download; never fall back to the unfiltered search order.
            result.lookup_attempts.append({'title': selected, 'status': 'download_failed'})
            approved = result.selection.get('approved_assets', [])
            for asset in [a for a in approved if a.get('title') != selected][:3]:
                candidate = download_assets(MediaResult(assets=[dict(asset)]), directory, relative_prefix)
                result.lookup_attempts.append({'title': asset.get('title'), 'status': 'downloaded' if candidate.assets else 'download_failed'})
                if candidate.assets:
                    result.assets = candidate.assets
                    result.selection.update(selected_title=asset.get('title'), status='downloaded')
                    break
            if not result.assets:
                result.selection.update(selected_title=None, status='download_failed')
        return result
    if kept and result.selection.get("strategy") == "first_available":
        result.lookup_attempts.append({"title": result.selection.get("selected_title"), "status": "downloaded"})
    # A selected search hit can still fail to download. Continue in search
    # order rather than leaving a broken image or choosing a random fallback.
    if not kept and result.selection.get("strategy") == "first_available" and result.selection.get("selected_title"):
        titles = result.selection.get("candidate_titles", [])
        selected = result.selection.get("selected_title")
        remaining = titles[titles.index(selected) + 1:] if selected in titles else []
        result.selection["selected_title"] = None
        for title in remaining:
            try:
                candidate = PublicMediaRegistry().image(title)
                url = candidate.assets[0]["url"]
                if Path(urlparse(url).path).suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                    continue
                candidate = download_assets(candidate, directory, relative_prefix)
                if candidate.assets:
                    result.assets = candidate.assets
                    result.selection["selected_title"] = title
                    result.lookup_attempts.append({"title": title, "status": "downloaded"})
                    break
                result.lookup_attempts.append({"title": title, "status": "download_failed"})
            except Exception:
                result.lookup_attempts.append({"title": title, "status": "unavailable"})
        if not result.assets:
            result.warnings.append("搜索结果均无法下载；本词卡不配图。")
    return result
