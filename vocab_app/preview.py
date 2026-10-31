"""Responsive vocabulary card: audio -> image -> senses -> analysis."""
import html
import re
from urllib.parse import urlparse

LABELS = {
 "en": {"pronunciation":"Pronunciation", "meaning":"Definition & Examples", "etymology":"Etymology",
        "nuance":"Native Speaker Analysis", "synonyms":"Nuances & Synonyms", "collocations":"Common Collocations",
        "inflections":"Word Forms", "forms":"Other Forms", "sources":"Sources & Tags"},
 "ja": {"pronunciation":"読み方・発音", "meaning":"意味と使用例", "etymology":"語源",
        "nuance":"母語話者の視点からの分析", "synonyms":"同義語・類義語との違い", "collocations":"よく使う組み合わせ",
        "inflections":"活用", "forms":"他の表記", "sources":"出典・タグ"},
 "ko": {"pronunciation":"读音与发音", "meaning":"基本释义与例句", "etymology":"汉字表记和语源",
        "nuance":"母语者小贴士与语感", "synonyms":"近义词辨析", "collocations":"常见搭配",
        "inflections":"词形变化说明", "forms":"其他表记", "sources":"来源与标签"},
}
CSS = """
.vocab-card{--ink:#24303d;--muted:#657482;--accent:#246864;--line:#dce5e4;color:var(--ink);background:#fff;max-width:790px;margin:24px auto;padding:32px 38px;font:17px/1.85 system-ui,'Segoe UI','Yu Gothic','Malgun Gothic',sans-serif;text-align:left;border-radius:16px;box-sizing:border-box}
.vocab-card h1{font-size:40px;line-height:1.25;margin:0 0 8px;letter-spacing:.015em}
.vocab-card h2{font-size:20px;color:var(--accent);margin:0 0 14px;line-height:1.5}
.vocab-card h3{font-size:18px;margin:12px 0}
.vocab-card .part-of-speech{font-size:1em;font-weight:600;color:var(--ink)}
.vocab-card strong{font-weight:700}
.vocab-card section{border-top:1px solid var(--line);padding-top:22px;margin-top:24px}
.vocab-card p{margin:10px 0;overflow-wrap:anywhere}
.vocab-card .meta,.vocab-card figcaption{font-size:12px;color:var(--muted);line-height:1.65}
.vocab-card .alternative-forms,.vocab-card .alternative-forms strong{font-size:inherit;color:var(--ink);line-height:inherit}
.vocab-card .phonetic{font-size:20px;letter-spacing:.03em}
.vocab-card audio{display:block;width:100%;max-width:420px;margin:10px 0}
.vocab-card figure{margin:22px 0 8px}.vocab-card img{display:block;max-width:100%;width:auto;max-height:300px;border-radius:10px;margin:auto;object-fit:contain}
.vocab-card .sense{padding:8px 0 10px}.vocab-card .examples{padding-left:23px;margin:12px 0}
.vocab-card .examples li{margin:9px 0}.vocab-card .tag{display:inline-block;background:var(--tag-bg,#edf3f1);color:var(--ink);padding:2px 8px;margin:3px 4px 3px 0;border-radius:5px;font-size:12px}
.vocab-card details{border-top:1px solid var(--line);margin-top:28px;padding-top:16px;font-size:13px}
.vocab-card summary{cursor:pointer;color:var(--ink);font-size:15px;font-weight:600}.vocab-card a{color:var(--accent)}
.vocab-card details,.vocab-card details p,.vocab-card details li{color:var(--ink)}
@media(max-width:600px){.vocab-card{margin:0;padding:24px 19px;border-radius:0;font-size:16px}.vocab-card h1{font-size:34px}}
.nightMode .vocab-card,.night_mode .vocab-card,.vocab-card.nightMode,.vocab-card.night_mode{--ink:#e1e8ed;--muted:#c0cbd3;--accent:#9eddd4;--line:#54616a;--tag-bg:#39464f;background:#252c32;color:var(--ink)}
"""
def esc(value):
    return html.escape(str(value), quote=True)

