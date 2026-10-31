"""Explicit knowledge-only, model-planned web, or selected-source grounding."""
import json,os,re
from urllib.parse import urlparse,quote,unquote
from .transport import request_json

SOURCES={
 "wiktionary":{"name":"Wiktionary","domains":["en.wiktionary.org","ja.wiktionary.org"],"languages":["en","ja","ko"]},
 "etymonline":{"name":"Online Etymology Dictionary","domains":["etymonline.com"],"languages":["en"]},
 "cambridge":{"name":"Cambridge Dictionary","domains":["dictionary.cambridge.org"],"languages":["en"]},
 "merriam_webster":{"name":"Merriam-Webster","domains":["merriam-webster.com"],"languages":["en"]},
 "kotobank":{"name":"コトバンク（収録国語辞典）","domains":["kotobank.jp"],"languages":["ja"]},
 "krdict":{"name":"国立国语院韩国语基础词典","domains":["krdict.korean.go.kr"],"languages":["ko"]},
 "oxford":{"name":"Oxford Learner’s Dictionaries","domains":["oxfordlearnersdictionaries.com"],"languages":["en"]},
 "longman":{"name":"Longman Dictionary of Contemporary English","domains":["ldoceonline.com"],"languages":["en"]},
 "free_dictionary":{"name":"Free Dictionary API","domains":["api.dictionaryapi.dev"],"languages":["en"]},
 "daum":{"name":"Daum 사전","domains":["dic.daum.net"],"languages":["ko"]},
}
def domain_matches(url,domains):
 host=(urlparse(url).hostname or "").lower()
 return any(host==d or host.endswith("."+d) for d in domains)

def wiktionary_entry(word,language):
 """Retrieve the exact headword's language section, without search substitutions."""
 from .public_media import api,plain
 try:
  name={"en":"English","ja":"Japanese","ko":"Korean"}[language]
  sections=api("en.wiktionary.org",action="parse",page=word,prop="sections")["parse"]["sections"]
  section=next(s["index"] for s in sections if s["line"]==name and s["level"]=="2")
  markup=api("en.wiktionary.org",action="parse",page=word,section=section,prop="text")["parse"]["text"]["*"]
  markup=re.sub(r'<(?:script|style)\b[^>]*>.*?</(?:script|style)>','',markup,flags=re.S)
  text=" ".join(plain(markup).split())[:4500]
  if not text:return None
  return {"url":"https://en.wiktionary.org/wiki/"+quote(word,safe="")+"#"+name,
          "title":word+" — Wiktionary ("+name+")","excerpt":text,
          "content_type":"dictionary_entry_excerpt"}
 except Exception:
  return None

def free_dictionary_entry(word, language):
 """Fetch the exact English API entry, retaining a short evidence excerpt."""
 if language != "en":return None
 from .public_media import fetch
 url="https://api.dictionaryapi.dev/api/v2/entries/en/"+quote(word,safe="")
 try:
  payload=json.loads(fetch(url));parts=[]
  for entry in payload:
   if entry.get("word","").casefold()!=word.casefold():continue
   for meaning in entry.get("meanings",[]):
    for definition in meaning.get("definitions",[])[:3]:
     parts.append(meaning.get("partOfSpeech","")+": "+definition.get("definition","")+" Example: "+definition.get("example",""))
  if not parts:return None
  return {"url":url,"title":word+" — Free Dictionary API","excerpt":"\n".join(parts)[:4500],"content_type":"dictionary_entry_excerpt"}
 except (ValueError,TypeError,AttributeError,RuntimeError,OSError):return None

class DeepSeekSearch:
 def search(self,query):
  key=os.getenv("DEEPSEEK_SEARCH_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
  if not key:raise ValueError("联网资料检索需要 DEEPSEEK_SEARCH_API_KEY 或 DEEPSEEK_API_KEY。")
  data=request_json("https://api.deepseek.com/v1/tools/search",{"query":query[:128],"count":4,"need_content":True},headers={"Authorization":"Bearer "+key},timeout=60)
  return data.get("results",[])

class ResearchCollector:
 def __init__(self,search=None):
  self.search=search or DeepSeekSearch()
 def collect(self,word,language,mode="independent",selected=(),planner=None):
  if mode not in ("independent","web","sources"):raise ValueError("未知生成模式。")
  if mode=="independent":return {"mode":mode,"sources":[],"queries":[]}
  if mode=="sources" and not selected:raise ValueError("指定来源模式至少选择一个词典。")
  for source in selected:
   if source not in SOURCES or language not in SOURCES[source]["languages"]:raise ValueError("所选词典不支持当前语言。")
  direct=[];covered=set()
  if mode=="sources" and "wiktionary" in selected:
   entry=wiktionary_entry(word,language)
   if entry:direct.append(entry);covered.add("wiktionary")
   if entry and len(selected)==1:
    return {"mode":mode,"sources":[{"id":"S1",**entry}],"queries":["Wiktionary exact entry: "+word+" ("+language+")"]}
  if mode=="sources" and "free_dictionary" in selected:
   entry=free_dictionary_entry(word,language)
   if entry:direct.append(entry);covered.add("free_dictionary")
  if mode=="sources" and set(selected)==covered:
   return {"mode":mode,"sources":[{"id":"S"+str(i+1),**entry} for i,entry in enumerate(direct)],"queries":["Exact dictionary entry: "+word+" ("+language+")"]}
  if mode=="web":
   if planner is None:raise ValueError("自动联网模式需要模型规划检索词。")
   query=planner(word,language)
   queries=[query[:128]]
   domains=None
  else:
   # Quote the headword and avoid generic English keywords outweighing a
   # Japanese/Korean term. English Wiktionary contains all three languages.
   queries=[]
   for source in selected:
    if source in covered:continue
    hosts=SOURCES[source]["domains"]
    if source=="wiktionary":hosts=["ja.wiktionary.org" if language=="ja" else "en.wiktionary.org"]
    queries.append('"'+word.replace('"','')+'" '+" OR ".join("site:"+d for d in hosts))
   domains=[d for s in selected for d in SOURCES[s]["domains"]]
  results=[{"id":"S"+str(i+1),**entry} for i,entry in enumerate(direct)];seen={entry["url"] for entry in direct}
  for query in queries:
   for hit in self.search.search(query[:128]):
    url=hit.get("url","")
    if urlparse(url).scheme!="https" or url in seen:continue
    if domains and not domain_matches(url,domains):continue
    if mode=="sources" and list(selected)==["wiktionary"] and unquote(urlparse(url).path).rstrip("/")!="/wiki/"+word:continue
    text=hit.get("content") or hit.get("summary") or hit.get("snippet","")
    if not text.strip():continue
    seen.add(url)
    # Retain a short evidence excerpt, not a mirror of a proprietary dictionary.
    excerpt=" ".join(text.split()[:100])[:1800]
    results.append({"id":"S"+str(len(results)+1),"url":url,"title":hit.get("title",url),
                    "excerpt":excerpt,"content_type":"page_excerpt" if hit.get("content") else "search_summary"})
  if not results:raise ValueError("没有取到可用资料；不会静默改为模型独立生成。")
  return {"mode":mode,"sources":results,"queries":queries}
