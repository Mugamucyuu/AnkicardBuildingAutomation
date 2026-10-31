"""Japanese dictionary pitch: local Kanjium -> OJAD -> U-biq."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from .media import MediaResult
from .ojad import Tree, Node, normalize, lookup as lookup_ojad
from .public_media import fetch
from .settings import RESOURCE_ROOT

PRIORITY = ("kanjium", "ojad", "ubiq")
LABELS = {"kanjium": "Kanjium", "ojad": "OJAD", "ubiq": "U-biq"}
DATA = RESOURCE_ROOT / "data/pronunciation/kanjium/accents.tsv"
SMALL_KANA = set("ゃゅょぁぃぅぇぉゎゕゖ")


def moras(reading):
    reading = normalize(reading)
    if not re.fullmatch(r"[ぁ-ゖー]+", reading):
        return []
    result = []
    for char in reading:
        if char in SMALL_KANA and result:
            result[-1] += char
        else:
            result.append(char)
    return result


def pitch_record(word, reading, nucleus, source, page, **metadata):
    count = len(moras(reading))
    if not count or not 0 <= nucleus <= count:
        raise ValueError("声调核不在有效音拍范围内。")
    kind = "平板型" if nucleus == 0 else "頭高型" if nucleus == 1 else "尾高型" if nucleus == count else "中高型"
    return {"label": f"東京式 [{nucleus}] {kind}", "source": source, "source_page": page,
            "reading_scope": word, "reading": normalize(reading), "nucleus": nucleus, "mora_count": count,
            "pattern": "".join("H" if (nucleus == 1 and i == 1) or (i > 1 and (nucleus == 0 or i <= nucleus)) else "L" for i in range(1, count + 1)), **metadata}


def kanji(text):
    return "".join(re.findall(r"[\u4e00-\u9fff]", normalize(text)))


@lru_cache(maxsize=2)
def load_kanjium(path, modified_ns, size):
    path = Path(path)
    raw = path.read_bytes()
    metadata = json.loads(path.with_name("metadata.json").read_text(encoding="utf-8"))
    if hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
        raise ValueError("Kanjium 数据校验失败。")
    words, readings = {}, {}
    for number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        columns = line.split("\t")
        if len(columns) != 3 or not re.fullmatch(r"\d+(?:,\d+)*", columns[2]):
            continue
        head, reading, positions = columns
        entry = (head, normalize(reading), tuple(int(n) for n in positions.split(",")), number)
        words.setdefault(normalize(head), []).append(entry)
        readings.setdefault(normalize(reading), []).append(entry)
    return words, readings, metadata


def lookup_kanjium(word, reading="", data_path=DATA):
    path = Path(data_path)
    stat = path.stat()
    words, readings, metadata = load_kanjium(str(path), stat.st_mtime_ns, stat.st_size)
    target, hint = normalize(word), normalize(reading)
    entries = words.get(target, [])
    if hint:
        entries = [entry for entry in entries if entry[1] == hint]
    if not entries:
        if not kanji(word):
            entries = readings.get(target, []) if not hint or hint == target else []
        elif hint:
            # Permit spelling/okurigana differences, but never different kanji
            # that happen to have the same reading.
            entries = [entry for entry in readings.get(hint, []) if kanji(entry[0]) == kanji(word)]
    result = MediaResult()
    seen = set()
    for head, kana, positions, line in entries:
        for nucleus in positions:
            key = (head, kana, nucleus)
            if key in seen:
                continue
            try:
                result.pitch_accents.append(pitch_record(head, kana, nucleus, "Kanjium", metadata["source_page"] + "#L" + str(line),
                    attribution=metadata["attribution"], license=metadata["license"], license_url=metadata["license_url"],
                    data_version=metadata["revision"]))
                seen.add(key)
            except ValueError:
                continue
    return result


def ubiq_page(reading):
    kana = normalize(reading)
    if not moras(kana):
        return None
    first = unicodedata.normalize("NFD", kana[0])[0]
    first = {"ゃ": "や", "ゅ": "ゆ", "ょ": "よ", "っ": "つ"}.get(first, first)
    chars = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわ"
    pages = "a i u e o ka ki ku ke ko sa si su se so ta ti tu te to na ni nu ne no ha hi hu he ho ma mi mu me mo ya yu yo ra ri ru re ro wa".split()
    name = dict(zip(chars, pages)).get(first)
    return "https://accent.u-biq.org/" + name + ".html" if name else None


def parse_ubiq(markup, word, reading, page):
    result = MediaResult()
    for row in Tree(markup).root.find("tr"):
        cell = next(row.find("td"), None)
        if cell is None:
            continue
        segments = []
        for child in cell.children:
            if isinstance(child, str):
                if segments and child.strip():
                    break
                continue
            if isinstance(child, Node):
                css = next((c for c in ("a1", "a2", "a3", "a4") if child.has_class(c)), None)
                if css:
                    segments.append((css, child.text()))
                elif segments:
                    break
        kana = normalize("".join(text for _, text in segments))
        if not segments or kana != normalize(reading) or not moras(kana):
            continue
        match = re.search(r"[（(]([^）)]+)[）)]", cell.text())
        forms = re.split(r"\s*[/／・、]\s*", match[1]) if match else [kana]
        matched_form = forms[0].strip()
        if kanji(word):
            matched_form = next((form.strip() for form in forms if normalize(word) == normalize(form) or kanji(word) == kanji(form)), "")
            if not matched_form:
                continue
        if not kanji(word) and normalize(word) != kana:
            continue
        tones = "".join(("H" if css in ("a2", "a4") else "L") * len(moras(text)) for css, text in segments)
        if len(tones) != len(moras(kana)):
            continue
        drops = [i + 1 for i in range(len(tones) - 1) if tones[i:i + 2] == "HL"]
        if segments[-1][0] == "a2":
            drops.append(len(tones))
        if len(drops) > 1:
            continue
        nucleus = drops[0] if drops else 0
        record = pitch_record(matched_form, kana, nucleus, "U-biq", page,
                              attribution="U-biq 日本語教育用アクセント辞典", license="Copyright U-biq; see source")
        if record["pattern"] != tones:
            continue
        if record not in result.pitch_accents:
            result.pitch_accents.append(record)
    return result


def lookup_ubiq(word, reading=""):
    reading = reading or (word if not kanji(word) else "")
    page = ubiq_page(reading)
    if page is None:
        return MediaResult(lookup_attempts=[{"source": "U-biq", "query": word, "status": "needs_reading"}])
    raw = fetch(page, binary=True)
    # This site declares Shift_JIS. Do not force UTF-8 as with modern sources.
    markup = raw.decode("cp932")
    return parse_ubiq(markup, word, reading, page)


def lookup(word, reading="", sources=PRIORITY):
    merged = MediaResult()
    adapters = {"kanjium": lookup_kanjium, "ojad": lookup_ojad, "ubiq": lookup_ubiq}
    for source in sources:
        if source not in adapters:
            raise ValueError("不支持的日语声调来源。")
        try:
            found = adapters[source](word, reading)
            merged.lookup_attempts.extend(found.lookup_attempts or [{"source": LABELS[source], "query": word,
                "reading": reading, "status": "matched" if found.pitch_accents else "no_match", "pitch": len(found.pitch_accents)}])
            if found.pitch_accents:
                merged.pitch_accents = found.pitch_accents
                merged.assets = found.assets
                return merged
        except Exception as error:
            merged.lookup_attempts.append({"source": LABELS[source], "query": word, "reading": reading,
                                           "status": "error", "error_type": type(error).__name__})
    merged.warnings.append("日语声调尚无可核对记录；已查：" + ", ".join(LABELS[s] for s in sources))
    return merged
