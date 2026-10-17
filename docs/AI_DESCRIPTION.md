# AI Coding Desktop

与 Kimi/xAI Code-Web 同一套交互的整合前端（v1.3.2，未打包 zip）。Tab 用各家官网 logo 切换 Kimi / xAI / Codex / Claude / Qwen Code / DeepSeek 引擎模组。顶栏 G 砖 + `Coding platform`。聊天记录：全选 / 多选 / 删除所选。

**Kimi（v1.3.1 起）**：不接 `kimi acp`，改接 Kimi 自带的本地服务（kap-server，HTTP + WebSocket）。先挂正在运行的 Kimi Code 桌面实例（token 只走请求头，不进日志），挂不上才起 `kimi web --no-open`；删除对话由 Kimi 自己处理（`POST /sessions/{id}:delete`），不再改写它的索引文件。设置里可切回 ACP 通道。

**其它模组：** xAI / Qwen Code / Codex / Claude 走 ACP（Qwen 只接 `qwen`，不接 `qwencloud`；Claude 官方 CLI 没有 ACP 则提示开终端）。DeepSeek 隐藏启动官方 `dsh`（不弹 CMD、不嵌其网页）。

日志：`%LOCALAPPDATA%\AI-Coding-Desktop\logs`，先看 `LATEST` 指向的 `IMPORTANT.log`。配置：`~/.ai-coding-desktop/config.json`（`kimi_engine`: `kap` | `acp`）。审计：`AUDIT_2026-08-23.md`；Kimi 引擎计划：`PLAN_kimi-kap-adapter_20261017.md`。
