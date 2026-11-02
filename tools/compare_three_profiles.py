"""Compare fixed-prefix, draft-repair and two-phase profiles with explicit controls."""
import argparse
from collections import Counter
import html
import json
from pathlib import Path

LABELS=['A 固定前缀版','B 草稿修复版','C 内容／排版分离版']


def summarize(data):
    rows=[r for b in data['batches'] for r in b['rows']]
    n=len(rows);passed=sum(r['status']=='success' for r in rows)
    costs={k:sum(r['cost'][k] for r in rows) for k in ('off_peak_yuan','peak_yuan')}
    phases=Counter();tokens=Counter();stage_tokens={}
    failure_phases=Counter()
    for r in rows:
        tokens.update(r['tokens'])
        for c in r['calls']:
            stage=c['stage'];phases[stage]+=1
            if stage not in stage_tokens:stage_tokens[stage]=Counter()
            for key in ('input','hit','miss','output'):stage_tokens[stage][key]+=c[key]
        if r['status']!='success':
            phase=r.get('failed_stage')
            if not phase:
                error=r.get('error','')
                phase='tag_audit' if '标签复核' in error else 'generation' if '模型输出未通过' in error else 'service/unknown'
            failure_phases[phase]+=1
    return {'attempts':n,'successes':passed,'failures':n-passed,'failure_rate':(n-passed)/n,
            'cost':costs,'mean_per_attempt':{k:v/n for k,v in costs.items()},
            'mean_per_success':{k:v/passed if passed else None for k,v in costs.items()},
            'calls_by_stage':dict(phases),'tokens':dict(tokens),
            'tokens_by_stage':{k:dict(v) for k,v in stage_tokens.items()},
            'off_peak_cost_by_stage':{k:(v['hit']*.02+v['miss']+v['output']*4)/1e6 for k,v in stage_tokens.items()},
            'failure_stages':dict(failure_phases),
            'unknown_usage_errors':sum(len(r.get('unmetered_errors',[])) for r in rows)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before',type=Path);parser.add_argument('repair',type=Path);parser.add_argument('latest',type=Path)
    parser.add_argument('--aborted-trial',type=Path,help='Separate diagnostic-trial summary JSON; excluded from formal comparison')
    args=parser.parse_args();paths=[args.before,args.repair,args.latest]
    datasets=[json.loads((p/'profile.json').read_text(encoding='utf-8')) for p in paths]
    complete=[len(d['batches']) for d in datasets]
    ids={s['id'] for s in datasets[-1]['summary']}
    for data in datasets:
        assert data['method']['words']==datasets[0]['method']['words']
        assert data['method']['settings']==datasets[0]['method']['settings']
        assert data['method']['concurrency']==datasets[0]['method']['concurrency']
    changed={}
    baseline=datasets[0]['method']['prompt_hashes']
    for i,data in enumerate(datasets):
        current=data['method']['prompt_hashes']
        changed[LABELS[i]]=[k for k in sorted(set(baseline)|set(current)) if baseline.get(k)!=current.get(k)]
    totals=[summarize({**d,'batches':[b for b in d['batches'] if b['id'] in ids]}) for d in datasets]
    comparisons=[]
    maps=[{s['id']:s for s in d['summary']} for d in datasets]
    for batch_id in [s['id'] for s in datasets[-1]['summary']]:
        cases=[m[batch_id] for m in maps]
        for i in range(1,3):assert [r['word'] for r in next(b for b in datasets[i]['batches'] if b['id']==batch_id)['rows']]==[r['word'] for r in next(b for b in datasets[0]['batches'] if b['id']==batch_id)['rows']]
        comparisons.append({'id':batch_id,'requested':cases[0]['requested'],
            'total_yuan':[c['cost']['off_peak_yuan'] for c in cases],
            'mean_yuan':[c['mean_cost_per_requested']['off_peak_yuan'] for c in cases],
            'failures':[c['requested']-c['successes'] for c in cases],
            'failure_rates':[(c['requested']-c['successes'])/c['requested'] for c in cases],
            'mean_per_success':[c['cost_per_success_including_failures']['off_peak_yuan'] for c in cases]})
    report={'labels':LABELS,'completed_latest_batches':len(ids),'totals':totals,'batches':comparisons,
            'controlled':['same words and order','same model and parameters','same starter tags','same concurrency','sequential isolated batches','same final content/style/tag validators; C additionally protects accepted wording during formatting'],
            'intentional_changes':'A→B adds draft-aware repair. B→C changes content/style prompts to plain-text authoring and adds a dedicated formatting prompt/stage with protected-content checking.',
            'prompt_hash_differences_vs_A':changed,
            'caveat':'One run per batch size; model randomness, search results, routing and cache may differ. Prompt hashes intentionally differ in C. Known usage costs exclude unobservable billing on lost responses.'}
    if args.aborted_trial:
        report['excluded_diagnostic_trial']=json.loads(args.aborted_trial.read_text(encoding='utf-8'))
    out=args.latest
    (out/'three-version-comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    page='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>三版制卡费用与失败率对比</title><style>body{font:16px/1.6 system-ui;max-width:1500px;margin:40px auto;padding:0 24px}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}td,th{padding:9px;border-bottom:1px solid #ddd;text-align:right}td:first-child,th:first-child{text-align:left}.scroll{overflow:auto}.note{padding:16px;background:#eeeafa;border-radius:8px}</style><h1>三版制卡费用与失败率对比</h1><p class="note">A：固定前缀；B：携带草稿修复；C：内容撰写与排版分离。相同词表、顺序、模型参数、初始标签、并发4及最终校验标准。12批依次运行，批内并行、批间缓存隔离。C的提示词和流程有意改变，不能声称三版提示词相同。费用统一空闲人民币价，包含已知失败/修正及成功Search；非账号余额对账。</p>'''
    page+=f'<p>C 已完成 {len(ids)}/12 批。每个完整版本244次提交。</p><table><tr><th>版本</th><th>成功</th><th>失败</th><th>失败率</th><th>总费用</th><th>均费/提交词</th><th>含失败均费/成功卡</th><th>未知用量异常</th></tr>'
    for label,t in zip(LABELS,totals):
        cells=[label,t['successes'],t['failures'],f'{t["failure_rate"]:.2%}',f'¥{t["cost"]["off_peak_yuan"]:.4f}',
               f'¥{t["mean_per_attempt"]["off_peak_yuan"]:.5f}',f'¥{t["mean_per_success"]["off_peak_yuan"]:.5f}' if t['successes'] else '—',t['unknown_usage_errors']]
        page+='<tr>'+''.join('<td>'+str(v)+'</td>' for v in cells)+'</tr>'
    page+='</table>'
    if args.aborted_trial:
        trial=report['excluded_diagnostic_trial']
        page+=f'<p class="note">正式C采用修复排版返回契约后的代码。最初异常试测发现模型回显外层上下文，36次已完成制卡中仅1次成功，已停止。该试测已知空闲费用¥{trial["known_off_peak_yuan"]:.4f}，另有中断时在途请求用量无法确定，单独列出、不混入正式244次对比。修复明确返回词卡本体，并仅安全解包完全匹配的上下文外壳；原有内容保护和排版标准保留。</p>'
    page+='<h2>逐批对比（A / B / C）</h2><div class="scroll"><table><tr><th>批次</th><th>总费用</th><th>均费/提交词</th><th>失败次数</th><th>失败率</th></tr>'
    for b in comparisons:
        cells=[b['id'],' / '.join(f'¥{v:.4f}' for v in b['total_yuan']),
               ' / '.join(f'¥{v:.4f}' for v in b['mean_yuan']),
               ' / '.join(str(v) for v in b['failures']),
               ' / '.join(f'{v:.1%}' for v in b['failure_rates'])]
        page+='<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in cells)+'</tr>'
    page+='</table></div><h2>模型调用与失败阶段</h2><table><tr><th>版本</th><th>检索规划调用</th><th>内容生成/修正</th><th>排版/排版修正</th><th>标签复核/修正</th><th>失败阶段</th></tr>'
    for label,t in zip(LABELS,totals):
        page+='<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in [label,*[t['calls_by_stage'].get(k,0) for k in ('search_planner','generation','formatting','tag_audit')],t['failure_stages']])+'</tr>'
    page+='</table><h2>阶段费用（统一空闲价，Search按次费用另计）</h2><table><tr><th>版本</th><th>检索规划</th><th>内容生成/修正</th><th>排版/修正</th><th>标签复核/修正</th></tr>'
    for label,t in zip(LABELS,totals):
        page+='<tr><td>'+label+'</td>'+''.join(f'<td>¥{t["off_peak_cost_by_stage"].get(k,0):.4f}</td>' for k in ('search_planner','generation','formatting','tag_audit'))+'</tr>'
    page+='</table><p>失败归类：A/B依据保存的错误文本推定；C使用明确失败stage，服务异常可能没有stage。C的格式保护会拒绝改写正文/例句/引用/标签，即使排版看起来合格。服务异常的未知usage单独计数，不能视作免费。</p><h2>限制</h2><p>每档只测一轮；相同词在1/10/50档重复，不是244个独立随机词。只能描述本轮表现，不能把所有差异都归因于架构。各版本未知用量异常及缓存/搜索波动可能影响真实账单。高峰价及本次逐调用明细见完整Profile。</p>'
    page+='<p><a href="profile.html">C完整Profile及生成样例</a> · <a href="three-version-comparison.json">三版对比JSON</a> · <a href="../'+args.before.name+'/profile.html">A</a> · <a href="../'+args.repair.name+'/profile.html">B</a></p></html>'
    (out/'three-version-comparison.html').write_text(page,encoding='utf-8')
    print(json.dumps({'completed':len(ids),'labels':LABELS,'totals':totals},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
