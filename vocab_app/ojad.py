"""OJAD dictionary-form pitch accents, independent of recording availability."""
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import quote

from .media import MediaResult
from .public_media import fetch


class Node:
    def __init__(self, tag="", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def has_class(self, name):
        return name in self.attrs.get("class", "").split()

    def find(self, tag=None, css_class=None):
        for child in self.children:
            if isinstance(child, Node):
                if (tag is None or child.tag == tag) and (css_class is None or child.has_class(css_class)):
                    yield child
                yield from child.find(tag, css_class)

    def text(self):
        return "".join(child.text() if isinstance(child, Node) else child for child in self.children)


class Tree(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def normalize(text):
    text = unicodedata.normalize("NFKC", text)
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text if not c.isspace())


def matches(word, headword, kana, reading=""):
    forms = [normalize(form) for form in headword.split("・")]
    target = normalize(word)
    if target in forms:
        return True
    kanji = "".join(re.findall(r"[\u4e00-\u9fff]", target))
    if not kanji:
        # Only the dictionary-form reading, never a potential/inflected form.
        return target == normalize(kana)
    # Reading fallback may reconcile omitted okurigana, but must not select a
    # different homophone such as 橋 vs 箸 merely because both read はし.
    return bool(reading and normalize(reading) == normalize(kana) and
                kanji == "".join(re.findall(r"[\u4e00-\u9fff]", forms[0])))


def parse(markup, word, page, reading=""):
    result = MediaResult()
    for row in Tree(markup).root.find("tr"):
        head = next(row.find(css_class="midashi_word"), None)
        cell = next(row.find("td", "katsuyo_jisho_js"), None)
        if head is None or cell is None:
            continue
        headword = head.text().strip()
        blocks = list(cell.find(css_class="katsuyo_proc")) or [cell]
        for block in blocks:
            accent = next(block.find(css_class="accented_word"), None)
            if accent is None:
                continue
            moras = [span for span in accent.find("span") if any(c.startswith("mola_") for c in span.attrs.get("class", "").split())]
            if not moras or any(not mora.text().strip() for mora in moras):
                continue
            kana = "".join(mora.text().strip() for mora in moras)
            if not matches(word, headword, kana, reading):
                continue
            tops = [i + 1 for i, mora in enumerate(moras) if mora.has_class("accent_top")]
            if len(tops) > 1:
                continue
            nucleus = tops[0] if tops else 0
            kind = "平板型" if nucleus == 0 else "頭高型" if nucleus == 1 else "尾高型" if nucleus == len(moras) else "中高型"
            pitch = {"label": f"東京式 [{nucleus}] {kind}", "source": "OJAD", "source_page": page,
                     "reading_scope": headword.split("・")[0], "reading": kana,
                     "nucleus": nucleus, "mora_count": len(moras),
                     "pattern": "".join("H" if (nucleus == 1 and i == 1) or (i > 1 and (nucleus == 0 or i <= nucleus)) else "L" for i in range(1, len(moras) + 1))}
            if pitch not in result.pitch_accents:
                result.pitch_accents.append(pitch)
            if not result.assets:
                sounds = [a.attrs.get("id", "") for a in block.find("a")]
                sid = next((s for s in sounds if re.fullmatch(r"\d+_1_\d+_female", s)), None)
                sid = sid or next((s for s in sounds if re.fullmatch(r"\d+_1_\d+_male", s)), None)
                if sid:
                    gender = sid.rsplit("_", 1)[1]
                    group = str(int(sid.split("_")[0]) // 100).zfill(3)
                    result.assets.append({"kind": "audio", "url": f"https://www.gavo.t.u-tokyo.ac.jp/ojad/sound4/mp3/{gender}/{group}/{sid}.mp3",
                                          "source_page": page, "attribution": "OJAD project; professional speaker",
                                          "license": "OJAD personal learning use; redistribution not verified",
                                          "variety": "Japanese", "headword": headword})
    return result


def lookup(word, reading=""):
    result = MediaResult()
    queries = [word]
    if reading and normalize(reading) != normalize(word) and re.fullmatch(r"[ぁ-ゖァ-ヺー\s]+", reading):
        queries.append(reading.strip())
    for query in queries:
        page = "https://www.gavo.t.u-tokyo.ac.jp/ojad/search/index/word:" + quote(query, safe="")
        try:
            found = parse(fetch(page), word, page, reading)
            result.lookup_attempts.append({"source": "OJAD", "query": query, "source_page": page,
                                           "status": "matched" if found.pitch_accents else "no_match",
                                           "audio": len(found.assets), "pitch": len(found.pitch_accents)})
            if found.pitch_accents:
                result.pitch_accents = found.pitch_accents
                result.assets = found.assets
                return result
        except Exception as error:
            result.lookup_attempts.append({"source": "OJAD", "query": query, "source_page": page,
                                           "status": "error", "error_type": type(error).__name__})
    return result
