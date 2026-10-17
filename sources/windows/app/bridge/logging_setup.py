"""Run-scoped logs under %LOCALAPPDATA%\\AI-Coding-Desktop\\logs (never OneDrive)."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

LEVELS = ("DEBUG", "INFO", "WARN", "ERROR", "ALERT")
_IMPORTANT = frozenset({"WARN", "ERROR", "ALERT"})
_SECRET_RE = re.compile(
    r"(?i)(sk-[A-Za-z0-9_\-]{8,}|sk-ant-[A-Za-z0-9_\-]{8,}|bearer\s+[A-Za-z0-9_\-\.]+|"
    r"(?:api[_-]?key|token|secret)\s*[=:]\s*['\"]?[A-Za-z0-9_\-\.]{12,})"
)
_repeat_lock = threading.Lock()
_repeat: dict[tuple[str, str], tuple[float, int]] = {}


def logs_root() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "AI-Coding-Desktop" / "logs"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(dt: datetime | None = None) -> str:
    d = dt or _utc_now()
    return d.strftime("%Y%m%dT%H%M%SZ")


def redact(text: str) -> str:
    return _SECRET_RE.sub("[redacted]", text or "")


class LogRun:
    def __init__(self, run_dir: Path, run_id: str) -> None:
        self.run_dir = run_dir
        self.run_id = run_id
        self._lock = threading.Lock()
        self._fps: dict[str, TextIO] = {}
        self._last_alert = ""

    def close(self) -> None:
        with self._lock:
            for fp in self._fps.values():
                try:
                    fp.close()
                except Exception:
                    pass
            self._fps.clear()

    def _fp(self, rel: str) -> TextIO:
        path = self.run_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        key = rel.replace("\\", "/")
        fp = self._fps.get(key)
        if fp is None:
            new = not path.is_file()
            fp = path.open("a", encoding="utf-8")
            self._fps[key] = fp
            if new and rel == "IMPORTANT.log":
                fp.write("# IMPORTANT — 只含 WARN / ERROR / ALERT\n")
                fp.write("# 完整过程看同目录 shell.log / bridge.log / modules/<name>.log\n")
                fp.write("# 引擎原文看 agents/<name>.stderr.log\n")
                fp.flush()
        return fp

    def write(self, level: str, module: str, event: str, message: str = "") -> None:
        level = level.upper()
        if level not in LEVELS:
            level = "INFO"
        module = (module or "shell").replace(" ", "-")[:32]
        event = (event or "note").replace(" ", ".")[:64]
        message = redact(str(message or "")).replace("\n", " ").replace("\r", "")
        line = f"{_utc_now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]}Z  {level:<5}  {module:<10}  {event:<22}  {message}"
        if level == "ALERT":
            important_line = f"!!! {line}"
            self._last_alert = f"{module} · {message or event}"[:160]
        else:
            important_line = line
        channel = {
            "shell": "shell.log",
            "bridge": "bridge.log",
        }.get(module, f"modules/{module}.log")
        with self._lock:
            fp = self._fp(channel)
            fp.write(line + "\n")
            fp.flush()
            if level in _IMPORTANT:
                key = (module, event)
                now = time.monotonic()
                last, n = _repeat.get(key, (0.0, 0))
                if now - last < 10 and n >= 1:
                    _repeat[key] = (last, n + 1)
                    # rewrite last IMPORTANT conceptually via extra repeats= on next allowed
                    return
                _repeat[key] = (now, 1)
                extra = f" repeats={n}" if n > 1 else ""
                imp = self._fp("IMPORTANT.log")
                imp.write(important_line + extra + "\n")
                imp.flush()

    def write_health(self, obj: dict[str, Any]) -> None:
        with self._lock:
            fp = self._fp("health.jsonl")
            fp.write(json.dumps(obj, ensure_ascii=False) + "\n")
            fp.flush()

    def agent_stderr(self, module: str, text: str) -> None:
        text = redact(text.rstrip())
        if not text:
            return
        with self._lock:
            fp = self._fp(f"agents/{module}.stderr.log")
            fp.write(text + "\n")
            fp.flush()

    def last_alert(self) -> str:
        if self._last_alert:
            return self._last_alert
        path = self.run_dir / "IMPORTANT.log"
        if not path.is_file():
            return ""
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return ""
        for line in reversed(lines):
            if not line.startswith("!!! "):
                continue
            # !!! stamp  LEVEL  module  event  message
            body = line[4:]
            parts = [p for p in body.split("  ") if p.strip()]
            if len(parts) >= 4:
                module = parts[2].strip()
                msg = parts[-1].strip()
                return f"{module} · {msg}"[:160]
            return body.strip()[:160]
        return ""


_current: LogRun | None = None
_current_lock = threading.Lock()


def current_run() -> LogRun | None:
    return _current


def start_run(*, app_version: str, pid: int, workspace: str, enabled_modules: list[str], python: str) -> LogRun:
    global _current
    root = logs_root()
    root.mkdir(parents=True, exist_ok=True)
    now = _utc_now()
    run_id = os.urandom(3).hex()
    run_dir = root / "runs" / now.strftime("%Y-%m-%d") / f"{_stamp(now)}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "modules").mkdir(exist_ok=True)
    (run_dir / "agents").mkdir(exist_ok=True)
    meta = {
        "run_id": run_id,
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "app_version": app_version,
        "pid": pid,
        "workspace": workspace,
        "enabled_modules": enabled_modules,
        "python": python,
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    latest = root / "LATEST"
    tmp = latest.with_suffix(".tmp")
    tmp.write_text(str(run_dir), encoding="utf-8")
    os.replace(str(tmp), str(latest))
    readme = root / "README.txt"
    if not readme.is_file():
        readme.write_text(
            "先看 LATEST 指向的目录里的 IMPORTANT.log（只含警告和故障）。\n"
            "过程：shell.log / bridge.log / modules/<引擎>.log\n"
            "引擎原文：agents/<引擎>.stderr.log\n"
            "ALERT 行以 !!! 开头。\n",
            encoding="utf-8",
        )
    prune_old_runs(root)
    run = LogRun(run_dir, run_id)
    with _current_lock:
        if _current is not None:
            _current.close()
        _current = run
    run.write("INFO", "shell", "run.start", f"version={app_version} pid={pid}")
    return run


def prune_old_runs(root: Path, *, max_runs: int = 20, max_days: int = 14) -> None:
    runs_root = root / "runs"
    if not runs_root.is_dir():
        return
    dirs: list[Path] = []
    for day in runs_root.iterdir():
        if day.is_dir():
            for run in day.iterdir():
                if run.is_dir():
                    dirs.append(run)
    dirs.sort(key=lambda p: p.name, reverse=True)
    cutoff = time.time() - max_days * 86400
    archive = root / "archive"
    for i, d in enumerate(dirs):
        too_many = i >= max_runs
        try:
            too_old = d.stat().st_mtime < cutoff
        except OSError:
            too_old = False
        if too_many or too_old:
            dest = archive / d.parent.name / d.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                if dest.exists():
                    continue
                d.rename(dest)
            except OSError:
                pass
    # drop archive older than 30 days
    if archive.is_dir():
        arch_cutoff = time.time() - 30 * 86400
        for day in archive.iterdir():
            if not day.is_dir():
                continue
            for run in list(day.iterdir()):
                try:
                    if run.stat().st_mtime < arch_cutoff:
                        for p in run.rglob("*"):
                            if p.is_file():
                                p.unlink(missing_ok=True)
                        run.rmdir()
                except OSError:
                    pass


def log(level: str, module: str, event: str, message: str = "") -> None:
    run = _current
    if run is None:
        return
    run.write(level, module, event, message)
