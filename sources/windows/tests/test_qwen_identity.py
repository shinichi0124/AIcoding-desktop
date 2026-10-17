from __future__ import annotations

import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "app" / "bridge"
APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(BRIDGE))
sys.path.insert(0, str(APP))

import paths as paths_mod  # noqa: E402
from paths import find_binary, is_qwen_code_binary  # noqa: E402


def test_accepts_qwen_code_shim():
    assert is_qwen_code_binary(r"C:\Users\USER\AppData\Local\qwen-code\bin\qwen.cmd")
    assert is_qwen_code_binary(r"C:\Users\USER\AppData\Local\qwen-code\qwen-code\bin\qwen.cmd")


def test_rejects_qwencloud_and_launchers():
    assert not is_qwen_code_binary(r"C:\Users\USER\AppData\Roaming\npm\qwencloud.cmd")
    assert not is_qwen_code_binary(r"C:\Users\USER\AppData\Roaming\npm\qwencloud.ps1")
    assert not is_qwen_code_binary(
        r"C:\Users\USER\workspace\AI coding platform\QwenCloud-CLI\Launch-Qwen-Code.cmd"
    )


def test_override_qwencloud_does_not_stick(monkeypatch):
    paths_mod._CACHE.clear()
    cloud = r"C:\Users\USER\AppData\Roaming\npm\qwencloud.cmd"
    hit = find_binary("qwen", cloud)
    assert hit
    assert "qwencloud" not in hit.lower()
    assert is_qwen_code_binary(hit)
    assert Path(hit).name.lower() in ("qwen.cmd", "qwen.exe", "qwen")
