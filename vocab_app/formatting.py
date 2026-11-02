"""Formatting may decorate accepted prose; it cannot rewrite card content."""
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
def format_content(model, content, language, prompt, repair_prompt, attempts=3):
    initial = readability_issues(content,language)
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
            feedback=['Formatting changed protected content at '+', '.join(changed)+'. Restore the original text/data; only bold and paragraph whitespace may change.'] if changed else readability_issues(candidate,language)
            if not feedback:return candidate,{'enabled':True,'attempts':attempt+1,'passed':True}
        except (ValueError,TypeError):feedback=['Return a complete valid JSON object.']
        history.append({'attempt':attempt+1,'issues':list(feedback),'response':raw})
    raise RepairValidationError('排版修正未通过：'+'; '.join(feedback),'formatting',history)
