# AI Coding Desktop — lessons

项目专属。跨项目铁律仍看 `desktop-code-web-shell` 与平台 `AGENTS.md`。

### 2026-10-17 - kap 新会话不发 model 就必然 `model.not_configured`

Context: 首次实录 kap WS 帧，`POST /sessions` 建会话后直接 `POST /prompts`，两轮都在 40 ms 内 `turn.step.interrupted`。
Problem: 助手一个字都没出，只有 `turn.ended reason=failed` + `error {code:model.not_configured, message:"Model not set"}`。
Root cause: kap 建会话时不会替你套 `/config` 的 `default_model`；`agent.status.updated` 里的 `model` 是空串。
Fix: prompt body 必须带 `model`（取 `GET /config` 的 `default_model`，或用户在模型条里选的 `/models` 值）。
Prevention: 接新引擎先看「新建会话后哪些字段为空」——空 `model` 不会报 400，只会让每一轮都失败。

### 2026-10-17 - kap WS 不回 pong 会被服务端掐掉

Context: 同样的实录脚本第二轮（工具调用）读到一半 `recv` 返回空，看起来像「服务端崩了」。
Problem: 连接被关，但 REST 全通、日志无报错。
Root cause: `server_hello` 里 `heartbeat_ms=10000`；服务端发 `ping{nonce}`，客户端 10 s 内不回 `pong{nonce}` 就断。
Fix: 读循环里 `ping` → 立刻回 `pong`（走同一把 send 锁，不阻塞读线程）。
Prevention: 任何 WS 长连接先读 `server_hello` 的心跳字段，把 `ping/pong` 当契约，不要当可选项。

### 2026-10-17 - 挂别人的实例不等于拥有它

Context: Kimi Tab 默认挂正在运行的 Kimi Code 桌面实例（与桌面端同一份 minidb 存储）。
规则: 挂接路径 `stop()` 只关自己的 WS，**禁止** `POST /shutdown`、禁止杀进程、禁止 `rotate-token`；只有自己 `kimi web --no-open` 起的进程才 terminate。会话增删一律走 API（`:delete`），禁止读写 `~/.kimi-code/sessions/`、`session_index.jsonl`、`search-index/`。
Prevention: 适配器里 `self.owned` 是唯一判据；加新能力前先问「这动作会不会动到用户的 Kimi」。

### 2026-10-17 - 会话 load 的 transcript 是 turn/step/frame 三层

Context: `GET /sessions/{id}/transcript?agent_id=main` 返回 `items[]`，不是扁平消息流。
Problem: 直接按 `items[].text` 取会全空。
Root cause: 每项是 `{kind:"turn", prompt, steps:[{frames:[{kind:"thinking"|"text"|"tool"}]}]}`；用户 prompt 在 `turn.prompt`，助手文本在 `frames[kind=text].text`。
Fix: `_replay()` 只重放 `origin.kind=="user"` 的 turn，thinking 丢掉，tool frame 变 `tool_call`（title=工具名、status=state）。
Prevention: 接 transcript 前先 dump 一条真实项看层级，别照 REST 直觉写。

### 2026-09-10 - Kimi 删除必须清目录和 session_index.jsonl

Context: 用户在母项目里删 Kimi 聊天记录，确认后列表还在。
Problem: 适配器发 ACP `session/delete`；Kimi 回 `Internal error`。磁盘兜底只覆盖 Qwen/Codex/Claude。
Root cause: Kimi CLI 的 `session/list` 读 `~/.kimi-code/session_index.jsonl`，没有可用的 ACP 删除。Kimi-Code-Web 早已走 rmtree + 改索引。
Fix: `disk_sessions.delete_kimi_sessions`；Kimi 适配器先停 ACP 再清存储。禁止再把 ACP delete 当持久化。
Prevention: 新引擎删除前先问「列表从哪来」。

### 2026-09-10 - DeepSeek 隐藏启动：CREATE_NO_WINDOW 在 subprocess 上

Context: 切 DeepSeek Tab 弹出 CMD，卡二十秒以上；日志里 stderr 只有 `^C`。
Problem: `getattr(os, "CREATE_NO_WINDOW", 0)` 永远是 0；再经 npm `dsh.cmd`（含 `title %COMSPEC%`）；`/api/start` 同步等 `_wait_host(60)`。
Fix: `subprocess.CREATE_NO_WINDOW` + 直跑 `node.exe …/dsh/lib/bin.js`；start 立刻返回 `starting`，就绪发 `engine_ready`。
Prevention: 不要从 `os` 取 Windows process creation flags。`.cmd` 启动器能弹窗时改直跑解释器。

### 2026-08-23 - 会话删除要跟 Code-Web：全选/多选/删所选

Context: 用户发现侧栏只能逐条点垃圾桶。
Problem: 只做了单条 `/api/session/delete`，没有管理模式。
Fix: 抄 Kimi/xAI：管理条全选/全不选/删除所选/完成；行用标记图标；批量 `/api/sessions/delete`。不要再发明第二套勾选。
Prevention: 聊天记录列表先对一下 Code-Web 兄弟项目，再写删除。

### 2026-08-23 - Qwen Tab 只接 Qwen Code，不接 qwencloud

Context: 本机同时有 Qwen Code（`qwen`，编码 agent）和 QwenCloud CLI（`qwencloud`，账号管理）。
Problem: 设置/PATH/浏览可能把 `qwencloud.cmd` 或 `Launch-Qwen-Code.cmd` 当成引擎。
Fix: `is_qwen_code_binary` 拒绝路径含 `qwencloud` 或 `Launch-*`；覆盖无效则回退 `%LOCALAPPDATA%\qwen-code\bin\qwen.cmd`。ACP 仍是 `qwen --acp`。
Prevention: 不要用 PATH 里第一个名叫 qwen 的东西；先认安装目录。

