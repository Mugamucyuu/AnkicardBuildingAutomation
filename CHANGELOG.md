# Changelog

## Unreleased

- Content and tag repair requests now include the latest complete draft and precise validation feedback, with instructions to preserve unaffected fields. Keep all style/content checks and the original three-attempt limits; retain failed drafts and per-attempt errors in local diagnostics.
- Move the unchanged tag catalog before per-word data in generation and tag-audit JSON requests, allowing a batch to reuse longer DeepSeek cache prefixes. Keep prompts, output schemas, proposal handling and all validation/repair rules intact.
- Add request-equivalence regression tests and an opt-in paid benchmark for sequential en/ja × knowledge/search × 1/10/50-word batches, with batch-level cache isolation and explicit failure-cost accounting.

## 0.3.0

- Added current/latest version display, optional startup update checks and one-click Windows updates with checksum verification, a local-data backup and automatic relaunch.
- Setup detects the previous installation directory and rejects detected downgrades. Data schema versioning migrates 0.2.x data additively after a verified backup.
- Added real cross-version installer/helper/relaunch and data-preservation checks, including PowerShell environment isolation.

- Added four coordinated palettes (Paper & ink, Paper & moss, Soft iris, Graphite), each with light/dark/system appearance, bundled offline fonts and persistent preferences.
- Added an in-app plain-text prompt editor with new documents, native undo/redo, Ctrl/Cmd+S, imports, versioned saves, explicit activation and custom-version deletion.
- Preserved shipped prompt originals and job snapshots; active-version deletion restores the stage default. Added dirty-draft warnings and stale-file checks.
- Kept the existing Anki connection/tag error recovery fix from the latest local workbench.
- Added real-browser workflow checks and font provenance/license verification; refreshed installer and contributor/user documentation.

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
