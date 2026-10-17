"""One engine adapter per module + in-memory event log for the UI."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from acp_client import AcpError
from config import load_config, resolved_cli
from logging_setup import log
from modules.acp_engine import AcpAdapter
from modules.deepseek_host import DeepSeekAdapter, DeepSeekHost
from modules.kimi_kap import KimiKapAdapter, KimiKapHost
from paths import MODULES, is_qwen_code_binary  # re-exported for server.py
from win_cli import claude_acp_argv, wrap_argv


def spawn_argv(module: str, binary: str) -> tuple[list[str], dict[str, Any] | None]:
    if module == "kimi":
        return wrap_argv(binary, ["acp"]), None
    if module == "xai":
        return wrap_argv(binary, ["agent", "stdio"]), {"methodId": "cached_token"}
    if module == "qwen":
        return wrap_argv(binary, ["--acp"]), None
    if module == "codex":
        return wrap_argv(binary, ["app-server"]), None
    if module == "claude":
        return claude_acp_argv(binary), None
    raise AcpError(f"unknown_acp_module:{module}")


class ModuleSlot:
    def __init__(self, name: str) -> None:
        self.name = name
        self.adapter: Any = None
        self.lock = threading.Lock()
        self.events: list[dict[str, Any]] = []
        self.seq = 0
        self.state = "idle"
        self.error = ""
        self.draft = ""
        self.cache_hit: dict[str, Any] | None = None

    def _push(self, ev: dict[str, Any]) -> None:
        self.seq += 1
        item = {"seq": self.seq, **ev}
        self.events.append(item)
        self.events = self.events[-800:]
        if ev.get("type") == "cache" and ev.get("cache_hit"):
            self.cache_hit = ev["cache_hit"]

    def on_event(self, ev: dict[str, Any]) -> None:
        kind = ev.get("type")
        if kind == "agent_exit":
            self.state = "error"
            tail = ev.get("stderr") or []
            first = ""
            if isinstance(tail, list) and tail:
                first = str(tail[0])
            elif isinstance(tail, str):
                first = tail
            detail = first or f"code={ev.get('code')}"
            if not self.error or self.error in ("agent_exit", "agent_connection_closed"):
                self.error = detail
        if kind == "engine_error":
            self.state = "error"
            self.error = str(ev.get("code") or ev.get("text") or "engine_error")
        if kind == "engine_ready":
            self.state = "ready"
            self.error = ""
        self._push(ev)

    def snapshot(self) -> dict[str, Any]:
        extra = self.adapter.snapshot() if self.adapter else {}
        return {
            "name": self.name,
            "state": self.state,
            "error": self.error or extra.get("error") or "",
            "alive": bool(self.adapter.alive) if self.adapter else False,
            "session_id": extra.get("session_id"),
            "model": extra.get("model") or "",
            "mode": extra.get("mode") or "",
            "config_options": extra.get("config_options") or [],
            "agent_version": extra.get("agent_version") or "",
            "stderr_tail": extra.get("stderr_tail") or [],
            "seq": self.seq,
            "cache_hit": self.cache_hit or extra.get("cache_hit"),
            "acp": extra.get("acp"),
        }


class Runtime:
    def __init__(self) -> None:
        self.slots = {m: ModuleSlot(m) for m in MODULES}
        self.active = "kimi"

    def set_active(self, module: str) -> None:
        if module not in self.slots:
            raise AcpError("unknown_module")
        prev = self.active
        self.active = module
        log("INFO", "shell", "tab.switch", f"{prev} → {module}")

    def slot(self, module: str | None = None) -> ModuleSlot:
        return self.slots[module or self.active]

    def start_module(self, module: str) -> dict[str, Any]:
        cfg = load_config()
        binary = resolved_cli(module, cfg)
        if not binary:
            log("ALERT", module, "cli.missing", "binary not found")
            raise AcpError("cli_not_found")
        workspace = str(cfg.get("workspace") or Path.home())
        sl = self.slots[module]
        if module == "qwen" and not is_qwen_code_binary(binary):
            log("ALERT", module, "cli.wrong", "refused non-Qwen-Code binary")
            with sl.lock:
                sl.state = "error"
                sl.error = "not_qwen_code"
            sl._push({"type": "engine_error", "code": "not_qwen_code"})
            return sl.snapshot()
        with sl.lock:
            if sl.adapter and sl.adapter.alive:
                sl.state = "ready"
                return sl.snapshot()
            if sl.adapter:
                try:
                    sl.adapter.stop()
                except Exception:
                    pass
                sl.adapter = None
            sl.state = "starting"
            sl.error = ""
            api = cfg.get("api") or {}
            env: dict[str, str] = {}
            if module == "kimi" and api.get("moonshot"):
                env["MOONSHOT_API_KEY"] = str(api["moonshot"])
            if module == "xai" and api.get("xai"):
                env["XAI_API_KEY"] = str(api["xai"])
            if module == "codex" and api.get("openai"):
                env["OPENAI_API_KEY"] = str(api["openai"])
            if module == "claude" and api.get("anthropic"):
                env["ANTHROPIC_API_KEY"] = str(api["anthropic"])
            if module == "qwen" and api.get("qwen"):
                env["BAILIAN_TOKEN_PLAN_API_KEY"] = str(api["qwen"])
                env["OPENAI_API_KEY"] = str(api["qwen"])
            if module == "deepseek" and api.get("deepseek"):
                env["DEEPSEEK_API_KEY"] = str(api["deepseek"])

            def _on(ev: dict[str, Any], s=sl) -> None:
                s.on_event(ev)

            if module == "deepseek":
                host = DeepSeekHost(binary, workspace, 18773, _on, env=env or None)
                sl.adapter = DeepSeekAdapter(host)
            elif module == "kimi" and str(cfg.get("kimi_engine") or "kap").lower() != "acp":
                kap = KimiKapHost(
                    binary,
                    workspace,
                    18774,
                    _on,
                    env=env or None,
                    auto_approve=bool(cfg.get("auto_approve", True)),
                )
                sl.adapter = KimiKapAdapter(kap)
                log("INFO", module, "adapter.pick", "kimi_engine=kap")
            else:
                argv, auth = spawn_argv(module, binary)
                sl.adapter = AcpAdapter(
                    module,
                    argv,
                    workspace,
                    env=env or None,
                    authenticate=auth,
                    auto_approve=bool(cfg.get("auto_approve", True)),
                    on_event=_on,
                )
                if not argv:
                    sl.state = "error"
                    sl.error = "claude_no_acp"
                    sl.adapter.error = "claude_no_acp"
                    log("WARN", module, "adapter.skip", "no ACP entry; use open terminal")
                    sl._push({"type": "engine_error", "code": "claude_no_acp"})
                    return sl.snapshot()
        try:
            info = sl.adapter.start()
            if sl.adapter.alive:
                sl.state = "ready"
                log("INFO", module, "agent.ready", sl.snapshot().get("agent_version") or "")
            elif isinstance(info, dict) and info.get("starting"):
                sl.state = "starting"
                log("INFO", module, "agent.starting", sl.snapshot().get("agent_version") or "dsh-host")
            else:
                sl.state = "error"
                sl.error = sl.snapshot().get("error") or sl.error or "start_failed"
            return sl.snapshot()
        except Exception as e:
            sl.state = "error"
            sl.error = str(e)
            log("ERROR", module, "agent.start", str(e))
            raise

    def ensure_started(self, module: str, *, retry: bool = False) -> dict[str, Any]:
        sl = self.slots[module]
        if sl.adapter and sl.adapter.alive:
            sl.state = "ready"
            return sl.snapshot()
        if sl.state == "starting" and sl.adapter:
            return sl.snapshot()
        if sl.state == "error" and sl.error and not retry:
            return sl.snapshot()
        return self.start_module(module)

    def stop_all(self) -> None:
        for sl in self.slots.values():
            if sl.adapter:
                try:
                    sl.adapter.stop()
                except Exception:
                    pass


def delete_sessions_batch(adapter: Any, ids: list[Any]) -> dict[str, Any]:
    """Delete many sessions; one failure does not abort the rest."""
    deleted: list[str] = []
    failed: list[dict[str, str]] = []
    missing: list[str] = []
    if adapter is None:
        return {"ok": False, "error": "engine_offline", "deleted": [], "deleted_count": 0, "failed": [], "missing": []}
    many = getattr(adapter, "session_delete_many", None)
    if callable(many):
        return many(list(ids))
    for raw in ids:
        sid = str(raw or "").strip()
        if not sid:
            continue
        try:
            info = adapter.session_delete(sid)
        except Exception as e:
            failed.append({"sessionId": sid, "error": str(e)[:160]})
            continue
        if isinstance(info, dict) and info.get("ok") is False:
            err = str(info.get("error") or "delete_failed")
            if err in ("delete_unsupported", "not_found"):
                missing.append(sid)
            else:
                failed.append({"sessionId": sid, "error": err})
            continue
        deleted.append(sid)
    return {
        "ok": not failed,
        "deleted": deleted,
        "deleted_count": len(deleted),
        "failed": failed,
        "missing": missing,
    }


RUNTIME = Runtime()
