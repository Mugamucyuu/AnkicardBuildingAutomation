"""Curate live search evidence for the built-in English/Japanese web recipe."""
import re
import unicodedata
from urllib.parse import unquote, urlparse

from .japanese_pitch import kanji, lookup_kanjium, normalize as kana_normalize
from .research import DeepSeekSearch, NoEvidenceError, ResearchCollector, SOURCES, domain_matches
from .transport import ServiceError


def dictionary_query(word, language):
    # Shorten the data first so the closing quote and search hints survive.
    hints = 'definition usage etymology dictionary' if language == 'en' else '意味 語源 用例 国語辞典'
    headword = ' '.join(word.replace('"', '').split())[:126-len(hints)-1]
    return f'"{headword}" {hints}' if headword else hints

SEARCH_ENGINES = ('duckduckgo.com', 'google.com', 'bing.com', 'search.yahoo.com')
DICTIONARIES = tuple({d for source in SOURCES.values() for d in source['domains']}) + (
    'collinsdictionary.com', 'dictionary.com', 'thefreedictionary.com', 'wordreference.com',
    'gcide.gnu.org.ua', 'jitenon.jp', 'kanjipedia.jp', 'weblio.jp', 'dictionary.goo.ne.jp',
)

def normalized(text):
    return ' '.join(unicodedata.normalize('NFKC', unquote(text or '')).casefold().split())

def headword_pattern(word, language):
    word = re.escape(normalized(word))
    return re.compile(r'(?<!\w)' + word + r'(?!\w)' if language == 'en' else word)

NAVIGATION_TITLE = re.compile(
    r'検索結果|で始まる言葉|に一致する言葉|を解説文に含む|\bsearch results\b|\bresults for\b', re.I)

def is_navigation(title):
    return bool(NAVIGATION_TITLE.search(title or ''))

def select_evidence(hits, word, language):
    """Prefer headword evidence and keep multiple independent sources."""
    match = headword_pattern(word, language)
    limit = 940 if language == 'ja' else 750
    candidates = []
    seen = set()
    seen_excerpts = set()
    for rank, hit in enumerate(hits):
        url = hit.get('url') or ''
        parsed = urlparse(url)
        if (parsed.scheme != 'https' or url in seen or '/revisions/' in parsed.path
            or domain_matches(url,SEARCH_ENGINES)):
            continue
        title = hit.get('title') or ''
        if is_navigation(title):
            continue
        seen.add(url)
        content = (hit.get('content') or '').strip()
        summary = (hit.get('summary') or hit.get('snippet') or '').strip()
        excerpt = content or summary
        excerpt_key = normalized(excerpt[:limit])
        if not excerpt_key or excerpt_key in seen_excerpts:
            continue
        seen_excerpts.add(excerpt_key)
        in_title = bool(match.search(normalized(title)))
        in_excerpt = bool(match.search(normalized(excerpt[:limit])))
        in_summary = bool(match.search(normalized(summary[:limit])))
        dictionary = domain_matches(url, DICTIONARIES)
        score = 4*in_title + 3*(in_excerpt or in_summary) + 2*dictionary
        candidates.append((score, rank, in_title or in_excerpt or in_summary, hit, in_excerpt, in_summary))
    if not candidates:
        return []
    relevant = [x for x in candidates if x[2] and x[0] > 0]
    if not relevant:
        return [x[3] for x in candidates[:3]]
    ranked = sorted(relevant, key=lambda x:(-x[0],x[1]))
    chosen = []
    domains = set()
    for distinct in (True, False):
        for score, rank, _, hit, in_excerpt, in_summary in ranked:
            host = (urlparse(hit['url']).hostname or '').removeprefix('www.')
            if rank in {r for r,_ in chosen} or (distinct and host in domains):
                continue
            candidate = dict(hit)
            if in_summary and not in_excerpt:
                candidate['content'] = ''
            for field in ('content','summary','snippet'):
                value = candidate.get(field)
                if value and len(value) > limit:
                    boundary = max(value.rfind(sep, limit//2, limit) for sep in ('\n', '。', '. ', '；'))
                    candidate[field] = value[:boundary+1] if boundary >= 0 else value[:limit]
            domains.add(host)
            chosen.append((rank,candidate))
            if len(chosen) == 3:
                return [item for _,item in chosen]
    return [item for _,item in chosen]

def trusted_entry(source, word, language, readings=()):
    if not domain_matches(source['url'],DICTIONARIES) or is_navigation(source['title']):
        return False
    pattern = headword_pattern(word,language)
    title = normalized(source['title'])
    excerpt = normalized(source['excerpt'])
    if pattern.search(title) or pattern.search(excerpt):
        return True
    # Reading alone matches homophones. For another spelling also require
    # the input's kanji to occur in order in the dictionary title.
    characters = kanji(word) if language == 'ja' else ''
    return bool(characters and characters in kanji(title)
                and any(kana_normalize(r) in kana_normalize(title) for r in readings))

def scoped_query(word, language, readings=()):
    bare = ' '.join(word.replace('"','').split())
    if language == 'ja':
        reading = next(iter(readings),'')
        keywords = ' '.join(x for x in (bare,reading,'意味') if x)
        domains = ('kotobank.jp','weblio.jp')
    else:
        keywords = f'"{bare}" definition'
        domains = ('merriam-webster.com','dictionary.cambridge.org')
    query = ' OR '.join(f'{keywords} site:{domain}' for domain in domains)
    return query if len(query) <= 128 else None

class DirectEntryCollector(ResearchCollector):
    """One live search per term, with a targeted dictionary supplement when needed."""

    def __init__(self, search=None):
        super().__init__(search or DeepSeekSearch(count=8))

    def collect(self, word, language, mode="independent", selected=(), planner=None):
        if mode != "web":
            return super().collect(word, language, mode, selected, planner)
        underlying = self.search

        class CuratedSearch:
            def search(self, query):
                return select_evidence(underlying.search(query), word, language)

        curated = ResearchCollector(CuratedSearch())
        try:
            base = curated.collect(word, language, mode, selected, dictionary_query)
        except NoEvidenceError:
            if planner is None:
                raise
            base = curated.collect(word, language, mode, selected, planner)
        if any(trusted_entry(source, word, language) for source in base["sources"]):
            return base

        readings = ()
        if language == "ja":
            readings = tuple(dict.fromkeys(
                item["reading"] for item in lookup_kanjium(word).pitch_accents if item["reading_scope"] == word
            ))
        query = scoped_query(word, language, readings)
        if not query:
            return base
        base["queries"].append(query)
        try:
            additional = super().collect(word, language, mode, selected, lambda *_: query)
        except (ServiceError, NoEvidenceError):
            return base
        trusted = next((s for s in additional["sources"] if trusted_entry(s, word, language, readings)), None)
        if trusted:
            sources = [trusted] + [s for s in base["sources"] if s["url"] != trusted["url"]]
            base["sources"] = [{**s, "id": f"S{i}"} for i, s in enumerate(sources[:3], 1)]
        return base
