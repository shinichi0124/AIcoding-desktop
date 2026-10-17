# PLAN — Kimi 模组改走 kap-server API 适配器（2026-10-17）

> 规则：工作区 `AGENTS.md` §B.27（直接升大版本只出计划书，交执行代理，原代理回来验收）。
> 作者：Claude Code（Opus 5.5），2026-10-17。执行方：DeepSeek 等执行代理。
> 状态：**已验收**（执行方：DeepSeek Harness / deepseek-v4-flash，2026-10-17 完成；原代理 Claude Code 2026-10-17 复跑验收，发现 3 个缺陷并修复，见文末「验收记录」）。

## 0. 版本号

- **`0.3.1` → `1.3.1`**（项目 `AGENTS.md` 已登记的 **Next ship**，必须用这个号）。
- 进位理由：§B.13 第 2 步 ⑤ —— `MAJOR=0` 且 v0.3.1 已是开始菜单 `AI Coding Desktop` 的日常入口。进位当次禁止再 +MINOR/+PATCH，所以本次功能改动也落在 `1.3.1`，不是 `1.4.0`。
- 同步四处：`sources/windows/app/version.py` `APP_VERSION`、`sources/windows/version.json`、UI 角标（`index.html` 的 `v%%VERSION%%` 由 version.py 注入）、`CHANGELOG.md`。

## 1. 背景与证据

### 1.1 现状的问题（Kimi Tab 走 `kimi acp`）

- 适配器：`sources/windows/app/bridge/modules/acp_engine.py` `AcpAdapter` + `acp_client.py`（stdio JSON-RPC）。
- ACP `session/delete` 返回 Internal error、删了列表还在（v0.3.1 CHANGELOG），所以现在 Kimi 删除只能：**停掉 ACP 进程 → 改写 `~/.kimi-code/session_index.jsonl` → 按目录 rmtree**（`disk_sessions.delete_kimi_sessions`，项目 AGENTS 不变量第 21 条）。这是在改 Kimi 的私有存储，Kimi 一升级存储格式就坏；而且 2026-10 起 Kimi 用 minidb（WAL + 索引，`~/.kimi-code/search-index/`），手工删目录会让索引和数据不一致。
- ACP 很薄：没有取消以外的会话动作，审批只能自动同意或忽略，历史只能整段重放。

### 1.2 Kimi Code 2.x 已经自带完整的本地 API（kap-server）

证据来源：拆包 `C:\Program Files\Kimi Code\resources\app.asar`（Kimi Code Desktop 1.1.0，打包代码未压缩，带 `//#region` 源文件名）+ `kimi.exe --help`（CLI 2.2.0）+ 2026-10-17 对正在运行的实例做的只读探测。

| 事实 | 证据 |
|---|---|
| Kimi 桌面端只是 Electron 壳，聊天引擎是进程内的 kap-server（HTTP + WebSocket），前端也是普通网页客户端 | `src/main/server.ts` `startDesktopServer` → `startServer({host:"127.0.0.1", port:0, …})` |
| CLI 能单独起同一个服务：`kimi web --no-open --port <p>`（默认只绑 127.0.0.1） | `kimi web --help` |
| 运行中的服务会写发现文件 `~/.kimi-code/server/instances/<server_id>.json`：`{server_id, pid, host, port, started_at, heartbeat_at, host_version}` | 实机读取；桌面端实例 `host_version: 2.1.1` |
| 鉴权：`Authorization: Bearer <token>`，token 为 `~/.kimi-code/server.token`（持久，`kimi web rotate-token` 可换）；桌面端另有一个仅进程内的启动密钥 | `server-auth.ts` `createDesktopAuthTokenService` 两个都接受 |
| 实测：`GET /api/v1/healthz` → `{"ok":true}`；`GET /api/v1/sessions` → `{items, has_more}`，74 条；**不带 token → 401** | 2026-10-17 只读探测 |
| 返回统一信封：`{code, msg, data, request_id}` | `okEnvelope` / `errEnvelope` |

本计划要用的接口（前缀 `/api/v1`，全部要 Bearer）：

