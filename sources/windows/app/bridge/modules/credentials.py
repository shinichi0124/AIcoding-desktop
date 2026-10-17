"""Write API keys to vendor-native stores. Never log values."""
from __future__ import annotations

import json
import os
from pathlib import Path

from logging_setup import log


def apply_vendor_credentials(api: dict[str, str]) -> None:
    ds = str(api.get("deepseek") or "").strip()
    if ds:
        _write_dsh_key(ds)
    qwen = str(api.get("qwen") or "").strip()
    if qwen:
        _touch_qwen_env_ref()


def _write_dsh_key(value: str) -> None:
    home = Path.home() / ".dsh"
    home.mkdir(parents=True, exist_ok=True)
    path = home / ".credentials.yaml"
    lines: list[str] = []
    if path.is_file():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
    out: list[str] = []
    written = False
    for line in lines:
        if line.startswith("DEEPSEEK_API_KEY:"):
            out.append("DEEPSEEK_API_KEY: " + value)
            written = True
        else:
            out.append(line)
    if not written:
        out.append("DEEPSEEK_API_KEY: " + value)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(path))
    log("INFO", "deepseek", "cred.write", "DEEPSEEK_API_KEY file=set")


def _touch_qwen_env_ref() -> None:
    """Keep qwen settings pointing at envKey; value is injected at spawn."""
    path = Path.home() / ".qwen" / "settings.json"
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(data, dict):
        return
    # Do not dump the secret into this json (plan: envKey only).
    log("INFO", "qwen", "cred.ref", "envKey left in settings.json")
