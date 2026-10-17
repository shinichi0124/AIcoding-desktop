"""Kimi kap adapter - Kimi Code's own local API (HTTP + WebSocket).

Plan: docs/PLAN_kimi-kap-adapter_20261017.md (workspace AGENTS.md B.27).
API only: never load the "kimi web" page in any window (platform rule 6). The
bearer token lives in ~/.kimi-code/server.token; it must never reach a log, an
event, a URL or a fixture - every error raised here drops the request headers.

Attach first (a running Kimi Code desktop instance owns the store), spawn only
when nothing healthy is around: "kimi web --no-open --port <p>".
"""
from __future__ import annotations

import ctypes
import json
import os
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import websocket

from acp_client import AcpError
from logging_setup import log, redact
from win_cli import hidden_popen_kwargs, kimi_web_argv

LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")
DEFAULT_PORT = 18774
PORT_TRIES = 6
HEARTBEAT_MAX_AGE = 90.0
HTTP_TIMEOUT = 10.0
PROMPT_TIMEOUT = 30.0
TURN_IDLE_TIMEOUT = 600.0  # same idle budget as the ACP prompt wait
HELLO_TIMEOUT = 5.0
WS_POLL = 1.0
BACKOFF = (1.0, 2.0, 5.0, 10.0)
CONNECT_FAILS_BEFORE_DEAD = 3
LIST_PAGE = 100
LIST_MAX = 200
SESSION_NOT_FOUND = 40401


class KapError(AcpError):
    """kap answered with a non-zero envelope code."""

    def __init__(self, code: Any, msg: str) -> None:
        try:
            self.code = int(code)
        except (TypeError, ValueError):
            self.code = -1
        self.msg = str(msg or "")
        super().__init__(f"kap:{self.code}:{self.msg}")


class KapTransportError(AcpError):
    """kap could not be reached, or the answer was not an envelope."""


# ------------------------------------------------------------- token and pids

_TOKEN_LOCK = threading.Lock()
_TOKEN_CACHE: dict[str, Any] = {"key": None, "value": ""}


def kimi_home() -> Path:
    return Path.home() / ".kimi-code"


def read_token() -> str:
    """Bearer token, cached by file mtime. Callers must never log the value."""
    path = kimi_home() / "server.token"
    try:
        st = path.stat()
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        return ""
    with _TOKEN_LOCK:
        if _TOKEN_CACHE["key"] == key:
            return str(_TOKEN_CACHE["value"] or "")
    try:
        value = path.read_text(encoding="ascii", errors="replace").strip()
    except OSError:
        return ""
    with _TOKEN_LOCK:
        _TOKEN_CACHE["key"] = key
        _TOKEN_CACHE["value"] = value
    return value


