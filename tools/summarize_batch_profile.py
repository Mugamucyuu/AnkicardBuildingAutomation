"""Build a reviewable HTML/JSON report from profile_batches.py outputs."""
import argparse
from datetime import datetime, timezone, timedelta
import html
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vocab_app.preview import render_preview


def actual_model_cost(call):
    created=call.get('created')
    if not created:return None
    t=datetime.fromtimestamp(created,timezone.utc).astimezone(timezone(timedelta(hours=8)))
    # The recorded run date is 2026-11-02, a non-holiday Monday. Do not use this
    # simplification for runs on Chinese statutory holidays without reviewing it.
    peak=t.weekday()<5 and (9<=t.hour<12 or 14<=t.hour<18)
    return (call['hit']*.02+call['miss']+call['output']*4)/1e6*(2 if peak else 1)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args();root=args.directory
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    summary=[];batches=[]
    for info in manifest['batches']:
        batch=json.loads((root/info['id']/'batch.json').read_text(encoding='utf-8'))
        rows=batch['rows'];n=batch['requested'];k=batch['successes']
        total={key:sum(r['tokens'][key] for r in rows) for key in ('input','hit','miss','output','total')}
        assert total['input']==total['hit']+total['miss']
        costs=batch['known_total_cost']
        actual=sum(actual_model_cost(c) or 0 for r in rows for c in r['calls'])+.005*sum(r['searches'] for r in rows)
        stages={stage:{key:sum(c[key] for r in rows for c in r['calls'] if c['stage']==stage)
                       for key in ('input','hit','miss','output')} for stage in ('search_planner','generation','tag_audit')}
        s={'id':batch['id'],'language':batch['language'],'mode':batch['mode'],'requested':n,'successes':k,
           'seconds':batch['seconds'],'tokens':total,'mean_tokens_per_requested':total['total']/n,
           'cost':costs,'mean_cost_per_requested':{a:b/n for a,b in costs.items()},
           'cost_per_success_including_failures':{a:b/k if k else None for a,b in costs.items()},
           'actual_known_yuan':actual,'mean_actual_known_yuan':actual/n,
           'cache_hit_ratio':total['hit']/total['input'] if total['input'] else 0,
           'model_calls':sum(len(r['calls']) for r in rows),'searches':sum(r['searches'] for r in rows),
           'unmetered_errors':sum(len(r['unmetered_errors']) for r in rows),
           'generation_retries':sum(max(0,sum(c['stage']=='generation' for c in r['calls'])-1) for r in rows),
           'audit_retries':sum(max(0,sum(c['stage']=='tag_audit' for c in r['calls'])-1) for r in rows),
           'stages':stages,'failures':[{'word':r['word'],'type':r.get('error_type'),'error':r.get('error')} for r in rows if r['status']!='success']}
        summary.append(s);batches.append(batch)
    data={'method':manifest,'completed_batches':len(summary),'summary':summary,'batches':batches}
    (root/'profile.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    labels={'en':'英语','ja':'日语','independent':'模型知识','web':'AI检索'}
    def table(tier):
        result='<table><tr><th>语言</th><th>模式</th><th>词数</th><th>成功</th><th>总tokens</th><th>平均tokens/提交词</th><th>总费用</th><th>均费/提交词</th><th>含失败均费/成功词</th><th>输入缓存命中</th></tr>'
        for s in summary:
            per_success=s['cost_per_success_including_failures'][tier]
            cells=[labels[s['language']],labels[s['mode']],s['requested'],s['successes'],
                   f'{s["tokens"]["total"]:,}',f'{s["mean_tokens_per_requested"]:,.0f}',
                   f'¥{s["cost"][tier]:.4f}',f'¥{s["mean_cost_per_requested"][tier]:.4f}',
                   '—' if per_success is None else f'¥{per_success:.4f}',f'{s["cache_hit_ratio"]:.1%}']
            result+='<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in cells)+'</tr>'
        return result+'</table>'
    page='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>v0.3.0 批量制卡缓存 Profile</title><style>body{font:16px/1.65 system-ui;max-width:1400px;margin:40px auto;padding:0 24px;color:#222}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}td,th{padding:9px;border-bottom:1px solid #ddd;text-align:right}td:first-child,th:first-child{text-align:left}.scroll{overflow:auto}.note{background:#eeeafa;padding:16px;border-radius:8px}h2{margin-top:36px}</style><h1>v0.3.0 批量制卡缓存 Profile</h1>'''
    page+=f'<p>已完成 {len(summary)}/12 独立批次，共 {sum(s["requested"] for s in summary)} 次提交；成功 {sum(s["successes"] for s in summary)} 次。</p>'
    page+='''<p class="note">12批按语言→模式→1/10/50词顺序依次执行，批内默认并发4（1词时并发1）。每批独立中性标识隔离上批缓存，无预热请求；标识只在测试传输层添加，正式程序仅调整JSON字段顺序。模型原始规则、语言风格、标签、例句要求及全部校验不变。样本为每种语言固定50词的前1/10/50词，两种模式使用同一词集。默认提示词、初始标签表、非思考模式、4096输出上限，保留配图规划；跳过外部媒体下载，不写Anki。成功卡片保留JSON供复核。</p>'''
    page+='<h2>统一空闲价（便于比较批量规模）</h2><div class="scroll">'+table('off_peak_yuan')+'</div>'
    page+='<h2>统一高峰价</h2><div class="scroll">'+table('peak_yuan')+'</div>'
    page+='<p>总费用包含所有已返回usage的成功、失败及修正调用，并加成功Search每次¥0.005。平均/提交词=总费用÷提交数；含失败平均/成功词=总费用÷成功数，失败全部时无该值。服务端消耗但响应丢失无法精确计费，未返回usage的异常单独计数，不当成免费调用。</p>'
    page+='<h2>实际测试时间对应的已知费用</h2><table><tr><th>批次</th><th>费用（元）</th><th>无usage异常</th><th>额外生成轮数</th><th>额外复核轮数</th><th>批次秒数</th></tr>'
    for s in summary:
        page+='<tr>'+''.join('<td>'+str(v)+'</td>' for v in [s['id'],f'{s["actual_known_yuan"]:.4f}',s['unmetered_errors'],s['generation_retries'],s['audit_retries'],round(s['seconds'],1)])+'</tr>'
    page+='</table><p>按API返回created时间映射北京时间高峰（工作日09–12、14–18），本次日期为2026-11-02，非节假日。若跨过18:00按各调用分别计价。不是账号余额对账。</p>'
    page+='<h2>输出样例（仍使用原有质量与风格检查）</h2><ul>'
    previews=root/'previews';previews.mkdir(exist_ok=True)
    for s in summary:
        if s['requested']!=50:continue
        cards=sorted((root/s['id']).glob('*-card.json'))[:2]
        for card in cards:
            note=json.loads(card.read_text(encoding='utf-8'))
            filename=s['id']+'-'+card.stem+'.html'
            (previews/filename).write_text(render_preview(note),encoding='utf-8')
            page+='<li><a href="previews/'+filename+'">'+html.escape(s['id']+' / '+note['word'])+'</a></li>'
    page+='</ul><h2>失败记录</h2><ul>'
    for s in summary:
        for f in s['failures']:page+='<li>'+html.escape(s['id']+' / '+f['word']+': '+str(f['error']))+'</li>'
    page+='</ul><p>本次是每档一次的描述统计，不是多轮随机实验。缓存构建是尽力而为，冷启动并发会影响首批请求命中；不同词义复杂度和重试会造成均费不单调。质量/风格约束保留，不代表生成文字能与随机的旧输出逐字一致。</p><p><a href="profile.json">逐调用明细</a> · <a href="manifest.json">词表、参数、提示词指纹</a> · <a href="https://api-docs.deepseek.com/zh-cn/quick_start/pricing/">官方价格</a></p></html>'
    (root/'profile.html').write_text(page,encoding='utf-8')
    for s in summary:print(s['id'],f'{s["successes"]}/{s["requested"]}',s['cost'],s['mean_cost_per_requested'],round(s['cache_hit_ratio']*100,1))


if __name__=='__main__':main()
