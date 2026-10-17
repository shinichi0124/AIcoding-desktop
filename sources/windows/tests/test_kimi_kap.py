"""kap adapter tests (plan docs/PLAN_kimi-kap-adapter_20261017.md task 10).

fixtures/kap_ws_frames.jsonl was recorded from a live kap-server on 2026-10-17
(the failed "model not set" turn and a successful "pong" + Bash tool turn),
then sanitized: bearer token removed, home path -> C:/Users/USER, volatile
frames deduplicated. Tests never talk to a real server: the fake below replays
recorded frames and answers REST calls in memory.
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "app" / "bridge"
APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(BRIDGE))
sys.path.insert(0, str(APP))

import pytest  # noqa: E402

from modules import kimi_kap  # noqa: E402
from modules.base import EngineAdapter  # noqa: E402
from modules.kimi_kap import (  # noqa: E402
    KapError,
    KapTransportError,
    KimiKapAdapter,
    KimiKapHost,
    discover_instance,
    kap_http,
    read_token,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kap_ws_frames.jsonl"


def load_fixture() -> list[dict]:
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()]


def fixture_session_id() -> str:
    for row in load_fixture():
        sid = row["frame"].get("session_id")
        if sid:
            return str(sid)
    return ""


def make_host(events: list | None = None, **kwargs) -> KimiKapHost:
    sink = events if events is not None else []
    host = KimiKapHost("kimi.exe", ".", 18774, sink.append, **kwargs)
    host.session_id = fixture_session_id()
    host._alive = True
    return host


# ------------------------------------------------------------------ frame map


def test_recorded_frames_map_to_existing_ui_events():
    events: list[dict] = []
    host = make_host(events)
    for row in load_fixture():
        if row["tag"] == "transcript":
            continue
        host._handle_frame(row["frame"])

    chunks = [e for e in events if e["type"] == "session_update"]
    kinds = [e["params"]["update"]["sessionUpdate"] for e in chunks]
    # the recording holds a text turn ("pong") and then a Bash tool turn
    assert kinds[:3] == ["agent_message_chunk", "tool_call", "tool_call_update"], kinds
    assert chunks[0]["params"]["update"]["content"]["text"] == "pong"
    assert chunks[1]["params"]["update"]["title"] == "Bash"
    assert chunks[1]["params"]["update"]["status"] == "running"
    assert chunks[2]["params"]["update"]["status"] == "done"
    assert not [e for e in events if e["type"] == "user"]  # no prompt echo from kap
    tool_turn_text = "".join(
        e["params"]["update"]["content"]["text"] for e in chunks[3:]
    )
    assert "CHANGELOG.md" in tool_turn_text

    errors = [e for e in events if e["type"] == "engine_error"]
    assert errors and errors[-1]["code"] == "model.not_configured"
    # thinking deltas, status pings and tool argument deltas must stay silent
    assert not [e for e in events if e["type"] == "permission"]


def test_ping_is_answered_with_pong(monkeypatch):
    host = make_host()
    sent: list[dict] = []
    monkeypatch.setattr(host, "_send", lambda obj: sent.append(obj) or True)
    host._handle_frame({"type": "ping", "payload": {"nonce": "abc"}})
    assert sent == [{"type": "pong", "payload": {"nonce": "abc"}}]


def test_frames_from_another_session_are_ignored():
    events: list[dict] = []
    host = make_host(events)
    host._handle_frame(
        {
            "type": "assistant.delta",
            "session_id": "session_other",
            "payload": {"type": "assistant.delta", "delta": "leak"},
        }
    )
    assert events == []


def test_resync_required_refetches_transcript(monkeypatch):
    host = make_host()
    calls: list[str] = []
    monkeypatch.setattr(host, "_req", lambda m, p, body=None, timeout=None: calls.append(p) or {"items": [{}]})
    host._handle_frame(
        {"type": "resync_required", "session_id": host.session_id, "payload": {"session_id": host.session_id}}
    )
    assert calls and "/transcript" in calls[0]


def test_cursor_tracks_seq_and_epoch():
    host = make_host()
    host._handle_frame({"type": "assistant.delta", "session_id": host.session_id, "seq": 7, "epoch": "ep_1",
                        "payload": {"type": "assistant.delta", "delta": "x"}})
    assert host._cursors[host.session_id]["seq"] == 7
    host._handle_frame({"type": "assistant.delta", "session_id": host.session_id, "seq": 3,
                        "payload": {"type": "assistant.delta", "delta": "y"}})
    assert host._cursors[host.session_id]["seq"] == 7


def test_transcript_replay_emits_user_text_and_tool():
    events: list[dict] = []
    host = make_host(events)
    transcript = [row for row in load_fixture() if row["tag"] == "transcript"][0]["frame"]
    host._replay(transcript)
    assert events[0]["type"] == "user"
    assert "list the files" in events[0]["text"]
    kinds = [e["params"]["update"]["sessionUpdate"] for e in events if e["type"] == "session_update"]
    assert "tool_call" in kinds
    assert "agent_message_chunk" in kinds


# ------------------------------------------------------------------ discovery


def _write_instance(root: Path, **overrides) -> None:
    row = {
        "server_id": "srv-1",
        "pid": 1234,
        "host": "127.0.0.1",
        "port": 62809,
        "started_at": 1,
        "heartbeat_at": 9999999999999,
        "host_version": "2.1.1",
    }
    row.update(overrides)
    (root / "server" / "instances").mkdir(parents=True, exist_ok=True)
    (root / "server" / "instances" / "srv-1.json").write_text(json.dumps(row), encoding="utf-8")


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setattr(kimi_kap, "kimi_home", lambda: tmp_path)
    monkeypatch.setattr(kimi_kap, "read_token", lambda: "tok-not-logged")
    monkeypatch.setattr(kimi_kap, "pid_alive", lambda pid: int(pid) == 1234)
    monkeypatch.setattr(kimi_kap, "healthz", lambda *a, **k: True)
    return tmp_path


def test_discovery_accepts_healthy_loopback(fake_home):
    _write_instance(fake_home, heartbeat_at=kimi_kap.time.time() * 1000.0)
    inst = discover_instance()
    assert inst is not None
    assert inst["port"] == 62809
    assert inst["host"] == "127.0.0.1"


def test_discovery_rejects_stale_heartbeat(fake_home):
    _write_instance(fake_home, heartbeat_at=kimi_kap.time.time() * 1000.0 - 5 * 60 * 1000)
    assert discover_instance() is None


def test_discovery_rejects_dead_pid(fake_home):
    _write_instance(fake_home, heartbeat_at=kimi_kap.time.time() * 1000.0, pid=424242)
    assert discover_instance() is None


def test_discovery_rejects_non_loopback_host(fake_home):
    _write_instance(fake_home, heartbeat_at=kimi_kap.time.time() * 1000.0, host="192.0.2.10")
    assert discover_instance() is None


def test_discovery_rejects_failing_healthz(fake_home, monkeypatch):
    _write_instance(fake_home, heartbeat_at=kimi_kap.time.time() * 1000.0)
    monkeypatch.setattr(kimi_kap, "healthz", lambda *a, **k: False)
    assert discover_instance() is None


def test_read_token_caches_by_mtime(tmp_path, monkeypatch):
    monkeypatch.setattr(kimi_kap, "kimi_home", lambda: tmp_path)
    (tmp_path / "server.token").write_text("abc\n", encoding="ascii")
    monkeypatch.setitem(kimi_kap._TOKEN_CACHE, "key", None)
    assert read_token() == "abc"
    (tmp_path / "server.token").write_text("def\n", encoding="ascii")
    kimi_kap._TOKEN_CACHE["key"] = None
    assert read_token() == "def"


# ---------------------------------------------------------------- HTTP / auth


class _401(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(401)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_a):
        return


def test_missing_token_is_401_transport_error():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _401)
    port = httpd.server_address[1]
    import threading

    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with pytest.raises(KapTransportError):
            kap_http("GET", "127.0.0.1", port, "/sessions", token="", timeout=5)
        assert not kimi_kap.healthz("127.0.0.1", port, "x", timeout=5)
    finally:
        httpd.shutdown()


def test_error_envelope_raises_kap_error(monkeypatch):
    def fake_urlopen(_req, timeout=None):
        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def read(self):
                return b'{"code": 40401, "msg": "session x does not exist", "data": null}'

        return Resp()

    monkeypatch.setattr(kimi_kap, "urlopen", fake_urlopen)
    with pytest.raises(KapError) as err:
        kap_http("POST", "127.0.0.1", 1, "/sessions/x:delete", token="t", body={})
    assert err.value.code == 40401


# -------------------------------------------------------------------- adapter


def test_adapter_satisfies_engine_protocol():
    assert isinstance(KimiKapAdapter(make_host()), EngineAdapter)


def test_prompt_sends_model_and_permission_mode(monkeypatch):
    host = make_host()
    host.current_model = "kimi-code/k3"
    seen: dict = {}

    def fake_req(method, path, body=None, timeout=None):
        seen["method"] = method
        seen["path"] = path
        seen["body"] = body
        return {}

    monkeypatch.setattr(host, "_req", fake_req)
    host.prompt("hello")
    assert seen["path"].endswith("/prompts")
    assert seen["body"]["permission_mode"] == "auto"
    assert seen["body"]["model"] == "kimi-code/k3"
    assert seen["body"]["content"] == [{"type": "text", "text": "hello"}]


def test_prompt_uses_manual_mode_when_auto_approve_off(monkeypatch):
    host = make_host(auto_approve=False)
    host.current_model = "m"
    seen: dict = {}
    monkeypatch.setattr(host, "_req", lambda m, p, body=None, timeout=None: seen.update(body=body) or {})
    host.prompt("hi")
    assert seen["body"]["permission_mode"] == "manual"


def test_cancel_posts_abort(monkeypatch):
    host = make_host()
    seen: dict = {}
    monkeypatch.setattr(host, "_req", lambda m, p, body=None, timeout=None: seen.update(m=m, p=p) or {})
    host.cancel()
    assert seen["m"] == "POST"
    assert seen["p"].endswith(":abort")


def test_session_list_follows_before_id_pages(monkeypatch):
    host = make_host()
    pages = [
        {"items": [{"id": "s1", "title": "", "updated_at": "t1"}, {"id": "s2", "title": "T", "updated_at": "t2"}],
         "has_more": True},
        {"items": [{"id": "s3", "title": "U"}], "has_more": False},
    ]
    calls: list[str] = []

    def fake_req(method, path, body=None, timeout=None):
        calls.append(path)
        return pages[len(calls) - 1]

    monkeypatch.setattr(host, "_req", fake_req)
    rows = host.session_list()
    assert [r["sessionId"] for r in rows] == ["s1", "s2", "s3"]
    assert rows[0]["title"] == "s1"[:16]
    assert "before_id=s2" in calls[1]


def test_delete_many_partial_failure(monkeypatch):
    host = make_host()

    def fake_req(method, path, body=None, timeout=None):
        if "gone" in path:
            raise KapError(40401, "session gone does not exist")
        if "bad" in path:
            raise KapError(50001, "kap exploded")
        return {"deleted": True}

    monkeypatch.setattr(host, "_req", fake_req)
    out = host.session_delete_many(["ok-1", "gone", "bad", "ok-2"])
    assert out["via"] == "kap"
    assert out["deleted"] == ["ok-1", "ok-2"]
    assert out["deleted_count"] == 2
    assert out["missing"] == ["gone"]
    assert out["failed"] and out["failed"][0]["sessionId"] == "bad"
    assert out["ok"] is False


def test_delete_clears_current_session(monkeypatch):
    host = make_host()
    monkeypatch.setattr(host, "_req", lambda m, p, body=None, timeout=None: {"deleted": True})
    info = host.session_delete(host.session_id)
    assert info == {"ok": True, "via": "kap"}
    assert host.session_id is None


def test_alive_drops_when_reader_is_fatal():
    host = make_host()
    host._alive = True
    assert host.alive is True
    host._fatal = True
    assert host.alive is False


def test_snapshot_shape():
    host = make_host()
    snap = host.snapshot()
    assert snap["acp"] is False
    assert snap["transport"] == "kap"
    assert snap["starting"] is False
    assert snap["agent_version"].startswith("kap")


def test_set_config_model_rebuilds_bar():
    host = make_host()
    host._models = [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]
    host.current_model = "a"
    host.set_config("model", "b")
    assert host.current_model == "b"
    assert host.config_options[0]["value"] == "b"
    assert [o["value"] for o in host.config_options[0]["options"]] == ["a", "b"]


def test_set_config_rejects_unknown_key():
    from acp_client import AcpError

    with pytest.raises(AcpError):
        make_host().set_config("mode", "x")


def test_prompt_refuses_when_not_alive():
    from acp_client import AcpError

    with pytest.raises(AcpError):
        make_host().prompt("hi")


# ------------------------------------------------------------ hygiene / wiring


def test_fixture_holds_no_secret_or_home_path():
    blob = FIXTURE.read_text(encoding="utf-8")
    home = str(Path.home())
    assert home not in blob
    assert home.replace("\\", "/") not in blob
    token_file = Path.home() / ".kimi-code" / "server.token"
    if token_file.is_file():
        token = token_file.read_text(encoding="ascii").strip()
        assert token and token not in blob
    assert "C:/Users/USER" in blob or "Users" not in blob


def test_kap_path_never_touches_kimi_storage():
    """Plan 2.4: the kap path must not read or write Kimi's private store.

    Only two files under ~/.kimi-code are ours to read: the published instance
    file (discovery) and server.token. Session mutation goes through the API.
    """
    src = (BRIDGE / "modules" / "kimi_kap.py").read_text(encoding="utf-8")
    for forbidden in ("session_index.jsonl", "search-index", "rmtree", "shutil.", "unlink("):
        assert forbidden not in src, forbidden
    assert 'kimi_home() / "server.token"' in src
    assert 'kimi_home() / "server" / "instances"' in src
    assert ":delete" in src and "/prompts" in src

def test_kap_source_never_logs_token():
    src = (BRIDGE / "modules" / "kimi_kap.py").read_text(encoding="utf-8")
    assert "?token=" not in src
    for line in src.splitlines():
        if "log(" in line or "_note(" in line:
            assert "read_token()" not in line, line
            assert "token=" not in line.replace("token=token", ""), line


def test_kap_source_has_bounded_io():
    src = (BRIDGE / "modules" / "kimi_kap.py").read_text(encoding="utf-8")
    assert "timeout=HTTP_TIMEOUT" in src
    assert "create_connection(" in src and "timeout=HTTP_TIMEOUT" in src
    assert "subprocess.Popen" in src and "hidden_popen_kwargs" in src
    assert "--no-open" in (BRIDGE / "win_cli.py").read_text(encoding="utf-8")


def test_kimi_web_argv_never_uses_cmdline_string():
    from win_cli import kimi_web_argv

    argv = kimi_web_argv(r"C:\Users\x\kimi.exe", 18774)
    assert argv[0].lower().endswith("kimi.exe")
    assert argv[1:] == ["web", "--no-open", "--port", "18774"]

# ------------------------------------------------- acceptance fixes (Claude, 2026-10-17)


def test_startup_banner_token_never_reaches_stderr_tail():
    host = make_host()
    secret = "abcDEF0123456789abcDEF0123456789abcDEF01234"
    host._note("  Local:    http://127.0.0.1:18774/#token=" + secret)
    host._note("  Token:    " + secret)
    assert secret not in json.dumps(host.snapshot())


def _run_prompt_in_thread(host):
    import threading

    out: dict = {}
    th = threading.Thread(target=lambda: out.update(r=host.prompt("hi")), daemon=True)
    th.start()
    return th, out


def test_prompt_blocks_until_prompt_completed(monkeypatch):
    host = make_host()
    host.current_model = "m"
    host._ws_thread_alive = True
    monkeypatch.setattr(host, "_req", lambda m, p, body=None, timeout=None: {"prompt_id": "msg_1"})
    th, out = _run_prompt_in_thread(host)
    th.join(0.8)
    assert th.is_alive(), "prompt must wait for the turn to end"
    sid = host.session_id
    host._handle_frame({"type": "prompt.completed", "session_id": sid, "payload": {"promptId": "msg_other"}})
    th.join(0.8)
    assert th.is_alive(), "another prompt's completion must not release this one"
    host._handle_frame({"type": "prompt.completed", "session_id": sid, "payload": {"promptId": "msg_1"}})
    th.join(2)
    assert not th.is_alive() and out["r"]["finished"] is True


def test_fatal_error_frame_releases_prompt(monkeypatch):
    host = make_host()
    host.current_model = "m"
    host._ws_thread_alive = True
    monkeypatch.setattr(host, "_req", lambda m, p, body=None, timeout=None: {"prompt_id": "msg_2"})
    th, _ = _run_prompt_in_thread(host)
    th.join(0.6)
    host._handle_frame({"type": "error", "session_id": host.session_id,
                        "payload": {"code": "model.not_configured", "retryable": False}})
    th.join(2)
    assert not th.is_alive()


def test_cancel_releases_waiting_prompt(monkeypatch):
    host = make_host()
    host.current_model = "m"
    host._ws_thread_alive = True
    monkeypatch.setattr(host, "_req", lambda m, p, body=None, timeout=None: {"prompt_id": "msg_3"})
    th, _ = _run_prompt_in_thread(host)
    th.join(0.6)
    host.cancel()
    th.join(2)
    assert not th.is_alive()