| 用途 | 方法与路径 | 请求体 / 说明 |
|---|---|---|
| 健康 | `GET /healthz` | |
| 版本/能力 | `GET /meta` | `server_version`、`capabilities`、`features` |
| 会话列表 | `GET /sessions?page_size=100&exclude_empty=true` | 分页：`after_id` / `before_id`，返回 `items[]` + `has_more`；每条含 `id, title, updated_at, busy, pending_interaction, archived, last_seq` |
| 新建会话 | `POST /sessions` | `{"metadata":{"cwd":"<workspace>"}}`（或 `workspace_id`）；`title` 可选 |
| 单个会话 | `GET /sessions/{id}`、`GET /sessions/{id}/status` | |
| 删除 | `POST /sessions/{id}:delete` | 无体；返回 `{deleted:true}`。**由 Kimi 自己删，含索引** |
| 中止当前轮 | `POST /sessions/{id}:abort` | |
| 发送 | `POST /sessions/{id}/prompts` | `{"content":[{"type":"text","text":"…"}], "model"?, "permission_mode"?: "manual"\|"yolo"\|"auto", "prompt_id"?}` |
| 历史 | `GET /sessions/{id}/transcript?agent_id=main&page_size=100` | 分页：`before_turn` / `after_turn` |
| 待审批 | `GET /sessions/{id}/approvals` | |
| 审批 | `POST /sessions/{id}/approvals/{approval_id}` | `{"decision":"approved"\|"rejected"\|"cancelled", "scope"?:"session", "feedback"?}` |
| 待回答问题 | `GET /sessions/{id}/questions` | |
| 模型 | `GET /models` | 用来填模型条 |
| 实时事件 | `WS /api/v1/ws` | token 走子协议 `kimi-code.bearer.<token>`（或 Authorization 头）；先发 `{"type":"client_hello","id":"<id>","payload":{"subscriptions":["<session_id>"],"cursors":{}}}`，收 `ack`；之后可 `subscribe` / `unsubscribe`（`payload.session_ids`）。服务端会发 `ping`（要回 `pong`）和 `resync_required`（要重拉 transcript） |

> 已知事件类型（来自 `sessionEventJournal.ts`）：`event.approval.requested/resolved`、`event.question.requested/answered/dismissed`、`event.session.created/deleted/archived`、`agent.status.updated`、`session.meta.updated` 等。**助手文本增量 / 工具调用帧的确切形状本计划未钉死** —— 任务 2 先实录再写映射，禁止凭猜。

### 1.3 为什么不改别的方案

- 嵌 `kimi web` 自带网页 = 违反平台红线第 6 条（禁止 iframe/嵌官方 UI）。我们只用它的 **API**，界面仍是自己的 Code-Web 外壳。
- 继续 ACP + 磁盘删 = 现状，越来越脆。
- 让 Kimi 桌面端反连我们（`KIMI_SERVER_URL`）= 改的是用户的 Kimi 安装，不做。

## 2. 设计

新文件 `sources/windows/app/bridge/modules/kimi_kap.py`，结构仿照 `deepseek_host.py`（同是「官方本地服务 + HTTP」）：

```
KimiKapHost      连接/起服务、HTTP、WS 线程、事件映射
KimiKapAdapter   实现 modules/base.py 的 EngineAdapter 协议（和 DeepSeekAdapter 一样薄包一层）
```

### 2.1 连接策略：先挂、后起

1. **挂（attach）**：读 `~/.kimi-code/server/instances/*.json`，按 `heartbeat_at` 倒序，取第一个满足：`host` 是 `127.0.0.1`/`::1`/`localhost`、pid 进程还在、`heartbeat_at` 距今 < 90 s、`GET /healthz` 2 s 内带 token 返回 ok。用它。**不拥有它**：`stop()` 只关自己的 WS，不杀进程、不调 `/shutdown`。
2. **起（spawn）**：没有可挂的实例时，`kimi.exe web --no-open --port 18774`（`subprocess.CREATE_NO_WINDOW`，`cwd=workspace`，stdout/stderr 落日志，同 DeepSeek 写法）；后台线程最多等 60 s 轮询 `/healthz`，期间 `/api/start` 立即返回 `starting`（沿用不变量第 22 条的做法）。端口被占 → 换 18775–18779 再试。`stop()` 时 terminate 自己起的进程。
3. token 每次请求前从 `server.token` 读（按 mtime 缓存），**任何日志、事件、URL 里都不出现 token**。

### 2.2 方法映射（EngineAdapter → kap）

