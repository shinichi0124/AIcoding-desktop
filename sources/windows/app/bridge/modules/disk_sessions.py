"""Read-only session indexes + best-effort delete when ACP list/delete is missing."""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import time
from pathlib import Path
from typing import Any


def _safe_id(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)[:80]


def _encode_cwd(workspace: str) -> list[str]:
    raw = str(Path(workspace)).replace("\\", "/")
    alts = [
        raw.replace(":", ""),
        raw.replace(":", "").replace("/", "-"),
        _safe_id(raw),
    ]
    return list(dict.fromkeys(alts))


def list_qwen(workspace: str) -> list[dict[str, Any]]:
    root = Path.home() / ".qwen" / "projects"
    out: list[dict[str, Any]] = []
    if not root.is_dir():
        return out
    targets = {_encode_cwd(workspace)[0]}
    for folder in root.iterdir() if root.is_dir() else []:
        chats = folder / "chats"
        if not chats.is_dir():
            continue
        if targets and folder.name not in _encode_cwd(workspace) and len(list(root.iterdir())) > 8:
            # still include if name looks like this workspace
            if workspace.replace("\\", "/").split("/")[-1].lower() not in folder.name.lower():
                continue
        for p in sorted(chats.glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True)[:40]:
            title = p.stem
            try:
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[:8]:
                    obj = json.loads(line)
                    title = str(obj.get("title") or obj.get("name") or title)
                    break
            except Exception:
                pass
            out.append({"sessionId": p.stem, "title": title, "path": str(p), "updatedAt": int(p.stat().st_mtime)})
    return out


def list_codex() -> list[dict[str, Any]]:
    root = Path.home() / ".codex" / "sessions"
    out: list[dict[str, Any]] = []
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True)[:40]:
        out.append({"sessionId": p.stem, "title": p.stem[:40], "path": str(p), "updatedAt": int(p.stat().st_mtime)})
    return out


