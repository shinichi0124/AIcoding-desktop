# AI Coding Desktop — agent notes

- 产品规格：`../docs/PLATFORM_PLAN_2026-08-21.md`（在 `AI coding platform/docs/`）
- 执行大纲：`../docs/superpowers/plans/2026-08-21-ai-coding-desktop-execution.md`
- 进度：v1.3.2 可运行未打包 zip。审计 `docs/AUDIT_2026-08-23.md`，教训 `docs/LESSONS.md`。
- **Git 双目录**：日常目录本文件夹（无 `.git`）。Git 暂存副本 `AI projects/Github repos/AI-Coding-Desktop/`。同步：`scripts/Sync-To-GithubRepo.ps1`。向 GitHub **推送需用户当次明确指令**（不要装会自动 push 的 post-commit hook）。
- Windows 启动 CLI：`.cmd/.bat` 必须 `%ComSpec%` 全路径 wrap，禁止 argv[0]=`cmd.exe` 再 `Path.is_file()`。打开终端必须 list argv + `/k`（`.ps1` 用 PowerShell `-NoExit`），禁止 `Popen(整串, shell=False)`。
- Claude 官方 CLI **没有** `--acp`；不要再 spawn `claude.exe --acp`。无 sidecar 时只提示「打开终端」+ 磁盘会话。
- **Qwen Tab = Qwen Code only**：二进制必须是 `%LOCALAPPDATA%\qwen-code\bin\qwen.cmd`（或同目录 `qwen.exe`），ACP 为 `qwen --acp`。禁止接 `qwencloud`（`@qwencloud/qwencloud-cli`，账号管理，无 ACP），禁止把 `QwenCloud-CLI\Launch-Qwen-Code.cmd` 当引擎。
- 架构：bat/vbs → `supervisor.py` → `desktop.py` + HTTP bridge → `modules/` 一模组一适配器（ACP 或 dsh host）。无 C# 启动器、无 zip。
- 日志：`%LOCALAPPDATA%\AI-Coding-Desktop\logs`，合同见大纲 Log contract。
- 不要 iframe `dsh web`；不要裸 DeepSeek API 当聊天引擎。
- 不要合并 Kimi-Code-Web / xAI-Code-Web 源码。
- 版本：`sources/windows/app/version.py` `APP_VERSION` 必须与 `version.json`、UI 角标一致。**当前 v1.3.2**（已进 MAJOR=1 一档；下次按 §B.13 第 2 步重算，MINOR/PATCH 照常）。
- UI：顶栏 / 设置操作一律图标按钮（36×36、flex 居中），文字只进 `title` / `aria-label`，禁止再加带文字的按钮。模组 Tab 用 `web/logos/<id>.svg` 官网标（xAI / Codex 为单色，随深浅色反相）。发送 / 停止与输入框 `align-items: center`。
- 顶栏字标：`.brand-mark` 36×36 强调色底 + 白 G（`g-logo.png` 反相），右侧双行 `Coding` / `platform`。不要把透明底 G 直接贴在顶栏上。
- 快捷方式图标：`scripts/make_icon.py` 生成紫色 G + 右下角小写 `ai` 角标。ICO 必须是 16/24/32/48 不透明 BMP（禁止 PNG 帧，否则任务栏白板）。升版后跑 `Install-Shortcuts.ps1` 就地改 `TargetPath`/`IconLocation`，稳定名 `AI Coding Desktop.lnk`，图标副本 `%LOCALAPPDATA%\AI-Coding-Desktop\app.ico`。
- 运行中任务栏图标：`desktop.py` 在后台线程对 HWND 发 `WM_SETICON`（`SendMessageTimeoutW` 250ms）。禁止 pythonnet `Form.Icon`，禁止阻塞 `SendMessageW`。`pywebview icon=` 不够，Win11 仍会显示 pythonw。
- 设置：关闭按钮在面板右上角。关窗行为用互斥 radio（`close_action`: `quit` | `tray`），不要再发明第二套开关。点窗口 × 读磁盘配置；托盘用 pystray，缺库则 minimize。
- **会话列表**：与 Kimi/xAI Code-Web 同一套管理——侧栏「管理」进入多选；工具条 **全选 / 全不选 / 删除所选 / 完成**（短文案，侧栏可换行）；行左侧标记图标（不是系统 checkbox）；默认模式点标题加载、垃圾桶或右键删一条。批量走 `/api/sessions/delete`。切 Tab 退出管理模式。
- **Kimi 引擎 = kap API（v1.3.1 起默认）**：`KimiKapHost`（`modules/kimi_kap.py`）先挂运行中的 Kimi 实例（`~/.kimi-code/server/instances/*.json` + `server.token`），挂不上才 `kimi web --no-open --port 18774`。token 只进 `Authorization` 头，禁止进 URL / 日志 / 事件 / fixture；禁止 iframe 或打开 `kimi web` 自带网页；挂别人的实例时禁止 `/shutdown`、杀进程、`rotate-token`。新会话的 prompt 必须带 `model`（否则 kap 回 `model.not_configured`）。`/api/prompt` 对所有引擎都等本轮结束才返回（kap 等 `prompt.completed`）。`kimi web` 会在 stdout 打印 token：任何进 `stderr_tail`/事件/UI 的子进程输出必须先 `redact()`。
- **Kimi 删除**：`kimi_engine=kap`（默认）走 `POST /sessions/{id}:delete`，由 Kimi 自己删（含索引）。禁止只发 ACP `session/delete`；磁盘路径（停 ACP + 改写 `~/.kimi-code/session_index.jsonl` + rmtree，`disk_sessions.delete_kimi_sessions`）**只限** `kimi_engine=acp` 回退。
- **DeepSeek 启动**：`subprocess.CREATE_NO_WINDOW`（不要 `os.CREATE_NO_WINDOW`）+ 直跑 `node.exe`/`lib/bin.js`，禁止用会弹窗的 `dsh.cmd` 当 argv0。dsh（0.1.0-rc.6 起）的 `/api/events.mux` 是**只下行的 WebSocket**：普通 GET 回 426，客户端发任何消息都会被 1008 断开——只连不发。正文在 `assistant/chunk` 的 `text-delta`，`turn/end` 才算本轮结束；会话「删除」= `workspace.archiveSession`，列表须按 `workspace.list` 的 `archivedSessionIds` 过滤。宿主就绪前 `/api/start` 返回 `starting`，不要同步卡 60s。

## 交接文件（HANDOFF.md）

每次任务结束必须更新本目录的 `HANDOFF.md`（规则见工作区 `AGENTS.md` §D.5）。新会话/新模型接手本项目时，先读 `HANDOFF.md` 再开工。