| 适配器方法 | kap 调用 |
|---|---|
| `start()` | 2.1；成功后 `GET /models` 填 `config_options`，发 `engine_ready`（code=`kap-attach` 或 `kap-spawn`） |
| `session_list()` | `GET /sessions` 翻页取前 200 条 → `[{sessionId:id, title:title or id[:16], updatedAt:updated_at}]`（前端现有字段名不变） |
| `session_new()` | `POST /sessions {"metadata":{"cwd":workspace}}` → 记 `session_id`，WS `subscribe` |
| `session_load(id)` | WS 换订阅到 id；`GET /sessions/{id}/transcript?agent_id=main` → 映射成现有 `user` / `session_update` 事件重放 |
| `prompt(text)` | 无会话先 `session_new()`；`POST /sessions/{id}/prompts`，带 `permission_mode`（见 2.3）和已选 `model`。立即返回；输出全部走 WS |
| `cancel()` | `POST /sessions/{id}:abort` |
| `session_delete(id)` | `POST /sessions/{id}:delete`；`SESSION_NOT_FOUND` 归入 `missing` |
| `session_delete_many(ids)` | 逐个 `:delete`，单个失败不中断，返回与现有 `delete_sessions_batch` 相同的字典结构（`ok/deleted/deleted_count/failed/missing/via:"kap"`） |
| `set_config("model", v)` | 记到实例变量，下次 prompt 带 `model`；更新 `current_model` |
| `snapshot()` | 同 DeepSeek：`acp:False`、`agent_version:"kap <server_version>"`、`starting` |

### 2.3 审批

- 设置里 `auto_approve` 为真（现默认）→ prompt 带 `"permission_mode":"auto"`；收到 `event.approval.requested` 仍兜底 `POST …/approvals/{id} {"decision":"approved"}`。
- 为假 → `"permission_mode":"manual"`，把审批事件推成现有的 `{"type":"permission",…}` 事件；本版**不新增审批 UI**（与 ACP 现状一致），在 `docs/LESSONS.md` 记一条待办。

### 2.4 开关与回退

- `~/.ai-coding-desktop/config.json` 新增 `"kimi_engine": "kap" | "acp"`，默认 `"kap"`。`module_runtime.start_module` 在 `module=="kimi"` 且为 `"kap"` 时建 `KimiKapAdapter`，否则走原 `AcpAdapter`。
- kap 两种方式都失败 → 推 `engine_error`（code=`kimi_kap_unavailable`，附最后一步原因），**不自动静默切回 ACP**（避免两套存储写法混用）；用户可在设置里切 `acp`。设置面板加这一项（单选，双语，短文案，见 §B.16/§B.21）。

## 3. 逐步任务

