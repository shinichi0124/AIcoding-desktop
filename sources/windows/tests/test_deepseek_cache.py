from __future__ import annotations

import json
from pathlib import Path

import sys

BRIDGE = Path(__file__).resolve().parents[1] / "app" / "bridge"
APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(BRIDGE))
sys.path.insert(0, str(APP))

from modules.deepseek_host import _hit_pct  # noqa: E402


def test_fixture_cache_read_matches_formula(tmp_path):
    fixture = {
        "type": "assistant/message",
        "seq": 3,
        "time": 1,
        "data": {
            "usage": {
                "cacheReadTokens": 120,
                "cacheWriteTokens": 30,
                "inputTokens": 50,
            }
        },
    }
    p = tmp_path / "session.jsonl"
    p.write_text(json.dumps(fixture) + "\n", encoding="utf-8")
    line = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    usage = line["data"]["usage"]
    cr = int(usage["cacheReadTokens"])
    cw = int(usage["cacheWriteTokens"])
    un = int(usage["inputTokens"])
    assert cr == 120
    assert _hit_pct(cr, un, cw) == round(100.0 * 120 / (50 + 120 + 30), 1)
