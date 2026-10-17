# Changelog

## v1.3.2 — 2026-10-17

- **DeepSeek Tab 恢复流式输出**：dsh 0.1.0-rc.6 把 `/api/events.mux` 从 SSE 改成只下行的 WebSocket，旧的 GET 一直回 `426 Upgrade Required`（`sse.loop` 每 1.2 s 刷 WARN，聊天区收不到任何回复）。改为 `ws://127.0.0.1:18773/api/events.mux`（只连不发；断线 1.2 s 重连）。
- 按实录帧重写事件映射：正文取 `assistant/chunk` 的 `text-delta`（整段 `assistant/message` 只在没有流式块时补显）；`tool/call`/`tool/result` → 工具行；用量取 chunk 或 message 的 `usage`；系统注入的 `user/message`（策略、技能目录）不上屏，历史重放只显示用户本人的话。
- `/api/prompt` 对 DeepSeek 也等到 `turn/end` 才返回（与 ACP、Kimi 一致），界面不再提前清掉「生成中…」。
- 删除 DeepSeek 会话后列表不再残留：`session.list` 会连已归档的一起返回，现按 `workspace.list` 的 `archivedSessionIds` 过滤。
- 新增 `tests/test_deepseek_mux.py`（10 项）+ `tests/fixtures/dsh_mux_frames.jsonl`（2026-10-17 实录并脱敏）。

## v1.3.1 — 2026-10-17

- **Kimi Tab 改走 Kimi 自带的本地 API（kap-server，HTTP + WebSocket）**，不再依赖 `kimi acp`：先挂正在运行的 Kimi Code 桌面实例（`~/.kimi-code/server/instances/*.json` + `server.token`，心跳 < 90 s、回环地址、pid 存活、`/healthz` 2 s 内通），挂不上才 `kimi web --no-open --port 18774`（端口占用顺延 18775–18779，退出 app 自动终止自己起的进程）。
- Kimi 删除改 `POST /sessions/{id}:delete`，由 Kimi 自己删（含 minidb / 搜索索引）；不再停 ACP 改写 `session_index.jsonl`。磁盘删除保留给 `kimi_engine=acp` 回退。
- 新适配器 `modules/kimi_kap.py`（`KimiKapHost` + `KimiKapAdapter`）：真实帧映射（`assistant.delta` → `agent_message_chunk`、`tool.call.started/tool.result` → `tool_call`、`error` → `engine_error`、`ping` → `pong`、`resync_required` → 重拉 transcript），断线 1→2→5→10 s 退避重连并带 `cursors`，读线程死掉算 `alive=False`。
- 新会话的 prompt 必须带 `model`（不带时 kap 直接回 `model.not_configured`，本轮实测）；模型条从 `/models` 填，默认取 `/config` 的 `default_model`。
- 设置新增「Kimi 引擎：API / ACP」互斥 radio（中英同步，默认 API）；`~/.ai-coding-desktop/config.json` 新增 `"kimi_engine"`。ACP 分支代码原样保留，可随时回退。
- 新增 `websocket-client>=1.6` 依赖；`tests/test_kimi_kap.py`（30 项，含实录帧回放）+ `tests/fixtures/kap_ws_frames.jsonl`（2026-10-17 实录并脱敏）。
- 验收修复（Claude Code 复跑 §5 时发现）：`kimi web` 启动横幅会打印 token，`stderr_tail`（经 `/api/health` 发给 UI）现一律脱敏；`/api/prompt` 改为等到本轮 `prompt.completed` 才返回（与 ACP 一致，界面不再提前清掉「生成中…」）；kap 带点的错误码（如 `model.not_configured`）现可翻译；spawn 日志改为每个管道一个读线程。
- 版本号 `0.3.1 → 1.3.1`（§B.13 第 2 步 ⑤：MAJOR=0 且已是日常入口，进位当次不再 +MINOR/+PATCH）。

## v0.3.1 — 2026-09-10

- Kimi 删除聊天记录改为磁盘目录 + `session_index.jsonl`（Kimi ACP `session/delete` 会 Internal error，删了列表还在）。
- 切 DeepSeek：用 `subprocess.CREATE_NO_WINDOW` + 直跑 `node.exe`/`bin.js` 隐藏启动；`/api/start` 立即返回 `starting`，不再卡住等宿主。

## v0.3.0 — 2026-08-23

