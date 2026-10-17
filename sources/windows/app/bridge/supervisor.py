"""Thin watchdog: restart desktop.py on crash, not on clean close (exit 0)."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

BRIDGE = Path(__file__).resolve().parent
DESKTOP = BRIDGE / "desktop.py"
MAX_RESTARTS = 3


def main() -> int:
    py = sys.executable
    restarts = 0
    while True:
        proc = subprocess.Popen([py, str(DESKTOP)], cwd=str(BRIDGE))
        code = proc.wait()
        if code == 0:
            return 0
        restarts += 1
        if restarts > MAX_RESTARTS:
            return code or 1
        time.sleep(1.2)


if __name__ == "__main__":
    if os.environ.get("ACD_NO_SUPERVISOR") == "1":
        os.chdir(BRIDGE)
        from desktop import main as desktop_main

        raise SystemExit(desktop_main())
    raise SystemExit(main())
