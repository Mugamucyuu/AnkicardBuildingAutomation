"""Compare two completed isolated batch profiles at identical tariff assumptions."""
import argparse
import html
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before',type=Path);parser.add_argument('after',type=Path)
    args=parser.parse_args()
    old=json.loads((args.before/'profile.json').read_text(encoding='utf-8'))
    new=json.loads((args.after/'profile.json').read_text(encoding='utf-8'))
    assert old['method']['words']==new['method']['words']
    assert old['method']['prompt_hashes']==new['method']['prompt_hashes']
    assert old['method']['settings']==new['method']['settings']
    assert old['method']['concurrency']==new['method']['concurrency']
    previous={s['id']:s for s in old['summary']}
    comparisons=[]
    for after in new['summary']:
        before=previous[after['id']]
        n=after['requested'];assert n==before['requested']
        a,b=before['cost']['off_peak_yuan'],after['cost']['off_peak_yuan']
        comparisons.append({'id':after['id'],'requested':n,
             'before_total_yuan':a,'after_total_yuan':b,
             'before_mean_yuan':a/n,'after_mean_yuan':b/n,
             'cost_change_percent':(b/a-1)*100 if a else None,
             'before_failures':n-before['successes'],'after_failures':n-after['successes'],
             'before_failure_rate':1-before['successes']/n,'after_failure_rate':1-after['successes']/n,
             'before_success_cost':before['cost_per_success_including_failures']['off_peak_yuan'],
             'after_success_cost':after['cost_per_success_including_failures']['off_peak_yuan'],
             'before_generation_retries':before['generation_retries'],'after_generation_retries':after['generation_retries'],
             'before_audit_retries':before['audit_retries'],'after_audit_retries':after['audit_retries']})
    def aggregate(rows,ids=None):
        rows=[r for r in rows if ids is None or r['id'] in ids]
        n=sum(r['requested'] for r in rows);success=sum(r['successes'] for r in rows)
        total=sum(r['cost']['off_peak_yuan'] for r in rows)
        return {'attempts':n,'successes':success,'failures':n-success,
                'failure_rate':(n-success)/n if n else None,'total_yuan':total,
                'mean_per_attempt':total/n if n else None,'mean_per_success':total/success if success else None,
                'unknown_usage_errors':sum(r['unmetered_errors'] for r in rows)}
    ids={r['id'] for r in new['summary']}
    report={'tariff':'uniform off-peak CNY for both runs, includes successful search fees and known failed calls',
            'controls_verified':['same words/order','same eleven prompt hashes','same model/settings','same concurrency','sequential isolated batches'],
            'limitations':['one before/after run per size; provider randomness, search results, routing and cache can vary',
                           'unknown-usage calls may have been billed; not account-balance reconciliation'],
            'completed_batches':len(comparisons),'before':aggregate(old['summary'],ids),'after':aggregate(new['summary']),
            'comparisons':comparisons}
    (args.after/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    page='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>修正流程前后对比</title><style>body{font:16px/1.6 system-ui;max-width:1450px;margin:40px auto;padding:0 20px}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}td,th{padding:9px;border-bottom:1px solid #ddd;text-align:right}td:first-child,th:first-child{text-align:left}.scroll{overflow:auto}</style><h1>修正流程前后对比</h1><p>相同词表、语言与模式、1/10/50词档、默认并发4、相同模型和全部11个提示词指纹、相同校验规则。每批独立缓存标识，无交叉混测。新增：修正请求携带上轮完整草稿并要求保留已合格字段；失败草稿/逐轮错误保存在本地。最多3轮不变。</p>'''
    page+=f'<p>完成批次：{len(comparisons)}/12。统一空闲价比较，含搜索、失败和自动修正。总费用 ¥{report["before"]["total_yuan"]:.4f} → ¥{report["after"]["total_yuan"]:.4f}；失败 {report["before"]["failures"]} → {report["after"]["failures"]}，失败率 {report["before"]["failure_rate"]:.2%} → {report["after"]["failure_rate"]:.2%}。</p>'
    page+='<div class="scroll"><table><tr><th>批次</th><th>上次总费</th><th>本次总费</th><th>上次均费/提交词</th><th>本次均费/提交词</th><th>费用变化</th><th>上次失败</th><th>本次失败</th><th>上次失败率</th><th>本次失败率</th></tr>'
    for r in comparisons:
        cells=[r['id'],f'¥{r["before_total_yuan"]:.4f}',f'¥{r["after_total_yuan"]:.4f}',
               f'¥{r["before_mean_yuan"]:.4f}',f'¥{r["after_mean_yuan"]:.4f}',f'{r["cost_change_percent"]:+.1f}%',
               r['before_failures'],r['after_failures'],f'{r["before_failure_rate"]:.1%}',f'{r["after_failure_rate"]:.1%}']
        page+='<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in cells)+'</tr>'
    page+='</table></div><h2>含失败消耗的每张成功卡片成本</h2><table><tr><th>批次</th><th>上次</th><th>本次</th><th>额外生成轮数：上次→本次</th><th>额外复核轮数：上次→本次</th></tr>'
    fmt=lambda x:'—' if x is None else f'¥{x:.4f}'
    for r in comparisons:
        page+='<tr>'+''.join('<td>'+str(x)+'</td>' for x in [r['id'],fmt(r['before_success_cost']),fmt(r['after_success_cost']),
                           f'{r["before_generation_retries"]} → {r["after_generation_retries"]}',
                           f'{r["before_audit_retries"]} → {r["after_audit_retries"]}'])+'</tr>'
    page+='</table><p>只有一次前后测量，不能将全部差异都归因于修正策略；搜索返回内容、模型随机性、缓存路由和网络仍可能不同。原有风格/内容/引用/标签检查未放宽。未返回usage的异常单独列出，不能假定免费。</p><p><a href="profile.html">本次完整profile及生成样例</a> · <a href="comparison.json">对比JSON</a> · <a href="../'+args.before.name+'/profile.html">上次profile</a></p></html>'
    (args.after/'comparison.html').write_text(page,encoding='utf-8')
    print(json.dumps({'before':report['before'],'after':report['after'],'comparisons':comparisons},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