def list_claude(workspace: str) -> list[dict[str, Any]]:
    root = Path.home() / ".claude" / "projects"
    out: list[dict[str, Any]] = []
    if not root.is_dir():
        return out
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        for p in sorted(folder.glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
            out.append({"sessionId": p.stem, "title": p.stem[:40], "path": str(p), "updatedAt": int(p.stat().st_mtime)})
    return out[:40]


def delete_path(path_str: str) -> bool:
    p = Path(path_str)
    try:
        if p.is_file():
            p.unlink()
            return True
        if p.is_dir():
            for child in p.rglob("*"):
                if child.is_file():
                    child.unlink()
            p.rmdir()
            return True
    except OSError:
        return False
    return False


def delete_by_id(rows: list[dict[str, Any]], session_id: str) -> bool:
    for row in rows:
        sid = str(row.get("sessionId") or row.get("id") or "")
        if sid == session_id and row.get("path"):
            return delete_path(str(row["path"]))
    return False


# Kimi CLI has no working ACP session/delete. session/list is driven by
# ~/.kimi-code/session_index.jsonl plus session directories. Proven path from
# Kimi-Code-Web: rewrite the index, then rmtree exact-id directories.
KIMI_SESSIONS_ROOT = Path.home() / ".kimi-code" / "sessions"
KIMI_SESSION_INDEX = Path.home() / ".kimi-code" / "session_index.jsonl"
_KIMI_SESSION_ID_RE = re.compile(r"^(session|ses)_[A-Za-z0-9_-]+$")


def _filter_kimi_index(raw: str, session_ids: set[str]) -> tuple[str, int]:
    kept: list[str] = []
    removed = 0
    for line in raw.splitlines(keepends=True):
        payload = line.rstrip("\r\n")
        try:
            entry = json.loads(payload)
        except ValueError:
            kept.append(line)
            continue
        if not isinstance(entry, dict):
            kept.append(line)
            continue
        if str(entry.get("sessionId") or "") in session_ids:
            removed += 1
            continue
        kept.append(line)
    return "".join(kept), removed


def _write_kimi_index(content: str) -> str | None:
    tmp = KIMI_SESSION_INDEX.with_suffix(KIMI_SESSION_INDEX.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(KIMI_SESSION_INDEX)
        return None
    except OSError as e:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return str(e)


def _kimi_dir_matches(session_ids: list[str]) -> tuple[dict[str, list[Path]], str | None]:
    matches: dict[str, list[Path]] = {sid: [] for sid in session_ids}
    try:
        if not KIMI_SESSIONS_ROOT.is_dir():
            return matches, None
        for workspace_dir in KIMI_SESSIONS_ROOT.iterdir():
            if not workspace_dir.is_dir():
                continue
            for sid in session_ids:
                candidate = workspace_dir / sid
                if candidate.is_dir():
                    matches[sid].append(candidate)
    except OSError as e:
        return matches, str(e)
    return matches, None


def _remove_readonly_onerror(func: Any, path: str, exc_info: tuple[Any, Any, Any]) -> None:
    error = exc_info[1]
    access_denied = (
        isinstance(error, PermissionError)
        or getattr(error, "winerror", None) == 5
        or getattr(error, "errno", None) == 13
    )
    if not access_denied:
        raise error
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _delete_kimi_directory(directory: Path) -> str | None:
    retry_delays = (0.0, 0.15, 0.35, 0.75)
    last_error: OSError | None = None
    for attempt, delay in enumerate(retry_delays):
        if delay:
            time.sleep(delay)
        try:
            shutil.rmtree(directory, onerror=_remove_readonly_onerror)
            return None
        except FileNotFoundError:
            return None
        except OSError as error:
            last_error = error
            retryable = (
                isinstance(error, PermissionError)
                or getattr(error, "winerror", None) in (5, 32, 145)
                or getattr(error, "errno", None) in (13, 16, 39)
            )
            if not retryable or attempt == len(retry_delays) - 1:
                break
    return f"{last_error}; delete_retries_exhausted"


def delete_kimi_sessions(session_ids: list[str]) -> dict[str, Any]:
    """Purge Kimi session dirs + index rows. ACP session/delete is not enough."""
    requested: list[str] = []
    errors: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in session_ids:
        sid = str(raw or "").strip()
        if not sid:
            continue
        if not _KIMI_SESSION_ID_RE.fullmatch(sid):
            errors.append({"sessionId": sid, "error": "invalid_session_id"})
            continue
        if sid not in seen:
            requested.append(sid)
            seen.add(sid)
    if not requested:
        return {
            "ok": False,
            "deleted": [],
            "missing": [],
            "index_removed": 0,
            "errors": errors,
            "error": errors[0]["error"] if errors else "missing_session_ids",
        }

    matches, match_error = _kimi_dir_matches(requested)
    if match_error:
        return {
            "ok": False,
            "deleted": [],
            "missing": [],
            "index_removed": 0,
            "errors": [{"error": match_error}],
            "error": "session_directory_scan_failed",
        }

    raw_index: str | None = None
    rewritten: str | None = None
    index_removed = 0
    try:
        raw_index = KIMI_SESSION_INDEX.read_text(encoding="utf-8")
    except FileNotFoundError:
        raw_index = None
    except OSError as e:
        return {
            "ok": False,
            "deleted": [],
            "missing": [],
            "index_removed": 0,
            "errors": [{"error": str(e)}],
            "error": "session_index_read_failed",
        }
    if raw_index is not None:
        rewritten, index_removed = _filter_kimi_index(raw_index, set(requested))

    missing = [sid for sid in requested if not matches[sid]]
    if not any(matches.values()) and not index_removed:
        return {
            "ok": not errors,
            "deleted": [],
            "missing": missing,
            "index_removed": 0,
            "errors": errors,
            "error": errors[0]["error"] if errors else None,
        }

    if index_removed and rewritten is not None:
        write_error = _write_kimi_index(rewritten)
        if write_error:
            return {
                "ok": False,
                "deleted": [],
                "missing": missing,
                "index_removed": 0,
                "errors": [{"error": write_error}],
                "error": "session_index_write_failed",
            }

    deleted: list[str] = []
    completed: set[str] = set(missing)
    for sid in requested:
        for directory in matches[sid]:
            delete_error = _delete_kimi_directory(directory)
            if delete_error:
                if index_removed and raw_index is not None:
                    rollback, _ = _filter_kimi_index(raw_index, completed)
                    restore_error = _write_kimi_index(rollback)
                    if restore_error:
                        errors.append({"error": f"session_index_restore_failed: {restore_error}"})
                errors.append({"sessionId": sid, "error": delete_error})
                return {
                    "ok": False,
                    "deleted": deleted,
                    "missing": missing,
                    "index_removed": len(completed),
                    "errors": errors,
                    "error": "session_directory_delete_failed",
                }
        if matches[sid]:
            deleted.append(sid)
        completed.add(sid)

    return {
        "ok": not errors,
        "deleted": deleted,
        "missing": missing,
        "index_removed": index_removed,
        "errors": errors,
        "error": errors[0]["error"] if errors else None,
    }
