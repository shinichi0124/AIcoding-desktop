"""pywebview desktop window for AI Coding Desktop."""
from __future__ import annotations

import os
import shutil
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

BRIDGE_DIR = Path(__file__).resolve().parent
APP_DIR = BRIDGE_DIR.parent
sys.path.insert(0, str(BRIDGE_DIR))
sys.path.insert(0, str(APP_DIR))

from config import default_workspace, load_config  # noqa: E402
from logging_setup import current_run, log, start_run  # noqa: E402
from module_runtime import MODULES, RUNTIME  # noqa: E402
from server import BRIDGE_TOKEN, serve_http  # noqa: E402
from version import APP_NAME, APP_VERSION, AUMID, HOST  # noqa: E402

# Live taskbar icon: WM_SETICON from short-path classic BMP ICO.
# Do not use pythonnet Form.Icon (GIL deadlock). Do not SendMessageW (AppHang).
_hicon_big: Any = None
_hicon_small: Any = None
_window: Any = None
_force_quit = False
_tray_icon: Any = None
_tray_thread: threading.Thread | None = None


def _real_python() -> str:
    return sys.executable


def _stable_ico_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "AI-Coding-Desktop"


def _source_ico() -> Path | None:
    for p in (
        APP_DIR / "web" / "assets" / "ai-coding-desktop.ico",
        _stable_ico_dir() / "app.ico",
    ):
        if p.is_file():
            return p
    return None


def _ensure_stable_ico() -> Path | None:
    src = _source_ico()
    if src is None:
        return None
    dest = _stable_ico_dir() / "app.ico"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
    except OSError as e:
        log("WARN", "shell", "icon.copy", str(e))
        return src if src.is_file() else None
    return dest if dest.is_file() else src


def _window_hwnd(window: Any) -> int | None:
    if window is None:
        return None
    try:
        hwnd = int(getattr(window, "hwnd", 0) or 0)
        return hwnd or None
    except Exception:
        return None


def _root_hwnd(hwnd: int) -> int:
    if not hwnd:
        return 0
    try:
        import ctypes

        user32 = ctypes.windll.user32
        root = int(user32.GetAncestor(hwnd, 3) or 0) or int(user32.GetAncestor(hwnd, 2) or 0)
        return root or hwnd
    except Exception:
        return hwnd


def _enum_process_top_hwnds() -> list[int]:
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        pid_self = os.getpid()
        found: list[int] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _cb(hwnd: int, _lp: int) -> bool:  # type: ignore[misc]
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                proc = wintypes.DWORD(0)
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc))
                if int(proc.value) == pid_self and user32.GetParent(hwnd) == 0:
                    found.append(int(hwnd))
            except Exception:
                pass
            return True

        user32.EnumWindows(_cb, 0)
        return found
    except Exception as e:
        log("WARN", "shell", "icon.enum", str(e))
        return []


