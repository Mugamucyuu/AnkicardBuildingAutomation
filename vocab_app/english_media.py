"""Public American dictionary recordings, parsed from actual entry markup."""
import re
from urllib.parse import quote, urljoin, urlparse
from .media import MediaResult
from .ojad import Tree
from .public_media import fetch


def audio_result(url, page, publisher, ipa=""):
    return MediaResult(ipa, "IPA" if ipa else "", assets=[{
        "kind": "audio", "url": url, "source_page": page, "attribution": publisher,
        "license": "Publisher terms; personal learning use", "variety": "US",
        "variety_evidence": "Explicit American/US pronunciation block and linked US recording"}])


def cambridge(word):
    page = "https://dictionary.cambridge.org/us/pronunciation/english/" + quote(word.replace(" ", "-"), safe="-")
    root = Tree(fetch(page)).root
    heads = [" ".join(n.text().split()).casefold() for n in root.find("h1")]
    if not any(h == word.casefold() or h == "english pronunciation of " + word.casefold() for h in heads):
        return MediaResult()
    regions = [n for n in root.find() if n.attrs.get('data-pron-region') == 'US']
    for block in regions or [root]:
        for sound in block.find("audio"):
            for source in sound.find("source"):
                url = urljoin(page, source.attrs.get("src", ""))
                parsed = urlparse(url)
                if parsed.hostname == "dictionary.cambridge.org" and "/us_pron/" in parsed.path and parsed.path.endswith(".mp3"):
                    phon = next(block.find(css_class='ipa'), None) if regions else None
                    ipa = '/' + phon.text().strip().strip('/') + '/' if phon else ''
                    return audio_result(url, page, "Cambridge Dictionary · US pronunciation", ipa)
    return MediaResult()


def oxford(word):
    page = "https://www.oxfordlearnersdictionaries.com/definition/english/" + quote(word.replace(" ", "-"), safe="-")
    root = Tree(fetch(page)).root
    for block in root.find(css_class="phons_n_am"):
        if block.attrs.get("wd", "").casefold() != word.casefold():
            continue
        for button in block.find(css_class="pron-us"):
            url = button.attrs.get("data-src-mp3", "")
            parsed = urlparse(url)
            if parsed.hostname == "www.oxfordlearnersdictionaries.com" and "/us_pron/" in parsed.path and parsed.path.endswith(".mp3"):
                phon = next(block.find(css_class="phon"), None)
                return audio_result(url, page, "Oxford Learner's Dictionaries · North American", phon.text().strip() if phon else "")
    return MediaResult()


def longman(word):
    page = "https://www.ldoceonline.com/dictionary/" + quote(word.replace(" ", "-"), safe="-")
    root = Tree(fetch(page)).root
    for button in root.find(css_class="amefile"):
        title = button.attrs.get("title", "").casefold()
        if title != "play american pronunciation of " + word.casefold():
            continue
        url = button.attrs.get("data-src-mp3", "")
        parsed = urlparse(url)
        if parsed.hostname == "www.ldoceonline.com" and "/ameProns/" in parsed.path and parsed.path.endswith(".mp3"):
            return audio_result(url, page, "Longman Dictionary · American pronunciation")
    return MediaResult()


def lookup(registry, word, directory=None, sources=None):
    """Try the next source if lookup OR download fails, preserving each attempt."""
    from .expanded_media import free_dictionary
    from .public_media import download_assets
    adapters = {"wiktionary": ("English Wiktionary", lambda: registry.wiktionary(word, "en")),
                "free_dictionary": ("Free Dictionary API", lambda: free_dictionary(word)),
                "cambridge": ("Cambridge US", lambda: cambridge(word)),
                "oxford": ("Oxford North American", lambda: oxford(word)),
                "longman": ("Longman American", lambda: longman(word))}
    result = MediaResult()
    for key in sources or tuple(adapters):
        if key not in adapters:
            raise ValueError("不支持的英语发音来源。")
        label, adapter = adapters[key]
        try:
            found = adapter()
            status = "matched" if found.assets else "no_match"
            if not result.pronunciation_text and found.pronunciation_text:
                result.pronunciation_text, result.pronunciation_system = found.pronunciation_text, found.pronunciation_system
            if directory is not None and found.assets:
                found = download_assets(found, directory)
                status = "downloaded" if found.assets else "download_failed"
            result.lookup_attempts.append({"source": label, "query": word, "status": status, "audio": len(found.assets)})
            if found.assets:
                result.assets = found.assets
                return result
        except Exception as error:
            result.lookup_attempts.append({"source": label, "query": word, "status": "error", "error_type": type(error).__name__})
    result.warnings.append("公开来源未找到可用的美式真人录音；未用英式或合成语音替代。")
    return result
