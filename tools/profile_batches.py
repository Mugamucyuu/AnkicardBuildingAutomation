"""Paid, isolated batch benchmark. No Anki writes or saved credentials.

Run with --live. Twelve sequential batches: en/ja x independent/web x 1/10/50.
Within each batch use the application's default four concurrent word workers.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
from uuid import uuid4
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from vocab_app.pipeline import ImportPipeline
from vocab_app.providers import ModelClient
from vocab_app.settings import Settings
from vocab_app.media import MediaRegistry
from vocab_app.taxonomy import TagCatalog
from vocab_app.prompts import default_prompts
from vocab_app.transport import request_json
from vocab_app import __version__

WORDS={
 'en': 'apple peninsula curd charge resilient anastomosis lacquerware ubiquitous microscope umbrella bicycle waterfall triangle photosynthesis evaporation lantern harvest shelter negotiate intricate reluctant preserve flourish obscure diligent coherent subtle fragile abundant ambiguous inevitable versatile concise profound endure distinguish allocate contemplate genuine reluctantly landscape rhythm scarcity remedy acquire boundary consequence anticipate gratitude insight'.split(),
 'ja': '猫 桜 刺青 しわ寄せ 横領 生かす 曖昧 木漏れ日 学校 電車 図書館 約束 習慣 経験 努力 判断 誤解 配慮 工夫 憧れ 戸惑う ためらう 見直す 引き受ける 思い込む 取り組む 振り返る 落ち着く 立ち直る 見守る おおらか さりげない もどかしい ややこしい 潔い 儚い 懐かしい 頼もしい 厄介 素朴 繊細 偶然 必然 矛盾 葛藤 余韻 気配 面影 手応え 心掛け'.split()
}


def write(path,data):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


def cost(hit,miss,out,search):
    base=(hit*.02+miss+out*4)/1e6
    return {'off_peak_yuan':base+.005*search,'peak_yuan':base*2+.005*search}


def run(args):
    for lang,words in WORDS.items():assert len(words)==50 and len(set(words))==50,(lang,len(words))
    prompts=default_prompts()
    catalog=TagCatalog.load();catalog.snapshot_info()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    manifest={'version':__version__,'concurrency':4,'sizes':[1,10,50],'words':WORDS,
              'prompt_hashes':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in prompts.items()},
              'cache_isolation':'Unique neutral system-message batch identifier per batch; original instructions retained verbatim. No prewarming calls. +~20 tokens/request. Provider cache cannot be explicitly purged.',
              'settings':{'model':'deepseek-flash','thinking':'disabled','max_tokens':4096,'tags':'starter snapshot',
                          'image_planning':True,'external_media_downloads':False,'anki_writes':False},
              'pricing_source':'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/','batches':[]}
    write(output/'manifest.json',manifest)
    active=threading.local()
    original=request_json
    for lang in ('en','ja'):
      for mode in ('independent','web'):
       for size in (1,10,50):
        batch_id=f'{lang}-{mode}-{size}'
        scope=uuid4().hex
        directory=output/batch_id;directory.mkdir(exist_ok=True)
        if (directory/'batch.json').exists():raise RuntimeError('Refusing to overwrite an existing paid batch')
        start=time.monotonic()
        batch={'id':batch_id,'language':lang,'mode':mode,'requested':size,'scope':scope,
               'started_at':datetime.now(timezone.utc).isoformat(),'rows':[]}
        print('START',batch_id,flush=True)
        def observed(url,payload,**kwargs):
            row=active.row
            is_search='/tools/search' in url
            stage=None
            if not is_search:
                system=payload['messages'][0]['content']
                stage=('search_planner' if system==prompts['search_planner'] else
                       'tag_audit' if system.startswith(prompts['tag_review']) else 'generation')
                payload={**payload,'messages':[dict(m) for m in payload['messages']]}
                payload['messages'][0]['content']='Benchmark batch identifier: '+scope+'\n'+system
            begun=time.monotonic()
            try:response=original(url,payload,**kwargs)
            except Exception as error:
                row['unmetered_errors'].append({'stage':'search' if is_search else stage,'type':type(error).__name__})
                raise
            if is_search:
                row['searches']+=int(bool(response.get('results')))
            else:
                usage=response.get('usage')
                if usage:
                    hit=usage.get('prompt_cache_hit_tokens',usage.get('prompt_tokens_details',{}).get('cached_tokens',0))
                    row['calls'].append({'stage':stage,'input':usage['prompt_tokens'],'hit':hit,
                        'miss':usage['prompt_tokens']-hit,'output':usage['completion_tokens'],
                        'model':response.get('model'),'created':response.get('created'),
                        'finish_reason':response.get('choices',[{}])[0].get('finish_reason'),
                        'seconds':time.monotonic()-begun})
                else:row['unmetered_errors'].append({'stage':stage,'type':'missing_usage'})
            return response
        def word_run(index,word):
            row={'index':index,'word':word,'status':'running','calls':[],'searches':0,'unmetered_errors':[]}
            active.row=row
            begin=time.monotonic()
            try:
                pipeline=ImportPipeline(ModelClient(Settings('deepseek','deepseek-flash'),observed),MediaRegistry(),catalog.clone(),prompts)
                note=pipeline.generate(word,lang,'none','auto',mode)
                assert note['quality_check']['passed'] and note['tag_audit']['attempts'] >= 1
                row.update(status='success',quality=note.get('quality_check'),senses=len(note['senses']))
                # Retain previews for quality/style review; never import them.
                write(directory/f'{index:03}-card.json',note)
            except Exception as error:
                row.update(status='failed',error_type=type(error).__name__)
                # Application errors are sanitized; keep validation diagnostics.
                if isinstance(error,(ValueError,RuntimeError)):row['error']=str(error)
            row['seconds']=time.monotonic()-begin
            totals={key:sum(c[key] for c in row['calls']) for key in ('input','hit','miss','output')}
            row['tokens']={**totals,'total':totals['input']+totals['output']}
            row['cost']=cost(totals['hit'],totals['miss'],totals['output'],row['searches'])
            write(directory/f'{index:03}-usage.json',row)
            return row
        with patch('vocab_app.research.request_json',observed):
            with ThreadPoolExecutor(max_workers=min(size,4)) as pool:
                futures=[pool.submit(word_run,i,w) for i,w in enumerate(WORDS[lang][:size],1)]
                for future in as_completed(futures):
                    row=future.result();batch['rows'].append(row)
                    write(directory/'progress.json',batch)
                    print(batch_id,len(batch['rows']), '/',size,row['word'],row['status'],row['tokens']['total'],flush=True)
        batch['rows'].sort(key=lambda r:r['index'])
        batch.update(seconds=time.monotonic()-start,completed_at=datetime.now(timezone.utc).isoformat())
        batch['successes']=sum(r['status']=='success' for r in batch['rows'])
        batch['known_total_cost']={k:sum(r['cost'][k] for r in batch['rows']) for k in ('off_peak_yuan','peak_yuan')}
        write(directory/'batch.json',batch)
        manifest['batches'].append({k:v for k,v in batch.items() if k!='rows'})
        write(output/'manifest.json',manifest)
        print('DONE',batch_id,batch['successes'],batch['known_total_cost'],flush=True)
    print('COMPLETE 12 isolated batches, 244 requested cards.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='Allow 244 paid generation runs')
    parser.add_argument('--output',type=Path,default=ROOT/'output/cache-prefix-batches-20261102')
    args=parser.parse_args()
    if not args.live:parser.error('Use --live to authorize paid API calls')
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    os.environ['DEEPSEEK_API_KEY']=getpass.getpass('DeepSeek key (hidden): ')
    run(args)
