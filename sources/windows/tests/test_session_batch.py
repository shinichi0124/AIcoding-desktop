from __future__ import annotations

import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "app" / "bridge"
APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(BRIDGE))
sys.path.insert(0, str(APP))

from module_runtime import delete_sessions_batch  # noqa: E402


class FakeAdapter:
    def __init__(self) -> None:
        self.gone: list[str] = []

    def session_delete(self, sid: str) -> dict:
        if sid == "boom":
            raise RuntimeError("acp down")
        if sid == "missing":
            return {"ok": False, "error": "not_found"}
        if sid == "nope":
            return {"ok": False, "error": "delete_unsupported"}
        self.gone.append(sid)
        return {"ok": True, "via": "disk"}


def test_batch_skips_empty_and_keeps_going():
    ad = FakeAdapter()
    out = delete_sessions_batch(ad, ["a", "", "boom", "missing", "b", "nope"])
    assert ad.gone == ["a", "b"]
    assert out["deleted"] == ["a", "b"]
    assert out["deleted_count"] == 2
    assert out["missing"] == ["missing", "nope"]
    assert any(x["sessionId"] == "boom" for x in out["failed"])
    assert out["ok"] is False


def test_batch_none_adapter():
    out = delete_sessions_batch(None, ["a"])
    assert out["ok"] is False
    assert out["error"] == "engine_offline"
    assert out["deleted_count"] == 0


def test_batch_all_ok():
    ad = FakeAdapter()
    out = delete_sessions_batch(ad, ["x", "y"])
    assert out["ok"] is True
    assert out["deleted_count"] == 2
    assert out["failed"] == []


class ManyAdapter:
    def session_delete_many(self, ids):
        return {
            "ok": True,
            "deleted": [str(x) for x in ids],
            "deleted_count": len(ids),
            "failed": [],
            "missing": [],
            "via": "kimi_store",
        }

    def session_delete(self, sid: str) -> dict:
        raise AssertionError("batch must not loop session_delete when many exists")


def test_batch_prefers_session_delete_many():
    out = delete_sessions_batch(ManyAdapter(), ["a", "b"])
    assert out["deleted_count"] == 2
    assert out["via"] == "kimi_store"
