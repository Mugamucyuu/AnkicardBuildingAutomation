# Security and privacy

The UI binds to `127.0.0.1` only. Request-origin, host and per-process token checks protect API mutations. This is a single-user local application, not a public multi-user service; do not expose the port to a network or put it behind a public proxy.

The Windows desktop shell uses the same boundary on an automatically selected port. It exposes no application JavaScript-to-Python API, starts a separate owned worker and stops it when the window closes or the host process exits. Do not run the desktop and browser editions simultaneously against the same data directory. Installer builds package selected source assets only; private state and credentials are excluded. The installer checks for WebView2 and installs the bundled Microsoft-signed runtime only if missing. Application/installer code signing is not yet configured.

Model/search keys entered through Settings stay in the service process environment. They are not written into preferences, jobs, browser storage or logs. Restarting the service requires re-entry unless keys are supplied through environment variables. AnkiConnect API keys may be supplied through `ANKICONNECT_API_KEY`.

Live generation sends the selected word, prompt files, allowed tag names/descriptions and source excerpts to the selected model provider. Web research also sends search terms to the configured search provider. Public media lookup contacts dictionary/media sites even when explanations use independent mode. Your tag structure may therefore be included in a live model request. Offline demos do not call these services and cannot be imported into Anki.

User state contains generated learning material, tag snapshots and import receipts. Keep that directory private. The repository ignores outputs, local vocabulary, credentials and Anki exports. Repository audits supplement review; no pattern scanner can prove that arbitrary user-authored text is free of personal information.

Report vulnerabilities through GitHub's private vulnerability reporting if available. Otherwise, open an issue requesting a private reporting channel without publishing secrets, personal collection data or exploit details. Revoke any credential that has been publicly disclosed.
