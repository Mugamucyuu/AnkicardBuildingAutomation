"""Formatting may decorate accepted prose; it cannot rewrite card content."""
from copy import deepcopy
import json
import re
from .quality import readability_issues
from .repair import repair_request, RepairValidationError
from .validation import rules, validation_scope


def canonical_prose(text):
    text = re.sub(r'\s+', ' ', text.replace('**', '')).strip()
    # New paragraphs may be added at existing spaces or sentence boundaries.
    return re.sub(r'(?<=[。！？.!?:：]) | (?=[。！？.!?:：])', '', text)


def formatting_changes(original, candidate, path=''):
    if type(original) is not type(candidate):
        return [path or 'root']
    if isinstance(original, dict):
        if original.keys() != candidate.keys():return [path or 'root']
        return [p for k in original for p in formatting_changes(original[k], candidate[k], path+'.'+k if path else k)]
    if isinstance(original, list):
        if len(original) != len(candidate):return [path]
        return [p for i,(a,b) in enumerate(zip(original,candidate)) for p in formatting_changes(a,b,f'{path}[{i}]')]
    editable = bool(re.fullmatch(r'senses\[\d+\]\.definition|analysis\.(?:etymology|nuance|synonyms)|analysis\.collocations\[\d+\]\.phrase',path))
    if isinstance(original,str) and editable:
        return [] if canonical_prose(original)==canonical_prose(candidate) else [path]
    return [] if original==candidate else [path]


@validation_scope
def format_content(model, content, language, prompt, repair_prompt, attempts=3, *, defer_origin=False):
    initial = readability_issues(content,language,defer_origin=defer_origin)
    if not initial:return content,{'enabled':True,'attempts':0,'passed':True}
    request_context={'language':language,'format_rules':{
        k:rules()[k] for k in ('check_emphasis','max_bold_ratio','check_paragraphs','check_collocations')},
        'issues':initial}
    original=(json.dumps(request_context,ensure_ascii=False)+
              '\n\nReturn only the following card object, not the context above:\n'+
              json.dumps(content,ensure_ascii=False))
    feedback=[];history=[];raw=None
    for attempt in range(attempts):
        request=original if not feedback else repair_request(original,repair_prompt,feedback,raw)
        raw=model.generate(prompt,request,json_output=True)
        try:
            candidate=json.loads(raw)
            # Some providers echo the input envelope. Unwrap only the exact,
            # intact context envelope; never silently ignore arbitrary extra keys.
            if (isinstance(candidate,dict) and set(candidate)==set(request_context)|{'content'} and
                    all(candidate[k]==v for k,v in request_context.items())):
                candidate=candidate['content']
            changed=formatting_changes(content,candidate)
            feedback=['Formatting changed protected content at '+', '.join(changed)+'. Restore the original text/data; only bold and paragraph whitespace may change.'] if changed else readability_issues(candidate,language,defer_origin=defer_origin)
            if not feedback:return candidate,{'enabled':True,'attempts':attempt+1,'passed':True}
        except (ValueError,TypeError):feedback=['Return a complete valid JSON object.']
        history.append({'attempt':attempt+1,'issues':list(feedback),'response':raw})
    raise RepairValidationError('排版修正未通过：'+'; '.join(feedback),'formatting',history)


HEADINGS = {
    'en': r'Context\s*(?:&|and)\s*Tone|Emphasis|Native[ -]speaker impressions',
    'ja': r'使用場面[・と]語調|強調点|母語話者の印象',
}

def prose_fields(card):
    for i, sense in enumerate(card['senses']):
        yield f'd{i}', sense, 'definition'
    for key in ('etymology', 'nuance', 'synonyms'):
        yield key, card['analysis'], key

def safe_wrap(text, span):
    if not isinstance(span, str) or not span.strip() or '*' in span or '\n' in span or text.count(span) != 1:
        return text
    start = text.index(span)
    end = start + len(span)
    if any(m.start() < end and m.end() > start for m in re.finditer(r'\*\*[^*\n]+\*\*', text)):
        return text
    existing = sum(len(s) for s in re.findall(r'\*\*([^*\n]+)\*\*', text))
    if existing + len(span) > len(text.replace('**','')) * rules()['max_bold_ratio']:
        return text
    return text[:start] + '**' + span + '**' + text[end:]

