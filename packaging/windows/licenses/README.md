# License provenance

These files preserve third-party license texts for the Windows distribution.
They do not change the application's MIT license.

- `proxy_tools.txt`: unchanged `LICENSE.txt` from `jtushman/proxy_tools` on GitHub. The 0.1.0 wheel omits this file. Source attribution identifies BSD despite MIT in wheel metadata.
- `webview2-sdk.txt`: `LICENSE.txt` from Microsoft's NuGet package `Microsoft.Web.WebView2` **1.0.2957.106**, matching the assemblies in pywebview 6.1. Source: `https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/1.0.2957.106/microsoft.web.webview2.1.0.2957.106.nupkg`.
- `openssl.txt`: OpenSSL **3.6.5**, `LICENSE.txt`, Apache 2.0.
- `libffi.txt`: libffi **3.7.0**, `LICENSE`.
- `bzip2.txt`: bzip2 **1.0.8**, `LICENSE`.
- `expat.txt`: Expat **2.8.5**, `COPYING`.
- `xz.txt`, `xz-0bsd.txt`: liblzma/XZ **5.8.3**, `COPYING` and `COPYING.0BSD`.
- `zlib.txt`: zlib **1.3.2**, `LICENSE`.
- `msvc-runtime.docx`, `msvc-runtime.txt`: Microsoft VC runtime **14.51.36247** license; the DOCX is the original supplied by the distributor, the TXT is its convenience conversion.
- `windows-ucrt.txt`: Microsoft UCRT **10.0.26100.0** SDK runtime distribution terms.

Native runtime license files above were copied unchanged from the matching conda-forge package `info/licenses` directories used by the local CPython 3.12.15 build. CI may use python.org runtime builds with different library versions; the CPython license from that build is also included, and maintainers should review native dependency notices when changing the build interpreter.

All TXT files are appended to `THIRD_PARTY_LICENSES.txt` during build. The complete directory is also shipped at `_internal/licenses/`. Python package license texts and the CPython license are collected directly from the active build environment, rather than duplicated here. Microsoft WebView2 Evergreen Runtime remains a separate, unmodified, Microsoft-signed installer with Microsoft's own terms.