def pid_alive(pid: int) -> bool:
    """Cheap process probe (os.kill(pid, 0) would terminate on Windows)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    try:
        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        query_limited = 0x1000
        still_active = 259
        handle = k32.OpenProcess(query_limited, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong(0)
            if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return int(code.value) == still_active
        finally:
            k32.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------ kap HTTP


def kap_http(
    method: str,
    host: str,
    port: int,
    path: str,
    *,
    token: str = "",
    body: Any = None,
    timeout: float = HTTP_TIMEOUT,
) -> Any:
    """One kap REST call: returns envelope data, raises KapError/transport."""
    route = path.split("?")[0]
    url = f"http://{host}:{port}/api/v1{path}"
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8", "replace"))
    except HTTPError as e:
        raise KapTransportError(f"kap_http_{e.code}:{route}") from None
    except (URLError, OSError, ValueError) as e:
        raise KapTransportError(f"kap_http:{route}:{type(e).__name__}") from None
    if not isinstance(raw, dict):
        raise KapTransportError(f"kap_envelope:{route}")
    code = raw.get("code")
    if code not in (0, None):
        raise KapError(code, str(raw.get("msg") or ""))
    return raw.get("data")


def healthz(host: str, port: int, token: str, timeout: float = 2.0) -> bool:
    try:
        data = kap_http("GET", host, port, "/healthz", token=token, timeout=timeout)
    except AcpError:
        return False
    return bool(isinstance(data, dict) and data.get("ok"))


def discover_instance(*, max_age: float = HEARTBEAT_MAX_AGE) -> dict[str, Any] | None:
    """Newest loopback instance: fresh heartbeat, live pid, healthz ok in 2 s."""
    root = kimi_home() / "server" / "instances"
    try:
        files = list(root.glob("*.json"))
    except OSError:
        return None
    rows: list[dict[str, Any]] = []
    for f in files:
        try:
            info = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(info, dict):
            rows.append(info)
    rows.sort(key=lambda i: float(i.get("heartbeat_at") or 0), reverse=True)
    token = read_token()
    if not token:
        return None
    now_ms = time.time() * 1000.0
    for info in rows:
        host = str(info.get("host") or "")
        try:
            port = int(info.get("port") or 0)
            pid = int(info.get("pid") or 0)
            heartbeat = float(info.get("heartbeat_at") or 0)
        except (TypeError, ValueError):
            continue
        if host not in LOOPBACK_HOSTS or port <= 0:
            continue
        if now_ms - heartbeat > max_age * 1000.0:
            continue
        if not pid_alive(pid):
            continue
        if not healthz(host, port, token, timeout=2.0):
            continue
        return {
            "host": "127.0.0.1" if host in ("localhost", "::1") else host,
            "port": port,
            "pid": pid,
            "server_id": str(info.get("server_id") or ""),
            "host_version": str(info.get("host_version") or ""),
        }
    return None


def port_free(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", int(port)))
        return True
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


# ------------------------------------------------------------------- the host


class KimiKapHost:
    """Connection, HTTP, WS reader and event mapping for one kap server."""

    def __init__(
        self,
        binary: str,
        workspace: str,
        port: int = DEFAULT_PORT,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        env: dict[str, str] | None = None,
        *,
        auto_approve: bool = True,
    ) -> None:
        self.name = "kimi"
        self.binary = binary
        self.workspace = workspace or str(Path.home())
        self.port = int(port or DEFAULT_PORT)
        self.host = "127.0.0.1"
        self.env = env or {}
        self._on_event = on_event or (lambda _e: None)
        self._auto_approve = bool(auto_approve)
        self.proc: subprocess.Popen[bytes] | None = None
        self.owned = False
        self.session_id: str | None = None
        self.current_model = ""
        self.config_options: list[dict[str, Any]] = []
        self.agent_version = ""
        self.error = ""
        self._alive = False
        self._fatal = False
        self._starting = False
        self._ws_thread_alive = False
        self._stop = threading.Event()
        self._ws: Any = None
        self._send_lock = threading.Lock()
        self._subs: list[str] = []
        self._cursors: dict[str, dict[str, Any]] = {}
        self._models: list[dict[str, Any]] = []
        self._tools: dict[str, str] = {}
        self._stderr_tail: list[str] = []
        self.last_frame_at = 0.0
        # A prompt blocks until its turn ends, like the ACP prompt, so /api/prompt
        # keeps meaning "the reply is finished" for every engine.
        self._turn_done = threading.Event()
        self._turn_prompt_id = ""
        self._last_activity = 0.0

    # -------------------------------------------------------------- lifecycle

    @property
    def alive(self) -> bool:
        return bool(self._alive and not self._fatal)

    def start(self) -> dict[str, Any]:
        if self.alive:
            return self.snapshot()
        if self._starting:
            return self.snapshot()
        self.error = ""
        self._fatal = False
        self._stop.clear()
        inst = None
        try:
            inst = discover_instance()
        except Exception as e:  # noqa: BLE001 - discovery must never kill start
            log("WARN", "kimi", "kap.discover", type(e).__name__)
        if inst is not None:
            try:
                self._attach(inst)
                log("INFO", "kimi", "engine.ready", f"kap-attach port={self.port} v{self.agent_version}")
                self._on_event({"type": "engine_ready", "code": "kap-attach", "version": self.agent_version})
                return self.snapshot()
            except Exception as e:  # noqa: BLE001
                self.error = f"kap_attach_failed: {e}"
                log("WARN", "kimi", "kap.attach", f"{type(e).__name__}:{str(e)[:120]}")
                self._teardown_ws()
                self._alive = False
        self._starting = True
        try:
            self._spawn()
        except Exception as e:  # noqa: BLE001
            self._starting = False
            self._fail("kimi_kap_unavailable", f"{type(e).__name__}:{str(e)[:160]}")
        return self.snapshot()

    def stop(self) -> None:
        self._stop.set()
        self._alive = False
        self._starting = False
        self._turn_done.set()
        self._teardown_ws()
        proc = self.proc
        if self.owned and proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        if self.owned:
            log("INFO", "kimi", "engine.stop", "kap-spawn terminated")
        self.proc = None
        self.owned = False

    # ----------------------------------------------------------- attach/spawn

    def _attach(self, inst: dict[str, Any]) -> None:
        self.host = str(inst.get("host") or "127.0.0.1")
        self.port = int(inst.get("port") or DEFAULT_PORT)
        self.owned = False
        self.proc = None
        meta = self._req("GET", "/meta", timeout=HTTP_TIMEOUT)
        if isinstance(meta, dict):
            self.agent_version = str(meta.get("server_version") or inst.get("host_version") or "")
        self._refresh_models()
        self._alive = True
        self._starting = False
        self._start_ws()

    def _spawn(self) -> None:
        port = self._pick_port()
        self.host = "127.0.0.1"
        self.port = port
        argv = kimi_web_argv(self.binary, port)
        env = os.environ.copy()
        env.update(self.env)
        env.setdefault("BROWSER", "none")
        log("INFO", "kimi", "engine.spawn", f"kap-spawn port={port} argv0={Path(argv[0]).name}")
        self.proc = subprocess.Popen(
            argv,
            cwd=self.workspace if Path(self.workspace).is_dir() else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            **hidden_popen_kwargs(),
        )
        self.owned = True
        threading.Thread(target=self._boot_wait, daemon=True, name="kap-boot").start()

    def _pick_port(self) -> int:
        for i in range(PORT_TRIES):
            candidate = self.port + i
            if port_free(candidate):
                return candidate
        raise AcpError("kap_port_busy")

    def _boot_wait(self, seconds: float = 60.0) -> None:
        deadline = time.monotonic() + seconds
        try:
            last = ""
            while time.monotonic() < deadline and not self._stop.is_set():
                if self.proc is not None and self.proc.poll() is not None:
                    self._starting = False
                    self._fail("kimi_kap_unavailable", f"kimi web exited early code={self.proc.returncode}")
                    return
                token = read_token()
                if token and healthz(self.host, self.port, token, timeout=2.0):
                    self._alive = True
                    self._starting = False
                    self.error = ""
                    try:
                        meta = self._req("GET", "/meta", timeout=HTTP_TIMEOUT)
                        if isinstance(meta, dict):
                            self.agent_version = str(meta.get("server_version") or "")
                        self._refresh_models()
                    except AcpError as e:
                        last = str(e)
                    self._start_ws()
                    threading.Thread(target=self._pipe_logs, daemon=True, name="kap-log").start()
                    log("INFO", "kimi", "engine.ready", f"kap-spawn port={self.port} v{self.agent_version}")
                    self._on_event({"type": "engine_ready", "code": "kap-spawn", "version": self.agent_version})
                    return
                self._stop.wait(0.4)
            self._starting = False
            self._fail("kimi_kap_unavailable", last or "kimi web did not open /healthz within 60 s")
        except Exception as e:  # noqa: BLE001
            self._starting = False
            self._fail("kimi_kap_unavailable", f"{type(e).__name__}:{str(e)[:160]}")

    def _pipe_logs(self) -> None:
        from logging_setup import current_run

        run = current_run()
        proc = self.proc
        if proc is None:
            return

        # One reader per pipe: draining stdout to EOF first would let a full
        # stderr pipe block "kimi web" itself.
        def pump(stream: Any, tag: str) -> None:
            for raw in iter(stream.readline, b""):
                text = raw.decode("utf-8", errors="replace").rstrip()
                if not text:
                    continue
                if run is not None:
                    run.agent_stderr("kimi", f"[{tag}] {text}")
                self._note(text)

        for stream, tag in ((proc.stdout, "stdout"), (proc.stderr, "stderr")):
            if stream is not None:
                threading.Thread(target=pump, args=(stream, tag), daemon=True, name=f"kap-{tag}").start()

    def _fail(self, code: str, detail: str) -> None:
        self.error = f"{code}: {detail}"
        self._note(detail)
        log("ERROR", "kimi", "engine.start", f"{code} {detail}"[:200])
        self._on_event({"type": "engine_error", "code": code, "text": detail[:200]})

    def _note(self, line: str) -> None:
        # stderr_tail is served by /api/health; "kimi web" prints its bearer
        # token on stdout at startup, so every line is redacted here.
        text = redact(str(line or "")).strip()
        if not text:
            return
        self._stderr_tail.append(text[:300])
        self._stderr_tail = self._stderr_tail[-20:]

    # ------------------------------------------------------------------- HTTP

    def _req(self, method: str, path: str, body: Any = None, timeout: float = HTTP_TIMEOUT) -> Any:
        return kap_http(method, self.host, self.port, path, token=read_token(), body=body, timeout=timeout)

    def _sid_path(self, suffix: str) -> str:
        sid = str(self.session_id or "")
        if not sid:
            raise AcpError("no_session")
        return f"/sessions/{quote(sid)}{suffix}"

    def _refresh_models(self) -> None:
        models: list[dict[str, Any]] = []
        data: Any = None
        try:
            data = self._req("GET", "/models", timeout=HTTP_TIMEOUT)
        except AcpError as e:
            log("WARN", "kimi", "kap.models", str(e)[:120])
        items = data.get("items") if isinstance(data, dict) else None
        for it in items or []:
            if not isinstance(it, dict):
                continue
            value = str(it.get("model") or "")
            if not value:
                continue
            models.append({"value": value, "label": str(it.get("display_name") or value)})
        default_model = ""
        try:
            cfg = self._req("GET", "/config", timeout=HTTP_TIMEOUT)
            if isinstance(cfg, dict):
                default_model = str(cfg.get("default_model") or "")
        except AcpError:
            default_model = ""
        self._models = models
        if not self.current_model:
            known = {m["value"] for m in models}
            if default_model and (default_model in known or not known):
                self.current_model = default_model
            elif models:
                self.current_model = models[0]["value"]
        if models:
            self.config_options = [
                {"id": "model", "value": self.current_model, "options": list(models)}
            ]

    # ---------------------------------------------------------------- adapter

    def prompt(self, text: str) -> dict[str, Any]:
        if not self.alive:
            raise AcpError("kimi_kap_unavailable")
        if not self.session_id:
            self.session_new()
        elif self.session_id not in self._subs:
            # No subscription = no frames = the turn wait below could never end.
            self._subscribe([self.session_id])
        body: dict[str, Any] = {
            "content": [{"type": "text", "text": text}],
            "permission_mode": "auto" if self._auto_approve else "manual",
        }
        if self.current_model:
            body["model"] = self.current_model
        self._turn_prompt_id = ""
        self._turn_done.clear()
        self._last_activity = time.monotonic()
        data = self._req("POST", self._sid_path("/prompts"), body, timeout=PROMPT_TIMEOUT)
        if isinstance(data, dict):
            self._turn_prompt_id = str(data.get("prompt_id") or "")
        finished = self._wait_turn()
        return {"ok": True, "session_id": self.session_id, "finished": finished}

    def _wait_turn(self) -> bool:
        """Block until prompt.completed / a fatal error / abort for this prompt.

        Without a running event reader there is nothing to wait for, so return
        at once. Idle budget resets on every non-heartbeat frame.
        """
        while not self._turn_done.wait(0.5):
            if self._stop.is_set() or not self.alive or not self._ws_thread_alive:
                return False
            if time.monotonic() - self._last_activity > TURN_IDLE_TIMEOUT:
                log("WARN", "kimi", "prompt.wait", "no turn activity for 600 s; releasing /api/prompt")
                return False
        return True

    def cancel(self) -> None:
        if not self.session_id:
            return
        try:
            self._req("POST", self._sid_path(":abort"), {}, timeout=HTTP_TIMEOUT)
        except AcpError as e:
            log("WARN", "kimi", "session.cancel", str(e)[:120])
        self._turn_done.set()

    def session_list(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        before = ""
        for _ in range(10):
            path = f"/sessions?page_size={LIST_PAGE}&exclude_empty=true"
            if before:
                path += "&before_id=" + quote(before)
            data = self._req("GET", path, timeout=HTTP_TIMEOUT)
            items = data.get("items") if isinstance(data, dict) else None
            items = items or []
            for it in items:
                if not isinstance(it, dict):
                    continue
                sid = str(it.get("id") or "")
                if not sid:
                    continue
                title = str(it.get("title") or "")
                out.append({"sessionId": sid, "title": title or sid[:16], "updatedAt": it.get("updated_at")})
            has_more = bool(isinstance(data, dict) and data.get("has_more"))
            if len(out) >= LIST_MAX or not has_more or not items:
                break
            before = str(items[-1].get("id") or "")
            if not before:
                break
        return out[:LIST_MAX]

    def session_new(self) -> dict[str, Any]:
        data = self._req("POST", "/sessions", {"metadata": {"cwd": self.workspace}}, timeout=PROMPT_TIMEOUT)
        sid = str((data or {}).get("id") or "")
        if not sid:
            raise AcpError("kap_session_create_failed")
        self.session_id = sid
        self._subscribe([sid])
        if not self.current_model:
            self._refresh_models()
        log("INFO", "kimi", "session.new", sid)
        return {"session_id": sid, "model": self.current_model, "config_options": self.config_options}

    def session_load(self, session_id: str) -> dict[str, Any]:
        sid = str(session_id or "").strip()
        if not sid:
            raise AcpError("kap_session_id_required")
        self.session_id = sid
        self._subscribe([sid])
        try:
            data = self._req(
                "GET",
                f"/sessions/{quote(sid)}/transcript?agent_id=main&page_size=100",
                timeout=PROMPT_TIMEOUT,
            )
        except AcpError as e:
            log("WARN", "kimi", "session.load", str(e)[:120])
            data = None
        self._replay(data)
        log("INFO", "kimi", "session.load", sid)
        return {"sessionId": sid}

    def session_delete(self, session_id: str) -> dict[str, Any]:
        sid = str(session_id or "").strip()
        if not sid:
            return {"ok": False, "error": "not_found"}
        return self._delete_one(sid)

    def session_delete_many(self, session_ids: list[Any]) -> dict[str, Any]:
        deleted: list[str] = []
        failed: list[dict[str, str]] = []
        missing: list[str] = []
        for raw in session_ids:
            sid = str(raw or "").strip()
            if not sid:
                continue
            info = self._delete_one(sid)
            if info.get("ok"):
                deleted.append(sid)
                continue
            err = str(info.get("error") or "delete_failed")
            if err == "not_found":
                missing.append(sid)
            else:
                failed.append({"sessionId": sid, "error": err})
        return {
            "ok": not failed,
            "deleted": deleted,
            "deleted_count": len(deleted),
            "failed": failed,
            "missing": missing,
            "via": "kap",
        }

    def _delete_one(self, sid: str) -> dict[str, Any]:
        try:
            self._req("POST", f"/sessions/{quote(sid)}:delete", {}, timeout=HTTP_TIMEOUT)
        except KapError as e:
            if e.code == SESSION_NOT_FOUND or "does not exist" in e.msg.lower():
                return {"ok": False, "error": "not_found"}
            log("WARN", "kimi", "session.delete", str(e)[:160])
            return {"ok": False, "error": str(e)[:160]}
        except AcpError as e:
            log("WARN", "kimi", "session.delete", str(e)[:160])
            return {"ok": False, "error": str(e)[:160]}
        if self.session_id == sid:
            self.session_id = None
        self._drop_sub(sid)
        log("INFO", "kimi", "session.delete", f"{sid} via=kap")
        return {"ok": True, "via": "kap"}

    def set_config(self, config_id: str, value: Any) -> Any:
        if config_id != "model":
            raise AcpError(f"unsupported_config:{config_id}")
        self.current_model = str(value or "")
        if self._models:
            self.config_options = [
                {"id": "model", "value": self.current_model, "options": list(self._models)}
            ]
        log("INFO", "kimi", "session.model", self.current_model)
        return self.current_model

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": "kimi",
            "alive": self.alive,
            "acp": False,
            "error": self.error,
            "session_id": self.session_id,
            "model": self.current_model,
            "mode": "",
            "config_options": self.config_options,
            "agent_version": ("kap " + self.agent_version).strip(),
            "stderr_tail": list(self._stderr_tail[-8:]),
            "starting": bool(self._starting and not self._alive),
            "transport": "kap",
        }

    # --------------------------------------------------------------------- WS

    def _ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}/api/v1/ws"

    def _start_ws(self) -> None:
        self._ws_thread_alive = True
        threading.Thread(target=self._ws_loop, daemon=True, name="kap-ws").start()

    def _teardown_ws(self) -> None:
        with self._send_lock:
            ws = self._ws
            self._ws = None
        if ws is not None:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass

    def _ws_loop(self) -> None:
        fails = 0
        idx = 0
        try:
            while not self._stop.is_set() and self._alive:
                token = read_token()
                if not token:
                    self._fatal = True
                    self._alive = False
                    self._fail("kimi_kap_unavailable", "server.token missing (kimi web rotate-token)")
                    return
                try:
                    ws = websocket.create_connection(
                        self._ws_url(),
                        header=["Authorization: Bearer " + token],
                        timeout=HTTP_TIMEOUT,
                        enable_multithread=True,
                    )
                except Exception as e:  # noqa: BLE001
                    fails += 1
                    self._note(f"ws connect failed: {type(e).__name__}")
                    log("WARN", "kimi", "ws.connect", f"{type(e).__name__} try={fails}")
                    if fails >= CONNECT_FAILS_BEFORE_DEAD:
                        self._fatal = True
                        self._alive = False
                        log("ALERT", "kimi", "engine.dead", "kap websocket unreachable")
                        self._on_event(
                            {"type": "engine_error", "code": "kimi_kap_unreachable", "text": "websocket unreachable"}
                        )
                        return
                    self._stop.wait(BACKOFF[min(idx, len(BACKOFF) - 1)])
                    idx += 1
                    continue
                fails = 0
                idx = 0
                with self._send_lock:
                    self._ws = ws
                try:
                    ws.settimeout(2.0)
                    self._handshake(ws)
                    ws.settimeout(WS_POLL)
                    self._ws_read(ws)
                except Exception as e:  # noqa: BLE001
                    if not self._stop.is_set():
                        log("WARN", "kimi", "ws.loop", f"{type(e).__name__}:{str(e)[:100]}")
                        self._note(f"ws loop: {type(e).__name__}")
                finally:
                    with self._send_lock:
                        if self._ws is ws:
                            self._ws = None
                    try:
                        ws.close()
                    except Exception:  # noqa: BLE001
                        pass
                if self._stop.is_set() or not self._alive:
                    return
                self._stop.wait(BACKOFF[min(idx, len(BACKOFF) - 1)])
                idx += 1
        finally:
            self._ws_thread_alive = False

    def _handshake(self, ws: Any) -> None:
        subs = list(self._subs)
        cursors = {sid: dict(self._cursors[sid]) for sid in subs if sid in self._cursors}
        hello = {
            "type": "client_hello",
            "id": uuid.uuid4().hex,
            "payload": {"client_id": "ai-coding-desktop", "subscriptions": subs, "cursors": cursors},
        }
        ws.send(json.dumps(hello))
        deadline = time.monotonic() + HELLO_TIMEOUT
        while time.monotonic() < deadline and not self._stop.is_set():
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if not raw:
                raise KapTransportError("kap_ws_closed")
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            self._handle_frame(obj)
            if str(obj.get("type") or "") == "ack":
                return
        raise KapTransportError("kap_hello_timeout")

    def _ws_read(self, ws: Any) -> None:
        while not self._stop.is_set() and self._alive:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:  # noqa: BLE001 - a closed socket just ends the loop
                return
            if not raw:
                return
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            try:
                self._handle_frame(obj)
            except Exception as e:  # noqa: BLE001 - one bad frame must not kill the reader
                self._note(f"handler: {type(e).__name__}")
                log("ERROR", "kimi", "handler.error", repr(e)[:160])

    def _send(self, obj: dict[str, Any]) -> bool:
        payload = json.dumps(obj, ensure_ascii=False)
        with self._send_lock:
            ws = self._ws
            if ws is None:
                return False
            try:
                ws.send(payload)
            except Exception as e:  # noqa: BLE001
                log("WARN", "kimi", "ws.send", f"{type(e).__name__}:{str(e)[:80]}")
                return False
        return True

    def _subscribe(self, session_ids: list[str]) -> None:
        want = [s for s in dict.fromkeys(str(i) for i in session_ids if i)]
        if not want:
            return
        prev = list(self._subs)
        self._subs = want[-4:]
        if self._ws is None:
            return
        drop = [s for s in prev if s not in self._subs]
        if drop:
            self._send({"type": "unsubscribe", "id": uuid.uuid4().hex, "payload": {"session_ids": drop}})
        add = [s for s in self._subs if s not in prev]
        if add:
            self._send(
                {"type": "subscribe", "id": uuid.uuid4().hex, "payload": {"session_ids": add, "cursors": {}}}
            )

    def _drop_sub(self, sid: str) -> None:
        if sid in self._subs:
            self._subs = [s for s in self._subs if s != sid]
            if self._ws is not None:
                self._send({"type": "unsubscribe", "id": uuid.uuid4().hex, "payload": {"session_ids": [sid]}})
        self._cursors.pop(sid, None)

    # ---------------------------------------------------------- frame mapping

    def _handle_frame(self, obj: dict[str, Any]) -> None:
        kind = str(obj.get("type") or "")
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        sid = str(obj.get("session_id") or payload.get("sessionId") or "")
        seq = obj.get("seq")
        if sid and isinstance(seq, int):
            prev = self._cursors.get(sid) or {}
            if int(seq) >= int(prev.get("seq") or 0):
                entry: dict[str, Any] = {"seq": int(seq)}
                epoch = obj.get("epoch")
                if epoch:
                    entry["epoch"] = str(epoch)
                self._cursors[sid] = entry
        self.last_frame_at = time.time()
        if kind == "ping":
            self._send({"type": "pong", "payload": {"nonce": str(payload.get("nonce") or "")}})
            return
        if kind == "resync_required":
            self._resync(sid)
            return
        if kind not in ("ack", "server_hello", "pong"):
            self._last_activity = time.monotonic()
        self._note_turn_end(kind, payload, sid)
        for ev in self._map_event(kind, payload, sid):
            self._on_event(ev)

    def _note_turn_end(self, kind: str, payload: dict[str, Any], sid: str) -> None:
        if sid and self.session_id and sid != self.session_id:
            return
        if kind == "prompt.completed":
            pid = str(payload.get("promptId") or "")
            if not self._turn_prompt_id or not pid or pid == self._turn_prompt_id:
                self._turn_done.set()
        elif kind == "error" and not payload.get("retryable"):
            self._turn_done.set()

    def _map_event(self, kind: str, payload: dict[str, Any], sid: str) -> list[dict[str, Any]]:
        """kap frame -> the event shapes the existing UI already renders."""
        current = self.session_id
        if sid and current and sid != current:
            return []
        if kind == "assistant.delta":
            text = str(payload.get("delta") or "")
            if not text:
                return []
            return [
                {
                    "type": "session_update",
                    "params": {"update": {"sessionUpdate": "agent_message_chunk", "content": {"text": text}}},
                }
            ]
        if kind == "tool.call.started":
            name = str(payload.get("name") or "tool")
            call_id = str(payload.get("toolCallId") or "")
            if call_id:
                self._tools[call_id] = name
            return [
                {
                    "type": "session_update",
                    "params": {"update": {"sessionUpdate": "tool_call", "title": name, "status": "running"}},
                }
            ]
        if kind == "tool.result":
            name = self._tools.get(str(payload.get("toolCallId") or ""), "tool")
            return [
                {
                    "type": "session_update",
                    "params": {"update": {"sessionUpdate": "tool_call_update", "title": name, "status": "done"}},
                }
            ]
        if kind == "error":
            code = str(payload.get("code") or "kap_error")
            detail = str(payload.get("message") or "")
            self._note(f"{code}: {detail}")
            return [{"type": "engine_error", "code": code, "text": detail}]
        if kind == "event.approval.requested":
            return self._map_approval(payload, sid)
        return []

    def _map_approval(self, payload: dict[str, Any], sid: str) -> list[dict[str, Any]]:
        approval_id = ""
        for key in ("approvalId", "approval_id", "id", "interactionId"):
            if payload.get(key):
                approval_id = str(payload[key])
                break
        if not approval_id:
            return []
        if self._auto_approve and sid:
            threading.Thread(
                target=self._approve, args=(sid, approval_id), daemon=True, name="kap-approve"
            ).start()
            return []
        return [
            {"type": "permission", "params": {"sessionId": sid, "approvalId": approval_id, "request": payload}}
        ]

    def _approve(self, sid: str, approval_id: str) -> None:
        try:
            self._req(
                "POST",
                f"/sessions/{quote(sid)}/approvals/{quote(approval_id)}",
                {"decision": "approved"},
                timeout=HTTP_TIMEOUT,
            )
            log("INFO", "kimi", "approval.auto", approval_id)
        except AcpError as e:
            log("WARN", "kimi", "approval.auto", str(e)[:120])

    def _resync(self, sid: str) -> None:
        if not sid or sid != self.session_id:
            return
        log("WARN", "kimi", "ws.resync", "resync_required; refetching transcript")
        self._cursors.pop(sid, None)
        try:
            data = self._req(
                "GET",
                f"/sessions/{quote(sid)}/transcript?agent_id=main&page_size=100",
                timeout=PROMPT_TIMEOUT,
            )
        except AcpError as e:
            log("WARN", "kimi", "ws.resync", str(e)[:120])
            return
        turns = len(data.get("items") or []) if isinstance(data, dict) else 0
        log("INFO", "kimi", "ws.resync", f"transcript turns={turns}")

    def _replay(self, data: Any) -> None:
        """Transcript -> the same user / session_update events a live turn emits."""
        items = data.get("items") if isinstance(data, dict) else None
        for item in items or []:
            if not isinstance(item, dict) or str(item.get("kind") or "") != "turn":
                continue
            origin = item.get("origin") if isinstance(item.get("origin"), dict) else {}
            if str(origin.get("kind") or "user") == "user":
                text = str(item.get("prompt") or "")
                if text:
                    self._on_event({"type": "user", "text": text})
            for step in item.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                for frame in step.get("frames") or []:
                    if not isinstance(frame, dict):
                        continue
                    kind = str(frame.get("kind") or "")
                    if kind == "text":
                        text = str(frame.get("text") or "")
                        if text:
                            self._on_event(
                                {
                                    "type": "session_update",
                                    "params": {
                                        "update": {
                                            "sessionUpdate": "agent_message_chunk",
                                            "content": {"text": text},
                                        }
                                    },
                                }
                            )
                    elif kind == "tool":
                        name = str(frame.get("name") or "tool")
                        state = str(frame.get("state") or "")
                        status = "done" if state in ("done", "completed") else (state or "running")
                        self._on_event(
                            {
                                "type": "session_update",
                                "params": {
                                    "update": {"sessionUpdate": "tool_call", "title": name, "status": status}
                                },
                            }
                        )


class KimiKapAdapter:
    """Thin wrapper so module_runtime can treat kap like every other engine."""

    def __init__(self, host: KimiKapHost) -> None:
        self.name = "kimi"
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

    def session_delete_many(self, session_ids: list[Any]) -> dict[str, Any]:
        return self.host.session_delete_many(session_ids)

    def set_config(self, config_id: str, value: Any) -> Any:
        return self.host.set_config(config_id, value)

    def snapshot(self) -> dict[str, Any]:
        return self.host.snapshot()