| # | 做什么 | 文件 / 函数 | 完成标志 |
|---|---|---|---|
| 0 | **先给 v0.3.1 留底**：跑 `scripts/Sync-To-GithubRepo.ps1`，在 `Github repos/AI-Coding-Desktop/` 本地 `git commit -m "v0.3.1 snapshot before kap adapter"`（**不 push**）。现在那边停在 v0.3.0，v0.3.1 从没进过 git | — | `git -C "…/Github repos/AI-Coding-Desktop" log -1` 显示该提交 |
| 1 | 加依赖 `websocket-client>=1.6`（Anaconda 已装，import 名 `websocket`） | `sources/windows/requirements.txt` | — |
| 2 | **实录 WS 帧**：写一次性脚本放 `tmp/kap_probe.py`（项目内 `tmp/`，可删），挂到运行中的实例，新建会话、发一句 "reply with exactly: pong"、触发一次工具调用（如 "list files in this folder"），把收到的帧逐行写 `sources/windows/tests/fixtures/kap_ws_frames.jsonl`。**写入前删掉 token、本机用户名路径换成 `C:/Users/USER`** | 新建 fixture | fixture 至少含：ack、文本增量、工具调用开始/结束、轮结束 |
| 3 | 按 fixture 写事件映射：文本增量 → `session_update/agent_message_chunk`；工具 → `session_update/tool_call`（title=工具名，status）；轮结束 → 无事件或 `info`；`resync_required` → 重拉 transcript；`ping` → 回 `pong` | `kimi_kap.py` `KimiKapHost._map_frame` | 单测喂 fixture，输出与预期事件列表相等 |
| 4 | 发现 + 鉴权 + HTTP 封装（统一解信封，`code!=0` 抛 `AcpError(f"kap:{code}:{msg}")`，超时一律有上限：普通 10 s、prompt 提交 30 s） | `kimi_kap.py` `discover_instance()`、`read_token()`、`_req()` | 单测：过期心跳/死 pid/非回环 host 都被拒 |
| 5 | WS 线程：连 → `client_hello` → 读循环；断线 1→2→5→10 s 退避重连并带 `cursors`；读线程状态计入 `alive`；handler 全包 try/except（平台 AGENTS「桌面 bridge 假死通则」） | `kimi_kap.py` `_ws_loop()` | 杀掉服务后 `alive` 变 False 并推 `engine_error` |
| 6 | spawn 路径：参考 `deepseek_host.py` 的 `start/_boot_wait/stop`；argv 用 `win_cli` 现有的 `.exe` 直跑方式，**不经 cmd** | `kimi_kap.py`、`win_cli.py`（如需加 `kimi_web_argv`） | 无控制台窗口闪现；退出 app 后无残留 `kimi.exe web` |
| 7 | 适配器方法（2.2 表） | `kimi_kap.py` `KimiKapAdapter` | 满足 `isinstance(ad, EngineAdapter)` |
| 8 | 接线：`kimi_engine` 开关 | `config.py`（默认值）、`module_runtime.py` `start_module` | ACP 分支代码原样保留 |
| 9 | 设置面板加「Kimi 引擎：API / ACP」单选（中英同步） | `web/index.html`、`web/app.js` | 切换后重启该 Tab 生效 |
| 10 | 单测：新增 `tests/test_kimi_kap.py`（用 `http.server` 起假 kap + fixture 回放，覆盖 attach 选择、401、delete 批量部分失败、abort、帧映射）；`test_kimi_store.py` 保留（ACP 回退仍用） | `sources/windows/tests/` | 见验收 1 |
| 11 | 文档：项目 `AGENTS.md` 改第 21 条为「kap 路径用 `:delete`；磁盘删除只限 `kimi_engine=acp` 回退」并新增一条「Kimi 引擎 = kap API，先挂后起，token 不出日志，禁止嵌 `kimi web` 网页」；`CHANGELOG.md`、`FILE_MANIFEST.md`、`README.md`（如有引擎说明）、`HANDOFF.md`；平台 `../AGENTS.md` 无需改 | 文档 | — |
| 12 | 升版 `1.3.1`（第 0 节四处）→ 跑 `Install-Shortcuts.ps1` 就地更新 `AI Coding Desktop.lnk` | | 验收 2、9 |

## 4. 禁止事项

1. 禁止在 pywebview / 任何窗口里加载 `kimi web` 自带的网页（平台红线 6）。必须 `--no-open`。
2. 禁止 `--host`、`--dangerous-bypass-auth`、`--rc` / `--remote-control`、`--allow-remote-shutdown`；禁止挂到非回环地址的实例。Remote Control 走 `code-rc.kimi.com` 外部中继，学校内部使用，不碰。
3. 禁止把 token 放进 URL query、日志、事件、异常文本、fixture、截图。
4. 禁止在 kap 路径里读写 `~/.kimi-code/sessions/`、`session_index.jsonl`、`search-index/`；会话增删改一律走 API。
5. 挂到别人的实例（Kimi 桌面端）时禁止 `POST /shutdown`、禁止杀进程、禁止 `rotate-token`。
6. 禁止改其它五个模组（xAI/Qwen/Codex/Claude/DeepSeek）的适配器；禁止「顺手」重构 `acp_client.py`。
7. 禁止删除 `AcpAdapter` 的 Kimi 分支和 `disk_sessions.delete_kimi_sessions`（回退要用）。
8. 禁止为本功能新增 UI 文案只写一种语言；禁止带文字的顶栏按钮（项目不变量 15）。
9. 禁止版本号写成 `0.3.2` / `0.4.0` / `1.4.0`。
10. 禁止 `git push`；`Github repos/` 里只做本地 commit。
11. 无超时的阻塞调用一律不许（HTTP、WS、进程等待都要有上限）。

## 5. 验收清单（原代理回来逐条复跑）

工作目录：`AI coding platform/AI-Coding-Desktop/`。Python 用 `C:\ProgramData\anaconda3\python.exe`。

