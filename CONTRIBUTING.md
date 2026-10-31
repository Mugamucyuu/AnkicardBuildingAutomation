# Contributing

Please open an issue describing the problem or proposed change before a large refactor.

## Development

Python 3.10+ is required. The application uses the Python standard library at runtime.

```sh
python -m venv .venv
# Activate the environment for your shell.
python -m pip install -e .
python -m unittest discover -s tests -v
python tools/audit_release.py
```

Tests use fixtures, fake model responses and a temporary localhost HTTP server. They must not require API keys, paid requests, the contributor's Anki collection or private vocabulary. Run live checks separately and describe their scope in the pull request.

Keep model instructions in `vocab_app/resources/prompts/` and register new types in `vocab_app/prompts.py`. Include all three UI translations for new controls. Validate external content and preserve media attribution. Never commit local outputs, credentials, collection exports or personal word lists.

Use focused commits and explain behavior, relevant validation and limitations in pull requests. The source is MIT licensed; third-party assets retain the licenses listed in `THIRD_PARTY_NOTICES.md`.
