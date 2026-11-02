# Windows 安装版 / Windows desktop distribution

## 下载与使用

1. 从 [GitHub Releases](https://github.com/Mugamucyuu/AnkicardBuildingAutomation/releases/latest) 下载 `Ankicard-0.2.0-windows-x64-Setup.exe`。
2. 双击安装，默认安装到当前用户，无需管理员权限。桌面快捷方式默认选中。
3. 从桌面或开始菜单打开 **Ankicard**，原有界面显示在独立窗口中。

支持 Windows 10 1809+ 和 Windows 11 的 x64 系统；原生 ARM64、32 位 Windows、macOS 和 Linux 安装包不在本次发布范围。源码 / 浏览器版仍支持原有平台。

安装包含 Python、应用代码、默认提示词、词汇示例、声调数据，以及 Microsoft WebView2 的完整离线安装组件。缺少 WebView2 时，安装程序会自动安装；不需要用户自行配置 Python、环境变量、端口或 localhost。完整运行时让安装包体积较大。安装和离线演示不要求网络；真实制卡与公开媒体查询仍需联网。

界面及功能沿用当前本地版。模型 API key 仍在原有设置中填写；导入仍需安装桌面 Anki 和 AnkiConnect，并保持 Anki 运行。安装程序不会安装或修改 Anki，也不会替用户申请模型账号。密钥沿用现有策略，仅在本次进程中有效，退出后需重新填写。

本版本尚未购买代码签名证书，安装包与应用程序未签名。Windows 可能显示未知发布者或下载信誉提示。下载页同时提供 `SHA256SUMS.txt` 供校验。内含的微软运行时保留微软原始数字签名；构建时验证其签名。

## 退出、升级与卸载

- 再次打开同一数据目录的桌面应用时，激活已有窗口，不重复启动服务。
- 软件自动选择可用的内部端口，只监听本机；无需访问浏览器地址。
- 关闭窗口即停止对应后台服务。正在生成、批量导入或写入 Anki 时会弹出退出确认。确认退出后，当前网络请求会被中止；下次打开可重试未完成项目。已发出的模型请求可能已经产生费用。
- 若导入时退出，已有逻辑会在下次启动标记结果待确认；重试时先按 run ID 核对 Anki，避免盲目重复导入。
- 更新前关闭程序，然后运行新版安装包，使用相同安装目录。首版采用手动下载升级，不含自动更新器。
- 从 Windows“已安装的应用”卸载。不会删除 Anki 内容，也不会删除用户数据或共享的 WebView2。

现有用户数据默认在 `%LOCALAPPDATA%\AnkicardBuildingAutomation`，安装位置默认在 `%LOCALAPPDATA%\Programs\Ankicard`，两者独立。安装版直接使用相同用户数据目录，可读取已有任务、偏好与自定义提示词。高级用户仍可用 `ANKICARD_DATA_DIR` 指向其他目录。桌面与旧版浏览器服务不要同时操作同一数据目录。

## Build from source

These instructions are for maintainers. End users only need the Setup executable.

Use **CPython 3.12 x64 on Windows**, PowerShell, Git and network access. Build in a clean virtual environment so unrelated GUI/tooling packages cannot enter the bundle.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r packaging/windows/requirements-build.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
powershell -ExecutionPolicy Bypass -File tools/prepare_windows_toolchain.ps1
powershell -ExecutionPolicy Bypass -File tools/build_windows.ps1 `
  -Python .\.venv\Scripts\python.exe `
  -Iscc output/toolchain/inno/ISCC.exe `
  -WebViewInstaller output/toolchain/MicrosoftEdgeWebView2RuntimeInstallerX64.exe
.\.venv\Scripts\python.exe tools/check_desktop.py dist/Ankicard/Ankicard.exe
powershell -ExecutionPolicy Bypass -File tools/check_windows_installer.ps1 `
  -Python .\.venv\Scripts\python.exe `
  -Installer dist/windows/Ankicard-0.2.0-windows-x64-Setup.exe
```

`prepare_windows_toolchain.ps1` obtains Inno Setup 7.1.1 from its official GitHub release, checks its pinned SHA-256 and signature, and installs the compiler in `output/toolchain/inno`. It downloads the x64 WebView2 Evergreen Standalone Installer from Microsoft's distribution link and checks its Microsoft signature. This shared runtime updates independently; rebuilding later can produce different bytes. Build dependencies and the compiler are pinned, but the result is not claimed to be bit-for-bit reproducible.

`build_windows.ps1` generates Windows version resources and consolidated dependency licenses, builds a windowed PyInstaller one-folder application, then wraps it with Inno Setup into one downloadable installer. It packages only selected application resources, never the local state directory. Outputs:

- `dist/Ankicard/`: self-contained application, including Python.
- `dist/windows/Ankicard-0.2.0-windows-x64-Setup.exe`: distributable installer.
- `dist/windows/SHA256SUMS.txt`: installer checksum.
- `dist/windows/BUILD-INFO.json`: application/source revision and compiler/runtime provenance (no local paths or credentials).

The editable icon source is `tools/generate_windows_icon.ps1`; run it to regenerate `packaging/windows/ankicard.ico`. Dependency license fallbacks live in `packaging/windows/licenses/`, with provenance in the third-party notices. The installer is Windows-specific and is not included in the runtime requirements of the browser edition.

## Verification and release

`tests/test_desktop.py` checks the single-instance lock, free-port startup, unchanged API boundary, normal shutdown and worker exit after host failure. The core suite covers the existing application behavior.

`tools/check_desktop.py` runs the actual frozen WebView2 window in a clean working directory and strips Python from PATH. It checks the existing page, all eleven prompt stages, offline previews in three languages, and that both the worker process and port are closed on exit. It does not use model keys or the real Anki collection.

`tools/check_windows_installer.ps1` installs into a disposable directory, verifies the installed desktop app, reinstalls to exercise manual upgrade, verifies previous generated jobs still exist, uninstalls, and checks user data is retained. It creates a temporary Windows uninstall entry and removes it on completion. Run it on a build/test machine where Ankicard is not already installed.

The GitHub Actions Windows workflow builds and verifies installers for pushes/PRs. A version tag matching `vocab_app.__version__` publishes the verified installer and checksum as GitHub Release assets. The regular CI continues testing the core/browser edition on Windows, macOS and Linux and building wheel/sdist packages.

Current local verification uses the available Windows machine with WebView2 already installed. The branch that installs WebView2 on a machine without it follows [Microsoft's documented offline deployment and registry detection](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution); a separate clean Windows VM test is still recommended before broad distribution.