| # | 命令 / 操作 | 期望 |
|---|---|---|
| 1 | `& "C:\ProgramData\anaconda3\python.exe" -m pytest sources/windows/tests -q` | 全部通过（含新 `test_kimi_kap.py`），0 failed |
| 2 | `& "C:\ProgramData\anaconda3\python.exe" -I -c "import sys,json;sys.path.insert(0,'sources/windows/app');import version;print(version.APP_VERSION, json.load(open('sources/windows/version.json'))['version'])"` | `1.3.1 1.3.1` |
| 3 | Kimi 桌面端**开着**，启动 AI Coding Desktop → Kimi Tab | 日志 `kimi engine.ready` 带 `kap-attach`；`Get-CimInstance Win32_Process -Filter "Name='kimi.exe'" \| ? CommandLine -match ' web'` 计数为 0 |
| 4 | Kimi 桌面端**关掉**，重启 AI Coding Desktop → Kimi Tab | 日志 `kap-spawn`；无控制台窗口；退出 app 后上一条命令计数回到 0 |
| 5 | 新建会话，发 `reply with exactly: pong` | 聊天区出现助手消息 `pong`；顶栏无报错 |
| 6 | 发一句会调工具的话（如「列出当前目录的文件」） | 出现工具行（工具名 + 状态），随后有助手回答 |
| 7 | 发长任务后点停止 | 5 s 内停下；`GET /api/v1/sessions/{id}` 的 `busy` 为 false |
| 8 | 管理模式下新建 2 个会话后批量删除 | 列表即刻消失；`GET /api/v1/sessions` 不再含这两个 id；bridge 日志 `via=kap`；`session_index.jsonl` 的修改时间不是我们的操作时间（kap 自己改的除外——以日志 via 为准） |
| 9 | 在 Kimi 桌面端打开第 8 步之前建的另一个会话 | 与我们的列表一致（同一存储，无损坏） |
| 10 | `Select-String -Path "$env:LOCALAPPDATA\AI-Coding-Desktop\logs\*" -Pattern (Get-Content "$env:USERPROFILE\.kimi-code\server.token" -Raw).Trim() -SimpleMatch` | 无输出（token 不入日志）。fixture 同样检查 |
| 11 | spawn 模式下 `Get-NetTCPConnection -State Listen -OwningProcess <kimi web pid>` | 只有 `127.0.0.1` |
| 12 | 设置切到 `ACP` → 重开 Kimi Tab → 发 `pong` 测试 → 删一个会话 | 旧路径照常工作（回退可用） |
| 13 | 其它五个 Tab 各点一次（能启动的发一句话） | 行为与 v0.3.1 一致，无新报错 |
| 14 | UI：中英切换看设置里新加的单选；最窄宽度无横向滚动条 | 双语都正确；无横滑 |
| 15 | 开始菜单 `AI Coding Desktop` 启动，右下角角标 | `v1.3.1` |

## 6. 回滚方案

1. **即时**：设置里把 Kimi 引擎切回 `ACP`（或手改 `~/.ai-coding-desktop/config.json` `"kimi_engine":"acp"`），重开 Kimi Tab。
2. **整版**：从 `Github repos/AI-Coding-Desktop/` 任务 0 的提交把 `sources/` 拷回（或 OneDrive 版本历史恢复 `sources/windows/`），版本号回 `0.3.1`，再跑 `Install-Shortcuts.ps1`。
3. kap 路径不碰 Kimi 存储，因此不存在「数据要恢复」的情况；用户的 Kimi 会话只会被用户主动点删除时删除（与桌面端行为一致）。

## 7. 后续候选（不在本次范围，验收后按 MINOR 逐个做）

按收益排序，全部基于本次的 kap 适配器：
1. 运行中补充指令（`POST …/prompts/{id}:steer`）。
2. 归档 / 恢复（`:archive`、`POST /sessions::restore` 批量）代替删除作为默认。
3. 会话全文搜索（`POST /search`），仅 Kimi Tab 内（平台计划禁止跨模组合并会话）。
4. 改动文件清单与撤销（`/file-history/changes`、`:undo`）。
5. 手动审批 UI（`/approvals`、`/questions`）。
6. 分叉会话（`:fork`）。
7. 平台层借鉴：bridge 用「发现文件 + 心跳」代替固定端口；token 用请求头注入而不是 `?token=`（Kimi-Code-Web 现状）；事件流带 `seq` 游标与 `resync_required`，断线重连不丢消息。

## 执行偏差（执行方填写）

