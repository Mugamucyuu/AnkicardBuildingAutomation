# Third-party notices

Application source code is licensed under MIT. That license does not relicense third-party data or externally downloaded media.

## Bundled Kanjium pitch accent data

- Source: [mifunetoshiro/kanjium](https://github.com/mifunetoshiro/kanjium), revision `685d4d723d6d20bf9beb169103aeac188eb067ad`.
- File: `vocab_app/resources/data/pronunciation/kanjium/accents.tsv`, an unchanged copy of upstream `accents.txt`.
- License: **CC BY-SA 4.0**, with the full text in the same directory's `LICENSE.txt`.
- Attribution: The pitch accent notation was provided by Uros O. through the free Kanjium database.
- Integrity, provenance and licensing links are recorded in `metadata.json` beside the data.

## Windows desktop distribution

The Windows installer also bundles CPython, pywebview, pythonnet, clr_loader, CFFI, pycparser, bottle, proxy_tools, typing_extensions and PyInstaller's bootloader. Their available license texts and version notices are consolidated into `_internal/THIRD_PARTY_LICENSES.txt` in the installed application. PyInstaller's license includes its bootloader exception. The pywebview package contains Microsoft's WebView2 SDK assemblies and native loader; their terms are preserved at `packaging/windows/licenses/webview2-sdk.txt` and in the consolidated installed notices. Native runtime notices for OpenSSL, libffi, bzip2, Expat, XZ, zlib and the Microsoft C runtime are preserved in `_internal/licenses/`; provenance is recorded in that directory's README.

The proxy_tools 0.1.0 wheel omits its license file; the unchanged upstream [LICENSE.txt](https://github.com/jtushman/proxy_tools/blob/master/LICENSE.txt) is retained at `packaging/windows/licenses/proxy_tools.txt`. It includes attribution to Armin Ronacher and Jonathan Tushman. Its source header identifies BSD licensing, despite the distribution metadata's MIT label.

The installer embeds the unmodified, Microsoft-signed WebView2 Evergreen Standalone Installer, obtained from Microsoft's official distribution endpoint. WebView2 remains subject to [Microsoft's runtime distribution terms](https://developer.microsoft.com/en-us/microsoft-edge/webview2/); the app's MIT license does not relicense it. The shared runtime is not removed when uninstalling Ankicard.

## External runtime sources

Wiktionary, Wikimedia Commons, OJAD, U-biq, Free Dictionary API and dictionary publishers provide material under their respective licenses/terms. The application records available source/attribution/license metadata and displays it in previews/cards. Availability, personal use, redistribution and attribution obligations vary by source. Recording a publisher-terms label is not permission to redistribute a recording. Public releases do not include downloaded dictionary audio, scraped entries or personal generated cards.
