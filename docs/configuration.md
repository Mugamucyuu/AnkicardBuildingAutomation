# Configuration

Prompt instructions, content checks and feedback are documented in the [complete prompt inventory](prompts.md). The UI offers assembled-instruction previews and per-word actual model requests. New live jobs store their provider JSON request bodies under `jobs/<job-id>/requests/<word-index>/`; these records contain vocabulary, tags and research text, so keep them private. Authentication headers and API credentials are excluded. Older jobs without request records are identified explicitly.

The UI runs on `http://127.0.0.1:8877` by default. `ankicard --help` documents launch options.

The Windows desktop installer starts the same UI in its own window, selects a free internal port automatically and stops its service when the window closes. No address or port configuration is needed. Its data directory and credential policy are the same as the browser edition. See [Windows installation](windows.md).

| Environment variable | Purpose |
| --- | --- |
| `ANKICARD_DATA_DIR` | Writable state directory; independent of package/source location. |
| `ANKI_AI_PROVIDER` | Default provider: `deepseek` or `openai`. |
| `DEEPSEEK_MODEL`, `OPENAI_MODEL` | Model IDs supported by your provider account. |
| `DEEPSEEK_API_KEY`, `OPENAI_API_KEY` | Live generation credentials. UI-entered values are process-only. |
| `DEEPSEEK_SEARCH_API_KEY` | Optional separate search key; otherwise DeepSeek generation key is used for search. |
| `ANKICONNECT_URL` | AnkiConnect endpoint; default `http://127.0.0.1:8765`. |
| `ANKICONNECT_API_KEY` | Optional key matching AnkiConnect's configured API key. |

`.env.example` is a reference, not an auto-loaded credential file. Use your shell's environment mechanism or the UI. Avoid putting actual keys in terminal commands saved to shell history. API keys are never returned to the browser after submission.

## User data

The default is `%LOCALAPPDATA%\AnkicardBuildingAutomation` on Windows, and `$XDG_DATA_HOME/AnkicardBuildingAutomation` (fallback `~/.local/share/AnkicardBuildingAutomation`) elsewhere. The directory contains:

- `settings.json`: public preferences only.
- `prompts/`: typed prompt uploads, versioned files and bindings.
- `vocabulary/`: optional personal saved TXT/MD lists.
- `tag_metadata.json`: optional descriptions of actual Anki tags.
- `jobs/`: generated JSON/HTML, downloaded media, prompt/tag snapshots and import receipts.

Each job fixes its prompt/catalog snapshot. Stops affect subsequent words; an already-sent model request may complete. Restarts retain results and mark unfinished generation for manual retry. Uncertain imports are reconciled using the unique run ID before trying another add. Offline fixtures cannot be imported.

## Parallel generation and batch import

The generation form accepts **1–32** concurrent words, default **4**. Save a default in Settings, or override it for one batch; running jobs retain their saved value. This is a conservative local default rather than a provider quota. [DeepSeek's concurrency limits](https://api-docs.deepseek.com/quick_start/rate_limit/) apply to the entire provider account; search and media services may have separate limits. Choose 1 for serial generation or lower the value if sources are throttled. Batches queue in order, so their concurrency does not multiply. Stop prevents queued words from starting; in-flight words may finish.

After a batch stops or completes, choose its destination deck in Activity and click **Import all into Anki**. If there are proposed tags, **Approve new tags & import all** approves them together; schema and tag validation still apply. Imports run serially in the background and show imported, failed and skipped counts. Failures do not stop later cards. Already imported cards and unsuccessful generations are skipped; use the button again to retry remaining imports without regeneration. After a restart, interrupted imports reconcile their run IDs before adding anything. Offline demo cards cannot be imported.

Custom metadata example:

```json
{"tags":{"domain::nature::plants::trees":{"definition_zh":"树木名称","languages":["en","ja","ko"]}}}
```

Metadata describes existing Anki tags; it does not create or rename them.

## Anki setup and troubleshooting

Install [AnkiConnect](https://ankiweb.net/shared/info/2055492159), restart desktop Anki and keep the main window open. Backend calls originate from the Python service, so the browser does not need direct cross-origin access to AnkiConnect. If an API key is configured in the add-on, set the matching environment variable before launching the application. Custom ports use `ANKICONNECT_URL`.

The first import automatically provisions the named deck and the application note type. It does not alter incompatible existing types. If Anki reports an editor lock, close the affected editor/browser and retry. No knowledge-only fallback is used when requested public evidence cannot be obtained.

If a model fails, check provider/model ID, API credit, network and prompt schema. Research through non-direct dictionary sources also needs a search key. Missing public audio/pictures are warnings, not invented assets. Browser previews and Anki use the same card renderer; media is uploaded and read back before adding the note.
