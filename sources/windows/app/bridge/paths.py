"""Resolve CLI binaries (standard locations first, PATH cached 60s)."""
from __future__ import annotations

import os
import time
from pathlib import Path

_CACHE: dict[str, tuple[float, str | None]] = {}
_TTL = 60.0

MODULES = ("kimi", "xai", "codex", "claude", "qwen", "deepseek")


def _first_file(candidates: list[Path]) -> str | None:
    for c in candidates:
        try:
            if c.is_file():
                return str(c.resolve())
        except OSError:
            continue
    return None


def _path_scan(names: tuple[str, ...], accept=None) -> str | None:
    skip = ("windowsapps",)
    for part in os.environ.get("PATH", "").split(os.pathsep):
        if not part or any(s in part.lower() for s in skip):
            continue
        p = Path(part)
        for name in names:
            c = p / name
            try:
                if c.is_file():
                    resolved = str(c.resolve())
                    if accept is None or accept(resolved):
                        return resolved
            except OSError:
                continue
    return None


def is_qwen_code_binary(path: str | Path | None) -> bool:
    """Qwen Tab must be Qwen Code (`qwen`), never QwenCloud CLI (`qwencloud`)."""
    if not path:
        return False
    p = Path(str(path))
    low = str(p).replace("\\", "/").lower()
    name = p.name.lower()
    if "qwencloud" in low or name.startswith("qwencloud"):
        return False
    if name.startswith("launch-"):
        return False
    if name in ("qwen.cmd", "qwen.exe", "qwen.bat", "qwen"):
        return True
    return False


def _uncached(module: str) -> str | None:
    home = Path.home()
    la = Path(os.environ.get("LOCALAPPDATA") or (home / "AppData" / "Local"))
    if module == "kimi":
        return _first_file([home / ".kimi-code" / "bin" / "kimi.exe", home / ".kimi-code" / "bin" / "kimi"]) or _path_scan(("kimi.exe", "kimi"))
    if module == "xai":
        return _first_file([home / ".grok" / "bin" / "grok.exe", home / ".local" / "bin" / "grok.exe"]) or _path_scan(("grok.exe", "grok"))
    if module == "codex":
        return _first_file(
            [
                la / "OpenAI" / "Codex" / "bin" / "codex.exe",
                home / ".codex" / "bin" / "codex.exe",
            ]
        ) or _path_scan(("codex.exe", "codex"))
    if module == "claude":
        return _first_file([home / ".local" / "bin" / "claude.exe"]) or _path_scan(("claude.exe", "claude"))
    if module == "qwen":
        return _first_file(
            [
                la / "qwen-code" / "bin" / "qwen.cmd",
                la / "qwen-code" / "qwen-code" / "bin" / "qwen.cmd",
                la / "qwen-code" / "bin" / "qwen.exe",
            ]
        ) or _path_scan(("qwen.cmd", "qwen.exe", "qwen"), accept=is_qwen_code_binary)
    if module == "deepseek":
        npm = Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming")) / "npm"
        return _first_file([npm / "dsh.cmd", npm / "dsh.ps1"]) or _path_scan(("dsh.cmd", "dsh.exe", "dsh"))
    return None


def find_binary(module: str, override: str = "") -> str | None:
    if override:
        p = Path(override)
        try:
            if p.is_file():
                resolved = str(p.resolve())
                if module != "qwen" or is_qwen_code_binary(resolved):
                    return resolved
        except OSError:
            pass
    now = time.monotonic()
    hit = _CACHE.get(module)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    found = _uncached(module)
    _CACHE[module] = (now, found)
    return found
