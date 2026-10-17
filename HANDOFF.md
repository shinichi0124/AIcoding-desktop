# AI Coding Desktop 交接文件（HANDOFF）

> 规则：每次任务结束必须更新本文件（工作区 AGENTS.md §D.5）。
> 新会话/新模型接手：先读 AGENTS.md（或 CLAUDE.md）+ 本文件，再开工。
> 最后更新：2026-10-17 · by Claude Code (Opus 5.5)

## 当前状态
- 当前版本与运行入口：**v1.3.2**（可运行，未打包 zip）；运行 = 开始菜单/桌面「AI Coding Desktop」或双击 `Launch-Desktop.bat`（Anaconda `C:\ProgramData\anaconda3\python.exe` + pywebview）。开始菜单/桌面快捷方式已就地更新。
- **Kimi Tab 默认走 Kimi 自带本地 API（kap-server）**：`KimiKapHost` 先挂运行中的 Kimi Code 桌面实例，挂不上才 `kimi web --no-open --port 18774`（端口占用顺延 18775–18779）。设置里「Kimi 引擎：API / ACP」可切回旧 `kimi acp` 通道（`~/.ai-coding-desktop/config.json` `kimi_engine`）。
- 正在进行的工作：无。计划书 `docs/PLAN_kimi-kap-adapter_20261017.md` 状态 **已验收**（2026-10-17，Claude Code 复跑 §5 并修 3 个缺陷，记录见该文件末尾「验收记录」）。

## 上次任务做了什么
- 2026-10-17（v1.3.2，Claude Code）：修 DeepSeek Tab 无输出——dsh 0.1.0-rc.6 的 `/api/events.mux` 改为只下行 WebSocket（旧 SSE GET 回 426）；`deepseek_host.py` 改连 WS、按实录帧重写映射、`/api/prompt` 等 `turn/end`、列表过滤已归档会话。新增 `tests/test_deepseek_mux.py` + `fixtures/dsh_mux_frames.jsonl`；全量 83 passed；重启 app 实测 DeepSeek 回 `pong`、删除后列表消失、日志无 426/`sse.loop`。
- 2026-10-17（验收，Claude Code）：复跑计划 §5 全部通过；修 `kimi_kap.py` 三处——`stderr_tail` 脱敏（`kimi web` 启动横幅打印 token，经 `/api/health` 外泄）、`/api/prompt` 等到 `prompt.completed` 再返回、日志泵每管道一线程；`app.js` `translateErr` 支持带点错误码。新增 4 项回归测试（全量 73 passed）。接受执行偏差第 1 条（`acp_client.py` 一行修复）。清理了验收在 Kimi 里留下的 6 个测试会话。
- 2026-10-17（本任务，执行 §B.27 计划书）：新增 `sources/windows/app/bridge/modules/kimi_kap.py`（实例发现 + token + HTTP + WS 线程 + 帧映射 + 适配器）；`config.py` 加 `kimi_engine`（默认 `kap`）；`module_runtime.start_module` 按开关建 kap/ACP 适配器；`win_cli.kimi_web_argv`；设置面板加「Kimi 引擎：API/ACP」单选（中英同步）；Kimi 删除改 `POST /sessions/{id}:delete`（磁盘删除只留给 ACP 回退）；实录 kap WS 帧成 `tests/fixtures/kap_ws_frames.jsonl`（脱敏）+ `tests/test_kimi_kap.py`（31 项）。
- 同轮修的既存缺陷（计划外、必要）：`acp_client.prompt()` 的 `_wrap` 自递归 → 每个 `session/update` 都 RecursionError、ACP 通道不出流；一行修复 + `tests/test_acp_prompt_stream.py`。
- 版本 `0.3.1 → 1.3.1`（§B.13 第 2 步 ⑤）；文档五件套 + `CHANGELOG` + `docs/LESSONS.md`（4 条新教训）+ `docs/AI_DESCRIPTION.md/.html` 同步。
- 全量单测 **69 passed**；验收 §5 逐项自跑（attach/spawn/工具调用/停止/批量删除/ACP 回退/token 不透/端口/UI 双语/角标）。

## 下一步 / 待办
- [ ] 打包 zip 尚未做（项目当前形态为源码直跑）；若推进，按 §E.1 + skill `desktop-code-web-shell`。
- [ ] 后续候选（计划 §7）：steer 补充指令、归档代替删除、会话搜索、改动文件清单、手动审批 UI、分叉会话、bridge 事件游标复用。
- [ ] 子项目各自维护自身 HANDOFF.md（Kimi-Code-Web / xAI-Code-Web / AI-Coding-Desktop / DeepSeek-Harness / QwenCloud-CLI）。

## 未决问题 / 已知坑
- kap 新会话不带 `model` 发 prompt 必然 `model.not_configured`；WS 不回 `pong` 10 s 内被断；`kimi web` 启动时在 stdout 打印 token（进 UI 的输出必须 `redact()`）。细节见 `docs/LESSONS.md`。
- 挂 Kimi 桌面实例时禁止 `/shutdown`、杀进程、`rotate-token`；只有自己 spawn 的 `kimi web` 才 terminate（`self.owned` 判据）。
- `~/.kimi-code/session_index.jsonl` 是历史索引：kap 的 `:delete` 会重写它但不清理旧行，权威列表是 kap 存储。
- 用户配置当前 `close_action: "tray"`（点 × 只是收进托盘）；要优雅退出（触发 `stop_all` 收掉 spawn 的 `kimi web`）需先切 `quit` 或走托盘菜单退出。
- Claude 官方 CLI 没有 `--acp`，`claude_no_acp` 是预期错误，不是新故障。
- Qwen Tab 只接 Qwen Code（`%LOCALAPPDATA%\qwen-code\bin\qwen.cmd`），禁止 `qwencloud`。

## 新模型必读上下文
- 入口/不可移动：本目录 `Launch-Desktop.bat` / `Launch-Desktop-Silent.vbs`（快捷方式 TargetPath 指向它）；版本单一源 `sources/windows/app/version.py`（与 `version.json`、UI 角标一致）。
- 架构：bat/vbs → `supervisor.py` → `desktop.py` + HTTP bridge → `sources/windows/app/bridge/modules/` 一模组一适配器（ACP / dsh host / **kap**）。
- 规则文件：本目录 `AGENTS.md`（不变量全集，含 kap 两条）；通用规则见工作区 `AI projects/AGENTS.md`。
- Git 双目录：本文件夹无 `.git`；暂存副本 `AI projects/Github repos/AI-Coding-Desktop/`（本版已本地 commit，**未 push**）。同步：`scripts/Sync-To-GithubRepo.ps1`。**未获当次明确指令不要 git push**。
- 日志：`%LOCALAPPDATA%\AI-Coding-Desktop\logs\`（`LATEST` 是指针文件）；配置：`%USERPROFILE%\.ai-coding-desktop\config.json`。
- 计划与审计：`docs/PLAN_kimi-kap-adapter_20261017.md`（现行）、`docs/AUDIT_2026-08-23.md`、父目录 `../docs/PLATFORM_PLAN_2026-08-21.md`。
