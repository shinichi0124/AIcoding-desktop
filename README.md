# AI Coding Desktop

Kimi/xAI Code-Web 同一套交互的整合前端：Tab 切换引擎模组。聊天、记录、打开终端、CLI/API 设置。DeepSeek 用官方 harness 当引擎，不嵌 `dsh web`；Kimi 用 Kimi 自带的本地服务（kap-server，HTTP + WebSocket）当引擎，不嵌 `kimi web` 的网页。

当前 **v1.3.1**（可运行，未打包 zip）。对照计划见 `docs/AUDIT_2026-08-23.md`；Kimi 引擎改造见 `docs/PLAN_kimi-kap-adapter_20261017.md`。

## Kimi Tab 用哪个引擎？

默认 **API**（kap）：先挂已开着的 Kimi Code 桌面端；桌面端没开就自己起 `kimi web --no-open`（只绑回环地址，退出 app 即收）。设置里可切回 **ACP**（旧 `kimi acp` 通道，删除走磁盘索引）。Kimi 的 token 只进请求头，不进日志。

## Which file should I run?

开始菜单 / 桌面：**AI Coding Desktop**（紫色 G + 右下角 `ai`）。也可双击 `Launch-Desktop.bat`（Anaconda `C:\ProgramData\anaconda3\python.exe` + `pywebview`）。升版或改入口后跑 `Install-Shortcuts.ps1`。

日志：`%LOCALAPPDATA%\AI-Coding-Desktop\logs\` — 打开 `LATEST` 文件里的路径，先看该 run 的 `IMPORTANT.log`（`LATEST` 是指针文件，不是目录）。

配置：`%USERPROFILE%\.ai-coding-desktop\config.json`（`kimi_engine`: `kap` | `acp`）

Kimi / xAI 原壳快捷方式保留，不要合并那两套源码。

## Git copy

日常编辑这个文件夹（无 `.git`）。Git 暂存副本：`AI projects/Github repos/AI-Coding-Desktop/`。同步：`scripts/Sync-To-GithubRepo.ps1`。未获明确指令不要 `git push`。
