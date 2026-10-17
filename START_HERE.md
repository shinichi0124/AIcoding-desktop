# START HERE — AI Coding Desktop v1.3.2

1. `C:\ProgramData\anaconda3\python.exe -m pip install -r sources\windows\requirements.txt`（含 `websocket-client`）
2. 开始菜单 / 桌面 **AI Coding Desktop**，或双击 `Launch-Desktop.bat`。改图标后跑 `Install-Shortcuts.ps1`。
3. 顶栏切模组。**Kimi 走 Kimi 自带本地 API（kap）**：有 Kimi Code 桌面端就挂上去，没有就 `kimi web --no-open`；设置里可切回 `ACP`。xAI / **Qwen Code** / Codex / Claude 走 ACP（失败则磁盘会话索引 + 打开终端）。Qwen Tab 只接 `qwen`，不接 `qwencloud`。DeepSeek 走官方 `dsh` 宿主 HTTP（不打开其网页）。
4. 设置：CLI 路径一行、API 一行、验证连接；关窗 = 到托盘或直接关；Kimi 引擎 = API / ACP。打开终端 = 可见 cmd。
5. 出问题先打开设置 → IMPORTANT。完成度：`docs/AUDIT_2026-08-23.md`。
