from __future__ import annotations

import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "app" / "bridge"
APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(BRIDGE))
sys.path.insert(0, str(APP))

from win_cli import claude_acp_argv, comspec, resolve_exe, terminal_argv, wrap_argv  # noqa: E402
from module_runtime import spawn_argv  # noqa: E402


def test_comspec_is_real_file():
    p = Path(comspec())
    assert p.is_file()
    assert p.name.lower() == "cmd.exe"


def test_wrap_cmd_uses_full_comspec():
    argv = wrap_argv(r"C:\Users\USER\AppData\Local\qwen-code\bin\qwen.cmd", ["--acp"])
    assert Path(argv[0]).is_file()
    assert argv[0].lower().endswith("cmd.exe")
    assert argv[0] != "cmd.exe"
    assert "--acp" in argv[-1]


def test_resolve_exe_finds_cmd():
    path = resolve_exe("cmd.exe")
    assert Path(path).is_file()


def test_qwen_spawn_not_bare_cmd():
    argv, auth = spawn_argv("qwen", r"C:\Users\USER\AppData\Local\qwen-code\bin\qwen.cmd")
    assert argv[0].lower().endswith("cmd.exe")
    assert Path(argv[0]).is_file()
    assert auth is None


def test_claude_exe_has_no_acp_argv(monkeypatch):
    monkeypatch.setattr("win_cli.shutil.which", lambda _n: None)
    argv = claude_acp_argv(r"C:\Users\USER\.local\bin\claude.exe")
    assert argv == []
    spawned, _ = spawn_argv("claude", r"C:\Users\USER\.local\bin\claude.exe")
    assert spawned == []


def test_claude_sidecar_is_used(monkeypatch, tmp_path):
    sidecar = tmp_path / "claude-agent-acp.cmd"
    sidecar.write_text("@echo off\n", encoding="utf-8")

    def _which(name: str):
        if name == "claude-agent-acp.cmd":
            return str(sidecar)
        return None

    monkeypatch.setattr("win_cli.shutil.which", _which)
    argv = claude_acp_argv(r"C:\Users\USER\.local\bin\claude.exe")
    assert argv
    assert str(sidecar) in argv[-1]


def test_terminal_cmd_stays_open():
    ws = r"C:\Users\USER"
    argv = terminal_argv(r"C:\Users\USER\AppData\Roaming\npm\dsh.cmd", ws)
    assert argv[0].lower().endswith("cmd.exe")
    assert "/k" in argv
    inner = argv[-1]
    assert "call" in inner
    assert "dsh.cmd" in inner
    assert "&&" not in inner


def test_terminal_ps1_uses_powershell():
    argv = terminal_argv(r"C:\Users\USER\AppData\Roaming\npm\dsh.ps1", r"C:\Users\USER")
    assert "powershell" in argv[0].lower()
    assert "-NoExit" in argv
    assert "-File" in argv
    assert argv[-1].endswith(".ps1")


def test_last_alert_includes_module(monkeypatch, tmp_path):
    import logging_setup as ls

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    run = ls.start_run(
        app_version="0.2.1",
        pid=1,
        workspace=str(tmp_path),
        enabled_modules=["claude"],
        python=sys.executable,
    )
    run.write("ALERT", "claude", "agent.dead", "read loop ended")
    assert run.last_alert().startswith("claude")
    assert "read loop ended" in run.last_alert()
    run.close()
