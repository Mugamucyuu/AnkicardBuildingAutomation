"""Repair semantic tags against the catalog, without altering learning prose."""
from .validation import message as _message, validation_scope
import json
from .taxonomy import TagCatalog
from .prompts import default_prompts

@validation_scope
def audit_tags(model, content, language, research, word='', catalog=None, policy=None, prompts=None):
    prompts = prompts if prompts is not None else default_prompts()
    client = type(model)(model.settings, model.transport)
    catalog = catalog.clone() if catalog is not None else TagCatalog.load()
    catalog.add_proposals(content.get('proposed_tags', []), language)
    context = catalog.prompt_context(language)
    original = {s['id']: set(s['tags']) for s in content['senses']}
    payload = {'word': word or content.get('word', ''), 'reading': content.get('reading', ''), 'language': language, 'senses': content['senses'], 'analysis': content.get('analysis', {}), 'sources': research.get('sources', []), **context}
    known = {e['tag'] for e in context['allowed_tags']}
    instruction = prompts['tag_review'] + '\n\n' + (policy if policy is not None else prompts['tag_policy'])
    feedback = ''
    for attempt in range(3):
        try:
            result = json.loads(client.generate(instruction, json.dumps(payload, ensure_ascii=False) + feedback, json_output=True))
            decisions = result.get('decisions')
            if not isinstance(decisions, list) or len(decisions) != len(original):
                raise ValueError(_message('tag_021'))
            by_id = {d['sense_id']: d for d in decisions}
            if set(by_id) != set(original):
                raise ValueError(_message('tag_022'))
            staged = []
            for sense in content['senses']:
                decision = by_id[sense['id']]
                tags = decision['keep_tags']
                if not isinstance(tags, list) or any((not isinstance(t, str) or t not in known for t in tags)):
                    raise ValueError(_message('tag_023'))
                if not any((t.startswith('pos::') for t in tags)) or (language in ('ja', 'ko') and (not any((t.startswith('origin::') for t in tags)))):
                    raise ValueError(_message('tag_024'))
                if language == 'en' and any((t.startswith('origin::') for t in tags)):
                    raise ValueError(_message('tag_025'))
                reasons = decision.get('tag_reasons', {})
                if not isinstance(reasons, dict) or any((not isinstance(reasons.get(t), str) or not reasons[t].strip() for t in tags)):
                    raise ValueError(_message('tag_026'))
                tags = catalog.validate_sense(tags, language)
                staged.append((sense, tags, {t: reasons[t] for t in tags}))
            for sense, tags, reasons in staged:
                sense['tags'], sense['tag_reasons'] = (tags, reasons)
            result['attempts'] = attempt + 1
            return result
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            feedback = '\n\n' + prompts['tag_repair'].replace('{issues}', str(error))
    raise ValueError('标签复核未通过：' + feedback)
