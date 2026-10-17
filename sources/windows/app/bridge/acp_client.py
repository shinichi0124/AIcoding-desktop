"""Generic ACP JSON-RPC client. Transport copied from proven Kimi 64KB read loop."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from logging_setup import current_run, log
from win_cli import resolve_exe


class AcpError(Exception):
    pass


class AcpClient:
    def __init__(
        self,
        module: str,
        argv: list[str],
        workspace: str,
        *,
        env: dict[str, str] | None = None,
        auto_approve: bool = True,
        authenticate: dict[str, Any] | None = None,
        client_name: str = "ai-coding-desktop",
        client_version: str = "0.1.0",
        on_event: Callable[[dict[str, Any]], None] | None = None,
        extra_init: dict[str, Any] | None = None,
    ) -> None:
        self.module = module
        self.argv = list(argv)
        self.workspace = str(Path(workspace).resolve()) if workspace else str(Path.home())
        self.env = env
        self.auto_approve = auto_approve
        self.authenticate = authenticate
        self.client_name = client_name
        self.client_version = client_version
        self.extra_init = extra_init or {}
        self.on_event = on_event or (lambda _e: None)
        self.proc: subprocess.Popen[bytes] | None = None
        self._reader: threading.Thread | None = None
        self._lock = threading.Lock()
        self._pending: dict[Any, queue.Queue] = {}
        self._id = 0
        self._alive = False
        self._read_thread_alive = False
        self.session_id: str | None = None
        self.init_result: dict[str, Any] | None = None
        self.config_options: list[dict[str, Any]] = []
        self.agent_capabilities: dict[str, Any] = {}
        self.current_model: str = ""
        self.current_mode: str = ""
        self.agent_version: str = ""
        self._stderr_tail: list[str] = []
        self.history_events: list[dict[str, Any]] = []

    @property
    def alive(self) -> bool:
        return bool(self._alive and self._read_thread_alive and self.proc and self.proc.poll() is None)

    @property
    def stderr_tail(self) -> list[str]:
        return list(self._stderr_tail)

    def start(self) -> dict[str, Any]:
        if not Path(self.workspace).is_dir():
            raise AcpError(f"workspace_not_found: {self.workspace}")
        if not self.argv:
            raise AcpError("empty_argv")
        try:
            self.argv[0] = resolve_exe(self.argv[0])
        except ValueError as e:
            raise AcpError(str(e)) from e
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        env = os.environ.copy()
        if self.env:
            env.update(self.env)
        log("INFO", self.module, "agent.spawn", " ".join(self.argv))
        self.proc = subprocess.Popen(
            self.argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.workspace,
            bufsize=0,
            creationflags=creationflags,
            env=env,
        )
        self._alive = True
        self._read_thread_alive = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True, name=f"{self.module}-acp")
        self._reader.start()
        threading.Thread(target=self._stderr_loop, daemon=True, name=f"{self.module}-err").start()
        params = {
            "protocolVersion": 1,
            "clientInfo": {"name": self.client_name, "version": self.client_version},
            "capabilities": {"fs": {"readTextFile": True, "writeTextFile": True}},
        }
        params.update(self.extra_init)
        init = self.request("initialize", params, timeout=120)
        self.init_result = init or {}
        self.agent_capabilities = dict(self.init_result.get("agentCapabilities") or {})
        info = dict(self.init_result.get("agentInfo") or {})
        self.agent_version = str(info.get("version") or "")
        if self.authenticate:
            try:
                auth = self.request("authenticate", self.authenticate, timeout=60)
                meta = (auth or {}).get("_meta") or {}
                log("INFO", self.module, "agent.auth", str(meta.get("email") or "ok"))
            except AcpError as e:
                log("WARN", self.module, "agent.auth", str(e))
        self.on_event({"type": "ready", "module": self.module, "agent_version": self.agent_version})
        return {"agent_version": self.agent_version, "workspace": self.workspace}

    def stop(self) -> None:
        self._alive = False
        proc = self.proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait(timeout=3)
                except Exception:
                    pass
        self.proc = None
        self._read_thread_alive = False
        self._fail_pending("agent_stopped")
        log("INFO", self.module, "agent.stop", "")

    def new_session(self) -> dict[str, Any]:
        sess = self.request("session/new", {"cwd": self.workspace, "mcpServers": []}, timeout=120)
        self.session_id = str((sess or {}).get("sessionId") or "")
        if not self.session_id:
            raise AcpError(f"session_new_failed: {sess}")
        self._store_config((sess or {}).get("configOptions"))
        models = (sess or {}).get("models") or {}
        if models.get("currentModelId"):
            self.current_model = str(models["currentModelId"])
        self.history_events = []
        log("INFO", self.module, "session.new", self.session_id)
        return {"session_id": self.session_id, "config_options": self.config_options, "model": self.current_model}

    def list_sessions(self) -> list[dict[str, Any]]:
        try:
            raw = self.request("session/list", {}, timeout=30)
        except AcpError as e:
            log("WARN", self.module, "session.list", str(e))
            return []
        sessions = (raw or {}).get("sessions") or raw or []
        if isinstance(sessions, dict):
            sessions = sessions.get("sessions") or []
        return list(sessions) if isinstance(sessions, list) else []

    def load_session(self, session_id: str) -> dict[str, Any]:
        self.history_events = []
        raw = self.request(
            "session/load",
            {"sessionId": session_id, "cwd": self.workspace, "mcpServers": []},
            timeout=120,
        )
        self.session_id = session_id
        log("INFO", self.module, "session.load", session_id)
        return raw if isinstance(raw, dict) else {"sessionId": session_id}

    def prompt(self, text: str) -> dict[str, Any]:
        if not self.session_id:
            self.new_session()
        activity = threading.Event()

        prev = self.on_event

        def _wrap(ev: dict[str, Any]) -> None:
            if ev.get("type") in ("session_update", "tool", "chunk"):
                activity.set()
            prev(ev)  # must not call self.on_event: that is _wrap itself (RecursionError)

        self.on_event = _wrap
        try:
            result = self.request(
                "session/prompt",
                {"sessionId": self.session_id, "prompt": [{"type": "text", "text": text}]},
                timeout=600,
                activity_event=activity,
            )
        finally:
            self.on_event = prev
        return result if isinstance(result, dict) else {"result": result}

    def cancel(self) -> None:
        if not self.session_id:
            return
        try:
            self.notify("session/cancel", {"sessionId": self.session_id})
        except AcpError as e:
            log("WARN", self.module, "session.cancel", str(e))

    def session_delete(self, session_id: str) -> dict[str, Any]:
        raw = self.request("session/delete", {"sessionId": session_id}, timeout=30)
        log("INFO", self.module, "session.delete", session_id)
        return raw if isinstance(raw, dict) else {"ok": True}

    def set_config_option(self, config_id: str, value: Any) -> Any:
        if not self.session_id:
            raise AcpError("no_session")
        return self.request(
            "session/set_config_option",
            {"sessionId": self.session_id, "configId": config_id, "value": value},
            timeout=30,
        )

    def _store_config(self, options: Any) -> None:
        if isinstance(options, list):
            self.config_options = options
            for opt in options:
                cid = str(opt.get("id") or opt.get("configId") or "")
                val = opt.get("value") or opt.get("current") or ""
                if cid == "model":
                    self.current_model = str(val)
                if cid == "mode":
                    self.current_mode = str(val)

    def _next_id(self) -> int:
        with self._lock:
            self._id += 1
            return self._id

    def _send_raw(self, obj: dict[str, Any]) -> None:
        if not self.proc or not self.proc.stdin:
            raise AcpError("process_not_running")
        line = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        with self._lock:
            self.proc.stdin.write(line)
            self.proc.stdin.flush()

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = 120,
        activity_event: threading.Event | None = None,
    ) -> Any:
        rid = self._next_id()
        q: queue.Queue = queue.Queue()
        self._pending[rid] = q
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self._send_raw(msg)
        try:
            if activity_event is None:
                result = q.get(timeout=timeout)
            else:
                deadline = time.monotonic() + timeout
                while True:
                    remaining = max(0.0, deadline - time.monotonic())
                    try:
                        result = q.get(timeout=min(0.25, remaining or 0.25))
                        break
                    except queue.Empty:
                        if activity_event.is_set():
                            activity_event.clear()
                            deadline = time.monotonic() + timeout
                            continue
                        if time.monotonic() >= deadline:
                            raise
        except queue.Empty:
            self._pending.pop(rid, None)
            raise AcpError(f"timeout waiting for {method}")
        if isinstance(result, dict) and result.get("_error"):
            raise AcpError(str(result.get("message") or result))
        return result

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send_raw(msg)

    def respond(self, req_id: Any, result: Any) -> None:
        self._send_raw({"jsonrpc": "2.0", "id": req_id, "result": result})

    def respond_error(self, req_id: Any, code: int, message: str) -> None:
        self._send_raw({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})

    def _fail_pending(self, message: str) -> None:
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for waiter in pending:
            waiter.put({"_error": True, "message": message})

    def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        buf = bytearray()
        while self._alive and self.proc.poll() is None:
            try:
                chunk = self.proc.stdout.read(65536)
            except Exception:
                break
            if not chunk:
                break
            buf.extend(chunk)
            while True:
                nl = buf.find(b"\n")
                if nl < 0:
                    break
                line = bytes(buf[:nl]).decode("utf-8", errors="replace").strip()
                del buf[: nl + 1]
                if line:
                    try:
                        self._handle_line(line)
                    except Exception as e:
                        self._stderr_tail.append(f"[bridge] event handler error: {e!r}")
                        self._stderr_tail = self._stderr_tail[-50:]
                        log("ERROR", self.module, "handler.error", repr(e))
        self._alive = False
        self._read_thread_alive = False
        self._fail_pending("agent_connection_closed")
        had_init = bool(self.init_result)
        detail = (self._stderr_tail[0] if self._stderr_tail else "read loop ended")
        if had_init:
            log("ALERT", self.module, "agent.dead", detail[:200])
        else:
            log("WARN", self.module, "agent.exit", detail[:200])
        self.on_event({
            "type": "agent_exit",
            "code": self.proc.returncode if self.proc else None,
            "stderr": list(self._stderr_tail[-8:]),
            "had_init": had_init,
        })

    def _stderr_loop(self) -> None:
        if not self.proc or not self.proc.stderr:
            return
        run = current_run()
        for raw in iter(self.proc.stderr.readline, b""):
            try:
                text = raw.decode("utf-8", errors="replace").rstrip()
            except Exception:
                continue
            if not text:
                continue
            self._stderr_tail.append(text)
            self._stderr_tail = self._stderr_tail[-80:]
            if run:
                run.agent_stderr(self.module, text)
            self.on_event({"type": "stderr", "line": text})

    def _handle_line(self, line: str) -> None:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            self.on_event({"type": "parse_error", "line": line[:400]})
            return
        if "id" in msg and ("result" in msg or "error" in msg) and "method" not in msg:
            q = self._pending.pop(msg["id"], None)
            if q:
                if "error" in msg:
                    err = msg["error"]
                    q.put({"_error": True, "message": err.get("message") if isinstance(err, dict) else err})
                else:
                    q.put(msg.get("result"))
            return
        method = msg.get("method")
        params = msg.get("params") or {}
        req_id = msg.get("id")
        if method == "session/request_permission":
            self._handle_permission(req_id, params)
            return
        if method == "fs/read_text_file":
            self._handle_read_file(req_id, params)
            return
        if method == "fs/write_text_file":
            self._handle_write_file(req_id, params)
            return
        if method == "session/update":
            update = (params or {}).get("update") or {}
            if update.get("sessionUpdate") == "config_option_update":
                self._store_config(update.get("configOptions"))
            self.history_events.append({"type": "session_update", "params": params, "history": False})
            self.on_event({"type": "session_update", "params": params})
            return
        if method:
            self.on_event({"type": "notification", "method": method, "params": params, "id": req_id})
            if req_id is not None:
                try:
                    self.respond_error(req_id, -32601, f"method not found: {method}")
                except Exception:
                    pass

    def _handle_permission(self, req_id: Any, params: dict[str, Any]) -> None:
        options = params.get("options") or []
        self.on_event({"type": "permission", "params": params})
        if req_id is None:
            return
        if self.auto_approve and options:
            choice = None
            for kind in ("allow_always", "allow_once"):
                for opt in options:
                    if opt.get("kind") == kind:
                        choice = opt.get("optionId")
                        break
                if choice:
                    break
            if choice is None:
                choice = options[0].get("optionId")
            self.respond(req_id, {"outcome": {"outcome": "selected", "optionId": choice}})
        else:
            self.respond(req_id, {"outcome": {"outcome": "cancelled"}})

    def _handle_read_file(self, req_id: Any, params: dict[str, Any]) -> None:
        if req_id is None:
            return
        path = Path(str(params.get("path") or ""))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            self.respond(req_id, {"content": text})
        except Exception as e:
            self.respond_error(req_id, -32000, str(e))

    def _handle_write_file(self, req_id: Any, params: dict[str, Any]) -> None:
        if req_id is None:
            return
        path = Path(str(params.get("path") or ""))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(params.get("content") or ""), encoding="utf-8")
            self.respond(req_id, {})
        except Exception as e:
            self.respond_error(req_id, -32000, str(e))

    def snapshot(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "alive": self.alive,
            "session_id": self.session_id,
            "model": self.current_model,
            "mode": self.current_mode,
            "config_options": self.config_options,
            "agent_version": self.agent_version,
            "stderr_tail": list(self._stderr_tail[-20:]),
            "pid": self.proc.pid if self.proc else None,
        }
