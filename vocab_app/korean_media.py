"""Exact Korean dictionary recordings; no TTS or login-gate circumvention."""
import html
import re
from urllib.parse import quote, urlencode, urljoin, urlparse

from .media import MediaResult
from .ojad import Tree
from .public_media import fetch, plain


def krdict(word):
    search = "https://krdict.korean.go.kr/eng/dicMarinerSearch/search?" + urlencode({"mainSearchWord": word})
    markup = fetch(search)
    ids = []
    for link in Tree(markup).root.find("a"):
        head = next(link.find(css_class="word_type1_17"), None)
        if head is None or re.sub(r"\d+$", "", head.text().strip()) != word:
            continue
        match = re.search(r"checkSubmit\('(\d+)'\s*,\s*'Y'\)", link.attrs.get("href", ""))
        if match and match[1] not in ids:
            ids.append(match[1])
    result = MediaResult()
    for ident in ids[:3]:
        page = "https://krdict.korean.go.kr/eng/dicSearch/SearchView?ParaWordNo=" + ident
        detail = fetch(page)
        for block in re.findall(r"<dl\b[^>]*>.*?</dl>", detail, re.S):
            if not re.search(r"<dt\b[^>]*>\s*(?:Pronunciation|발음)\s*</dt>", block):
                continue
            clean = plain(re.sub(r"<a\b[^>]*>.*?</a>", "", block, flags=re.S))
            for reading in re.findall(r"\[[가-힣ː: ]+\]", clean):
                entry = {"text": reading, "source": "한국어기초사전 · 발음", "source_page": page}
                if entry not in result.phonetic_hangul:
                    result.phonetic_hangul.append(entry)
            match = re.search(r"fnSoundPlay\('(https://krdicmedia\.korean\.go\.kr/[^']+\.mp3)'\)", block)
            if match and not result.assets:
                result.assets.append({"kind": "audio", "url": html.unescape(match[1]), "source_page": page,
                    "headword": word, "variety": "Korean dictionary pronunciation",
                    "attribution": "National Institute of Korean Language · Basic Korean Dictionary",
                    "license": "Source copyright policy; personal learning use",
                    "license_url": "https://krdict.korean.go.kr/eng/kboardPolicy/copyRightTermsInfo"})
        if result.assets:
            break
    return result


def daum(word):
    search = "https://dic.daum.net/search.do?q=" + quote(word, safe="")
    result = MediaResult()
    for link in Tree(fetch(search)).root.find("a"):
        href = link.attrs.get("href", "")
        if "wordid=kkw" not in href or link.text().strip() != word:
            continue
        page = urljoin("https://dic.daum.net/", href)
        if urlparse(page).hostname != "dic.daum.net":
            continue
        detail = fetch(page)
        tree = Tree(detail).root
        head = next(tree.find(css_class="txt_cleanword"), None)
        if head is None or re.sub(r"\d+$", "", head.text().strip()) != word:
            continue
        # Select the Korean entry's pronunciation block, never English example audio.
        for section in tree.find(css_class="txt_info"):
            if "발음" not in section.text():
                continue
            for audio in section.find("a"):
                url = audio.attrs.get("data-url", "")
                parsed = urlparse(url)
                if parsed.hostname != "t1.daumcdn.net" or not parsed.path.startswith("/language/"):
                    continue
                url = "https://t1.daumcdn.net" + parsed.path
                result.assets.append({"kind": "audio", "url": url, "source_page": page, "file_extension": ".mp3",
                    "headword": word, "variety": "Korean dictionary pronunciation", "attribution": "Daum Korean Dictionary",
                    "license": "Publisher terms; personal learning use"})
                return result
        break
    return result
