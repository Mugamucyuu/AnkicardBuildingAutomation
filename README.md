# Ankicard Building Automation

[![CI](https://github.com/Mugamucyuu/AnkicardBuildingAutomation/actions/workflows/ci.yml/badge.svg)](https://github.com/Mugamucyuu/AnkicardBuildingAutomation/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

A local vocabulary workbench for **English, Japanese and Korean**. Generate structured learning cards, look up public pronunciation/media, review the result and import it into Anki.

**Version 0.1.0 · Alpha.** Chinese, Japanese and English interface. [简体中文指南](docs/README.zh-CN.md) · [Configuration](docs/configuration.md) · [Architecture](docs/architecture.md) · [Changelog](CHANGELOG.md)

## Features

- Batch vocabulary from direct input, UTF-8 TXT/MD uploads or saved lists. Spaces inside phrases are preserved.
- Three explanation modes: model knowledge, model-planned web research, or one/more selected dictionaries.
- DeepSeek and OpenAI adapters with configurable model IDs. Card explanations use English for English, Japanese for Japanese and Simplified Chinese for Korean.
- Separately managed prompt types: generation, three language styles, search/image planning, tag policy, auditing and repair. Upload TXT/MD replacements or append an explicitly selected supplement.
- English hierarchical tags merged from the starter catalog and your actual Anki tags. Required POS and Japanese/Korean origin checks, with review for proposed tags.
- Public pronunciation/audio, Kanjium → OJAD → U-biq Japanese pitch, Korean phonetic Hangul and sense-aware Commons images. Missing/uncertain media stays absent and is reported.
- Light/dark card previews, source attribution, persistent jobs, retry recovery and automatic or reviewed import.
- Collapsible Anki tag explorer with AND/OR filtering in Anki's browser.

## Requirements

- **Python 3.10+** and a modern browser. Runtime application code has no third-party Python dependencies.
- For Anki import: desktop **Anki with AnkiConnect API v6 enabled and running**. Anki's installation drive does not matter. AnkiWeb and mobile Anki alone cannot provide the local API.
- For live generation: a provider API key, access to a supported model ID, internet connectivity and available API credit. Research currently uses DeepSeek Search, including when OpenAI generates the card.

## Install and run

```sh
git clone https://github.com/Mugamucyuu/AnkicardBuildingAutomation.git
cd AnkicardBuildingAutomation
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```sh
# macOS / Linux
source .venv/bin/activate
```

Install and launch:

```sh
python -m pip install .
ankicard
```

The application opens **http://127.0.0.1:8877**. If automatic opening is unavailable, visit that address yourself. Use `ankicard --no-browser --port 8878` to change the port. `python -m vocab_app` also starts the installed UI. From a source checkout, `python run_ui.py` works without installation.

### Try without an API key or Anki

Click **Try offline demo**, then **Generate cards**. Change vocabulary language to try `apple`, `猫` or `나무`. These are shipped fixtures: no paid/network calls and no Anki writes. Other words require live generation.

### Connect Anki

1. In Anki, open **Tools → Add-ons → Get Add-ons** and enter **2055492159** ([AnkiConnect](https://ankiweb.net/shared/info/2055492159)). Restart Anki and keep it running.
2. In the web UI, click **Connect Anki**.
3. Choose an existing destination deck or enter a new deck name. Set your provider/model/key in **Settings**.
4. Enter words, choose a generation mode and generate previews. Review them and click **Import into Anki**, or explicitly enable automatic import.

**No pre-existing vocabulary, tags, decks or `AI-note` type is required.** An empty collection uses the bundled starter tags. On import, the application creates the destination deck if missing and provisions its own `Ankicard Vocabulary v1` note type. A conflicting incompatible note type is left untouched and a separate suffixed type is used. Existing notes, templates, decks, tags and review history are not migrated or overwritten. Normal Anki duplicate checks are enabled; they are note-type scoped.

Back up your collection through Anki before extensive imports. AnkiConnect permission, editor locks, provider/network errors or unavailable external entries can still require user action; a failure is shown rather than silently changing generation mode.

## Generation and sources

| Mode | Behavior |
| --- | --- |
| Independent | AI explanations use model knowledge. Optional public media lookup remains separate. |
| AI web search | The model plans the query; DeepSeek Search supplies evidence; explanations cite supplied source IDs. |
| Selected dictionaries | Use only selected registered domains/entries as evidence. Multiple choices are supported. |

Registered explanation sources include Wiktionary (all languages); Etymonline, Cambridge, Merriam-Webster, Oxford, Longman and Free Dictionary API (English); Kotobank (Japanese); Korean Basic Dictionary and Daum (Korean). Wiktionary and Free Dictionary API support direct entry retrieval; others use domain-restricted search excerpts, not complete per-site scraping adapters. Coverage and publisher availability vary.

Audio/source selection is separate from explanation grounding. Images are selected by word sense and public metadata; ambiguous or unsupported matches may be skipped. Generated learning content and automatic semantic matches require review.

## Configuration and private data

Keys entered through Settings remain only in the local server process environment. They are not persisted in preferences/jobs/browser storage; re-enter after restart or supply process environment variables. The reference `.env.example` is **not automatically loaded**.

Writable state lives outside the installation:

- Windows: `%LOCALAPPDATA%\AnkicardBuildingAutomation`
- macOS/Linux: `$XDG_DATA_HOME/AnkicardBuildingAutomation`, or `~/.local/share/AnkicardBuildingAutomation`
- Override with `ANKICARD_DATA_DIR`.

This directory holds preferences, prompt versions/bindings, tag descriptions, jobs, media and previews. Place personal saved TXT/MD lists in its `vocabulary/` folder. Bundled examples are generic. See [configuration](docs/configuration.md) and [security/privacy](SECURITY.md), including what is sent to model/search providers during live generation.

## Command-line use

```sh
# Offline preview
ankicard-import --language ja --word 猫 --output-dir previews

# Live preview; set DEEPSEEK_API_KEY in the process first
ankicard-import --live --provider deepseek --model deepseek-flash --language en --word peninsula

# Import an existing reviewed live JSON; the named deck is created if missing
ankicard-import --import-anki --import-preview previews/card.json --deck English
```

Replace example model IDs with IDs available to your account. `ankicard-import --help` lists media/mode/source options. Source-checkout equivalent: `python run_import.py ...`. An explicit `--note-type AI-note` supports older compatible `正面/背面/笔记` types; the default uses the new dedicated English field names.

## Development and testing

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python tools/audit_release.py
```

Automated tests use fixtures, fake providers/collections and temporary localhost services. No real model keys or personal Anki collection are needed. CI covers Windows, macOS and Linux with Python 3.10/3.12/3.13 and builds installable distributions. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Current limits

- A batch has one vocabulary language; execution is currently serial.
- TXT/MD input only; no PDF/Word/OCR parser.
- Tag combinations open the Anki browser; automatic filtered-deck creation/review is not implemented.
- No automatic migration of old collections or bulk rewriting of existing cards.
- Public sites and model APIs can fail, rate-limit or change. The software cannot guarantee a recording/image/evidence hit for every word.
- This is a local single-user tool; keep its port private.

## License

Application code: [MIT](LICENSE). Bundled Kanjium pitch data: **CC BY-SA 4.0**, with attribution and full license preserved. External media and dictionary material retain their own terms. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
