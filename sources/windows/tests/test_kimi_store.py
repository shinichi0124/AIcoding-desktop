from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

BRIDGE = Path(__file__).resolve().parents[1] / "app" / "bridge"
APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(BRIDGE))
sys.path.insert(0, str(APP))

import pytest  # noqa: E402

from modules import disk_sessions  # noqa: E402
from modules.acp_engine import AcpAdapter  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_kimi_paths():
    old_root = disk_sessions.KIMI_SESSIONS_ROOT
    old_index = disk_sessions.KIMI_SESSION_INDEX
    yield
    disk_sessions.KIMI_SESSIONS_ROOT = old_root
    disk_sessions.KIMI_SESSION_INDEX = old_index


def _seed_kimi(tmp_path: Path, session_id: str) -> Path:
    root = tmp_path / "sessions"
    index = tmp_path / "session_index.jsonl"
    session_dir = root / "wd_test" / session_id
    session_dir.mkdir(parents=True)
    (session_dir / "state.json").write_text("{}", encoding="utf-8")
    index.write_text(
        "not-json-preserved\n"
        + json.dumps({"sessionId": session_id, "sessionDir": str(session_dir)})
        + "\n"
        + json.dumps({"sessionId": "session_keep-me", "note": "unrelated"})
        + "\n",
        encoding="utf-8",
    )
    disk_sessions.KIMI_SESSIONS_ROOT = root
    disk_sessions.KIMI_SESSION_INDEX = index
    return session_dir


def test_kimi_delete_removes_dir_and_index_keeps_other_lines(tmp_path):
    sid = "session_abc-delete-me"
    session_dir = _seed_kimi(tmp_path, sid)
    out = disk_sessions.delete_kimi_sessions([sid])
    assert out["ok"] is True
    assert sid in out["deleted"]
    assert not session_dir.exists()
    raw = disk_sessions.KIMI_SESSION_INDEX.read_text(encoding="utf-8")
    assert "not-json-preserved" in raw
    assert "session_keep-me" in raw
    assert sid not in raw


def test_kimi_zombie_index_is_purged(tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    index = tmp_path / "session_index.jsonl"
    sid = "session_zombie-1"
    index.write_text(json.dumps({"sessionId": sid, "sessionDir": "gone"}) + "\n", encoding="utf-8")
    disk_sessions.KIMI_SESSIONS_ROOT = root
    disk_sessions.KIMI_SESSION_INDEX = index
    out = disk_sessions.delete_kimi_sessions([sid])
    assert out["ok"] is True
    assert sid in out["missing"]
    assert out["index_removed"] == 1
    assert sid not in index.read_text(encoding="utf-8")


def test_kimi_index_write_failure_leaves_dir(tmp_path, monkeypatch):
    sid = "session_locked-index"
    session_dir = _seed_kimi(tmp_path, sid)
    original = Path.replace

    def boom(self, target):
        if str(self).endswith(".jsonl.tmp"):
            raise PermissionError("index locked")
        return original(self, target)

    monkeypatch.setattr(Path, "replace", boom)
    out = disk_sessions.delete_kimi_sessions([sid])
    assert out["ok"] is False
    assert out["error"] == "session_index_write_failed"
    assert session_dir.is_dir()


def test_kimi_adapter_stops_agent_then_uses_store(tmp_path, monkeypatch):
    sid = "session_live-1"
    _seed_kimi(tmp_path, sid)
    events = []
    ad = AcpAdapter(
        "kimi",
        ["kimi.exe", "acp"],
        str(tmp_path),
        env=None,
        authenticate=None,
        auto_approve=True,
        on_event=lambda e: events.append(e),
    )
    client = MagicMock()
    client.alive = True
    ad.client = client
    out = ad.session_delete_many([sid])
    client.stop.assert_called_once()
    assert out["ok"] is True
    assert out["via"] == "kimi_store"
    assert out["deleted_count"] >= 1
    assert sid not in disk_sessions.KIMI_SESSION_INDEX.read_text(encoding="utf-8")


def test_kimi_session_delete_skips_acp_rpc():
    src = (BRIDGE / "modules" / "acp_engine.py").read_text(encoding="utf-8")
    fn = src.split("def session_delete(self, session_id")[1].split("def session_delete_many")[0]
    assert fn.index('if self.name == "kimi"') < fn.index("self.client.session_delete")
