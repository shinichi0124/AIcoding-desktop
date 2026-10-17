from __future__ import annotations

import inspect
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "app" / "bridge"
APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(BRIDGE))
sys.path.insert(0, str(APP))

from modules.acp_engine import AcpAdapter  # noqa: E402
from modules.base import EngineAdapter  # noqa: E402
from modules.deepseek_host import DeepSeekAdapter, DeepSeekHost  # noqa: E402
from modules.kimi_kap import KimiKapAdapter  # noqa: E402


REQUIRED = (
    "start",
    "stop",
    "prompt",
    "cancel",
    "session_list",
    "session_load",
    "session_new",
    "session_delete",
    "set_config",
    "snapshot",
)


def test_adapters_expose_protocol_methods():
    for cls in (AcpAdapter, DeepSeekAdapter, KimiKapAdapter):
        for name in REQUIRED:
            assert callable(getattr(cls, name, None)), f"{cls.__name__}.{name}"


def test_engine_adapter_is_protocol():
    assert inspect.isclass(EngineAdapter)


def test_cache_formula():
    from modules.deepseek_host import _hit_pct

    assert _hit_pct(50, 40, 10) == 50.0
    assert _hit_pct(0, 0, 0) is None