def paragraphs(text):
    # Older/model prose sometimes places several comparison headings in one paragraph.
    text = re.sub(r'(?<=[。.!?：:])\s*(?=\*\*(?:[^*\n]{1,65}(?:vs\.|との違い|Emphasis|Context|Native-speaker|强调|语气|语境))[^*\n]*\*\*)', '\n\n', str(text))
    text = re.sub(r'(?<=\S) +(?=\*\*(?:Emphasis|Context & Tone|Native-speaker impressions)[^*]*\*\*)', '\n\n', text)
    text = re.sub(r'(?<=\S)[ \t]+(?=(?:Emphasis|Context & Tone|Native-speaker impressions)\s*[:：])', '\n\n', text)
    blocks = re.split(r"\n\s*\n", str(text).strip())
    return "".join("<p>" + inline_text(block).replace("\n","<br>") + "</p>" for block in blocks if block)

def inline_text(text):
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(text))

def local_asset(asset):
    path = asset.get("local_path", "")
    return path if re.fullmatch(r"media/[a-zA-Z0-9_.-]+", path) else ""

def anki_asset_name(asset, local_path):
    name = asset.get("anki_filename", local_path.split('/')[-1])
    return name if re.fullmatch(r"[a-zA-Z0-9_.() -]+", name) else ""

def source_link(asset):
    url = asset.get("source_page", "")
    if urlparse(url).scheme != "https":
        return ""
    return '<a href="' + esc(url) + '" target="_blank" rel="noopener">source</a>'