def decorate_structure(content, language):
    card = deepcopy(content)
    if rules()['check_collocations']:
        for item in card['analysis']['collocations']:
            phrase = item['phrase'].replace('**', '').strip()
            if '*' not in phrase and '\n' not in phrase:
                item['phrase'] = '**' + phrase + '**'
    for key in ('nuance', 'synonyms'):
        text = card['analysis'][key]
        if key == 'nuance':
            heading = HEADINGS[language]
        elif language == 'en':
            heading = r'[^\n。.!?*：:]{1,65} vs\. [^\n。.!?*：:]{1,65}'
        else:
            heading = r'[^\n。.!?*：:]{1,30}との違い'
        # Only explicit headings at line or sentence boundaries. Recognize
        # an existing heading wrapper and put the separator outside it.
        pattern = rf'(?im)(^|(?<=[。！？.!?]))[ \t]*(?P<bold>\*\*)?(?P<label>{heading})(?(bold)\*\*)[ \t]*(?P<colon>[:：]|(?=\n|$))'
        def replace(match):
            label = match['label'].strip()
            if match['bold'] or rules()['check_emphasis']:
                label = '**' + label + '**'
            prefix = '\n\n' if match.start() and rules()['check_paragraphs'] else match[1]
            return prefix + label + match['colon']
        candidate = re.sub(pattern, replace, text)
        # When replacing a heading would remove meaningful internal spacing,
        # retain the exact original prose and let the fallback handle it.
        if canonical_prose(candidate) == canonical_prose(text):
            card['analysis'][key] = candidate
    return card

BOLD_LABEL = re.compile(r'\*\*[^*\n]{0,60}(?:vs\.|との違い|Context & Tone|Emphasis|Native-speaker impressions)[^*\n]*\*\*')

def split_combined_headings(text):
    """Split at labels the existing paragraph validator already recognizes."""
    paragraphs = []
    for paragraph in re.split(r'\n\s*\n', text):
        boundaries = [match.start() for match in BOLD_LABEL.finditer(paragraph)][1:]
        for position in reversed(boundaries):
            paragraph = paragraph[:position].rstrip() + '\n\n' + paragraph[position:]
        paragraphs.append(paragraph)
    candidate = '\n\n'.join(paragraphs)
    return candidate if canonical_prose(candidate) == canonical_prose(text) else text

def needs_emphasis(key, text):
    spans = re.findall(r'\*\*([^*\n]+)\*\*', text)
    if key in ('nuance', 'synonyms'):
        spans = [s for s in spans if not re.search(r'との違い|\bvs\.|Context\s*&\s*Tone|Emphasis|Native-speaker impressions|使用場面|強調点|母語話者の印象', s, re.I)]
    return rules()['check_emphasis'] and not spans

@validation_scope
def format_web_content(model, content, language, prompt, repair_prompt, emphasis_prompt):
    card = decorate_structure(content, language)
    if rules()['check_paragraphs']:
        for key in ('nuance','synonyms'):
            card['analysis'][key] = split_combined_headings(card['analysis'][key])
    if formatting_changes(content, card):
        card = deepcopy(content)
    # A field with excessive or unbalanced emphasis can be decorated anew
    # without paying to have the model reproduce its prose.
    selected = {}
    if rules()['check_emphasis']:
        for key, obj, field in prose_fields(card):
            text = obj[field]
            plain = text.replace('**', '')
            emphasized = re.findall(r'\*\*([^*\n]+)\*\*', text)
            if text.count('**') % 2 or sum(map(len, emphasized)) > len(plain) * rules()['max_bold_ratio']:
                obj[field] = plain
            if needs_emphasis(key, obj[field]):
                selected[key] = obj[field]

    def issues():
        return readability_issues(card, language, defer_origin=language == 'ja')
    history = []
    calls = 0
    if selected:
        request = {'max_bold_ratio': rules()['max_bold_ratio'], 'fields': selected}
        raw = model.generate(emphasis_prompt, json.dumps(request, ensure_ascii=False), json_output=True)
        calls += 1
        try:
            spans = json.loads(raw)['spans']
            if not isinstance(spans, dict):
                raise ValueError('spans must be an object')
            for key, obj, field in prose_fields(card):
                if key not in selected or not isinstance(spans.get(key), list):
                    continue
                for span in spans[key][:4]:
                    obj[field] = safe_wrap(obj[field], span)
        except (ValueError, KeyError, TypeError):
            pass
        history.append({'attempt': calls, 'response': raw, 'issues': issues()})
    changed = formatting_changes(content, card)
    feedback = issues()
    if not changed and not feedback and not any(needs_emphasis(k,o[f]) for k,o,f in prose_fields(card)):
        return card, {'enabled':True, 'attempts':calls, 'passed':True, 'method':'exact_spans','requested_emphasis':list(selected)}
    try:
        result, check = format_content(
            model, content if changed else card, language, prompt, repair_prompt,
            attempts=3-calls, defer_origin=language == 'ja',
        )
    except RepairValidationError as error:
        raise RepairValidationError(str(error), error.stage, history + [
            {**entry, 'attempt': entry['attempt'] + calls} for entry in error.repair_history
        ]) from None
    return result, {**check, 'attempts':check['attempts']+calls, 'method':'full_fallback'}
