"""Validate model-authored emphasis and explained collocations before rendering."""
import json
import re

def explanation_language_issues(content, language):
    """Catch common language drift while allowing quoted words and source names."""
    issues = []
    fields = []
    for index, sense in enumerate(content.get("senses", [])):
        if isinstance(sense, dict):
            fields.append(("senses[" + str(index) + "].definition", sense.get("definition")))
            if language == "ko":
                for number, example in enumerate(sense.get("examples", [])):
                    if isinstance(example, str) and (not re.search(r"[가-힣]", example) or
                                                    len(re.findall(r"[\u4e00-\u9fff]", example)) < 2):
                        issues.append(f"senses[{index}].examples[{number}]: use a Korean example followed by a Simplified Chinese translation.")
    analysis = content.get("analysis", {})
    if not isinstance(analysis, dict):
        return issues
    for key in ("etymology", "nuance", "synonyms", "inflections"):
        if key in analysis:
            fields.append(("analysis." + key, analysis[key]))
    collocations = analysis.get("collocations", [])
    if isinstance(collocations, list):
        for index, item in enumerate(collocations):
            if isinstance(item, dict):
                fields.append((f"analysis.collocations[{index}].explanation", item.get("explanation")))
    for field, text in fields:
        if not isinstance(text, str) or not text.strip():
            continue
        if language == "ko":
            han = len(re.findall(r"[\u4e00-\u9fff]", text))
            hangul = len(re.findall(r"[가-힣]", text))
            if han < 2 or (hangul > 0 and han / (han + hangul) < .35):
                issues.append(field + ": write the explanation in Simplified Chinese, not Korean or English; Korean terms may appear inside Chinese prose. This applies to every generation mode.")
        if language == "ja" and re.search(r"\b(?:context\s*(?:&|and)\s*tone|emphasis|native[ -]speaker(?:s)?\s*(?:impressions?|analysis))\b|\*\*[^*\n]{1,60}\bvs\.", text, re.I):
            issues.append(field + ": use Japanese prose and Japanese subheadings: 使用場面・語調 / 強調点 / 母語話者の印象; replace English comparison headings with ○○との違い. Quoted etymological source words are allowed.")
    return issues

def readability_issues(content, language):
    issues = []
    if not isinstance(content, dict):
        return ["Return a JSON object."]
    if language == "ja":
        if not isinstance(content.get("reading"), str) or not content["reading"].strip():
            issues.append("reading: provide the Japanese reading in kana.")
        forms = content.get("alternative_forms")
        if not isinstance(forms, (str, list)) or (isinstance(forms, list) and any(not isinstance(f, str) for f in forms)):
            issues.append("alternative_forms: provide verified alternative spellings or 特になし; do not omit this field.")
    def check_emphasis(text, field):
        if not isinstance(text, str) or not text.strip():
            issues.append(field + ": missing explanation.")
            return
        spans = re.findall(r"\*\*([^*\n]+)\*\*", text)
        if not spans:
            issues.append(field + ": add selective **bold** around key ideas inside the explanation.")
        elif sum(len(s) for s in spans) > len(text.replace("**", "")) * .65:
            issues.append(field + ": too much bold; emphasize short key ideas, not whole paragraphs.")
        if text.count("**") % 2:
            issues.append(field + ": unmatched bold markers.")
    analysis = content.get("analysis", {})
    if not isinstance(analysis, dict):
        return ["analysis must be an object."]
    issues.extend(explanation_language_issues(content, language))
    for key in ("synonyms", "nuance"):
        text=analysis.get(key, "")
        if isinstance(text,str):
            for paragraph in re.split(r"\n\s*\n",text):
                labels=re.findall(r"\*\*[^*\n]{0,60}(?:vs\.|との違い|Context & Tone|Emphasis|Native-speaker impressions)[^*\n]*\*\*",paragraph)
                if len(labels)>1:
                    issues.append("analysis."+key+": put each comparison or subheading in a separate paragraph, separated by two newlines.")
    for key in ("etymology", "nuance", "synonyms"):
        check_emphasis(analysis.get(key), "analysis." + key)
    for index, sense in enumerate(content.get("senses", [])):
        if isinstance(sense, dict):
            check_emphasis(sense.get("definition"), "senses[" + str(index) + "].definition")
            if language in ("ja", "ko") and not any(isinstance(t, str) and t.startswith("origin::") for t in sense.get("tags", [])):
                issues.append(f"senses[{index}].tags: Japanese/Korean origin is mandatory; supply native, loanword or sino, or multiple origins for mixed components, with reasons. Do not infer from kanji alone.")
    collocations = analysis.get("collocations")
    if not isinstance(collocations, list) or not collocations:
        issues.append("analysis.collocations must be a nonempty array of {phrase, explanation} objects.")
    else:
        for index, item in enumerate(collocations):
            label = "collocations[" + str(index) + "]"
            if not isinstance(item, dict):
                issues.append(label + ": must be an object.")
                continue
            phrase, explanation = item.get("phrase"), item.get("explanation")
            if not isinstance(phrase, str) or not re.fullmatch(r"\*\*[^*\n]+\*\*", phrase):
                issues.append(label + ".phrase: model must wrap the collocation itself in **bold**.")
            if not isinstance(explanation, str) or len(explanation.strip()) < 12:
                issues.append(label + ".explanation: provide 1–2 short sentences explaining meaning or typical use, not just a translation.")
    minimum = 4 if language == "ja" else 3
    for index, sense in enumerate(content.get("senses", [])):
        if isinstance(sense, dict) and len(sense.get("examples", [])) < minimum:
            issues.append("senses[" + str(index) + "]: provide at least " + str(minimum) + " examples.")
    return issues

def generate_content(model, instruction, user, language, enforce=False, attempts=3, repair_prompt=None):
    if repair_prompt is None:
        from .prompts import default_prompts
        repair_prompt = default_prompts()["content_repair"]
    feedback = []
    try:
        source_ids={s["id"] for s in json.loads(user).get("research",{}).get("sources",[])}
    except (ValueError,TypeError,AttributeError):
        source_ids=set()
    for attempt in range(attempts if enforce else 1):
        request = user
        if feedback:
            request += "\n\n" + repair_prompt.replace("{issues}", "\n".join(feedback))
        raw = model.generate(instruction, request, json_output=True)
        try:
            content = json.loads(raw)
        except (ValueError, TypeError):
            if not enforce:
                raise ValueError("AI 输出不是有效 JSON，本次不生成可导入笔记。") from None
            feedback = ["Return valid JSON without Markdown fences."]
            continue
        feedback = readability_issues(content, language) if enforce else []
        if source_ids:
            cited=set(re.findall(r"\[(S\d+)\]",json.dumps(content,ensure_ascii=False)))
            if not cited or not cited.issubset(source_ids):
                feedback.append("Cite the supplied source IDs such as [S1] in relevant explanations; do not invent source IDs.")
        if not feedback:
            return content, {"enabled": enforce, "attempts": attempt + 1, "passed": True}
    raise ValueError("模型输出未通过自动检查：" + "; ".join(feedback))