- 聊天记录管理对齐 Kimi/xAI Code-Web：管理模式、全选、全不选、删除所选、确认框、右键删一条。行用标记图标，不是系统勾选框。

## v0.2.2 — 2026-08-23

- Qwen Tab 锁定 **Qwen Code**（`qwen` / `%LOCALAPPDATA%\qwen-code\bin\qwen.cmd`）。拒绝 `qwencloud` 管理 CLI 和 `Launch-Qwen-Code.cmd` 启动器。

## v0.2.1 — 2026-08-23

- Claude：官方 `claude.exe` 没有 `--acp`，不再用错误参数握手；错误跟当前 Tab 显示在右侧聊天栏。
- Qwen：`.cmd` 走 `%ComSpec%` 全路径，不再 `binary_not_found: cmd.exe`。
- 打开终端：list argv + `/k`（`.cmd` 用 `call`，`.ps1` 用 PowerShell `-NoExit`），DeepSeek 控制台不再空白闪退。
- 握手失败不再把无模组名的 `read loop ended` 刷在顶栏；会话列表不会反复重拉已失败的引擎。

## v0.2.0 — 2026-08-23

- 适配器协议 `modules/`：ACP（Kimi/xAI/Qwen/Codex/Claude）+ DeepSeek 官方 host HTTP（不嵌网页）。
- 会话删除、CLI 浏览、引擎暴露的模型条、DeepSeek 缓存命中公式（缺 usage 显示未知）。
- 设置保存时写入 `~/.dsh/.credentials.yaml` 的 `DEEPSEEK_API_KEY`。
- Qwen/Codex/Claude：ACP 失败则磁盘 jsonl 只读列表，不 iframe 官方 TUI。
- 薄 supervisor：desktop 非 0 退出最多重启 3 次。仍不打包 zip。

## v0.1.6 — 2026-08-23

- 设置关闭按钮移到面板右上角。
- 关窗选项：最小化到托盘 / 直接关闭（默认直接关）。无 pystray 时托盘退化为任务栏最小化。
- 文档：对照计划审计 `docs/AUDIT_2026-08-23.md`；纠正父 README「尚未开建」。

## v0.1.5 — 2026-08-23

- 运行中窗口任务栏图标：`WM_SETICON` 套同一套 G+ai BMP 图标（不用 pythonnet；`SendMessageTimeoutW` 防假死）。

## v0.1.4 — 2026-08-23

- 快捷方式 / 窗口图标：紫色 G 标 + 右下角小写 `ai` 角标（与其它 G 标项目区分）。
- 稳定快捷方式名 `AI Coding Desktop.lnk`（开始菜单 + 桌面）；图标走 `%LOCALAPPDATA%\AI-Coding-Desktop\app.ico`。

## v0.1.3 — 2026-08-23

- 顶栏大标题改为 G 标 + `Coding` / `platform` 双行字标。
- G 放进 36×36 圆角色块（强调色渐变 + 浅内高光），白字 G，避免透明底发干。

## v0.1.2 — 2026-08-23

- 所有操作按钮改为图标（文案只在 tooltip / aria-label）。
- 图标按钮 36×36，内容水平垂直居中。
- 模组 Tab 使用各家官网 logo（Kimi / xAI / OpenAI Codex / Claude / Qwen / DeepSeek）。
- 发送 / 停止与左侧输入框垂直居中对齐。

## v0.1.1 — 2026-08-23

- Tab 右对齐、图标 + 连接状态点；左侧 G 标；版权改为 `Copyright © 2026 by Dr. GENG Xun`。
- 背景随系统深浅色；发送/停止改图标（停止仍取消当前任务）。
- 按钮按压 `scale(0.97)` 160ms ease-out；设置弹层 250ms scale 入场。
- 验证连接会跑各家 CLI `--version`。

## v0.1.0 — 2026-08-21

- 首个可运行整合前端：同一套聊天/记录/打开终端/CLI+API 设置。
- Tab：Kimi、xAI、Codex、Claude、Qwen、DeepSeek。
- 日志：`%LOCALAPPDATA%\AI-Coding-Desktop\logs`，IMPORTANT.log 仅 WARN+，ALERT 以 `!!!` 凸显。
- DeepSeek：启动官方 `dsh` 引擎，不嵌网页；ACP 聊天桥接仍在加深。
- 未打包 zip。
