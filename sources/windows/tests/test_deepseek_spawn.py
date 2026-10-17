from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

BRIDGE = Path(__file__).resolve().parents[1] / "app" / "bridge"
APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(BRIDGE))
sys.path.insert(0, str(APP))

from modules.deepseek_host import DeepSeekHost  # noqa: E402
from win_cli import creation_no_window, dsh_web_argv, hidden_popen_kwargs  # noqa: E402


def test_create_no_window_is_subprocess_flag():
    import os

    assert not hasattr(os, "CREATE_NO_WINDOW")
    assert creation_no_window() == int(subprocess.CREATE_NO_WINDOW)


def test_deepseek_host_source_does_not_use_os_create_no_window():
    src = (BRIDGE / "modules" / "deepseek_host.py").read_text(encoding="utf-8")
    assert "os.CREATE_NO_WINDOW" not in src
    assert "hidden_popen_kwargs" in src
    assert "dsh_web_argv" in src


def test_dsh_web_argv_prefers_node_bin_js(tmp_path, monkeypatch):
    cmd = tmp_path / "dsh.cmd"
    cmd.write_text("@echo off\n", encoding="utf-8")
    js = tmp_path / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
    js.parent.mkdir(parents=True)
    js.write_text("console.log(1)\n", encoding="utf-8")
    monkeypatch.setattr("win_cli.resolve_node", lambda: r"C:\Program Files\nodejs\node.exe")
    argv = dsh_web_argv(str(cmd), ["web", "--host", "127.0.0.1", "--port", "18773"])
    assert argv[0].lower().endswith("node.exe")
    assert argv[1].replace("\\", "/").endswith("lib/bin.js")
    assert "web" in argv
    assert not argv[0].lower().endswith("cmd.exe")


def test_hidden_popen_kwargs_sets_no_window():
    kw = hidden_popen_kwargs()
    assert kw["creationflags"] == subprocess.CREATE_NO_WINDOW
    assert kw["startupinfo"].wShowWindow == 0


def test_deepseek_start_returns_before_host_ready(monkeypatch):
    captured = {}

    def fake_popen(*_a, **k):
        captured["kwargs"] = k
        proc = MagicMock()
        proc.poll.return_value = None
        proc.pid = 42
        proc.stderr = None
        return proc

    monkeypatch.setattr("modules.deepseek_host.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "modules.deepseek_host.dsh_web_argv",
        lambda _b, extra: ["node.exe", "bin.js", *extra],
    )
    host = DeepSeekHost("dsh.cmd", ".", 18773, lambda _e: None)

    def slow_wait(_seconds):
        time.sleep(0.4)
        return True

    monkeypatch.setattr(host, "_wait_host", slow_wait)
    t0 = time.monotonic()
    snap = host.start()
    elapsed = time.monotonic() - t0
    assert elapsed < 0.25
    assert snap.get("starting") is True
    assert captured["kwargs"]["creationflags"] == subprocess.CREATE_NO_WINDOW
