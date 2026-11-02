# Versions, updates and data compatibility

## 使用方式

在「设置 → 版本与更新」查看当前版本、最新发布版本和检查时间。Windows 安装版
默认在启动时检查官方稳定版，也可随时点「检查更新」。可以在设置中关闭启动检查；
检查更新不会自动下载安装。

点「一键更新」后，应用下载完整安装包、核对 SHA-256，随后备份数据，关闭自身与
本地服务、原位安装，再重新打开。下载期间可继续使用；安装时必须没有生成、导入
任务在执行。未保存的提示词会先提醒。暂时不能安装时，稍后点「安装并重启应用」。

直接运行新版安装包也可以升级：它根据固定应用 ID 找到同一 Windows 用户的旧安装，
自动沿用原目录和快捷方式选择。0.3.0 及之后的安装包拒绝覆盖检测到的更新版本；
相同版本允许修复安装，无需先卸载。**0.2.0 尚无内置更新按钮，首次升级到 0.3.0
需要运行新版安装包，之后即可使用应用内更新。**

断网、GitHub 暂不可用、限流、校验失败或空间不足时，可重试，当前版本仍可使用。
下载取消或失败不会修改安装文件。需要能访问 GitHub 官方 Release 及其附件服务。
一键安装仅用于 Windows 安装版，源码/浏览器用户可查看版本并通过发布页更新。

## 数据与备份

安装目录与用户数据目录分离。默认数据目录为 Windows
`%LOCALAPPDATA%\AnkicardBuildingAutomation`，或 `ANKICARD_DATA_DIR` 指定的目录。
设置、提示词版本及绑定、个人词库、标签元数据、历史任务、快照与媒体都保留。
卸载不会清除该目录。

- `data-version.json`：独立的数据格式版本及最后使用的应用版本。
- `backups/<UTC timestamp>-<id>.zip`：升级/迁移前的数据快照，含设置、提示词、
  词库、标签元数据、任务、媒体和数据版本文件。
- `updates/<version>/`：已下载的安装包，完整下载并校验后才可安装。
- `updates/last-result.json`：上次安装结果；`updates/handoff-*/installer.log`：安装日志。

0.2.x 的未标记数据迁移为格式版本 1：先备份，再添加数据版本文件，保留旧字段和
内容。新增设置使用默认值，原明暗模式等继续生效。同一版本重复启动不重复迁移。
应用发现超出自身支持的数据格式时会停止，避免写坏新格式。旧版 0.2.0 本身没有
这项保护，不应重新运行旧安装包或旧可执行程序来降级。

备份只保存在本地；缓存、下载的安装包和之前的备份不嵌套备份。备份失败会停止更新。
安装失败不会自动用旧备份覆盖数据，以免丢弃更新后产生的内容；可重试或运行最新版
安装包修复。需要恢复时，先关闭应用，保留当前数据目录的副本，将选定 ZIP 解压到
新目录，用 `ANKICARD_DATA_DIR` 指向该目录检查后使用。不要覆盖运行中的数据目录。

备份不包含 Anki collection；集合备份由 Anki 管理。API 密钥仍只保存在进程内存中，
更新重启后需重新输入或由环境变量提供。

## Engineering contract

- The update source is the fixed repository's latest public stable Release. Tags, exact asset
  names and repository URLs are validated; older/equal versions never auto-install.
- Downloads use HTTPS, restricted redirect hosts, bounded sizes, temporary files,
  `SHA256SUMS.txt` and GitHub's asset digest when supplied. Checksums must agree. Bytes
  are rechecked before handoff and immediately before running Setup.
- Installation is explicit and token-protected, rejects active tasks and freezes other HTTP
  writes during backup/shutdown. Existing job snapshots remain independent.
- The desktop closes only after a helper outside the installation directory signals readiness.
  It waits for app/worker process handles, runs Setup without force-closing other applications,
  verifies the installed version and relaunches. PowerShell modules come from Windows itself.
- Migrations run before recovery writes. Backups are CRC-verified and metadata is replaced
  atomically. Failed backup/migration does not overwrite the old data format.
- Application/installer code signing is not configured. HTTPS and checksums protect transfer
  integrity but are not an independent signing identity if the release account is compromised.
- No delta patches, telemetry, automatic downloads or installation without a user update action.

## Verification

`tests/test_updates.py` covers origin/version checks, cancellation, offline errors, tampering,
disk-full/backup failures, active-task protection and migration preservation with local fixtures.
HTTP tests cover CSRF/write freezing. The real-browser check stubs update responses only for
the update-button sequence; all theme/editor requests use the real local service.

`tools/check_windows_installer.ps1` exercises real Setup, download verification, backup, helper,
native relaunch, old-directory detection, downgrade rejection, uninstall and retained data.
Pass `-PreviousInstaller <0.3.0 Setup>` for cross-version migration. Its release transport points
at the local freshly built installer, so no unpublished release or paid service is needed.
It refuses to run over an existing registered user installation.

## 0.4.0 recovery

Interrupted generation appears as paused on the next launch. Choose Resume generation after re-entering credentials. Ready/imported cards are retained; saved completed stages are reused with the original job snapshots. Pending network requests may already have been billed and may need repeating. Interrupted imports are reconciled using their saved run IDs.

## Original 0.3.0 upgrade limitation

The 0.3.0 native FormClosing handler synchronously evaluates JavaScript on the renderer thread. This can deadlock both title-bar exit and the automatic update shutdown. The fix ships in 0.4.0; publishing new assets cannot patch an already installed old process. If its update install stalls, end that old process and run 0.4.0 Setup once. Setup discovers its original installation and preserves user state. Do not describe the local helper fixture as proof of the original application's end-to-end one-click update.

`tools/check_published_update.py <disposable-installed-exe> --state-directory <isolated-output-dir> --install` drives the installed binary's own official release check, verified download, install request and native update watcher. It records stalled shutdown as a failure. Both paths must be under the repository's `output` directory; use only a disposable installation.

The original published 0.3.0 binary was tested against public 0.4.0 release metadata and the verified official cached installer. Discovery and installer verification passed; native shutdown stalled at `install_requested`. Manual Setup then reused the old directory and retained data. The original-to-original results and download/cache boundaries are recorded in [0.4.0 verification](releases/0.4.0-verification.md).
