"""DeepSeek mux downlink (v1.3.2): dsh 0.1.0-rc.6 serves /api/events.mux as a
downlink-only WebSocket (plain GET -> 426). fixtures/dsh_mux_frames.jsonl was
recorded from a live `dsh web` on 2026-10-17 ("Reply with exactly: pong") and
sanitized (system prompt / skill catalog trimmed, local paths replaced).
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "app" / "bridge"
APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(BRIDGE))
sys.path.insert(0, str(APP))

from modules.deepseek_host import DeepSeekHost  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "dsh_mux_frames.jsonl"


def frames() -> list[dict]:
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()]


def session_id() -> str:
    for f in frames():
        sid = (f.get("payload") or {}).get("sessionId")
        if sid:
            return str(sid)
    return ""


class _Proc:
    def poll(self):
        return None


def make_host(events: list) -> DeepSeekHost:
    host = DeepSeekHost("dsh", ".", 18773, events.append)
    host.session_id = session_id()
    host._alive = True
    host.proc = _Proc()
    return host


def chunks(events: list) -> str:
    return "".join(
        ((e.get("params") or {}).get("update") or {}).get("content", {}).get("text", "")
        for e in events
        if e.get("type") == "session_update"
    )


def test_recorded_turn_streams_pong_once_and_reports_cache():
    events: list = []
    host = make_host(events)
    for f in frames():
        host._handle_envelope(f)
    assert chunks(events) == "pong"  # deltas only; assistant/message is not shown again
    assert not [e for e in events if e.get("type") == "user"]  # live user/message is not echoed
    cache = [e for e in events if e.get("type") == "cache"]
    assert cache and cache[-1]["cache_hit"]["uncached"] > 0
    assert host._turn_done.is_set()


def test_injected_user_messages_never_show_on_replay():
    events: list = []
    host = make_host(events)
    for f in frames():
        ev = (f.get("payload") or {}).get("event")
        if isinstance(ev, dict):
            host._map_session_event(session_id(), ev, replay=True)
    users = [e["text"] for e in events if e.get("type") == "user"]
    assert users == ["Reply with exactly: pong"]  # plugin / skill-catalog messages filtered
    assert chunks(events) == "pong"


def test_replay_without_chunks_falls_back_to_full_message():
    events: list = []
    host = make_host(events)
    for f in frames():
        ev = (f.get("payload") or {}).get("event") or {}
        if ev.get("type") == "assistant/message":
            host._map_session_event(session_id(), ev, replay=True)
    assert chunks(events) == "pong"


def test_tool_call_and_result_map_to_tool_lines():
    events: list = []
    host = make_host(events)
    sid = session_id()
    host._map_session_event(sid, {"type": "tool/call", "data": {"callId": "c1", "name": "bash"}})
    host._map_session_event(sid, {"type": "tool/result", "data": {"callId": "c1"}})
    ups = [((e.get("params") or {}).get("update") or {}) for e in events]
    assert [(u["sessionUpdate"], u["title"], u["status"]) for u in ups] == [
        ("tool_call", "bash", "running"),
        ("tool_call_update", "bash", "done"),
    ]


def test_other_session_frames_are_ignored():
    events: list = []
    host = make_host(events)
    host.session_id = "session-other"
    for f in frames():
        host._handle_envelope(f)
    assert not [e for e in events if e.get("type") == "session_update"]


def _prompt_in_thread(host):
    out: dict = {}
    th = threading.Thread(target=lambda: out.update(r=host.prompt("hi")), daemon=True)
    th.start()
    return th, out


def test_prompt_blocks_until_turn_end(monkeypatch):
    host = make_host([])
    host._ws_thread_alive = True
    monkeypatch.setattr(host, "_rpc", lambda method, payload, timeout=60: {"accepted": True})
    th, out = _prompt_in_thread(host)
    th.join(0.8)
    assert th.is_alive(), "prompt must wait for turn/end"
    host._map_session_event(host.session_id, {"type": "turn/end", "data": {"turn": 1, "reason": {"kind": "completed"}}})
    th.join(2)
    assert not th.is_alive() and out["r"]["finished"] is True


def test_cancel_releases_waiting_prompt(monkeypatch):
    host = make_host([])
    host._ws_thread_alive = True
    monkeypatch.setattr(host, "_rpc", lambda method, payload, timeout=60: {"accepted": True})
    th, _ = _prompt_in_thread(host)
    th.join(0.6)
    host.cancel()
    th.join(2)
    assert not th.is_alive()


def test_no_sse_and_downlink_never_sends():
    src = (BRIDGE / "modules" / "deepseek_host.py").read_text(encoding="utf-8")
    assert "text/event-stream" not in src  # SSE GET now answers 426
    assert "ws://127.0.0.1:" in src and "/api/events.mux" in src
    assert "ws.send" not in src  # any client message makes dsh close the socket (1008)
    assert "create_connection(url, timeout=10)" in src


def test_fixture_holds_no_local_paths():
    raw = FIXTURE.read_text(encoding="utf-8")
    for bad in ("scratchpad", str(Path.home())):
        assert bad not in raw


def test_session_list_hides_archived(monkeypatch):
    host = make_host([])

    def fake_rpc(method, payload, timeout=60):
        if method == "session.list":
            return {"items": [{"sessionId": "s-keep"}, {"sessionId": "s-gone"}]}
        if method == "workspace.list":
            return {"items": [], "archivedSessionIds": ["s-gone"]}
        raise AssertionError(method)

    monkeypatch.setattr(host, "_rpc", fake_rpc)
    assert [r["sessionId"] for r in host.session_list()] == ["s-keep"]
