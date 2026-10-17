"""Regression: ACP prompt wrapper recursed into itself (found during v1.3.1 acceptance).

Before the fix every session/update during session/prompt raised RecursionError in
the read-loop handler, so no assistant text ever reached the UI and the prompt
never settled (logged as handler.error + agent.dead).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "app" / "bridge"
APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(BRIDGE))
sys.path.insert(0, str(APP))

from acp_client import AcpClient  # noqa: E402


def test_prompt_wrapper_does_not_recurse():
    sink: list[dict] = []
    client = AcpClient("kimi", ["kimi.exe", "acp"], ".", on_event=sink.append)
    client.session_id = "session_test"

    def fake_request(method, params=None, timeout=120, activity_event=None):
        client._handle_line(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": "session_test",
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"text": "pong"},
                        },
                    },
                }
            )
        )
        assert activity_event is not None and activity_event.is_set()
        return {"stopReason": "end_turn"}

    client.request = fake_request
    out = client.prompt("hi")
    assert out == {"stopReason": "end_turn"}
    assert sink and sink[-1]["type"] == "session_update"
    assert client.on_event == sink.append


def test_prompt_restores_handler_on_failure():
    sink: list[dict] = []
    client = AcpClient("kimi", ["kimi.exe", "acp"], ".", on_event=sink.append)
    client.session_id = "session_test"

    def boom(*_a, **_k):
        raise RuntimeError("agent died")

    client.request = boom
    try:
        client.prompt("hi")
    except RuntimeError:
        pass
    assert client.on_event == sink.append
