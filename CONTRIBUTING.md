# Contributing

Please open an issue describing the problem or proposed change before a large refactor.

## Development

Python 3.10+ is required for the core/browser edition, which uses the standard library at runtime. The optional Windows desktop shell uses pywebview; installer builds use CPython 3.12 x64 and the pinned toolchain described in [Windows distribution](docs/windows.md).

```sh
python -m venv .venv
# Activate the environment for your shell.
python -m pip install -e .
python -m unittest discover -s tests -v
python tools/audit_release.py
```

Tests use fixtures, fake model responses and a temporary localhost HTTP server. They must not require API keys, paid requests, the contributor's Anki collection or private vocabulary. Run live checks separately and describe their scope in the pull request.

For browser UI changes, run the real-browser check (Node.js 22+, Python and Edge
on Windows). It creates isolated state/screenshots under `output/ui-check-*`:

```sh
npm install --prefix output/browser-check --no-save --ignore-scripts playwright@1.62.1
node tools/check_web_ui.cjs
```

Set `UI_TEST_PYTHON` if Python is not available as `python`. On other platforms,
install Chromium with `output/browser-check/node_modules/.bin/playwright install chromium`.
The check covers appearance persistence, all palettes, prompt editing/import/deletion,
unsaved drafts, snapshot isolation and responsive layouts; external page requests
are blocked. Windows installer CI runs it before packaging.

Keep fonts local and retain upstream OFL notices. `tools/vendor_fonts.py` fetches
the pinned originals; source URLs/hashes are in `vocab_app/web/fonts/sources.json`.
The core application has no Node.js runtime requirement.

Keep model instructions in `vocab_app/resources/prompts/` and register new types in `vocab_app/prompts.py`. Include all three UI translations for new controls. Validate external content and preserve media attribution. Never commit local outputs, credentials, collection exports or personal word lists.

Use focused commits and explain behavior, relevant validation and limitations in pull requests. The source is MIT licensed; third-party assets retain the licenses listed in `THIRD_PARTY_NOTICES.md`.
