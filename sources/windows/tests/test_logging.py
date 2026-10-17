from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "app" / "bridge"
sys.path.insert(0, str(BRIDGE))

import logging_setup as ls  # noqa: E402


def test_logs_not_under_onedrive(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    root = ls.logs_root()
    assert "OneDrive" not in str(root)
    assert root.name == "logs"
    assert root.parent.name == "AI-Coding-Desktop"


def test_important_only_warn_up(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    run = ls.start_run(
        app_version="0.1.0",
        pid=1,
        workspace=str(tmp_path),
        enabled_modules=["kimi"],
        python=sys.executable,
    )
    run.write("INFO", "kimi", "session.new", "ok")
    run.write("WARN", "kimi", "slow.start", "3s")
    run.write("ALERT", "kimi", "agent.dead", "health timeout")
    text = (run.run_dir / "IMPORTANT.log").read_text(encoding="utf-8")
    assert "session.new" not in text
    assert "slow.start" in text
    assert "!!! " in text
    assert "agent.dead" in text
    run.close()


def test_alert_prefix(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    run = ls.start_run(
        app_version="0.1.0",
        pid=1,
        workspace=str(tmp_path),
        enabled_modules=["kimi"],
        python=sys.executable,
    )
    run.write("ALERT", "bridge", "health.fail", "read_thread=dead")
    lines = [
        ln
        for ln in (run.run_dir / "IMPORTANT.log").read_text(encoding="utf-8").splitlines()
        if not ln.startswith("#")
    ]
    assert lines[-1].startswith("!!! ")
    run.close()


def test_log_redacts_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    run = ls.start_run(
        app_version="0.1.0",
        pid=1,
        workspace=str(tmp_path),
        enabled_modules=["kimi"],
        python=sys.executable,
    )
    run.write("ERROR", "qwen", "auth.fail", "api_key=sk-abcdefghijklmnopqrstuvwxyz1234")
    blob = (run.run_dir / "modules" / "qwen.log").read_text(encoding="utf-8")
    assert "sk-abcdefghijklmnopqrstuvwxyz1234" not in blob
    assert "[redacted]" in blob
    meta = json.loads((run.run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["app_version"] == "0.1.0"
    latest = (ls.logs_root() / "LATEST").read_text(encoding="utf-8").strip()
    assert latest == str(run.run_dir)
    run.close()
