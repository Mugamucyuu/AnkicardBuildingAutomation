"""Sense-aware Commons selection. Local metadata ranking; no extra model call."""
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

from .media import MediaResult

def clean_phrase(value, limit=60):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z '\-]{0,80}", value.strip()):
        return ''
    return ' '.join(value.lower().split())[:limit]


def validate_plan(value, senses):
    if not isinstance(value, dict):
        return None
    ids = {s.get('id') for s in senses if isinstance(s, dict)}
    query = clean_phrase(value.get('query'))
    if value.get('sense_id') not in ids or not query or len(query.split()) > 6:
        return None
    result = {'sense_id': value['sense_id'], 'query': query}
    topic = value.get('topic', '')
    if isinstance(topic, str) and re.fullmatch(r"[A-Za-z][A-Za-z ()'\-]{0,70}", topic.strip()) and len(topic.split()) <= 6:
        result['topic'] = ' '.join(topic.split())
    for key in ('anchors', 'context', 'exclude'):
        items = value.get(key, [])
        if not isinstance(items, list) or len(items) > 3:
            return None
        result[key] = list(dict.fromkeys(filter(None, (clean_phrase(v) for v in items))))
    if not result['anchors'] or not result['context'] or not any(contains(query, a) for a in result['anchors']):
        return None
    if sum(len(v.split()) for k in ('anchors', 'context', 'exclude') for v in result[k]) + len(query.split()) > 25:
        return None
    return result


def normalized(value):
    value = unicodedata.normalize('NFKC', value).casefold()
    return ' '.join(re.findall(r"[^\W_]+", value, re.UNICODE))


def contains(text, phrase):
    return ' ' + normalized(phrase) + ' ' in ' ' + normalized(text) + ' '


def rank_candidate(asset, plan):
    """Require subject evidence, then context; titles outrank long descriptions."""
    title = asset.get('title', '').removeprefix('File:')
    description = asset.get('description', '')[:2400]
    text = title + ' ' + description
    reasons = []
    if not asset.get('license') or not asset.get('attribution'):
        return -100, ['missing_credit_or_license']
    if Path(urlparse(asset.get('url', '')).path).suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp'):
        return -100, ['unsupported_image']
    width, height = asset.get('width', 0), asset.get('height', 0)
    if not width or not height or min(width, height) < 200 or max(width / height, height / width) > 4:
        return -100, ['too_small_or_extreme_aspect']
    if any(contains(text, term) for term in plan['exclude']):
        return -100, ['excluded_meaning']
    # File title signals a logo/cover/screenshot more reliably than a passing
    # mention in a long file description. Plans may explicitly target these.
    clutter = ('logo', 'album cover', 'movie poster', 'screenshot', 'coat of arms', 'flag', 'studio', 'preparation for', 'stencil', 'looking at')
    if any(contains(title, t) and not contains(plan['query'], t) for t in clutter):
        return -100, ['incidental_or_brand_image']
    representative = asset.get('representative_article')
    if representative:
        article_text = representative.get('title', '') + ' ' + representative.get('extract', '')
        if any(contains(article_text, c) for c in plan['context']) and any(contains(article_text, a) for a in plan['anchors']):
            return 12.5, ['representative_article_matches_subject_and_context']
        return -100, ['article_context_mismatch']
    title_anchor = any(contains(title, a) for a in plan['anchors'])
    description_anchor = any(contains(description, a) for a in plan['anchors'])
    if not title_anchor and not description_anchor:
        return -100, ['missing_subject']
    score = 6 if title_anchor else 3
    score -= min(1.5, max(0, len(title.split()) - 6) * 0.1)
    reasons.append('subject_in_title' if title_anchor else 'subject_in_description')
    context = [c for c in plan['context'] if contains(text, c)]
    score += min(4, len(context) * 2)
    if context:
        reasons.append('context:' + ','.join(context))
    # A description-only subject match needs corroborating visual context.
    if not title_anchor and not context:
        return -100, ['weak_description_only_match']
    # Clear objects in file names are useful even if metadata has no prose.
    if contains(title, plan['query']):
        score += 2
        reasons.append('query_in_title')
    if min(width, height) >= 600:
        score += 0.5
    return score, reasons


def select_image(registry, word, language, senses, raw_plan):
    plan = validate_plan(raw_plan, senses)
    result = MediaResult(selection={'strategy': 'sense_metadata_v1', 'word': word, 'language': language,
                                   'plan': plan, 'selected_title': None, 'candidates': [], 'approved_assets': []})
    if plan is None:
        result.selection['status'] = 'skipped_abstract' if raw_plan is None else 'invalid_plan'
        result.warnings.append('本词未提供可靠的具体配图对象；不配图。')
        return result
    result.selection['sense_id'] = plan['sense_id']
    if plan.get('topic'):
        try:
            assets = registry.representative_image(plan['topic'])
            result.lookup_attempts.append({'topic': plan['topic'], 'status': 'article_checked', 'candidates': len(assets)})
            for asset in assets:
                score, reasons = rank_candidate(asset, plan)
                result.selection['candidates'].append({'title':asset.get('title'), 'score':score, 'reasons':reasons})
                if score >= 5:
                    result.assets = [dict(asset)]
                    result.selection.update(approved_assets=[asset], selected_title=asset['title'], status='selected')
                    return result
        except Exception as error:
            result.lookup_attempts.append({'topic': plan['topic'], 'status':'error', 'error_type':type(error).__name__})
    queries = [plan['query']]
    # The shorter fallback preserves subject and context; never raw-word search.
    fallback = plan['anchors'][0] + ' ' + plan['context'][0]
    if fallback != queries[0]:
        queries.append(fallback)
    seen = set()
    ranked = []
    for query in queries:
        try:
            found = registry.image_search(query, limit=6)
            result.lookup_attempts.append({'query': query, 'status': 'searched', 'candidates': len(found)})
        except Exception as error:
            result.lookup_attempts.append({'query': query, 'status': 'error', 'error_type': type(error).__name__})
            continue
        for asset in found:
            title = asset.get('title', '')
            if not title or title in seen:
                continue
            seen.add(title)
            score, reasons = rank_candidate(asset, plan)
            result.selection['candidates'].append({'title': title, 'score': score, 'reasons': reasons})
            if score >= 5:
                ranked.append((score, asset))
        if ranked:
            break
    ranked.sort(key=lambda item: item[0], reverse=True)
    result.selection['approved_assets'] = [asset for _, asset in ranked]
    if ranked:
        result.assets = [dict(ranked[0][1])]
        result.selection.update(selected_title=ranked[0][1]['title'], status='selected')
    else:
        result.selection['status'] = 'no_confident_match'
        result.warnings.append('没有通过词义与图片元数据匹配检查的候选；不配图。')
    return result