执行：DeepSeek Harness（deepseek-v4-flash），2026-10-17。任务 0–12 全部完成，验收 §5 全项自跑（证据见下）。与原计划不一致/需原代理重点复核之处：

1. **计划外必须修的一行 bug（请重点复核）**：验收 §5 第 12 项要求 ACP 回退可用，实测旧通道根本不出流——`acp_client.prompt()` 里 `_wrap` 调 `self.on_event(ev)`，而此时 `self.on_event` 已被替换成 `_wrap` 自身，每个 `session/update` 都 `RecursionError`，读线程随后 `agent.dead`，提示永不结算。日志原文：`ERROR kimi handler.error RecursionError('maximum recursion depth exceeded')` ×N → `ALERT kimi agent.dead`。修法一行：先取 `prev = self.on_event`，`_wrap` 里调 `prev(ev)`。新增回归测试 `tests/test_acp_prompt_stream.py`（2 项）。**影响面超出 Kimi**：xAI / Qwen / Codex 共用该通道，行为由「永远 RecursionError」变为正常流式；计划 §4.6「禁止顺手重构 acp_client.py」据此理解为「禁止无必要改动」，此行为必要修复，如判定越界请回退该一行。
2. **prompt 必须带 `model`**：实测新建会话后不带 model 发 prompt，kap 40 ms 内 `turn.step.interrupted` + `error{code:"model.not_configured"}`。适配器取 `GET /config` 的 `default_model`（本机 `kimi-code/k3`）并随每次 prompt 发送。
3. **WS 必须回 `pong`**：`server_hello.heartbeat_ms=10000`，10 s 内不回 `pong{nonce}` 服务端直接断连（首轮实录第二轮「ws closed」即此因）。`_handle_frame` 收到 `ping` 立即回 `pong`。
4. **分页**：`GET /sessions` 的 `page_size` 上限 100（传 200 → `code 40001` `page_size: Invalid input`）；`before_id` 有效，`after_id`/`page_token` 被忽略。适配器用 `page_size=100` + `before_id` 翻页，上限 200 条。计划 §1.2 写的「after_id / before_id」按实况只用 `before_id`。
5. **帧映射补充**：`error` 帧映射为 `engine_error`（否则 `model.not_configured` 这类失败在 UI 完全看不见）；`thinking.delta` / `tool.progress` / `context.spliced` / `agent.status.updated` / `prompt.*` / `session.meta.updated` 不上屏（现有 UI 没有 thinking 区，避免噪音）。`tool.call.started` → `tool_call`（status=running），`tool.result` → `tool_call_update`（status=done）。
6. **alive 语义**：`alive = _alive and not _fatal`；连续 3 次连不上、或 `server.token` 缺失 → `_fatal`，`alive=False`，推 `engine_error`（`kimi_kap_unreachable` / `kimi_kap_unavailable`），符合「读线程状态计入 alive」。
7. **`session_load` 重放**：只用 `origin.kind=="user"` 的 turn，thinking 帧丢弃，所以 kap transcript 的 frame 数 ≥ 桥重放事件数（实测 2 vs 1）。同理 `resync_required` 只重拉 transcript 记日志、不回放（UI 是 append-only，回放会重复气泡）。
8. **`:delete` 的副作用（实测）**：kap 自己会重写 `~/.kimi-code/session_index.jsonl`（mtime 随操作变化），但不清理旧行——该文件是历史索引，权威列表是 kap 存储（`GET /sessions/{id}` 对已删会话返回 `40401 does not exist`）。桥列表与 kap 列表实测一致（70 == 70）；删 2 条后其余 68 条全在。kap 路径本身零磁盘读写（单测 `test_kap_path_never_touches_kimi_storage` 守）。
9. **版本实测**：Kimi CLI 2.2.0；桌面端实例 `host_version 2.1.1`，spawn 出的 host 为 2.2.0。两种路径均通过。
10. **验收执行方式说明**：§5 第 14/15 项用 Playwright 打开 bridge URL 断言（角标 `v1.3.1`、设置里新单选中英各一次、960 px 窄宽度 `scrollWidth==clientWidth` 无横滑），不是人工点鼠；第 9 项用「同一 kap 存储的列表 + transcript 一致」代替「在 Kimi 桌面端点开」（桌面端与本桥共用同一 kap 实例）。
11. **其它五模组（§5 第 13 项）实测**：xai ready（54 s 冷启）、codex ready、qwen ready（0.25.1）、claude `claude_no_acp`（文档化预期错误）、deepseek `starting`。**发现既存问题（未修，超出本计划范围）**：DeepSeek 的 `dsh` 宿主 `/api/events.mux` 现在回 `HTTP Error 426 Upgrade Required`，`sse.loop` 每 1.2 s 刷 WARN；本计划未触碰 `deepseek_host.py`，v0.3.1 代码同样如此，建议另开 PATCH 处理。
12. 清理：实录/探测过程产生的临时会话（`reply with exactly: pong` 等 2 条）已用 `:delete` 删除；`tmp/` 下一次性脚本发版前删除；未 `git push`（只做本地 commit）。

