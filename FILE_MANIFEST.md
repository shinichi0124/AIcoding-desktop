# FILE_MANIFEST — AI Coding Desktop

> 2026-10-17 v1.3.2 DeepSeek 事件流改 WebSocket（修 426）；v1.3.1 Kimi Tab 改走 kap-server API（未打包 zip）

| 路径 | 类型 | 用途 | 可安全删除？ |
|------|------|------|-------------|
| `Launch-Desktop.bat` | 源码 | 带控制台日常启动 | 否 |
| `Launch-Desktop-Silent.vbs` | 源码 | 快捷方式无窗口启动 | 否 |
| `Install-Shortcuts.ps1` | 源码 | 开始菜单/桌面稳定快捷方式 | 否 |
| `scripts/make_icon.py` | 源码 | 生成 G+ai 经典 BMP ICO | 否 |
| `scripts/Sync-To-GithubRepo.ps1` | 源码 | 同步到 `Github repos/AI-Coding-Desktop/`（不推送） | 否 |
| `LICENSE` | 文档 | MIT，Dr. GENG Xun | 否 |
| `.gitignore` | 配置 | 不提交缓存/密钥/日志 | 否 |
| `docs/AUDIT_2026-08-23.md` | 文档 | 对照计划的完成度/遗漏 | 否 |
| `docs/LESSONS.md` | 文档 | 项目专属教训 | 否 |
| `docs/PLAN_kimi-kap-adapter_20261017.md` | 文档 | §B.27 计划书：Kimi Tab 改走 kap-server API（v1.3.1），含验收清单与执行偏差 | 否 |
| `docs/AI_DESCRIPTION.md` / `.html` | 文档 | 简述；html 仅供查阅 | 否 |
| `sources/windows/app/web/assets/ai-coding-desktop.ico` | 源码 | 任务栏安全 ICO（16/24/32/48 BMP） | 否 |
| `sources/windows/app/web/assets/ai-coding-desktop.png` | 源码 | 256 图标 | 否 |
| `README.md` / `START_HERE.md` / `AGENTS.md` / `FILE_MANIFEST.md` / `HANDOFF.md` | 文档 | 五件套（HANDOFF = 交接文件，§D.5） | 否 |
| `sources/windows/app/version.py` | 源码 | APP_VERSION（单一源） | 否 |
| `sources/windows/version.json` | 配置 | 版本号（与 version.py 同步） | 否 |
| `sources/windows/app/bridge/` | 源码 | 日志、ACP、HTTP、桌面窗、supervisor | 否 |
| `sources/windows/app/bridge/win_cli.py` | 源码 | `%ComSpec%` wrap、可见终端 argv、`kimi_web_argv` | 否 |
| `sources/windows/app/bridge/modules/kimi_kap.py` | 源码 | **Kimi kap 适配器**：实例发现 + token + HTTP + WS 线程 + 帧映射（`KimiKapHost` / `KimiKapAdapter`） | 否 |
| `sources/windows/app/bridge/modules/` | 源码 | 其它适配器：ACP / DeepSeek host / 磁盘会话 / 凭据 | 否 |
| `sources/windows/app/web/` | 源码 | 聊天 UI（`index.html` / `app.js` / `styles.css`） | 否 |
| `sources/windows/app/web/g-logo.png` | 源码 | 顶栏 G 标 | 否 |
| `sources/windows/app/web/logos/` | 源码 | 六家官网 logo SVG | 否 |
| `sources/windows/tests/` | 源码 | 适配器 / Kimi 存储删除 / DeepSeek 隐藏启动 / 日志合同 | 否 |
| `sources/windows/tests/test_kimi_kap.py` | 源码 | kap 适配器 35 项单测（实录帧回放、发现/鉴权/删除/abort/时序；含验收修复的 token 脱敏与 prompt 等待回归） | 否 |
| `sources/windows/tests/test_acp_prompt_stream.py` | 源码 | ACP prompt 自递归回归（v1.3.1 验收发现并修复） | 否 |
| `sources/windows/tests/test_deepseek_mux.py` | 源码 | DeepSeek mux WebSocket 回归 10 项（实录帧回放、注入消息过滤、turn/end 等待、归档过滤） | 否 |
| `sources/windows/tests/fixtures/dsh_mux_frames.jsonl` | 数据 | 2026-10-17 实录 dsh `/api/events.mux` 帧（已脱敏：系统提示/技能目录裁掉、无本机路径），单测回放源 | 否（单测依赖） |
| `sources/windows/tests/fixtures/kap_ws_frames.jsonl` | 数据 | 2026-10-17 实录 kap WS 帧（已脱敏：无 token、无用户名路径），单测回放源 | 否（单测依赖） |
| `sources/windows/requirements.txt` | 配置 | pywebview / pystray / Pillow / websocket-client | 否 |
| `sources/windows/app/bridge/__pycache__/` | 构建产物 | Python 缓存 | 是 |
