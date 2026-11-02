# Request prefixes and token profiling

The v0.3.0-based optimization changes the **order of JSON fields only** in generation and tag-review requests. The stable catalog comes first, followed by the word, language and research/content. Existing system prompts, language style prompts, JSON values, tag proposals, generation limits and all content/tag validation and repair remain intact. Each word still has its own generation and audit calls; paid search remains separate.

The same catalog snapshot and prompts are reused within a batch. Moving the catalog ahead of the changing word makes it eligible for prefix caching across words. Generation and audit have different system instructions and should be treated as separate cache prefixes. New tag proposals are still included in the effective audit catalog; their presence may shorten prefix reuse. No cache-hit guarantee or free output is implied.

## Regression checks

`tests/test_request_prefix.py` verifies that generation retains the same parsed request data and exact system instruction for en/ja/ko, and that audit requests retain their data/instructions with the catalog first. The full core suite continues checking quality, style constraints, tag proposals, sources, recovery and concurrency.

## Opt-in paid benchmark

Run from the repository with Python; this makes real paid calls:

```powershell
python tools/profile_batches.py --live
python tools/summarize_batch_profile.py output/cache-prefix-batches-20261102
```

The key is entered with a hidden prompt, held in process memory and never saved. The script refuses to run without `--live` and refuses to overwrite an existing completed paid batch. Use a fresh `--output` directory for another experiment. There is no automatic outer retry of a failed word: normal application content/tag repair is retained and billed usage is recorded.

The twelve batches run sequentially: English knowledge 1/10/50, English search 1/10/50, Japanese knowledge 1/10/50, Japanese search 1/10/50. Within each batch concurrency is four, or one for a single word. Each language uses a fixed 50-word list; smaller sizes use its first 1/10 words. Modes are never interleaved.

Each batch has a different neutral identifier prepended to system messages **only by the benchmark transport**. This prevents the preceding test batch from deliberately warming its long prefix. The original system instruction is retained verbatim after the identifier, and the production application has no benchmark identifier. This adds roughly twenty input tokens per call and simulates separate cold-start batches without waiting for provider cache eviction. The provider offers no explicit purge; actual hit/miss usage is always recorded. No artificial prewarming calls are made.

The benchmark uses the shipped default prompts and starter tag snapshot, DeepSeek Flash with thinking disabled and a 4096-token output cap. Image planning remains enabled, while audio/image downloads are skipped because they consume no DeepSeek tokens. It never writes to Anki. Successful card JSON is retained locally for quality/style review; reports, cards and credentials must not be committed as private user data.

For each batch the report includes submitted/successful counts, known input/output/cache tokens, total cost, average per submitted word, average per successful word including failed-call spending, extra repair rounds, unknown-usage errors and timing. It provides both normalized off-peak/peak costs and costs using each call's returned timestamp. Search is counted separately per successful nonempty response. A lost response may still have been billed by the provider; such unknown usage is disclosed, not treated as known zero cost.

The timestamp-cost helper is written for the recorded 2026-11-02 non-holiday run. Review Chinese statutory holidays before using its weekday/hour calculation for another date. Prices must be verified against [DeepSeek's official table](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/), and caching behavior against [the cache guide](https://api-docs.deepseek.com/zh-cn/guides/kv_cache/).

One run at each size gives descriptive operational costs, not a statistically controlled proof of a fixed savings percentage. Cold-start concurrency, word complexity, provider routing, cache eviction and repair rates affect the result. Preserving style instructions and validation does not make stochastic model outputs identical word for word.

## Recorded run: 2026-11-02

The v0.3.0-based reordered requests were checked with 184 passing regression tests before paid execution. The twelve batches ran sequentially from 19:09 to 19:34 Beijing time (off-peak), with default concurrency four inside each batch. All 244 requested cards were attempted; 217 passed existing checks. Every stored successful card retained the exact original eleven prompt hashes. No Anki writes were made.

| Language | Mode | Submitted | Passed | Known total CNY | CNY/submitted word | Input cache hit |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| English | Knowledge | 1 | 1 | 0.0483 | 0.0483 | 33.4% |
| English | Knowledge | 10 | 9 | 0.2406 | 0.0241 | 76.5% |
| English | Knowledge | 50 | 48 | 0.7257 | 0.0145 | 93.9% |
| English | AI search | 1 | 1 | 0.0578 | 0.0578 | 33.2% |
| English | AI search | 10 | 7 | 0.2965 | 0.0297 | 77.4% |
| English | AI search | 50 | 44 | 1.0775 | 0.0215 | 90.8% |
| Japanese | Knowledge | 1 | 0 | 0.0369 | 0.0369 | 66.1% |
| Japanese | Knowledge | 10 | 9 | 0.2733 | 0.0273 | 78.3% |
| Japanese | Knowledge | 50 | 47 | 0.8986 | 0.0180 | 92.9% |
| Japanese | AI search | 1 | 1 | 0.0572 | 0.0572 | 0.0% |
| Japanese | AI search | 10 | 9 | 0.3620 | 0.0362 | 74.2% |
| Japanese | AI search | 50 | 41 | 1.4225 | 0.0285 | 86.7% |

Known usage totals: **15,183,042 tokens**, **121 successful searches**, **CNY 5.4971** at the run-time off-peak tariff. One call had an unknown-usage exception; the result is not an exact account-balance reconciliation. Costs include known failed and repaired calls. The zero-success one-word Japanese knowledge result is a paid failed attempt, not the price of a successful card.

For the 50-word batches, the cost including failures divided by successfully generated cards was CNY **0.0151** (English knowledge), **0.0245** (English search), **0.0191** (Japanese knowledge), **0.0347** (Japanese search). Cache hit rates were 86.7–93.9%. The savings across sizes also reflect word complexity and repair rates; this is not a paired before/after causal experiment.

Content and style constraints were not relaxed. Many failures were existing selective-bold/JSON checks that still failed after automatic repair. Full local usage records, error details and generated samples are kept under the ignored `output/cache-prefix-batches-20261102/` directory; they are not distributed as application data. Use the two profiling scripts to reproduce the method with a new output directory and current prices.
