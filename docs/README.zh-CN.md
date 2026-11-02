# 中文使用指南

Ankicard Building Automation 是本地运行的英日韩词汇制卡工具，支持中日英界面。当前版本为 **0.2.0（Alpha）**，提供 Windows 本地安装版，保留现有界面和功能。

## 安装

### Windows 安装版（推荐）

从 [GitHub Releases](https://github.com/Mugamucyuu/AnkicardBuildingAutomation/releases/latest) 下载 `Ankicard-0.2.0-windows-x64-Setup.exe`，双击安装，然后从桌面或开始菜单打开 **Ankicard**。支持 Windows 10 1809+ / Windows 11 的 x64 系统。

无需安装 Python、配置环境、输入命令或访问 localhost。程序在独立窗口中呈现原有界面，自动启动和关闭内部服务；安装包包含 WebView2 完整安装组件，缺少时自动安装。联网生成仍需要模型密钥和额度，导入仍需要桌面 Anki 和 AnkiConnect。

更新时先退出程序，再运行新版安装包。历史数据保存在用户目录，更新和卸载均会保留。当前安装包未进行代码签名，Windows 可能提示未知发布者。详情见 [Windows 安装、升级与构建说明](windows.md)。

### 源码 / 浏览器版

需要 Python 3.10+、浏览器；导入还需要桌面 Anki 和 AnkiConnect 插件。Anki 装在哪个盘没有影响。

```sh
git clone https://github.com/Mugamucyuu/AnkicardBuildingAutomation.git
cd AnkicardBuildingAutomation
python -m venv .venv
```

Windows PowerShell 激活：`.\.venv\Scripts\Activate.ps1`。macOS/Linux 激活：`source .venv/bin/activate`。如果 PowerShell 不允许激活脚本，也可以直接用 `.\.venv\Scripts\python.exe -m pip install .` 和 `.\.venv\Scripts\python.exe -m vocab_app`。

```sh
python -m pip install .
ankicard
```

浏览器打开 `http://127.0.0.1:8877`。源码目录也能直接运行 `python run_ui.py`。遇到端口占用可使用 `ankicard --port 8878`。

## 首次使用

1. 无需密钥也能点击“体验离线演示”，再生成 apple / 猫 / 나무 的示例；不联网、不写 Anki。
2. 在 Anki 的“工具 → 插件 → 获取插件”输入 **2055492159** 安装 AnkiConnect，重启 Anki，保持主窗口开启。
3. 在界面设置中选择模型来源、填写账号可用的模型 ID 和 API key。密钥只在本地服务进程内存中，重启需重新填写；也能通过环境变量设置。
4. 连接 Anki。选择已有牌组，或直接输入新牌组名称。
5. 选择词汇语言，输入词汇或上传 UTF-8 TXT/MD。短语内空格保留，词条之间用换行、逗号或顿号分隔。
6. 选择独立生成、AI 检索或指定词典，设置同时生成词卡数（默认 4，可调 1–32；设置页可保存默认值）。生成结束后，在任务页选择本批牌组并点击「全部导入 Anki」；含新标签时按钮为「全部导入并批准新标签」，统一批准，无需逐张审核。也可逐张导入，或生成前启用自动导入。

空词库不需要预建标签或笔记类型：使用产品初始标签表，导入时按需创建目标牌组和应用专用笔记类型。已有词库会读取现有英文层级标签；不规范旧标签仍可展示，但不会盲目用于生成。同名不兼容的笔记类型不会被覆盖。已有笔记、模板和复习记录保持原样。Anki 的默认重复检查按笔记类型生效。

## Prompt 管理

按类型分别查看、上传和选择。主生成、英/日/韩风格、网络检索规划、配图规划、标签规则、复核及修正提示各有自己的文件列表。选用文件替换该阶段默认文件；“附加说明”类型独立管理，导入页仅列出该类型，并在本批主生成末尾追加。上传保留版本，正在执行的批次使用固定快照。

## 标签与数据

词性必填，日韩语源必填；混合来源允许多个语源标签。地域仅用于地域限定用法。标签树可以搜索、展开/收起，组合标签在 Anki 浏览器中查看。新标签提案可逐张批准、在全部导入时统一批准，或移除提案后导入。

界面语言与卡片讲解语言分开：英文词用英文讲解，日文词用日文，韩文词用中文。日语声调优先 Kanjium → OJAD → U-biq；韩语显示公开来源实际发音韩文。录音、配图或公开资料未找到时会提示，不保证每词都能命中。

本地状态默认位于 Windows `%LOCALAPPDATA%\AnkicardBuildingAutomation`，或 macOS/Linux 的 XDG 数据目录。可用 `ANKICARD_DATA_DIR` 改位置。个人词库可放在其中的 `vocabulary/`；配置、任务、媒体和自定义 prompt 也保存在用户数据目录，不写安装目录。

联网模式目前依赖 DeepSeek Search，使用 OpenAI 生成时也需要检索凭据。模型服务需要有效账号、权限和额度，Anki 需要插件可连接且未锁定待写笔记。第一次大量导入前建议在 Anki 备份。更多内容见[主 README](../README.md)、[配置](configuration.md)、[隐私说明](../SECURITY.md)。