### 2026-08-23 - Claude 没有 --acp；裸 cmd.exe；终端整串 Popen 空白

Context: Claude/Qwen Tab 握手失败；DeepSeek「打开终端」空窗；顶栏反复 `read loop ended` 看不出是哪个 Tab。
Problem: `claude.exe --acp` → `unknown option '--acp'` 立刻退出；Qwen `.cmd` wrap 成 `argv[0]=cmd.exe`，`Path.is_file()` 为假；`Popen("cmd.exe /k …", shell=False)` 把整串当程序名。
Root cause: 官方 Claude Code 2.1.x 没有 ACP 旗标（ACP 要 sidecar）；Windows 批处理必须 `%ComSpec%` 全路径；CreateProcess 字符串不是 cmd 命令行。
Fix: `win_cli.py` wrap/terminal；Claude 无 sidecar 则不 spawn；握手/引擎错误画在右侧聊天栏并带模组名；会话列表不重拉已失败引擎。
Prevention: 新引擎先 `--help` 核对入口，再写 spawn。终端永远 list argv。ALERT 必须带 module。

### 2026-08-23 - pywebview 没有 icon= 时任务栏仍是 Python

Context: 快捷方式已换成 G+ai BMP ICO，窗口任务栏仍显示 python。
Problem: `webview.create_window(..., icon=path)` 在本机 pywebview 直接 TypeError；即使有该参数，Win11 仍按进程（pythonw）画图标。
Root cause: 壳是 python 宿主，不是带图标的 exe；PNG/透明 ICO 还会白板。
Fix: 短路径 `%LOCALAPPDATA%\AI-Coding-Desktop\app.ico`（16/24/32/48 不透明 BMP）+ 后台线程 `LoadImageW` + `SendMessageTimeoutW(WM_SETICON)`。禁止 pythonnet `Form.Icon`、禁止阻塞 `SendMessageW`。
Prevention: 第三套 Code-Web 不要假设 `icon=` 够用。改图标后重跑 `Install-Shortcuts.ps1`，并重启窗口。

### 2026-08-23 - 多个 G 标产品要靠角标区分

Context: smartLarch 与本客户端都用大写 G。
Problem: 纯 G、透明底，开始菜单和任务栏分不清。
Fix: 紫色砖上白 G，右下角小写 `ai` 角标。顶栏字标是 G 砖 + `Coding` / `platform` 两行，不要把透明 PNG 直接贴顶栏。
Prevention: 新的 G 系程序先做角标，不要复用无角标的 `app_icon_g.png` 当快捷方式。

### 2026-08-23 - 关窗到托盘是 radio，设置关闭钮在面板右上角

Context: 用户要设置里的 close 到右上角，并要「到托盘 / 直接关」。
Problem: 把设置面板关闭和窗口关闭搅在一起，或再做一套按钮。
Fix: 面板 `panel-head` 右侧 X 只关设置；`close_action`=`quit`|`tray` 互斥 radio。窗口 × 读磁盘配置；pystray 缺则 minimize。
Prevention: 不要用第二套全选/开关冒充关窗策略。

### 2026-10-17 - kap 验收：日志脱敏了，UI 通道没脱敏；HTTP 返回不等于回复结束

Context: v1.3.1 Kimi Tab 改走 kap-server，执行方自测「token 不入日志」通过。
Problem: ①spawn 模式下 `/api/health` 的 `stderr_tail` 含 token；②`/api/prompt` 0.3 s 就返回，界面在 Kimi 还在回答时清掉「生成中…」。
Root cause: ①`kimi web` 启动横幅把 token 打到 stdout；写日志走 `redact()`，但 `_note()` 存原文，snapshot 再发给 UI。只查日志文件，漏了第二条出口。②kap 的 `POST /prompts` 是「已受理」，结束信号在 WS 的 `prompt.completed`；ACP 的 `session/prompt` 则是结束才回。
Fix: `_note()` 一律脱敏；`prompt()` 按 `promptId` 等 `prompt.completed`（或致命 error / cancel / stop，空闲 600 s 兜底）。
Prevention: 查密钥泄漏要查**所有出口**（日志、snapshot、事件、异常文本），不只日志文件。换引擎时核对「请求返回」的语义是受理还是完成。PowerShell 扫描注意：管道里 `Select-String -Quiet` 每个文件回一个布尔，`[bool]` 一个数组恒为 True。

### 2026-10-17 - dsh 升级把事件流从 SSE 换成 WebSocket，DeepSeek Tab 静默无输出

Context: DeepSeek Tab 能启动、能发送，聊天区却没有任何回复；日志 `sse.loop HTTP Error 426` 每 1.2 s 一条。
Problem: dsh 0.1.0-rc.6 的 `/api/events.mux` 只接受 WebSocket 升级（普通 GET 回 426）；而且旧映射读 `data.text`，新帧的正文在 `data.chunk`（`text-delta`）和 `data.message.content`，就算连上也不会出字。
Root cause: 依赖官方宿主的内部 HTTP 接口，宿主一升级传输层与帧形状一起变；旧代码没有实录帧做对照，映射是按字段名猜的。
Fix: 改连 `ws://…/api/events.mux`，只连不发（发消息会被 1008 断开）；按实录帧重写映射；`/api/prompt` 等 `turn/end`；列表过滤 `archivedSessionIds`。
Prevention: 接官方宿主接口时先读宿主自带客户端（`dsh-client-connection`）怎么连，再实录帧存 fixture；日志里同一 WARN 高频重复就是信号，不要当噪音。
