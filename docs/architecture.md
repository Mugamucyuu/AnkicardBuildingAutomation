# Architecture

```text
vocab_app/
  desktop.py        Windows window, single-instance lock and owned worker lifecycle
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
packaging/windows/  pinned build dependencies, PyInstaller spec, Inno Setup script and icon
```

Source resources are read-only. Writable state is selected by `user_data_dir()` and kept outside the installed package. UI and CLI reuse the same pipeline and Anki boundary. Import never creates a card from an invalid generation or an offline fixture; new tags require an explicit review decision. Anki operations are additive and existing note types are not rewritten.

The optional Windows desktop host uses pywebview/EdgeChromium to load the existing HTML/CSS/JavaScript unchanged. An OS-held file lock scopes it to one desktop instance per data directory. A separate worker serves the original HTTP API on an automatically allocated loopback port, with the same host/origin/token checks. The host signals the worker to exit on close; the worker also watches the host process handle to avoid orphan services after a crash. Persisted job recovery remains in UIService. The installer embeds Python and a signed offline WebView2 installer, keeps state outside the installation and preserves it on upgrade/uninstall. See [Windows distribution](windows.md).

Public sources are untrusted input. Model prose is rendered through a small escaping formatter; downloaded assets use host/type/path constraints. Batch snapshots retain prompt hashes, source references and tag reasons. Errors never include HTTP authorization headers or response bodies. All paid requests require a live provider selection and usable credentials.

The local service is single-user. Batches queue serially; each batch uses a bounded word executor (default 4, range 1–32), with separate clients, catalog copies and media staging per word. Imports remain serial. Batch import runs in the background, persists counts and reuses individual import validation and run-ID recovery; its explicit new-tag approval covers the whole batch. Interrupted imports can be resumed without regenerating cards. The repository's CI verifies fake empty/populated/conflicting collections and builds a distribution; real provider/website coverage remains dependent on external services.
