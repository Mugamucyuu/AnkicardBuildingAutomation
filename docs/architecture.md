# Architecture

```text
vocab_app/
  ui_server.py      localhost HTTP boundary and request protection
  ui_service.py     persistent jobs, settings and reviewed import
  cli.py            offline/live CLI
  pipeline.py       media → research → generation → quality → tag audit
  providers.py      DeepSeek/OpenAI request adapters
  prompts.py        typed prompt files and immutable batch snapshots
  taxonomy.py       starter + live Anki tag catalog, validation and proposals
  anki.py           additive deck/note-type setup, media upload and note import
  preview.py        escaped light/dark HTML and native Anki media markup
  *_media.py        source-specific public pronunciation adapters
  japanese_pitch.py local Kanjium and OJAD/U-biq fallback
  image_selection.py sense-grounded public image candidate validation/ranking
  web/              local HTML/CSS/JavaScript interface
  resources/        shipped prompts, taxonomy, demo examples and licensed data
tests/              deterministic unit/integration tests with fake collections
tools/              portable developer/release checks
```

Source resources are read-only. Writable state is selected by `user_data_dir()` and kept outside the installed package. UI and CLI reuse the same pipeline and Anki boundary. Import never creates a card from an invalid generation or an offline fixture; new tags require an explicit review decision. Anki operations are additive and existing note types are not rewritten.

Public sources are untrusted input. Model prose is rendered through a small escaping formatter; downloaded assets use host/type/path constraints. Batch snapshots retain prompt hashes, source references and tag reasons. Errors never include HTTP authorization headers or response bodies. All paid requests require a live provider selection and usable credentials.

The local service is single-user. It processes batches serially and serializes imports. The repository's CI verifies fake empty/populated/conflicting collections and builds a distribution; real provider/website coverage remains dependent on external services.
