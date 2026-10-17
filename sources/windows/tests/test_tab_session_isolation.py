from __future__ import annotations

import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "app" / "bridge"
APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(BRIDGE))
sys.path.insert(0, str(APP))

from module_runtime import Runtime  # noqa: E402


def test_switch_tab_keeps_other_module_events():
    rt = Runtime()
    rt.slots["kimi"]._push({"type": "user", "text": "hello-kimi"})
    rt.set_active("xai")
    rt.slots["xai"]._push({"type": "user", "text": "hello-xai"})
    assert rt.active == "xai"
    kimi_texts = [e.get("text") for e in rt.slots["kimi"].events]
    xai_texts = [e.get("text") for e in rt.slots["xai"].events]
    assert "hello-kimi" in kimi_texts
    assert "hello-xai" in xai_texts
    assert "hello-kimi" not in xai_texts


def test_drafts_are_per_slot():
    rt = Runtime()
    rt.slots["kimi"].draft = "k"
    rt.slots["qwen"].draft = "q"
    assert rt.slots["kimi"].draft == "k"
    assert rt.slots["qwen"].draft == "q"
