"""Local HTTP bridge for AI Coding Desktop."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from acp_client import AcpError
from config import host_port, load_config, save_config, resolved_cli
from logging_setup import current_run, log, start_run
from module_runtime import MODULES, RUNTIME, delete_sessions_batch
from modules.credentials import apply_vendor_credentials
from paths import is_qwen_code_binary
from version import APP_NAME, APP_VERSION, DEFAULT_PORT, HOST
from win_cli import open_visible_terminal, wrap_argv

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
BRIDGE_TOKEN = uuid.uuid4().hex


def publish_bridge_token() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "AI-Coding-Desktop"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "bridge_token.txt"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(BRIDGE_TOKEN, encoding="ascii")
    os.replace(str(tmp), str(path))
    return path


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        log("DEBUG", "bridge", "http", fmt % args)

    def _check(self) -> bool:
        if self.path.startswith("/api/"):
            tok = self.headers.get("X-ACD-Token") or ""
            if tok != BRIDGE_TOKEN:
                from urllib.parse import parse_qs

                q = parse_qs(urlparse(self.path).query)
                if (q.get("token") or [""])[0] != BRIDGE_TOKEN:
                    self._send(401, {"ok": False, "error": "bad_token"})
                    return False
        return True

    def _send(self, code: int, obj: Any | None = None, body: bytes | None = None, ctype: str = "application/json; charset=utf-8") -> None:
        data = body if body is not None else (_json_bytes(obj) if obj is not None else b"")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Allow", "GET,POST,HEAD,OPTIONS")
        self.end_headers()

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        if not self._check():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
            html = html.replace("%%TOKEN%%", BRIDGE_TOKEN).replace("%%VERSION%%", APP_VERSION)
            self._send(200, body=html.encode("utf-8"), ctype="text/html; charset=utf-8")
            return
        if path.startswith("/static/") or path.endswith((".js", ".css", ".png", ".svg", ".ico")):
            rel = path[len("/static/") :] if path.startswith("/static/") else path.lstrip("/")
            fp = (WEB_DIR / rel.replace("\\", "/")).resolve()
            try:
                fp.relative_to(WEB_DIR.resolve())
            except ValueError:
                self._send(404, {"ok": False})
                return
            if not fp.is_file():
                self._send(404, {"ok": False})
                return
            ctype = {
                ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".png": "image/png",
                ".svg": "image/svg+xml",
                ".ico": "image/x-icon",
            }.get(fp.suffix.lower(), "application/octet-stream")
            self._send(200, body=fp.read_bytes(), ctype=ctype)
            return
        if path == "/api/health":
            run = current_run()
            modules = {n: RUNTIME.slots[n].snapshot() for n in MODULES}
            alert = run.last_alert() if run else ""
            if run:
                run.write_health({"t": __import__("time").time(), "modules": {k: v.get("state") for k, v in modules.items()}})
            self._send(200, {"ok": True, "version": APP_VERSION, "alert": alert, "active": RUNTIME.active, "modules": modules, "run_dir": str(run.run_dir) if run else ""})
            return
        if path == "/api/events":
            sl = RUNTIME.slot()
            since = 0
            from urllib.parse import parse_qs

            qs = parse_qs(parsed.query)
            try:
                since = int((qs.get("since") or ["0"])[0])
            except ValueError:
                since = 0
            ev = [e for e in sl.events if int(e.get("seq") or 0) > since]
            self._send(200, {"ok": True, "events": ev, "seq": sl.seq, "state": sl.snapshot()})
            return
        if path == "/api/sessions":
            sl = RUNTIME.slot()
            items: list = []
            try:
                RUNTIME.ensure_started(sl.name)
                if sl.adapter:
                    items = sl.adapter.session_list()
            except AcpError as e:
                log("WARN", sl.name, "session.list", str(e))
            self._send(200, {"ok": True, "sessions": items})
            return
        if path == "/api/settings":
            cfg = load_config()
            # never send raw keys to a query log; UI still needs them masked-capable
            safe = json.loads(json.dumps(cfg))
            for k, v in list((safe.get("api") or {}).items()):
                if v and k != "qwen_base_url":
                    safe["api"][k] = v  # keep for local settings form; not logged
            resolved = {m: resolved_cli(m, cfg) or "" for m in MODULES}
            self._send(200, {"ok": True, "config": safe, "resolved": resolved})
            return
        self._send(404, {"ok": False, "error": "not_found"})

    def _read_json(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        try:
            obj = json.loads(raw.decode("utf-8"))
        except Exception:
            return {}
        return obj if isinstance(obj, dict) else {}

    def do_POST(self) -> None:  # noqa: N802
        if not self._check():
            return
        path = urlparse(self.path).path
        body = self._read_json()
        try:
            if path == "/api/tab":
                RUNTIME.set_active(str(body.get("module") or "kimi"))
                self._send(200, {"ok": True, "active": RUNTIME.active, "state": RUNTIME.slot().snapshot()})
                return
            if path == "/api/start":
                mod = str(body.get("module") or RUNTIME.active)
                snap = RUNTIME.ensure_started(mod, retry=True)
                self._send(200, {"ok": True, "state": snap})
                return
            if path == "/api/session/new":
                sl = RUNTIME.slot()
                RUNTIME.ensure_started(sl.name)
                if not sl.adapter:
                    self._send(400, {"ok": False, "error": "engine_offline"})
                    return
                info = sl.adapter.session_new()
                sl._push({"type": "session_new", **info})
                self._send(200, {"ok": True, **info})
                return
            if path == "/api/session/load":
                sl = RUNTIME.slot()
                RUNTIME.ensure_started(sl.name)
                if not sl.adapter:
                    self._send(400, {"ok": False, "error": "engine_offline"})
                    return
                sid = str(body.get("sessionId") or body.get("id") or "")
                info = sl.adapter.session_load(sid)
                sl._push({"type": "session_load", "session_id": sid})
                self._send(200, {"ok": True, "session": info})
                return
            if path == "/api/session/delete":
                sl = RUNTIME.slot()
                RUNTIME.ensure_started(sl.name)
                sid = str(body.get("sessionId") or body.get("id") or "")
                if not sl.adapter or not sid:
                    self._send(400, {"ok": False, "error": "engine_offline"})
                    return
                info = sl.adapter.session_delete(sid)
                log("INFO", sl.name, "session.delete", sid)
                self._send(200, {"ok": True, **(info if isinstance(info, dict) else {})})
                return
            if path == "/api/sessions/delete":
                sl = RUNTIME.slot()
                RUNTIME.ensure_started(sl.name)
                raw_ids = body.get("sessionIds") or body.get("ids") or []
                if isinstance(raw_ids, str):
                    raw_ids = [raw_ids]
                one = str(body.get("sessionId") or body.get("id") or "")
                if one:
                    raw_ids = list(raw_ids) + [one]
                if not sl.adapter:
                    self._send(400, {"ok": False, "error": "engine_offline"})
                    return
                info = delete_sessions_batch(sl.adapter, list(raw_ids))
                log("INFO", sl.name, "sessions.delete", f"n={info.get('deleted_count')}")
                self._send(200, {"ok": True, **info})
                return
            if path == "/api/prompt":
                sl = RUNTIME.slot()
                RUNTIME.ensure_started(sl.name)
                text = str(body.get("text") or "")
                if not text.strip():
                    self._send(400, {"ok": False, "error": "empty"})
                    return
                if not sl.adapter:
                    self._send(400, {"ok": False, "error": "engine_offline"})
                    return
                sl._push({"type": "user", "text": text})
                result = sl.adapter.prompt(text)
                self._send(200, {"ok": True, "result": result})
                return
            if path == "/api/cancel":
                sl = RUNTIME.slot()
                if sl.adapter:
                    sl.adapter.cancel()
                self._send(200, {"ok": True})
                return
            if path == "/api/config":
                sl = RUNTIME.slot()
                if not sl.adapter:
                    self._send(400, {"ok": False, "error": "engine_offline"})
                    return
                cid = str(body.get("configId") or body.get("id") or "")
                val = body.get("value")
                sl.adapter.set_config(cid, val)
                self._send(200, {"ok": True, "state": sl.snapshot()})
                return
            if path == "/api/browse":
                path_picked = _browse_cli()
                self._send(200, {"ok": True, "path": path_picked or ""})
                return
            if path == "/api/settings":
                save_config(body)
                try:
                    apply_vendor_credentials(dict((body.get("api") or {})))
                except Exception as e:
                    log("WARN", "shell", "cred.write", str(e))
                log("INFO", "shell", "settings.save", "ok")
                self._send(200, {"ok": True})
                return
            if path == "/api/verify":
                cfg = load_config()
                rows = {}
                for m in MODULES:
                    p = resolved_cli(m, cfg)
                    ver = ""
                    ok = bool(p and Path(p).is_file())
                    if m == "qwen" and p and not is_qwen_code_binary(p):
                        ok = False
                        ver = "not Qwen Code"
                    if ok:
                        try:
                            argv = [p, "--version"]
                            if p.lower().endswith((".cmd", ".bat")):
                                argv = wrap_argv(p, ["--version"])
                            proc = subprocess.run(
                                argv,
                                capture_output=True,
                                timeout=12,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                            )
                            ver = ((proc.stdout or b"") + (proc.stderr or b"")).decode("utf-8", "replace").strip().splitlines()
                            ver = ver[0][:80] if ver else ""
                            ok = proc.returncode == 0 or bool(ver)
                            if m == "qwen" and ok:
                                ver = ("Qwen Code " + ver).strip()
                        except Exception as e:
                            ok = False
                            ver = str(e)[:80]
                    rows[m] = {
                        "cli": ok,
                        "path": p or "",
                        "version": ver,
                        "mark": "✓" if ok else "✗",
                    }
                    log("INFO", m, "verify.cli", "ok " + ver if ok else "missing")
                self._send(200, {"ok": True, "rows": rows})
                return
            if path == "/api/terminal":
                cfg = load_config()
                mod = str(body.get("module") or RUNTIME.active)
                binary = resolved_cli(mod, cfg)
                ws = str(cfg.get("workspace") or "")
                if not binary:
                    self._send(400, {"ok": False, "error": "cli_not_found"})
                    return
                open_visible_terminal(binary, ws)
                log("INFO", "shell", "terminal.open", f"{mod} {binary}")
                self._send(200, {"ok": True})
                return
            if path == "/api/logs/open":
                run = current_run()
                target = run.run_dir if run else None
                which = str(body.get("which") or "dir")
                if run and which == "important":
                    target = run.run_dir / "IMPORTANT.log"
                if target:
                    os.startfile(str(target))  # type: ignore[attr-defined]
                self._send(200, {"ok": True, "path": str(target or "")})
                return
            self._send(404, {"ok": False})
        except AcpError as e:
            log("ERROR", RUNTIME.active, "api.fail", str(e))
            self._send(500, {"ok": False, "error": str(e)})
        except Exception as e:
            log("ERROR", "bridge", "api.fail", repr(e))
            self._send(500, {"ok": False, "error": str(e)})


def _browse_cli() -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        picked = filedialog.askopenfilename(
            title="CLI",
            filetypes=[("Programs", "*.exe;*.cmd;*.bat"), ("All", "*.*")],
        )
        root.destroy()
        return str(picked or "")
    except Exception as e:
        log("WARN", "shell", "browse.fail", str(e))
        return ""


def serve_http() -> ThreadingHTTPServer:
    publish_bridge_token()
    host, port = host_port()
    httpd = ThreadingHTTPServer((host, port), Handler)
    log("INFO", "bridge", "listen", f"http://{host}:{httpd.server_address[1]}/")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