def render_preview(note, standalone=True, anki=False):
    language = note["language"]
    labels = LABELS[language]
    offline = note["provenance"]["provider"] == "offline"
    status = "离线样例 · 待审核" if offline else {"en":"AI generated · Preview", "ja":"AI生成・確認用", "ko":"AI 生成 · 测试预览"}[language]
    if anki and not offline:
        status = {"en": "AI generated", "ja": "AI生成", "ko": "AI 生成"}[language]
    chunks = []
    if standalone:
        chunks += ['<!doctype html><html lang="' + esc(language) + '"><head><meta charset="utf-8">',
                   '<meta name="viewport" content="width=device-width,initial-scale=1">',
                   '<title>' + esc(note["word"]) + ' · Vocabulary Card</title></head><body style="margin:0;background:#edf1ef">']
    chunks += ['<style>' + CSS + '</style><main class="vocab-card">',
               '<h1>' + esc(note["word"]) + '</h1><div class="meta">' + esc(status) + '</div>',
               '<section class="pronunciation"><h2>' + labels["pronunciation"] + '</h2>']
    pronunciation = note.get("pronunciation", {})
    if pronunciation.get("pronunciation_text"):
        chunks += ['<div class="phonetic">' + esc(pronunciation["pronunciation_text"]) + '</div>']
    if language == "ko":
        hangul = pronunciation.get("phonetic_hangul", [])
        chunks += ['<p class="phonetic-hangul"><strong>实际读音（韩文）：</strong>' + (' / '.join(esc(p["text"]) + ' (' + esc(p.get("source", "")) + ' · ' + source_link(p) + ')' for p in hangul) if hangul else '公开来源未确认') + '</p>']
    if note.get("reading"):
        chunks += ['<div>' + esc(note["reading"]) + '</div>']
    if language == "ja":
        pitches = pronunciation.get("pitch_accents", [])
        chunks += ['<p class="pitch-accent">アクセント：' + (' / '.join(esc(p.get("reading_scope", "") + "：" + p["label"] + (" · " + p["source"] if p.get("source") else "")) + ' (' + source_link(p) + ')' for p in pitches) if pitches else '公開資料で未確認') + '</p>']
    if language == "ja":
        forms = note.get("alternative_forms") or "特になし"
        chunks += ['<p class="alternative-forms"><strong>' + labels["forms"] + '：</strong>' + esc(forms) + '</p>']
    for asset in pronunciation.get("assets", []):
        path = local_asset(asset)
        if asset.get("kind") == "audio" and path:
            chunks += ['[sound:' + esc(anki_asset_name(asset, path)) + ']'] if anki else ['<audio controls preload="none" src="' + esc(path) + '"></audio>']
            if asset.get("headword"):
                chunks += ['<p>' + esc(asset["headword"]) + ' · ' + source_link(asset) + '</p>']
    for warning in pronunciation.get("warnings", []):
        chunks += ['<p class="meta">' + esc(warning) + '</p>']
    chunks += ['</section>']
    for asset in note.get("images", {}).get("assets", []):
        path = local_asset(asset)
        if asset.get("kind") == "image" and path:
            if anki:
                path = anki_asset_name(asset, path)
            selection = note.get('images', {}).get('selection', {})
            sense_id = selection.get('sense_id')
            sense_number = next((str(i) for i, s in enumerate(note['senses'], 1) if s['id'] == sense_id), '')
            caption = {'en': 'Illustration for sense ', 'ja': '語義の図示：', 'ko': '词义示意：'}[language] + sense_number if sense_number else ''
            chunks += ['<figure><img src="' + esc(path) + '" alt="' + esc(note["word"] + (' · ' + caption if caption else '')) + '">',
                       '<figcaption>' + esc(caption) + '</figcaption>' if caption else '',
                       '<figcaption>' + esc(asset.get("attribution","")) + ' · ' +
                       esc(asset.get("license","")) + ' · ' + source_link(asset) + '</figcaption></figure>']
    if language != "ja" and note.get("alternative_forms") and note["alternative_forms"].strip() not in ("特になし", "なし"):
        chunks += ['<p class="meta">' + labels["forms"] + ': ' + esc(note["alternative_forms"]) + '</p>']
    chunks += ['<section><h2>' + labels["meaning"] + '</h2>']
    for index, sense in enumerate(note["senses"], 1):
        pos = ", ".join(t.split("::")[-1].capitalize() for t in sense["tags"] if t.startswith("pos::"))
        chunks += ['<article class="sense"><h3>' + str(index) + '. <span class="part-of-speech">' + esc(pos) + '</span></h3>',
                   paragraphs(sense["definition"]), '<ol class="examples">']
        chunks += ['<li>' + inline_text(example) + '</li>' for example in sense["examples"]]
        chunks += ['</ol></article>']
    chunks += ['</section>']
    for key in ("etymology", "nuance", "synonyms", "inflections", "collocations"):
        text = note["analysis"].get(key)
        if text:
            if key == "collocations" and isinstance(text, list):
                body = "".join(paragraphs(item["phrase"] + " — " + item["explanation"]) for item in text)
            else:
                body = paragraphs(text)
            chunks += ['<section data-section="' + key + '"><h2>' + labels[key] + '</h2>' + body + '</section>']
    if note["proposed_tags"]:
        chunks += ['<section><h2>待审核的新标签</h2>']
        chunks += [paragraphs(p["tag"] + " — " + p["definition_zh"]) for p in note["proposed_tags"]]
        chunks += ['</section>']
    chunks += ['<details><summary>' + labels["sources"] + '</summary>',
               '<p>' + ''.join('<span class="tag">' + esc(t) + '</span>' for t in note["note_tags"]) + '</p>']
    research=note.get("research",{})
    chunks += ['<p>Generation: ' + esc(research.get("mode","independent")) + '</p>']
    if note.get("tag_snapshot"):
        snapshot = note["tag_snapshot"]
        chunks += ['<p>Tag snapshot: ' + esc(snapshot.get("mode", "seed")) + ' · ' + esc(snapshot.get("id", "")[:16]) + '</p>']
    for source in research.get("sources",[]):
        chunks += ['<p>' + esc(source["id"] + ' · ' + source["title"]) + ' · ' + source_link({"source_page":source["url"]}) + '</p>']
    pitch_credits = set()
    for pitch in note.get("pronunciation", {}).get("pitch_accents", []):
        credit = (pitch.get("source", ""), pitch.get("attribution", ""), pitch.get("license", ""))
        if credit not in pitch_credits and any(credit[1:]):
            pitch_credits.add(credit)
            chunks += ['<p>' + esc(" · ".join(part for part in credit if part)) + ' · ' + source_link(pitch) + '</p>']
    for group in ("pronunciation", "images"):
        for asset in note.get(group, {}).get("assets", []):
            chunks += ['<p>' + source_link(asset) + ' · ' + esc(asset.get("attribution","")) + ' · ' + esc(asset.get("license","")) + '</p>']
        chunks += ['<p>' + esc(w) + '</p>' for w in note.get(group, {}).get("warnings", [])]
    chunks += ['<p class="meta">' + esc(note["provenance"]["provider"] + " / " + note["provenance"]["model"]) + '</p></details></main>']
    if standalone:
        chunks += ['</body></html>']
    return "\n".join(chunks)
