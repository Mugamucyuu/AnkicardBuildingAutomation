"""Supplemental public audio and accent sources with exact headword checks."""
import json,re
from urllib.parse import quote
from .media import MediaResult
from .public_media import fetch,plain

def ojad(word, reading=''):
 from .ojad import lookup
 return lookup(word, reading)

def free_dictionary(word):
 data=json.loads(fetch("https://api.dictionaryapi.dev/api/v2/entries/en/"+quote(word,safe="")))
 result=MediaResult()
 for entry in data if isinstance(data,list) else []:
  for phonetic in entry.get("phonetics",[]):
   url=phonetic.get("audio","")
   if url.startswith("//"):url="https:"+url
   if not re.search(r"(?:[-_]us)(?:[-_.]|$)",url,re.I):continue
   result.pronunciation_text=phonetic.get("text","")
   result.pronunciation_system="IPA"
   result.assets=[{"kind":"audio","url":url,"source_page":phonetic.get("sourceUrl") or "https://dictionaryapi.dev/",
      "attribution":"Free Dictionary API / linked recording source","license":phonetic.get("license",{}).get("name","See original recording license"),"variety":"US"}]
   return result
 return result

def cambridge(word):
 from .english_media import cambridge as adapter
 return adapter(word)

def lookup_expanded(registry,language,word):
 if language=="en":
  from .english_media import lookup
  return lookup(registry,word)
 merged=MediaResult();attempts=[]
 candidates=[("English Wiktionary",lambda:registry.wiktionary(word,language))]
 if language=="ko":
  from .korean_media import daum
  candidates += [("Korean Basic Dictionary",lambda:registry.korean(word)),("Daum Korean Dictionary",lambda:daum(word))]
 if language=="ja":
  pitch=registry.japanese_accent(word)
  merged.pitch_accents=pitch.pitch_accents
  merged.assets=pitch.assets
  merged.lookup_attempts.extend(pitch.lookup_attempts)
  # Audio is independent of the configured pitch priority. OJAD may still
  # supply a recording even when Kanjium already supplied the pitch.
  if not any(a.get("source")=="OJAD" for a in pitch.lookup_attempts):
   candidates = [("OJAD audio",lambda:ojad(word))] + candidates
  candidates += [("Japanese Wiktionary",lambda:registry.wiktionary(word,language,"ja.wiktionary.org"))]
 for source,lookup in candidates:
  if language=="ko" and merged.assets and merged.phonetic_hangul:break
  attempts.append(source)
  try:
   result=lookup()
   merged.lookup_attempts.append({"source":source,"status":"ok","purpose":"audio_and_transcription" if language=="ja" else "pronunciation","audio":len(result.assets),"pitch":0 if language=="ja" else len(result.pitch_accents)})
   merged.lookup_attempts.extend([{**a,"purpose":"audio_and_transcription"} for a in result.lookup_attempts] if language=="ja" else result.lookup_attempts)
   if not merged.pronunciation_text:merged.pronunciation_text=result.pronunciation_text;merged.pronunciation_system=result.pronunciation_system
   if not merged.assets:merged.assets=result.assets
   for reading in result.phonetic_hangul:
    if not any(p["text"]==reading["text"] for p in merged.phonetic_hangul):merged.phonetic_hangul.append(reading)
   if language!="ja" and not merged.pitch_accents:merged.pitch_accents=result.pitch_accents
  except Exception as error:
   merged.lookup_attempts.append({"source":source,"status":"error","error_type":type(error).__name__})
   continue
 merged.warnings=[] if merged.assets else ["未找到匹配真人录音；已查："+", ".join(attempts)]
 if language=="ja" and not merged.pitch_accents:merged.warnings.extend(pitch.warnings or ["声调尚无可核对的公开记录，未用 AI 猜测。"])
 return merged
