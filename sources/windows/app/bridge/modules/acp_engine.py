"""ACP adapter wrapping AcpClient + disk session fallback."""
from __future__ import annotations

from typing import Any, Callable

from acp_client import AcpClient, AcpError
from logging_setup import log
from modules import disk_sessions
from version import APP_VERSION


class AcpAdapter:
    def __init__(
        self,
        name: str,
        argv: list[str],
        workspace: str,
        *,
        env: dict[str, str] | None,
        authenticate: dict[str, Any] | None,
        auto_approve: bool,
        on_event: Callable[[dict[str, Any]], None],
    ) -> None:
        self.name = name
        self.workspace = workspace
        self._on_event = on_event
        self.client = AcpClient(
            name,
            argv,
            workspace,
            env=env,
            auto_approve=auto_approve,
            authenticate=authenticate,
            client_version=APP_VERSION,
            on_event=on_event,
        )
        self._acp_ok = False
        self.error = ""

    @property
    def alive(self) -> bool:
        return bool(self.client.alive)

    def start(self) -> dict[str, Any]:
        try:
            self.client.start()
            self._acp_ok = True
            self.error = ""
            return self.snapshot()
        except AcpError as e:
            self._acp_ok = False
            tail = self.client.stderr_tail
            detail = str(e)
            if tail:
                detail = f"{e}: {tail[0]}"
            self.error = detail
            log("ERROR", self.name, "agent.start", detail)
            log("WARN", self.name, "adapter.fallback", "ACP handshake failed; session list may use disk index")
            self._on_event({"type": "engine_error", "code": detail, "text": detail})
            return self.snapshot()

    def stop(self) -> None:
        try:
            self.client.stop()
        except Exception:
            pass

    def prompt(self, text: str) -> dict[str, Any]:
        if not self.client.alive:
            raise AcpError("engine_not_acp")
        return self.client.prompt(text)

    def cancel(self) -> None:
        if self.client.alive:
            self.client.cancel()

    def session_list(self) -> list[dict[str, Any]]:
        if self.client.alive:
            rows = self.client.list_sessions()
            if rows:
                return rows
            log("WARN", self.name, "session.list", "ACP empty, trying disk")
        return self._disk_list()

    def session_new(self) -> dict[str, Any]:
        if not self.client.alive:
            raise AcpError("engine_not_acp")
        return self.client.new_session()

    def session_load(self, session_id: str) -> dict[str, Any]:
        if not self.client.alive:
            raise AcpError("engine_not_acp")
        return self.client.load_session(session_id)

    def session_delete(self, session_id: str) -> dict[str, Any]:
        if self.name == "kimi":
            batch = self.session_delete_many([session_id])
            if batch.get("deleted_count") or batch.get("ok"):
                return {"ok": True, "via": "kimi_store"}
            err = ""
            failed = batch.get("failed") or []
            if failed:
                err = str(failed[0].get("error") or "")
            return {"ok": False, "error": err or batch.get("error") or "delete_failed"}
        if self.client.alive:
            try:
                self.client.session_delete(session_id)
                return {"ok": True, "via": "acp"}
            except AcpError as e:
                log("WARN", self.name, "session.delete", str(e))
        rows = self._disk_list()
        if disk_sessions.delete_by_id(rows, session_id):
            return {"ok": True, "via": "disk"}
        return {"ok": False, "error": "delete_unsupported"}

    def session_delete_many(self, session_ids: list[str]) -> dict[str, Any]:
        """Kimi: stop ACP once, then purge dirs + session_index.jsonl."""
        if self.name != "kimi":
            deleted: list[str] = []
            failed: list[dict[str, str]] = []
            missing: list[str] = []
            for raw in session_ids:
                sid = str(raw or "").strip()
                if not sid:
                    continue
                info = self.session_delete(sid)
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
        stop_err = self._stop_for_storage()
        if stop_err:
            log("ERROR", self.name, "session.delete", f"agent_stop_failed: {stop_err}")
            return {
                "ok": False,
                "error": f"agent_stop_failed: {stop_err}",
                "deleted": [],
                "deleted_count": 0,
                "failed": [{"error": stop_err}],
                "missing": [],
            }
        out = disk_sessions.delete_kimi_sessions(session_ids)
        failed = [
            {"sessionId": str(e.get("sessionId") or ""), "error": str(e.get("error") or "")}
            for e in (out.get("errors") or [])
        ]
        purged = list(out.get("deleted") or []) + list(out.get("missing") or [])
        ok = bool(out.get("ok")) and not failed
        log("INFO", self.name, "session.delete", f"kimi_store n={len(purged)} index={out.get('index_removed')}")
        return {
            "ok": ok,
            "deleted": purged,
            "deleted_count": len(purged),
            "failed": failed,
            "missing": list(out.get("missing") or []),
            "via": "kimi_store",
            "index_removed": int(out.get("index_removed") or 0),
            "error": out.get("error"),
        }

    def _stop_for_storage(self) -> str | None:
        if not self.client.alive:
            return None
        try:
            self.client.stop()
            self._acp_ok = False
            return None
        except Exception as e:
            return str(e)

    def set_config(self, config_id: str, value: Any) -> Any:
        if not self.client.alive:
            raise AcpError("engine_not_acp")
        return self.client.set_config_option(config_id, value)

    def snapshot(self) -> dict[str, Any]:
        c = self.client
        return {
            "name": self.name,
            "alive": self.alive,
            "acp": self._acp_ok,
            "error": self.error,
            "session_id": c.session_id,
            "model": c.current_model,
            "mode": c.current_mode,
            "config_options": c.config_options,
            "agent_version": c.agent_version,
            "stderr_tail": list(c.stderr_tail[-8:]),
        }

    def _disk_list(self) -> list[dict[str, Any]]:
        if self.name == "qwen":
            return disk_sessions.list_qwen(self.workspace)
        if self.name == "codex":
            return disk_sessions.list_codex()
        if self.name == "claude":
            return disk_sessions.list_claude(self.workspace)
        return []
