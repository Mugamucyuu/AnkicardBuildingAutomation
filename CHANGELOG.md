# Changelog

## 0.2.0

- Add a Windows x64 desktop application and single Setup executable. Bundle Python and the offline WebView2 runtime installer; keep the existing interface and features.
- Automatically start a loopback-only service on a free port, focus an existing desktop instance, confirm exit during active work and stop the owned service on exit or host failure.
- Preserve user data outside the installation directory through upgrades and uninstall. Retain the browser UI and command-line entry points.
- Add pinned Windows build dependencies, bundled dependency licenses, installer lifecycle checks and a GitHub Actions installer/release workflow.
- Include the latest local functionality: configurable word concurrency, batch Anki import, prompt transparency/validation controls and improved image selection. See the configuration and prompt documentation.

## 0.1.1

- Use UTF-8 CLI output on Windows regardless of the system/redirected stream code page. Prevent status printing from turning a successful generation or import into a reported failure.
- Add a subprocess regression test using a legacy ANSI output encoding.

## 0.1.0

Initial public release.

- Local web UI in Chinese, Japanese and English, with light/dark themes.
- Batch input from text or TXT/MD, three grounding modes, and DeepSeek/OpenAI adapters.
- Type-isolated prompt upload, replacement, snapshots and supplemental instructions.
- Dynamic Anki tag catalog and collapsible tag explorer.
- Public pronunciation, Japanese pitch accent, phonetic Hangul and sense-aware image selection.
- Persistent jobs, reviewable previews, retry recovery and additive Anki import.
- Automatic dedicated note type and destination deck creation for fresh collections.
- Installable Python package, bundled resources, portable user state and cross-platform CI.