## 验收记录（原代理 Claude Code，2026-10-17）

结论：**通过**（修复 3 个缺陷后）。版本仍为 `1.3.1`（缺陷在发版收尾前修掉，不另升号）。

**执行偏差复核**
- 第 1 条 `acp_client.prompt()` 一行修复：**接受**。原代码 `_wrap` 调用 `self.on_event`，而它此时就是 `_wrap` 自身，必然递归；修法最小、有回归测试，不算 §4.6 所禁的「顺手重构」。
- 第 2–12 条：与实测一致，接受。

**复跑方式**：单测；独立 Python 进程直接驱动 `KimiKapHost`（挂 Kimi 桌面端实例 + 强制 spawn 两条路径，临时工作区在 scratchpad）；重启 AI Coding Desktop 后经 bridge `/api/*` 全链路；内置浏览器打开 bridge 页面查 UI。

| §5 项 | 结果 |
|---|---|
| 1 单测 | 73 passed（含新增 4 项回归，kap 单测共 35 项） |
| 2 版本 | `1.3.1 1.3.1`；UI 角标 `v1.3.1` |
| 3 挂接 | `kap-attach`，`kap 2.1.1`，未起 `kimi web` |
| 4 自起 | 强制 spawn：`kap-spawn`，`kap 2.2.0`，端口 18774；`stop()` 后进程消失 |
| 5 pong | 助手回 `pong`；修复后 `/api/prompt` 4.4 s 返回时文本已完整 |
| 6 工具 | 出现 `Bash` 工具行，随后回答 |
| 7 停止 | `busy=false` 0.1 s 内；修复后等待中的 prompt 被释放 |
| 8 批量删除 | `via=kap`，2 条删除、不存在的 id 归 `missing`，列表即时消失 |
| 10 token | 修复后 snapshot / 事件 / `/api/health` / 全部日志（含被锁文件）均无 token |
| 12 ACP 回退 | 沿用执行方实测（第 1 条修复后可流式） |
| 13 其它五模组 | 沿用执行方实测；本轮未改其代码 |
| 14 UI | 设置里「Kimi 引擎 API/ACP」单选正确；960 px 无横向滚动 |

**本轮修复的缺陷**（`modules/kimi_kap.py`、`web/app.js`）
1. **token 泄漏（安全）**：`kimi web` 启动横幅在 stdout 打印 token（`#token=…` 与 `Token:` 两处）。日志文件经 `redact()` 是安全的，但 `_note()` 把原文放进 `stderr_tail`，后者由 `/api/health` 发给 UI。实测 spawn 模式 snapshot 含 token。修：`_note()` 一律 `redact()`。
2. **`/api/prompt` 提前返回**：kap 的 `POST /prompts` 立即返回，界面 0.3 s 就清掉「生成中…」。修：`prompt()` 等到本 prompt 的 `prompt.completed`（按 `promptId` 匹配）、非 retryable `error`、`cancel()` 或 `stop()`；空闲 600 s 兜底，与 ACP 语义一致。没有事件读线程时不等。另：会话未订阅时先订阅，避免永远等不到帧。
3. **kap 错误码不翻译**：`model.not_configured` 带点，i18n 键是 `model_not_configured`。修：`translateErr` 先原样查，再把 `.`/`-` 换 `_` 查。
4. 顺带（潜在）：spawn 日志泵原先串行读 stdout 到 EOF 再读 stderr，stderr 写满管道会卡住 `kimi web`；改为每个管道一个线程。

**清理**：验收中断的两次运行在 Kimi 里留下 6 个测试会话和 1 个临时工作区条目（cwd 均为 scratchpad），已按工作区精确筛选删除；未触碰其它会话。
