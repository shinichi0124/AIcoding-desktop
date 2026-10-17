"""User config in %USERPROFILE%\\.ai-coding-desktop (keys never logged)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from paths import MODULES, find_binary
from version import APP_NAME, DEFAULT_PORT, HOST


def data_root() -> Path:
    return Path.home() / ".ai-coding-desktop"


def config_path() -> Path:
    return data_root() / "config.json"


def default_workspace() -> str:
    here = Path(__file__).resolve()
    # bridge/app/windows/AI-Coding-Desktop/AI coding platform/AI projects
    for p in here.parents:
        if p.name == "AI projects":
            return str(p)
    return str(Path.home())


def _defaults() -> dict[str, Any]:
    return {
        "workspace": default_workspace(),
        "port": DEFAULT_PORT,
        "close_action": "quit",
        "lang": "zh",
        "auto_approve": True,
        "kimi_engine": "kap",
        "cli": {m: "" for m in MODULES},
        "api": {
            "moonshot": "",
            "xai": "",
            "openai": "",
            "anthropic": "",
            "deepseek": "",
            "qwen": "",
            "qwen_base_url": "",
        },
        "enabled": {m: True for m in MODULES},
    }


def load_config() -> dict[str, Any]:
    base = _defaults()
    path = config_path()
    if path.is_file():
        try:
            disk = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(disk, dict):
                for k, v in disk.items():
                    if isinstance(v, dict) and isinstance(base.get(k), dict):
                        base[k].update(v)
                    else:
                        base[k] = v
        except Exception:
            pass
    ca = str(base.get("close_action") or "quit").strip().lower()
    base["close_action"] = "tray" if ca in ("tray", "minimize", "min_tray", "tray_icon") else "quit"
    ke = str(base.get("kimi_engine") or "kap").strip().lower()
    base["kimi_engine"] = "acp" if ke in ("acp", "cli", "stdio") else "kap"
    return base


def save_config(cfg: dict[str, Any]) -> None:
    data_root().mkdir(parents=True, exist_ok=True)
    merged = load_config()
    for k, v in cfg.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v
    tmp = config_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(config_path()))


def resolved_cli(module: str, cfg: dict[str, Any] | None = None) -> str | None:
    cfg = cfg or load_config()
    override = str((cfg.get("cli") or {}).get(module) or "")
    return find_binary(module, override)


def host_port() -> tuple[str, int]:
    cfg = load_config()
    return HOST, int(cfg.get("port") or DEFAULT_PORT)


APP_NAME  # re-export silence
