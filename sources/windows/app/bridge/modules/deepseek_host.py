"""Official dsh host HTTP (no iframe). POST /api/<method> envelope + WebSocket mux downlink.

dsh 0.1.0-rc.6 moved /api/events.mux from SSE to a downlink-only WebSocket: a plain
GET now answers 426, and any client->server message closes the socket (1008).
Each WS text message is the same server-request envelope the SSE data lines carried.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import websocket

from acp_client import AcpError
from logging_setup import log
from win_cli import dsh_web_argv, hidden_popen_kwargs

TURN_IDLE_TIMEOUT = 600.0  # same idle budget as the ACP prompt wait
WS_RECONNECT = 1.2


def _hit_pct(cache_read: int, uncached: int, cache_write: int) -> float | None:
    billed = uncached + cache_read + cache_write
    if billed <= 0:
        return None
    return round(100.0 * cache_read / billed, 1)


class DeepSeekHost:
    def __init__(
        self,
        binary: str,
        workspace: str,
        port: int,
        on_event: Callable[[dict[str, Any]], None],
        env: dict[str, str] | None = None,
    ) -> None:
        self.name = "deepseek"
        self.binary = binary
        self.workspace = workspace
        self.port = port
        self._on_event = on_event
        self.env = env or {}
        self.proc: subprocess.Popen | None = None
        self.session_id: str | None = None
        self.cache_hit: dict[str, Any] | None = None
        self.error = ""
        self._sse_stop = threading.Event()
        self._ws: Any = None
        self._ws_lock = threading.Lock()
        self._ws_thread_alive = False
        # A prompt blocks until turn/end, like ACP, so /api/prompt means "reply finished".
        self._turn_done = threading.Event()
        self._last_activity = 0.0
        self._streamed: set[tuple[Any, Any]] = set()
        self._tools: dict[str, str] = {}
        self._alive = False
        self._starting = False
        self.current_model = ""
        self.config_options: list[dict[str, Any]] = []

    @property
    def alive(self) -> bool:
        return bool(self._alive and self.proc and self.proc.poll() is None)

    def start(self) -> dict[str, Any]:
        if self.alive:
            return self.snapshot()
        if self._starting and self.proc and self.proc.poll() is None:
            return self.snapshot()
        argv = dsh_web_argv(self.binary, ["web", "--host", "127.0.0.1", "--port", str(self.port)])
        env = os.environ.copy()
        env.update(self.env)
        env.setdefault("BROWSER", "none")
        log("INFO", "deepseek", "engine.spawn", f"port={self.port} argv0={argv[0]}")
        self.error = ""
        self._starting = True
        self._alive = False
        try:
            self.proc = subprocess.Popen(
                argv,
                cwd=self.workspace,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                **hidden_popen_kwargs(),
            )
        except Exception:
            self._starting = False
            raise
        threading.Thread(target=self._boot_wait, daemon=True, name="dsh-boot").start()
        return self.snapshot()

    def _boot_wait(self) -> None:
        try:
            ok = self._wait_host(60)
            if not ok:
                self.error = "dsh_host_timeout"
                self._starting = False
                self._alive = False
                log("ERROR", "deepseek", "engine.start", "host did not open /api")
                self._on_event({"type": "engine_error", "code": "dsh_host_timeout"})
                return
            self._alive = True
            self._starting = False
            self.error = ""
            self._sse_stop.clear()
            self._ws_thread_alive = True
            threading.Thread(target=self._ws_loop, daemon=True, name="dsh-ws").start()
            threading.Thread(target=self._stderr_loop, daemon=True, name="dsh-err").start()
            pid = self.proc.pid if self.proc else 0
            log("INFO", "deepseek", "engine.ready", f"pid={pid}")
            self._on_event({"type": "engine_ready", "code": "dsh-host"})
        except Exception as e:
            self._starting = False
            self._alive = False
            self.error = str(e)
            log("ERROR", "deepseek", "engine.start", str(e))
            self._on_event({"type": "engine_error", "code": str(e)})

    def stop(self) -> None:
        self._alive = False
        self._starting = False
        self._sse_stop.set()
        self._turn_done.set()
        with self._ws_lock:
            ws, self._ws = self._ws, None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None

    def prompt(self, text: str) -> dict[str, Any]:
        if not self.session_id:
            self.session_new()
        self._turn_done.clear()
        self._last_activity = time.monotonic()
        self._rpc(
            "session.prompt",
            {
                "sessionId": self.session_id,
                "mode": "queue",
                "content": [{"type": "text", "text": text}],
            },
        )
        return {"ok": True, "finished": self._wait_turn()}

    def _wait_turn(self) -> bool:
        """Block until turn/end (or cancel/stop); no event reader means nothing to wait for."""
        while not self._turn_done.wait(0.5):
            if self._sse_stop.is_set() or not self.alive or not self._ws_thread_alive:
                return False
            if time.monotonic() - self._last_activity > TURN_IDLE_TIMEOUT:
                log("WARN", "deepseek", "prompt.wait", "no turn activity for 600 s; releasing /api/prompt")
                return False
        return True

    def cancel(self) -> None:
        if not self.session_id:
            return
        try:
            self._rpc("session.cancel", {"sessionId": self.session_id})
        except AcpError as e:
            log("WARN", "deepseek", "session.cancel", str(e))
        self._turn_done.set()

    def session_list(self) -> list[dict[str, Any]]:
        raw = self._rpc("session.list", {})
        items = (raw or {}).get("items") or []
        # session.list still returns archived sessions; "delete" here is
        # workspace.archiveSession, so hide them the way dsh's own UI does.
        archived: set[str] = set()
        try:
            ws = self._rpc("workspace.list", {}, timeout=10)
            archived = {str(i) for i in (ws or {}).get("archivedSessionIds") or []}
        except AcpError as e:
            log("WARN", "deepseek", "session.list", f"archive set unavailable: {e}")
        out = []
        for it in items:
            sid = str(it.get("sessionId") or it.get("id") or "")
            if sid in archived:
                continue
            title = ""
            proj = it.get("projections") or {}
            vals = proj.get("values") if isinstance(proj, dict) else {}
            if isinstance(vals, dict):
                title = str(vals.get("title") or vals.get("name") or "")
            out.append({"sessionId": sid, "title": title or sid[:16], "updatedAt": it.get("updatedAt")})
        return out

    def session_new(self) -> dict[str, Any]:
        raw = self._rpc("session.create", {"cwd": self.workspace})
        self.session_id = str((raw or {}).get("sessionId") or "")
        if not self.session_id:
            raise AcpError("dsh_session_create_failed")
        log("INFO", "deepseek", "session.new", self.session_id)
        self._refresh_models()
        return {"session_id": self.session_id, "model": self.current_model}

    def session_load(self, session_id: str) -> dict[str, Any]:
        self.session_id = session_id
        hist = self._rpc("session.history", {"sessionId": session_id, "maxMessages": 80})
        events = (hist or {}).get("events") or []
        for entry in events:
            ev = entry.get("event") if isinstance(entry, dict) else None
            if isinstance(ev, dict):
                self._map_session_event(session_id, ev, replay=True)
        self._refresh_models()
        log("INFO", "deepseek", "session.load", session_id)
        return {"sessionId": session_id}

    def session_delete(self, session_id: str) -> dict[str, Any]:
        try:
            self._rpc("workspace.archiveSession", {"sessionId": session_id})
            return {"ok": True, "via": "archive"}
        except AcpError as e:
            log("WARN", "deepseek", "session.delete", str(e))
            return {"ok": False, "error": str(e)}

    def set_config(self, config_id: str, value: Any) -> Any:
        if not self.session_id:
            raise AcpError("no_session")
        if config_id == "model" and isinstance(value, str) and "/" in value:
            provider, model = value.split("/", 1)
            return self._rpc(
                "session.selectModel",
                {"sessionId": self.session_id, "provider": provider, "model": model},
            )
        if config_id == "model":
            return self._rpc(
                "session.selectModel",
                {"sessionId": self.session_id, "provider": "deepseek", "model": str(value)},
            )
        raise AcpError("unsupported_config")

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": "deepseek",
            "alive": self.alive,
            "acp": False,
            "error": self.error,
            "session_id": self.session_id,
            "model": self.current_model,
            "mode": "",
            "config_options": self.config_options,
            "agent_version": "dsh-host",
            "cache_hit": self.cache_hit,
            "starting": bool(self._starting and not self._alive),
        }

    def _wait_host(self, seconds: int) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.proc and self.proc.poll() is not None:
                return False
            try:
                self._rpc("session.list", {}, timeout=2)
                return True
            except Exception:
                try:
                    self._rpc("host.describe", {}, timeout=2)
                    return True
                except Exception:
                    time.sleep(0.4)
        return False

    def _rpc(self, method: str, payload: dict[str, Any], timeout: float = 60) -> Any:
        url = f"http://127.0.0.1:{self.port}/api/{method}"
        body = json.dumps(
            {"type": "client-request", "rpcId": str(uuid.uuid4()), "method": method, "payload": payload}
        ).encode("utf-8")
        req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            raise AcpError(f"dsh_http_{e.code}:{method}") from e
        except URLError as e:
            raise AcpError(f"dsh_http:{method}:{e.reason}") from e
        result = raw.get("result") if isinstance(raw, dict) else None
        if isinstance(result, dict) and result.get("ok") is False:
            err = result.get("error") or {}
            raise AcpError(str(err.get("message") or err.get("code") or result))
        if isinstance(result, dict) and "value" in result:
            return result.get("value")
        if isinstance(result, dict) and result.get("ok") is True:
            return result.get("value") if "value" in result else result
        return result

    def _refresh_models(self) -> None:
        if not self.session_id:
            return
        try:
            raw = self._rpc("session.models", {"sessionId": self.session_id})
        except AcpError as e:
            log("WARN", "deepseek", "session.models", str(e))
            return
        cur = (raw or {}).get("current") or {}
        if cur.get("model"):
            self.current_model = str(cur.get("provider") or "") + "/" + str(cur["model"])
        opts: list[dict[str, Any]] = []
        groups = (raw or {}).get("groups") or []
        values = []
        for g in groups:
            for m in g.get("models") or []:
                values.append(str(g.get("id") or "") + "/" + str(m.get("id") or ""))
        if values:
            opts.append({"id": "model", "value": self.current_model, "options": values})
        self.config_options = opts

    def _ws_loop(self) -> None:
        """Downlink-only WebSocket: never send a message (the host closes with 1008)."""
        url = f"ws://127.0.0.1:{self.port}/api/events.mux"
        try:
            while self.alive and not self._sse_stop.is_set():
                try:
                    ws = websocket.create_connection(url, timeout=10)
                except Exception as e:  # noqa: BLE001
                    log("WARN", "deepseek", "ws.connect", f"{type(e).__name__}:{str(e)[:100]}")
                    self._sse_stop.wait(WS_RECONNECT)
                    continue
                with self._ws_lock:
                    self._ws = ws
                try:
                    ws.settimeout(1.0)
                    while self.alive and not self._sse_stop.is_set():
                        try:
                            raw = ws.recv()
                        except websocket.WebSocketTimeoutException:
                            continue
                        if not raw:
                            break
                        try:
                            self._handle_envelope(json.loads(raw))
                        except Exception as e:  # noqa: BLE001 - one bad frame must not kill the reader
                            log("ERROR", "deepseek", "handler.error", repr(e)[:160])
                except Exception as e:  # noqa: BLE001 - closed socket: reconnect below
                    if self.alive and not self._sse_stop.is_set():
                        log("WARN", "deepseek", "ws.loop", f"{type(e).__name__}:{str(e)[:100]}")
                finally:
                    with self._ws_lock:
                        if self._ws is ws:
                            self._ws = None
                    try:
                        ws.close()
                    except Exception:  # noqa: BLE001
                        pass
                self._sse_stop.wait(WS_RECONNECT)
        finally:
            self._ws_thread_alive = False

    def _handle_envelope(self, msg: Any) -> None:
        payload = msg.get("payload") if isinstance(msg, dict) else None
        if not isinstance(payload, dict):
            return
        if str(payload.get("type") or "") == "session/event":
            sid = str(payload.get("sessionId") or "")
            ev = payload.get("event") or {}
            if isinstance(ev, dict):
                self._map_session_event(sid, ev)

    def _session_update(self, update: dict[str, Any]) -> None:
        self._on_event({"type": "session_update", "params": {"update": update}})

    def _note_usage(self, usage: Any) -> None:
        if not isinstance(usage, dict):
            return
        cr = int(usage.get("cacheReadTokens") or usage.get("cache_read_input_tokens") or 0)
        cw = int(usage.get("cacheWriteTokens") or usage.get("cache_creation_input_tokens") or 0)
        un = int(usage.get("inputTokens") or usage.get("uncached_input_tokens") or usage.get("input_tokens") or 0)
        pct = _hit_pct(cr, un, cw)
        self.cache_hit = {"cacheRead": cr, "cacheWrite": cw, "uncached": un, "hit_pct": pct}
        if pct is None:
            log("ALERT", "deepseek", "usage.missing", "usage present but billed=0")
        self._on_event({"type": "cache", "cache_hit": self.cache_hit})

    @staticmethod
    def _text_of(content: Any) -> str:
        return "".join(
            str(c.get("text") or "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text"
        )

    def _map_session_event(self, session_id: str, ev: dict[str, Any], *, replay: bool = False) -> None:
        """dsh session event -> the event shapes the existing UI renders (frames recorded 2026-10-17)."""
        et = str(ev.get("type") or "")
        data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
        if session_id and self.session_id and session_id != self.session_id:
            return
        self._last_activity = time.monotonic()
        if et == "assistant/chunk":
            chunk = data.get("chunk") if isinstance(data.get("chunk"), dict) else {}
            kind = str(chunk.get("type") or "")
            if kind == "text-delta" and chunk.get("text"):
                self._streamed.add((data.get("turn"), data.get("step")))
                self._session_update({"sessionUpdate": "agent_message_chunk", "content": {"text": str(chunk["text"])}})
            elif kind == "usage":
                self._note_usage(chunk.get("usage"))
            return
        if et == "assistant/message":
            self._note_usage(data.get("usage"))
            if (data.get("turn"), data.get("step")) in self._streamed:
                return  # already shown chunk by chunk
            message = data.get("message") if isinstance(data.get("message"), dict) else {}
            text = self._text_of(message.get("content"))
            if text:
                self._session_update({"sessionUpdate": "agent_message_chunk", "content": {"text": text}})
            return
        if et == "user/message":
            # Live: the bridge already shows what the user typed. Injected messages
            # (system policy, skill catalog) carry another source.kind and never show.
            source = data.get("source") if isinstance(data.get("source"), dict) else {}
            if replay and str(source.get("kind") or "") == "user":
                text = self._text_of(data.get("content"))
                if text:
                    self._on_event({"type": "user", "text": text})
            return
        if et == "tool/call":
            name = str(data.get("name") or "tool")
            if data.get("callId"):
                self._tools[str(data["callId"])] = name
            self._session_update({"sessionUpdate": "tool_call", "title": name, "status": "running"})
            return
        if et == "tool/result":
            name = self._tools.get(str(data.get("callId") or ""), "tool")
            self._session_update({"sessionUpdate": "tool_call_update", "title": name, "status": "done"})
            return
        if et == "turn/end":
            self._streamed.clear()
            if not replay:
                self._turn_done.set()

    def _stderr_loop(self) -> None:
        if not self.proc or not self.proc.stderr:
            return
        from logging_setup import current_run

        run = current_run()
        for raw in iter(self.proc.stderr.readline, b""):
            try:
                text = raw.decode("utf-8", errors="replace").rstrip()
            except Exception:
                continue
            if run and text:
                run.agent_stderr("deepseek", text)


class DeepSeekAdapter:
    def __init__(self, host: DeepSeekHost) -> None:
        self.name = "deepseek"
        self.host = host

    @property
    def alive(self) -> bool:
        return self.host.alive

    def start(self) -> dict[str, Any]:
        return self.host.start()

    def stop(self) -> None:
        self.host.stop()

    def prompt(self, text: str) -> dict[str, Any]:
        return self.host.prompt(text)

    def cancel(self) -> None:
        self.host.cancel()

    def session_list(self) -> list[dict[str, Any]]:
        return self.host.session_list()

    def session_load(self, session_id: str) -> dict[str, Any]:
        return self.host.session_load(session_id)

    def session_new(self) -> dict[str, Any]:
        return self.host.session_new()

    def session_delete(self, session_id: str) -> dict[str, Any]:
        return self.host.session_delete(session_id)

    def set_config(self, config_id: str, value: Any) -> Any:
        return self.host.set_config(config_id, value)

    def snapshot(self) -> dict[str, Any]:
        return self.host.snapshot()
