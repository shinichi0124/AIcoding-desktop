"""Windows CLI spawn helpers — never treat bare cmd.exe as a file path."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def comspec() -> str:
    env = os.environ.get("COMSPEC") or r"C:\Windows\System32\cmd.exe"
    p = Path(env)
    if p.is_file():
        return str(p)
    fallback = Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "cmd.exe"
    if fallback.is_file():
        return str(fallback)
    found = shutil.which("cmd.exe")
    return found or env


def resolve_exe(argv0: str) -> str:
    """Return a real file path, or raise ValueError."""
    if not argv0:
        raise ValueError("empty_argv")
    p = Path(argv0)
    try:
        if p.is_file():
            return str(p)
    except OSError:
        pass
    found = shutil.which(argv0)
    if found:
        return found
    raise ValueError(f"binary_not_found: {argv0}")


def wrap_argv(binary: str, args: list[str] | None = None) -> list[str]:
    extra = list(args or [])
    low = binary.lower()
    if low.endswith(".cmd") or low.endswith(".bat"):
        cmdline = subprocess.list2cmdline([binary, *extra])
        return [comspec(), "/d", "/s", "/c", cmdline]
    return [binary, *extra]


def creation_no_window() -> int:
    """Hide the spawned console. Lives on subprocess, not os."""
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def hidden_popen_kwargs() -> dict:
    """Flags for a headless Windows child (no CMD flash)."""
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return {"creationflags": creation_no_window(), "startupinfo": si}


def resolve_node() -> str | None:
    skip = "windowsapps"
    home = Path.home()
    candidates = [
        Path(os.environ.get("ProgramFiles") or r"C:\Program Files") / "nodejs" / "node.exe",
        Path(os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)") / "nodejs" / "node.exe",
        Path(os.environ.get("LOCALAPPDATA") or (home / "AppData" / "Local")) / "Programs" / "nodejs" / "node.exe",
    ]
    for c in candidates:
        try:
            if c.is_file():
                return str(c)
        except OSError:
            continue
    found = shutil.which("node.exe") or shutil.which("node")
    if found and skip not in found.lower():
        return found
    return None


def dsh_js_from_binary(binary: str) -> Path | None:
    p = Path(binary)
    cands = [
        p.parent / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js",
        p.parent / "lib" / "bin.js",
    ]
    for c in cands:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def dsh_web_argv(binary: str, extra: list[str] | None = None) -> list[str]:
    """Prefer node.exe + bin.js so npm's dsh.cmd `title` trick cannot pop a console."""
    args = list(extra or [])
    js = dsh_js_from_binary(binary)
    node = resolve_node()
    if js is not None and node:
        return [node, str(js), *args]
    return wrap_argv(binary, args)


def kimi_web_argv(binary: str, port: int) -> list[str]:
    """kap server: kimi.exe web --no-open --port <p> (never a plain cmd line).

    --no-open  : never show Kimi's own page (platform rule 6: no iframe / no UI).
    --port     : explicit loopback port so discovery after boot is deterministic.
    """
    return wrap_argv(binary, ["web", "--no-open", "--port", str(int(port))])


def claude_acp_argv(binary: str) -> list[str]:
    """Official claude.exe has no --acp (v2.1.x). Only spawn a real ACP sidecar."""
    name = Path(binary).name.lower()
    if "acp" in name:
        return wrap_argv(binary, [])
    for cand in ("claude-agent-acp", "claude-agent-acp.cmd", "claude-code-acp", "claude-code-acp.cmd"):
        hit = shutil.which(cand)
        if hit:
            return wrap_argv(hit, [])
    return []


def terminal_argv(binary: str, workspace: str) -> list[str]:
    """Keep a visible console open on the CLI. List form, never a single CreateProcess string."""
    ws = workspace or str(Path.home())
    low = binary.lower()
    if low.endswith(".ps1"):
        ps = (
            shutil.which("powershell.exe")
            or str(Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
        )
        return [ps, "-NoExit", "-NoLogo", "-ExecutionPolicy", "Bypass", "-File", binary]
    if low.endswith((".cmd", ".bat")):
        inner = f'cd /d "{ws}" & title AI-Coding-Desktop & call "{binary}"'
    else:
        inner = f'cd /d "{ws}" & title AI-Coding-Desktop & "{binary}"'
    return [comspec(), "/d", "/k", inner]


def open_visible_terminal(binary: str, workspace: str) -> subprocess.Popen:
    ws = workspace or str(Path.home())
    argv = terminal_argv(binary, ws)
    creation = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    return subprocess.Popen(argv, cwd=ws if Path(ws).is_dir() else None, creationflags=creation, shell=False)