def _load_brand_hicons() -> tuple[Any, Any]:
    global _hicon_big, _hicon_small
    if _hicon_big or _hicon_small:
        return _hicon_big, _hicon_small
    import ctypes
    from ctypes import wintypes

    ico = _ensure_stable_ico()
    if ico is None:
        log("WARN", "shell", "icon.missing", "no app.ico")
        return None, None
    path = str(ico.resolve())
    user32 = ctypes.windll.user32
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE,
        wintypes.LPCWSTR,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.LoadImageW.restype = ctypes.c_void_p
    IMAGE_ICON, LR_LOADFROMFILE = 1, 0x0010
    big = user32.LoadImageW(None, path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
    small = user32.LoadImageW(None, path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
    if not big:
        big = user32.LoadImageW(None, path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE)
    if not small:
        small = big
    _hicon_big = int(big) if big else None
    _hicon_small = int(small) if small else None
    log("INFO", "shell", "icon.load", f"big={bool(big)} small={bool(small)} path={path}")
    return _hicon_big, _hicon_small


def _apply_hwnd_taskbar_icon(hwnd: int, hbig: Any, hsmall: Any) -> None:
    if not hwnd:
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1
    GCLP_HICON, GCLP_HICONSM = -14, -34
    SMTO_ABORTIFHUNG, SMTO_BLOCK = 0x0002, 0x0001
    send_timeout = user32.SendMessageTimeoutW
    send_timeout.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
    ]
    send_timeout.restype = ctypes.c_size_t

    def _set_icon(which: int, hicon: Any) -> None:
        result = ctypes.c_size_t(0)
        send_timeout(
            hwnd, WM_SETICON, which, int(hicon),
            SMTO_ABORTIFHUNG | SMTO_BLOCK, 250, ctypes.byref(result),
        )

    if hbig:
        _set_icon(ICON_BIG, hbig)
    if hsmall:
        _set_icon(ICON_SMALL, hsmall)
    try:
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            user32.SetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            user32.SetClassLongPtrW.restype = ctypes.c_void_p
            if hbig:
                user32.SetClassLongPtrW(hwnd, GCLP_HICON, ctypes.c_void_p(int(hbig)))
            if hsmall:
                user32.SetClassLongPtrW(hwnd, GCLP_HICONSM, ctypes.c_void_p(int(hsmall)))
        else:
            if hbig:
                user32.SetClassLongW(hwnd, GCLP_HICON, int(hbig))
            if hsmall:
                user32.SetClassLongW(hwnd, GCLP_HICONSM, int(hsmall))
    except Exception as e:
        log("WARN", "shell", "icon.classlong", str(e))


def _apply_window_icon(window: Any) -> None:
    if os.name != "nt" or window is None:
        return
    hbig, hsmall = _load_brand_hicons()
    if not hbig and not hsmall:
        return
    targets: list[int] = []
    base = _window_hwnd(window)
    if base:
        targets.append(_root_hwnd(base))
        targets.append(base)
    targets.extend(_enum_process_top_hwnds())
    seen: set[int] = set()
    uniq: list[int] = []
    for h in targets:
        if h and h not in seen:
            seen.add(h)
            uniq.append(h)
    for h in uniq:
        _apply_hwnd_taskbar_icon(h, hbig, hsmall)
    log("INFO", "shell", "icon.apply", f"hwnds={uniq}")


def _close_action() -> str:
    try:
        ca = str(load_config().get("close_action") or "quit").strip().lower()
    except Exception:
        ca = "quit"
    return "tray" if ca in ("tray", "minimize", "min_tray", "tray_icon") else "quit"


def _load_tray_image() -> Any:
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return None
    for p in (
        APP_DIR / "web" / "assets" / "ai-coding-desktop.png",
        _stable_ico_dir() / "app.ico",
        APP_DIR / "web" / "assets" / "ai-coding-desktop.ico",
    ):
        if p.is_file():
            try:
                im = Image.open(p).convert("RGBA")
                return im.resize((64, 64), Image.Resampling.LANCZOS)
            except Exception:
                continue
    return None


def _stop_tray() -> None:
    global _tray_icon
    icon = _tray_icon
    _tray_icon = None
    if icon is not None:
        try:
            icon.stop()
        except Exception:
            pass


def _show_main_window() -> None:
    w = _window
    if w is None:
        return
    try:
        w.show()
    except Exception:
        pass
    try:
        w.restore()  # type: ignore[union-attr]
    except Exception:
        pass
    log("INFO", "shell", "tray.show", "")


def _quit_from_tray() -> None:
    global _force_quit
    _force_quit = True
    _stop_tray()
    w = _window
    if w is not None:
        try:
            w.destroy()
        except Exception:
            try:
                w.hide()
            except Exception:
                pass
    log("INFO", "shell", "tray.quit", "")


def _ensure_tray() -> bool:
    global _tray_icon, _tray_thread
    if _tray_icon is not None:
        return True
    try:
        import pystray  # type: ignore
        from pystray import Menu, MenuItem  # type: ignore
    except ImportError:
        log("WARN", "shell", "tray.missing", "pystray not installed — fall back to minimize")
        return False
    image = _load_tray_image()
    if image is None:
        log("WARN", "shell", "tray.image", "no tray image")
        return False

    def on_show(icon=None, item=None) -> None:  # noqa: ARG001
        _show_main_window()

    def on_quit(icon=None, item=None) -> None:  # noqa: ARG001
        _quit_from_tray()

    menu = Menu(
        MenuItem("Show / 显示", on_show, default=True),
        MenuItem("Quit / 退出", on_quit),
    )
    icon = pystray.Icon("ai-coding-desktop", image, f"{APP_NAME} v{APP_VERSION}", menu)
    _tray_icon = icon

    def _run() -> None:
        try:
            icon.run()
        except Exception:
            log("WARN", "shell", "tray.run", traceback.format_exc()[-300:])

    _tray_thread = threading.Thread(target=_run, daemon=True, name="tray")
    _tray_thread.start()
    log("INFO", "shell", "tray.start", "")
    return True


def _hide_to_tray() -> None:
    w = _window
    if w is None:
        return
    try:
        w.hide()
    except Exception:
        try:
            w.minimize()
        except Exception:
            pass
    if not _ensure_tray():
        try:
            w.minimize()
        except Exception:
            pass
        log("INFO", "shell", "tray.fallback", "minimize")
    else:
        log("INFO", "shell", "tray.hide", "")


def _brand_async(window: Any) -> None:
    lock = threading.Lock()

    def _run() -> None:
        for delay in (0.4, 1.2, 2.5):
            time.sleep(delay)
            try:
                with lock:
                    _apply_window_icon(window)
            except Exception as e:
                log("WARN", "shell", "icon.brand", f"{delay}s {e}")

    threading.Thread(target=_run, daemon=True, name="brand-icon").start()


def main() -> int:
    cfg = load_config()
    ws = str(cfg.get("workspace") or default_workspace())
    start_run(
        app_version=APP_VERSION,
        pid=os.getpid(),
        workspace=ws,
        enabled_modules=list(MODULES),
        python=_real_python(),
    )
    if "WindowsApps" in _real_python():
        log("ALERT", "shell", "python.stub", "Windows Store python stub — use Anaconda")
    httpd = serve_http()
    port = httpd.server_address[1]
    url = f"http://{HOST}:{port}/?token={BRIDGE_TOKEN}"
    log("INFO", "shell", "window.open", url.split("token=")[0] + "token=set")

    def _boot_active() -> None:
        try:
            RUNTIME.ensure_started(RUNTIME.active)
        except Exception as e:
            log("ERROR", RUNTIME.active, "boot", str(e))

    threading.Thread(target=_boot_active, daemon=True).start()

    try:
        import webview  # type: ignore
    except ImportError:
        log("ALERT", "shell", "webview.missing", "pip install pywebview")
        print("pywebview missing. pip install pywebview", file=sys.stderr)
        print(f"Open in browser: {url}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        RUNTIME.stop_all()
        return 0

    try:
        if os.name == "nt":
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(AUMID)
    except Exception as e:
        log("WARN", "shell", "aumid", str(e))

    _ensure_stable_ico()
    # This pywebview build has no create_window(icon=). Taskbar icon is WM_SETICON.
    global _window, _force_quit
    _force_quit = False
    window = webview.create_window(f"{APP_NAME} v{APP_VERSION}", url, width=1280, height=860, min_size=(960, 640))
    _window = window

    def _on_closed() -> None:
        log("INFO", "shell", "window.close", "")
        _stop_tray()
        RUNTIME.stop_all()
        try:
            httpd.shutdown()
        except Exception:
            pass

    def _on_closing() -> bool:
        if _force_quit:
            return True
        if _close_action() == "tray":
            _hide_to_tray()
            return False
        return True

    def _on_shown() -> None:
        _brand_async(window)

    try:
        window.events.closed += _on_closed
    except Exception:
        pass
    try:
        window.events.closing += _on_closing  # type: ignore[attr-defined]
    except Exception as e:
        log("WARN", "shell", "events.closing", str(e))
    try:
        window.events.shown += _on_shown
    except Exception:
        pass

    def _gui_ready() -> None:
        _brand_async(window)

    try:
        webview.start(_gui_ready, debug=False)
    except TypeError:
        try:
            webview.start(debug=False)
        except Exception:
            log("ALERT", "shell", "webview.crash", traceback.format_exc()[-500:])
            raise
    except Exception:
        log("ALERT", "shell", "webview.crash", traceback.format_exc()[-500:])
        raise
    finally:
        RUNTIME.stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
