"""Validate model-authored emphasis and explained collocations before rendering."""
from .validation import message as _message, rules as _rules, validation_scope
import json
import re

def explanation_language_issues(content, language):
    """Catch common language drift while allowing quoted words and source names."""
    issues = []
    fields = []
    for index, sense in enumerate(content.get('senses', [])):
        if isinstance(sense, dict):
            fields.append(('senses[' + str(index) + '].definition', sense.get('definition')))
            if language == 'ko':
                for number, example in enumerate(sense.get('examples', [])):
                    if isinstance(example, str) and (not re.search('[가-힣]', example) or len(re.findall('[\\u4e00-\\u9fff]', example)) < 2):
                        issues.append(_message('quality_001', v0=index, v1=number))
    analysis = content.get('analysis', {})
    if not isinstance(analysis, dict):
        return issues
    for key in ('etymology', 'nuance', 'synonyms', 'inflections'):
        if key in analysis:
            fields.append(('analysis.' + key, analysis[key]))
    collocations = analysis.get('collocations', [])
    if isinstance(collocations, list):
        for index, item in enumerate(collocations):
            if isinstance(item, dict):
                fields.append((f'analysis.collocations[{index}].explanation', item.get('explanation')))
    for field, text in fields:
        if not isinstance(text, str) or not text.strip():
            continue
        if language == 'ko':
            han = len(re.findall('[\\u4e00-\\u9fff]', text))
            hangul = len(re.findall('[가-힣]', text))
            if han < 2 or (hangul > 0 and han / (han + hangul) < 0.35):
                issues.append(_message('quality_002', v0=field))
        if language == 'ja' and re.search('\\b(?:context\\s*(?:&|and)\\s*tone|emphasis|native[ -]speaker(?:s)?\\s*(?:impressions?|analysis))\\b|\\*\\*[^*\\n]{1,60}\\bvs\\.', text, re.I):
            issues.append(_message('quality_003', v0=field))
    return issues

def readability_issues(content, language):
    issues = []
    if not isinstance(content, dict):
        return [_message('quality_004')]
    if language == 'ja' and _rules()['check_japanese_forms']:
        if not isinstance(content.get('reading'), str) or not content['reading'].strip():
            issues.append(_message('quality_005'))
        forms = content.get('alternative_forms')
        if not isinstance(forms, (str, list)) or (isinstance(forms, list) and any((not isinstance(f, str) for f in forms))):
            issues.append(_message('quality_006'))

    def check_emphasis(text, field):
        if not _rules()['check_emphasis']:
            return
        if not isinstance(text, str) or not text.strip():
            issues.append(_message('quality_007', v0=field))
            return
        spans = re.findall('\\*\\*([^*\\n]+)\\*\\*', text)
        if not spans:
            issues.append(_message('quality_008', v0=field))
        elif sum((len(s) for s in spans)) > len(text.replace('**', '')) * _rules()['max_bold_ratio']:
            issues.append(_message('quality_009', v0=field))
        if text.count('**') % 2:
            issues.append(_message('quality_010', v0=field))
    analysis = content.get('analysis', {})
    if not isinstance(analysis, dict):
        return [_message('quality_011')]
    if _rules()['check_language']:
        issues.extend(explanation_language_issues(content, language))
    for key in ('synonyms', 'nuance'):
        text = analysis.get(key, '')
        if isinstance(text, str):
            for paragraph in re.split('\\n\\s*\\n', text):
                labels = re.findall('\\*\\*[^*\\n]{0,60}(?:vs\\.|との違い|Context & Tone|Emphasis|Native-speaker impressions)[^*\\n]*\\*\\*', paragraph)
                if len(labels) > 1 and _rules()['check_paragraphs']:
                    issues.append(_message('quality_012', v0=key))
    for key in ('etymology', 'nuance', 'synonyms'):
        check_emphasis(analysis.get(key), 'analysis.' + key)
    for index, sense in enumerate(content.get('senses', [])):
        if isinstance(sense, dict):
            check_emphasis(sense.get('definition'), 'senses[' + str(index) + '].definition')
            if language in ('ja', 'ko') and (not any((isinstance(t, str) and t.startswith('origin::') for t in sense.get('tags', [])))):
                issues.append(_message('quality_013', v0=index))
    collocations = analysis.get('collocations')
    if not _rules()['check_collocations']:
        collocations = []
    elif not isinstance(collocations, list) or not collocations:
        issues.append(_message('quality_014'))
    else:
        for index, item in enumerate(collocations):
            label = 'collocations[' + str(index) + ']'
            if not isinstance(item, dict):
                issues.append(_message('quality_015', v0=label))
                continue
            phrase, explanation = (item.get('phrase'), item.get('explanation'))
            if not isinstance(phrase, str) or not re.fullmatch('\\*\\*[^*\\n]+\\*\\*', phrase):
                issues.append(_message('quality_016', v0=label))
            if not isinstance(explanation, str) or len(explanation.strip()) < _rules()['minimum_collocation_length']:
                issues.append(_message('quality_017', v0=label))
    minimum = _rules()['minimum_examples'][language]
    for index, sense in enumerate(content.get('senses', [])):
        if isinstance(sense, dict) and len(sense.get('examples', [])) < minimum:
            issues.append(_message('quality_018', v0=str(index), v1=str(minimum)))
    return issues

@validation_scope
def generate_content(model, instruction, user, language, enforce=False, attempts=3, repair_prompt=None):
    if repair_prompt is None:
        from .prompts import default_prompts
        repair_prompt = default_prompts()['content_repair']
    feedback = []
    try:
        source_ids = {s['id'] for s in json.loads(user).get('research', {}).get('sources', [])}
    except (ValueError, TypeError, AttributeError):
        source_ids = set()
    for attempt in range(attempts if enforce else 1):
        request = user
        if feedback:
            request += '\n\n' + repair_prompt.replace('{issues}', '\n'.join(feedback))
        raw = model.generate(instruction, request, json_output=True)
        try:
            content = json.loads(raw)
        except (ValueError, TypeError):
            if not enforce:
                raise ValueError('AI 输出不是有效 JSON，本次不生成可导入笔记。') from None
            feedback = [_message('quality_019')]
            continue
        feedback = readability_issues(content, language) if enforce else []
        if source_ids:
            cited = set(re.findall('\\[(S\\d+)\\]', json.dumps(content, ensure_ascii=False)))
            if not cited or not cited.issubset(source_ids):
                feedback.append(_message('quality_020'))
        if not feedback:
            return (content, {'enabled': enforce, 'attempts': attempt + 1, 'passed': True})
    raise ValueError('模型输出未通过自动检查：' + '; '.join(feedback))
