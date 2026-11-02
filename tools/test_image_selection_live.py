"""Public-network image regression with fixed sense plans; no model/Anki calls."""
import concurrent.futures
import html
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vocab_app.public_media import PublicMediaRegistry, download_assets
from vocab_app.image_selection import rank_candidate
from vocab_app.media import MediaResult

CASES = [
 ('apple','Apple','apple fruit',['apple','apples'],['fruit'],'photo',[]),
 ('acacia','Acacia','acacia tree',['acacia'],['tree','plant'],'photo',[]),
 ('antimony','Antimony','antimony element',['antimony'],['element','metal'],'photo',[]),
 ('lacquerware','Lacquerware','empty lacquered bowl',['lacquerware','lacquered','urushi'],['bowl','wood'],'photo',['rice','soup','food']),
 ('curd','Curd','milk curds',['curd','curds'],['milk','cheese'],'photo',['lemon']),
 ('microscope','Microscope','optical microscope',['microscope'],['optical','laboratory'],'photo',[]),
 ('umbrella','Umbrella','open umbrella',['umbrella'],['rain','canopy'],'photo',[]),
 ('bicycle','Bicycle','bicycle side view',['bicycle','bike'],['wheel','pedal'],'photo',[]),
 ('waterfall','Waterfall','waterfall landscape',['waterfall'],['water','river'],'photo',[]),
 ('peninsula','Peninsula','peninsula aerial geography',['peninsula'],['land','water'],'photo',[]),
 ('squatting','Squatting position','person squatting posture',['squatting','squat'],['posture','knees'],'photo',['abandoned']),
 ('rhombus','Rhombus','rhombus diagram',['rhombus','rhombi'],['quadrilateral','geometry'],'diagram',[]),
 ('triangle','Triangle','simple triangle geometry',['triangle'],['geometry','angle'],'diagram',[]),
 ('ellipse','Ellipse','ellipse geometry diagram',['ellipse'],['geometry','foci'],'diagram',[]),
 ('photosynthesis','Photosynthesis','photosynthesis overview diagram',['photosynthesis'],['plant','light'],'diagram',[]),
 ('evaporation','Evaporation','evaporation diagram',['evaporation'],['water','vapor'],'diagram',[]),
 ('water cycle','Water cycle','water cycle diagram english',['water cycle','hydrological cycle'],['water','precipitation'],'diagram',[]),
 ('food chain','Food chain','food chain diagram',['food chain','food web'],['ecosystem','energy'],'diagram',[]),
 ('electric circuit','Electrical network','simple electric circuit diagram',['circuit','electrical network'],['electric','voltage'],'diagram',['doorbell','integrated']),
 ('supply and demand','Supply and demand','supply demand graph',['supply','demand'],['price','economics'],'diagram',[]),
]

def main():
 folder=Path('output/image-selection-20-20261101');folder.mkdir(parents=True,exist_ok=True)
 def run(case):
  word,topic,query,anchors,context,kind,avoid=case
  path=folder/(word.replace(' ','-')+'.json')
  if path.exists():
   saved=json.loads(path.read_text(encoding='utf-8'))
   if '--rerank-cached' in sys.argv:
    result=saved['result'];selection=result['selection'];plan=selection.get('plan')
    ranked=[]
    for asset in selection.get('approved_assets',[]):
     score,reasons=rank_candidate(asset,plan)
     for candidate in selection.get('candidates',[]):
      if candidate['title']==asset['title']:candidate.update(score=score,reasons=reasons)
     if score>=5:ranked.append((score,asset))
    ranked.sort(key=lambda pair:pair[0],reverse=True)
    selection['approved_assets']=[a for _,a in ranked]
    result['assets']=[dict(ranked[0][1])] if ranked else []
    selection['selected_title']=ranked[0][1]['title'] if ranked else None
    selection['ranking_version']=2
    if ranked:
     selection['status']='selected';result=download_assets(MediaResult(**result),folder/'media').to_dict()
    elif selection['status']!='lookup_failed':selection['status']='no_confident_match'
    saved['result']=result
    path.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
    return saved
   refresh = '--refresh-diagrams' in sys.argv and kind=='diagram'
   if not refresh and ('--retry-failed' not in sys.argv or saved['result']['selection']['status']!='lookup_failed'):return saved
   archive=path.with_suffix('.previous.json')
   if not archive.exists():archive.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
  plan={'sense_id':'s1','topic':topic,'query':query,'anchors':anchors,'context':context,'exclude':[],'kind':kind,'avoid_scenes':avoid}
  if word=='lacquerware':plan['alternatives']=['urushi lacquer box','lacquerware bowl']
  registry=PublicMediaRegistry()
  result=download_assets(registry.select_image(word,'en',[{'id':'s1','definition':query}],plan),folder/'media').to_dict()
  row={'word':word,'kind':kind,'fixed_plan':True,'result':result}
  path.write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'word':word,'status':result['selection']['status'],'image':result['selection']['selected_title']},ensure_ascii=False),flush=True)
  return row
 with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:rows=list(pool.map(run,CASES))
 (folder/'report.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
 cards=[]
 for row in rows:
  r=row['result'];a=r['assets'][0] if r['assets'] else None
  picture='<img src="'+html.escape(a['local_path'],quote=True)+'">' if a else '<p>未找到或检索失败</p>'
  credit='<a href="'+html.escape(a['source_page'],quote=True)+'">'+html.escape(a['title'])+'</a><p>'+html.escape(a['license'])+'</p>' if a else ''
  cards.append('<article><h2>'+html.escape(row['word'])+'</h2><p>'+row['kind']+' · '+r['selection']['status']+'</p>'+picture+credit+'</article>')
 (folder/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>20-word image regression</title><style>body{font:16px/1.6 system-ui;margin:30px;background:#f3f5f2}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}article{padding:18px;background:white;border-radius:12px;overflow-wrap:anywhere}img{width:100%;height:230px;object-fit:contain}h2{margin:0}</style><h1>20 词真实选图测试</h1><p>固定词义/检索计划，真实公共网络查询、自动评分及下载；不调用模型，不写 Anki。需要人工判断图片的教学代表性。</p><main>'+''.join(cards)+'</main>',encoding='utf-8')
 print('Downloaded '+str(sum(bool(r['result']['assets']) for r in rows))+'/20',flush=True)
if __name__=='__main__':main()
