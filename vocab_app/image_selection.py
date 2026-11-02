"""Sense-aware Commons selection. Local metadata ranking; no extra model call."""
import re
import unicodedata
import locale
from pathlib import Path
from urllib.parse import urlparse

from .media import MediaResult
LANGUAGE_CODES = {name.split('_')[0] for name in locale.locale_alias if len(name.split('_')[0]) == 2}

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
    result['kind'] = value.get('kind') if value.get('kind') in ('photo', 'diagram') else 'photo'
    for key in ('alternatives', 'avoid_scenes'):
        items = value.get(key, [])
        if not isinstance(items, list) or len(items) > 3:
            return None
        result[key] = list(dict.fromkeys(filter(None, (clean_phrase(v) for v in items))))
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
    article_bonus = 0
    if representative:
        article_text = representative.get('title', '') + ' ' + representative.get('extract', '')
        if any(contains(article_text, c) for c in plan['context']) and any(contains(article_text, a) for a in plan['anchors']):
            article_bonus = 3
            reasons.append('representative_article_matches_subject_and_context')
        else:
            return -100, ['article_context_mismatch']
    title_anchor = any(contains(title, a) for a in plan['anchors'])
    description_anchor = any(contains(description, a) for a in plan['anchors'])
    if not title_anchor and not description_anchor:
        return -100, ['missing_subject']
    score = (6 if title_anchor else 3) + article_bonus
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
    for scene in plan.get('avoid_scenes', []):
        if contains(text, scene):
            score -= 7
            reasons.append('distracting_scene:' + scene)
    diagram = asset.get('original_mime') == 'image/svg+xml' or any(contains(text, term) for term in ('diagram', 'schematic', 'illustration', 'geometry', 'graph'))
    if plan.get('kind') == 'diagram':
        score += 3 if diagram else -3
        reasons.append('diagram_preferred' if diagram else 'not_identified_as_diagram')
        label = re.search(r'[-_. ]([a-z]{2})\.(?:svg|png|jpg)$', title, re.I)
        if label and label.group(1).lower() in LANGUAGE_CODES and label.group(1).lower() != plan.get('label_language', 'en'):
            return -100, ['different_label_language']
        if any(contains(title, word) for word in ('simple', 'simplified', 'basic')):
            score += 2
            reasons.append('simple_diagram')
        if any(contains(title, word) and not contains(plan['query'], word) for word in ('theorem', 'derivation', 'c4', 'c3', 'calvin', 'tiling', 'tessellation', 'fractal', 'lattice', 'poynting', 'phasor')):
            score -= 8
            reasons.append('specialized_diagram')
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
    seen, ranked = set(), []
    if plan.get('topic'):
        try:
            assets = registry.representative_image(plan['topic'])
            result.lookup_attempts.append({'topic': plan['topic'], 'status': 'article_checked', 'candidates': len(assets)})
            for asset in assets:
                score, reasons = rank_candidate(asset, plan)
                result.selection['candidates'].append({'title':asset.get('title'), 'score':score, 'reasons':reasons})
                if score >= 5:
                    ranked.append((score, asset))
                seen.add(asset.get('title'))
        except Exception as error:
            result.lookup_attempts.append({'topic': plan['topic'], 'status':'error', 'error_type':type(error).__name__})
    queries = [plan['query'], *plan.get('alternatives', [])]
    # The shorter fallback preserves subject and context; never raw-word search.
    fallback = plan['anchors'][0] + ' ' + plan['context'][0]
    if fallback not in queries:
        queries.append(fallback)
    queries = list(dict.fromkeys(queries))[:3]
    for query in queries:
        try:
            found = registry.image_search(query, limit=6)
            result.lookup_attempts.append({'query': query, 'status': 'searched', 'candidates': len(found)})
        except Exception as error:
            result.lookup_attempts.append({'query': query, 'status': 'error', 'error_type': type(error).__name__, 'http_status': getattr(error, 'code', None)})
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
    ranked.sort(key=lambda item: item[0], reverse=True)
    result.selection['approved_assets'] = [asset for _, asset in ranked]
    if ranked:
        result.assets = [dict(ranked[0][1])]
        result.selection.update(selected_title=ranked[0][1]['title'], status='selected')
    else:
        network_failed = all(a['status'] == 'error' for a in result.lookup_attempts)
        result.selection['status'] = 'lookup_failed' if network_failed else 'no_confident_match'
        result.warnings.append('图片检索服务暂不可用；不配图。' if network_failed else '没有通过词义与图片元数据匹配检查的候选；不配图。')
    return result
