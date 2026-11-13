"""Fail-soft diagnostics for the Waypoints desktop helper.

This module deliberately has no GUI dependency.  Callers provide the small set
of useful runtime facts through ``set_context`` and a controlled state snapshot
to ``report``; environment variables, command line arguments, and global Python
configuration are never collected.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import traceback
import uuid
from collections import deque
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_BYTES = 1024 * 1024
BACKUP_COUNT = 2
MAX_LOG_GROUPS = 10
MAX_REPORT_CHARS = 32 * 1024
MAX_EVENT_LIMIT = 200
_EVENT_CACHE_SIZE = 500
_EVENT_READ_BYTES = 512 * 1024
_MAX_VALUE_CHARS = 2 * 1024
_MAX_COLLECTION_ITEMS = 30
_MAX_DEPTH = 4
_SNAPSHOT_KEYS = {
    "activeRequestId",
    "activity",
    "app",
    "beacons",
    "connection",
    "contextComparison",
    "currentWaypoint",
    "diagnostics",
    "floor",
    "guidance",
    "markers",
    "playback",
    "player",
    "pose",
    "preview",
    "radar",
    "recording",
    "recentResults",
    "rift",
    "route",
    "routeLibrary",
    "status",
    "target",
    "trail",
    "view",
    "waypoints",
    "zone",
}
_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "credential",
    "token",
    "authorization",
    "apikey",
    "api_key",
    "privatekey",
    "private_key",
    "cookie",
)
_ACTIVE_LOGS_LOCK = threading.RLock()
_ACTIVE_LOGS: set[str] = set()
_LOG_OWNER_PATTERN = re.compile(r"-(?P<pid>\d+)-[0-9a-fA-F]{8}\.log$")


def _path_identity(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _register_active(path: Path) -> None:
    with _ACTIVE_LOGS_LOCK:
        _ACTIVE_LOGS.add(_path_identity(path))


def _unregister_active(path: Path) -> None:
    with _ACTIVE_LOGS_LOCK:
        _ACTIVE_LOGS.discard(_path_identity(path))


def _process_is_active(pid: int) -> bool | None:
    """Read process liveness without signalling or modifying the target.

    ``None`` means Windows would not let us establish the answer. Callers must
    conservatively retain logs in that case.
    """
    if pid == os.getpid():
        return True
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_process.restype = wintypes.HANDLE
        wait_for_single_object = kernel32.WaitForSingleObject
        wait_for_single_object.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        wait_for_single_object.restype = wintypes.DWORD
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL

        synchronize = 0x00100000
        query_limited_information = 0x1000
        handle = open_process(synchronize | query_limited_information, False, pid)
        if not handle:
            # ERROR_INVALID_PARAMETER is returned for a PID that does not
            # identify a live process. Access denied and all other failures are
            # intentionally treated as unknown.
            return False if ctypes.get_last_error() == 87 else None
        try:
            result = wait_for_single_object(handle, 0)
            if result == 0:  # WAIT_OBJECT_0: process has exited.
                return False
            if result == 258:  # WAIT_TIMEOUT: process is still running.
                return True
            return None
        finally:
            close_handle(handle)
    except Exception:
        return None


def _log_group_active(path: Path) -> bool:
    identity = _path_identity(path)
    match = _LOG_OWNER_PATTERN.search(path.name)
    if match is None:
        # Legacy/unowned file names cannot refer to a log created by this
        # implementation and are safe to handle with normal filesystem rules.
        return False
    pid = int(match.group("pid"))
    if pid == os.getpid():
        with _ACTIVE_LOGS_LOCK:
            return identity in _ACTIVE_LOGS
    active = _process_is_active(pid)
    return active is not False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_text(value: Any, limit: int = _MAX_VALUE_CHARS) -> str:
    try:
        text = str(value)
    except Exception:
        text = f"<{type(value).__name__}>"
    # Keep reports and messages one-line readable without silently discarding
    # potentially useful characters. JSON encoding will escape these again.
    text = "".join(ch if ch >= " " and ch != "\x7f" else f"\\x{ord(ch):02x}" for ch in text)
    if len(text) > limit:
        return text[: max(0, limit - 14)] + "... [truncated]"
    return text


def _safe_traceback(value: Any, limit: int = 16 * 1024) -> str:
    """Preserve useful traceback layout while escaping unsafe controls."""
    try:
        text = str(value)
    except Exception:
        text = f"<{type(value).__name__}>"
    text = "".join(
        ch if ch in "\n\t" or (ch >= " " and ch != "\x7f") else f"\\x{ord(ch):02x}" for ch in text
    )
    if len(text) > limit:
        return text[: max(0, limit - 14)] + "... [truncated]"
    return text


def _is_sensitive_key(key: Any) -> bool:
    lowered = str(key).casefold()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth >= _MAX_DEPTH:
        return _safe_text(value, 200)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_COLLECTION_ITEMS:
                result["..."] = f"{len(value) - _MAX_COLLECTION_ITEMS} more items"
                break
            safe_key = _safe_text(key, 120)
            result[safe_key] = "<redacted>" if _is_sensitive_key(safe_key) else _sanitize(item, depth=depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items = [_sanitize(item, depth=depth + 1) for item in value[:_MAX_COLLECTION_ITEMS]]
        if len(value) > _MAX_COLLECTION_ITEMS:
            items.append(f"... {len(value) - _MAX_COLLECTION_ITEMS} more items")
        return items
    return _safe_text(value)


def _event_query(limit: Any, level: Any, search: Any) -> tuple[int, str, str]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_EVENT_LIMIT:
        raise ValueError(f"limit must be an integer from 1 to {MAX_EVENT_LIMIT}")
    if not isinstance(level, str) or level.casefold() not in {"all", "info", "warning", "error"}:
        raise ValueError("level must be one of: all, info, warning, error")
    if not isinstance(search, str):
        raise ValueError("search must be a string")
    search = search.strip()
    if len(search) > 200:
        raise ValueError("search must be 200 characters or fewer")
    return limit, level.upper(), search.casefold()


def _event_matches(entry: Mapping[str, Any], level: str, search: str) -> bool:
    severity = {"INFO": 10, "WARNING": 20, "ERROR": 30}
    minimum = {"ALL": 0, "INFO": 10, "WARNING": 20, "ERROR": 30}[level]
    if severity.get(str(entry.get("level", "")).upper(), 0) < minimum:
        return False
    if not search:
        return True
    try:
        rendered = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        rendered = _safe_text(entry)
    return search in rendered.casefold()


def _read_event_group(path: Path) -> list[dict[str, Any]]:
    """Read a bounded chronological tail from one log and its rotations."""
    data = bytearray()
    for candidate in (path, *(Path(f"{path}.{index}") for index in range(1, BACKUP_COUNT + 1))):
        try:
            with candidate.open("rb") as stream:
                stream.seek(0, os.SEEK_END)
                size = stream.tell()
                take = min(size, _EVENT_READ_BYTES - len(data))
                if take <= 0:
                    break
                stream.seek(-take, os.SEEK_END)
                data = bytearray(stream.read(take)) + data
        except (FileNotFoundError, PermissionError, OSError):
            continue

    entries: list[dict[str, Any]] = []
    # A bounded tail may begin in the middle of a JSON record. Invalid or
    # non-object records are intentionally ignored rather than surfaced.
    for line in bytes(data).decode("utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries[-_EVENT_CACHE_SIZE:]


class Diagnostics:
    """Small, thread-safe, fail-soft JSON-lines diagnostic log."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.directory = Path(root) / "artifacts" / "waypoint-logs"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.log_path = self.directory / f"waypoints-{stamp}-{os.getpid()}-{uuid.uuid4().hex[:8]}.log"
        self._lock = threading.RLock()
        self._context: dict[str, Any] = {}
        self._events: deque[tuple[int, dict[str, Any]]] = deque(maxlen=_EVENT_CACHE_SIZE)
        self._revision = 0
        self._available = False
        self._error: str | None = None
        self._closed = False
        self._previous_sys_hook = None
        self._previous_thread_hook = None
        self._sys_hook = None
        self._thread_hook = None
        _register_active(self.log_path)
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self._cleanup_old_groups()
        except Exception as exc:
            self._mark_failed(exc)
        self._append(
            {
                "timestamp": _utc_now(),
                "level": "INFO",
                "message": "Diagnostics started",
                "threadName": threading.current_thread().name,
            }
        )

    def set_context(self, **fields: Any) -> None:
        with self._lock:
            for key, value in fields.items():
                safe_key = _safe_text(key, 120)
                self._context[safe_key] = "<redacted>" if _is_sensitive_key(safe_key) else _sanitize(value)

    def info(self, message: Any, **fields: Any) -> None:
        self._write("INFO", message, fields)

    def warning(self, message: Any, **fields: Any) -> None:
        self._write("WARNING", message, fields)

    def exception(self, message: Any, exc: BaseException | None = None, **fields: Any) -> None:
        exc_type: type[BaseException] | None
        exc_value: BaseException | None
        exc_tb: Any
        if exc is None:
            exc_type, exc_value, exc_tb = sys.exc_info()
        else:
            exc_type, exc_value, exc_tb = type(exc), exc, exc.__traceback__
        if exc_type is not None and exc_value is not None:
            rendered = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            fields = dict(fields)
            fields["exceptionType"] = exc_type.__name__
            fields["exceptionMessage"] = _safe_text(exc_value)
            fields["traceback"] = rendered
        self._write("ERROR", message, fields)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "directory": str(self.directory),
                "logFile": str(self.log_path),
                "available": bool(self._available and not self._closed),
                "error": self._error,
                "eventRevision": self._revision,
                "retainedEvents": len(self._events),
                "droppedEvents": max(0, self._revision - len(self._events)),
            }

    def events(self, *, limit: int = 100, level: str = "all", search: str = "") -> dict[str, Any]:
        """Return a bounded newest-first view of records written this session.

        ``revision`` advances for every attempted record, allowing polling
        callers to skip redraws when nothing changed. Each entry's
        ``persisted`` field distinguishes durable writes from fail-soft memory
        records retained when the log destination is unavailable.
        """
        limit, normalized_level, normalized_search = _event_query(limit, level, search)
        with self._lock:
            shown: list[dict[str, Any]] = []
            matched_count = 0
            for event_id, entry in reversed(self._events):
                if _event_matches(entry, normalized_level, normalized_search):
                    matched_count += 1
                    if len(shown) >= limit:
                        continue
                    # A JSON round trip makes the returned values independent
                    # of the cache while preserving the exact persisted shape.
                    item = json.loads(json.dumps(entry, ensure_ascii=False))
                    item["eventId"] = event_id
                    shown.append(item)
            return {
                "entries": shown,
                "shownCount": len(shown),
                "matchedCount": matched_count,
                "totalBuffered": len(self._events),
                "droppedEvents": max(0, self._revision - len(self._events)),
                "revision": self._revision,
                "order": "newest-first",
                "available": bool(self._available and not self._closed),
                "error": self._error,
                "directory": str(self.directory),
                "logFile": str(self.log_path),
                "offline": False,
            }

    def report(self, snapshot: Any) -> str:
        """Return a bounded, clipboard-friendly diagnostic report."""
        with self._lock:
            context = dict(self._context)
            status = self.status()
            cached_tail = [entry for _event_id, entry in list(self._events)[-60:]]
        controlled: dict[str, Any]
        if isinstance(snapshot, Mapping):
            controlled = {
                str(key): _sanitize(value)
                for key, value in snapshot.items()
                if str(key) in _SNAPSHOT_KEYS and not _is_sensitive_key(key)
            }
        else:
            controlled = {"status": _sanitize(snapshot)}

        tail = self._read_tail(max_bytes=16 * 1024, max_lines=60)
        if (not status["available"] or not tail) and cached_tail:
            tail = [json.dumps(entry, ensure_ascii=False, separators=(",", ":")) for entry in cached_tail]
        errors: list[str] = []
        recent_error_entries = [entry for entry in cached_tail if entry.get("level") in {"WARNING", "ERROR"}]
        if not recent_error_entries:
            for line in tail:
                try:
                    entry = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if entry.get("level") in {"WARNING", "ERROR"}:
                    recent_error_entries.append(entry)
        for entry in recent_error_entries:
            if entry.get("level") in {"WARNING", "ERROR"}:
                rendered = f"{entry.get('timestamp', '?')} {entry.get('level')}: {entry.get('message', '')}"
                if entry.get("traceback"):
                    rendered += "\n" + str(entry["traceback"])
                errors.append(rendered)

        app_version = context.get("appVersion", context.get("appversion", "unknown"))
        sections = [
            "Joey D's Waypoints diagnostics",
            f"Generated: {_utc_now()}",
            f"App version: {_safe_text(app_version, 200)}",
            "",
            "Context:",
            json.dumps(context, ensure_ascii=False, indent=2, sort_keys=True),
            "",
            "Current state (controlled snapshot):",
            json.dumps(controlled, ensure_ascii=False, indent=2, sort_keys=True),
            "",
            "Logging:",
            json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True),
            "",
            "Recent warnings and errors:",
            "\n\n".join(errors[-10:]) if errors else "None recorded.",
            "",
            "Recent log tail:",
            "\n".join(tail) if tail else "Unavailable.",
        ]
        report = "\n".join(sections)
        if len(report) > MAX_REPORT_CHARS:
            suffix = "\n... [diagnostic report truncated]"
            report = report[: MAX_REPORT_CHARS - len(suffix)] + suffix
        return report

    def install_hooks(self) -> None:
        """Log unhandled main/worker exceptions and preserve existing hooks."""
        with self._lock:
            if self._closed or self._sys_hook is not None:
                return
            self._previous_sys_hook = sys.excepthook
            self._previous_thread_hook = getattr(threading, "excepthook", None)

            def sys_hook(exc_type: type[BaseException], exc_value: BaseException, exc_tb: Any) -> None:
                try:
                    self._exception_info("Unhandled exception", exc_type, exc_value, exc_tb)
                finally:
                    previous = self._previous_sys_hook
                    if previous is not None:
                        previous(exc_type, exc_value, exc_tb)

            def thread_hook(args: Any) -> None:
                thread = getattr(args, "thread", None)
                try:
                    self._exception_info(
                        "Unhandled thread exception",
                        getattr(args, "exc_type", type(getattr(args, "exc_value", Exception()))),
                        getattr(args, "exc_value", None),
                        getattr(args, "exc_traceback", None),
                        threadName=getattr(thread, "name", None),
                        threadIdent=getattr(thread, "ident", None),
                    )
                finally:
                    previous = self._previous_thread_hook
                    if previous is not None:
                        previous(args)

            self._sys_hook = sys_hook
            self._thread_hook = thread_hook
            sys.excepthook = sys_hook
            if hasattr(threading, "excepthook"):
                threading.excepthook = thread_hook

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            if self._sys_hook is not None and sys.excepthook is self._sys_hook:
                sys.excepthook = self._previous_sys_hook
            if (
                self._thread_hook is not None
                and hasattr(threading, "excepthook")
                and threading.excepthook is self._thread_hook
            ):
                threading.excepthook = self._previous_thread_hook
            self._sys_hook = None
            self._thread_hook = None
            self._closed = True
            self._available = False
            _unregister_active(self.log_path)

    def _exception_info(
        self,
        message: str,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_tb: Any,
        **fields: Any,
    ) -> None:
        if exc_type is not None and exc_value is not None:
            fields["exceptionType"] = exc_type.__name__
            fields["exceptionMessage"] = _safe_text(exc_value)
            fields["traceback"] = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        self._write("ERROR", message, fields)

    def _write(self, level: str, message: Any, fields: Mapping[str, Any]) -> None:
        with self._lock:
            if self._closed:
                return
            entry: dict[str, Any] = {
                "timestamp": _utc_now(),
                "level": level,
                "message": _safe_text(message),
                "threadName": _safe_text(threading.current_thread().name, 200),
            }
            if self._context:
                entry["context"] = dict(self._context)
            for key, value in fields.items():
                safe_key = _safe_text(key, 120)
                if _is_sensitive_key(safe_key):
                    entry[safe_key] = "<redacted>"
                elif safe_key == "traceback":
                    entry[safe_key] = _safe_traceback(value)
                else:
                    entry[safe_key] = _sanitize(value)
            self._append(entry)

    def _append(self, entry: Mapping[str, Any]) -> None:
        cached_entry = dict(entry)
        try:
            persisted_entry = dict(entry)
            persisted_entry["persisted"] = True
            data = (json.dumps(persisted_entry, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
            self.directory.mkdir(parents=True, exist_ok=True)
            self._rotate_if_needed(len(data))
            with self.log_path.open("ab") as stream:
                stream.write(data)
                stream.flush()
            cached_entry = json.loads(data)
            self._available = True
            self._error = None
        except Exception as exc:
            self._mark_failed(exc)
            cached_entry["persisted"] = False
            cached_entry["persistenceError"] = self._error
        finally:
            self._revision += 1
            self._events.append((self._revision, cached_entry))

    def _rotate_if_needed(self, incoming: int) -> None:
        try:
            current = self.log_path.stat().st_size
        except FileNotFoundError:
            return
        if current + incoming <= MAX_BYTES:
            return
        oldest = Path(f"{self.log_path}.{BACKUP_COUNT}")
        try:
            oldest.unlink()
        except FileNotFoundError:
            pass
        for index in range(BACKUP_COUNT - 1, 0, -1):
            source = Path(f"{self.log_path}.{index}")
            destination = Path(f"{self.log_path}.{index + 1}")
            if source.exists():
                source.replace(destination)
        self.log_path.replace(Path(f"{self.log_path}.1"))

    def _cleanup_old_groups(self) -> None:
        try:
            bases = sorted(
                self.directory.glob("waypoints-*.log"),
                key=lambda path: path.stat().st_mtime_ns,
                reverse=True,
            )
        except OSError:
            return
        for base in bases[MAX_LOG_GROUPS - 1 :]:
            if base == self.log_path:
                continue
            if _log_group_active(base):
                continue
            for candidate in (base, *(Path(f"{base}.{index}") for index in range(1, BACKUP_COUNT + 1))):
                try:
                    candidate.unlink()
                except (FileNotFoundError, PermissionError, OSError):
                    # An active Windows file is expected to refuse deletion.
                    pass

    def _read_tail(self, *, max_bytes: int, max_lines: int) -> list[str]:
        paths = [self.log_path, Path(f"{self.log_path}.1"), Path(f"{self.log_path}.2")]
        data = bytearray()
        for path in paths:
            try:
                with path.open("rb") as stream:
                    stream.seek(0, os.SEEK_END)
                    size = stream.tell()
                    take = min(size, max_bytes - len(data))
                    if take <= 0:
                        break
                    stream.seek(-take, os.SEEK_END)
                    chunk = stream.read(take)
                data = bytearray(chunk) + data
            except (FileNotFoundError, PermissionError, OSError):
                continue
        return bytes(data).decode("utf-8", errors="replace").splitlines()[-max_lines:]

    def _mark_failed(self, exc: BaseException) -> None:
        self._available = False
        self._error = f"{type(exc).__name__}: {_safe_text(exc, 500)}"


def _latest_log(root: str | os.PathLike[str]) -> tuple[Path, Path | None, str | None]:
    directory = Path(root) / "artifacts" / "waypoint-logs"
    try:
        candidates = list(directory.glob("waypoints-*.log"))
        if not candidates:
            return directory, None, "No saved Waypoints diagnostic logs were found."
        latest = max(candidates, key=lambda path: path.stat().st_mtime_ns)
        return directory, latest, None
    except Exception as exc:
        return directory, None, f"{type(exc).__name__}: {_safe_text(exc, 500)}"


def existing_status(root: str | os.PathLike[str]) -> dict[str, Any]:
    """Describe the newest saved log without starting a diagnostic session."""
    directory, latest, error = _latest_log(root)
    available = False
    if latest is not None:
        try:
            with latest.open("rb") as stream:
                stream.read(1)
            available = True
        except Exception as exc:
            error = f"{type(exc).__name__}: {_safe_text(exc, 500)}"
    return {
        "directory": str(directory),
        "logFile": str(latest) if latest is not None else None,
        "available": available,
        "error": error,
        "offline": True,
    }


def existing_events(
    root: str | os.PathLike[str],
    *,
    limit: int = 100,
    level: str = "all",
    search: str = "",
) -> dict[str, Any]:
    """Return recent saved events without creating a session, files, or hooks."""
    limit, normalized_level, normalized_search = _event_query(limit, level, search)
    status = existing_status(root)
    entries: list[dict[str, Any]] = []
    if status["logFile"]:
        entries = _read_event_group(Path(status["logFile"]))
    matched = [
        entry
        for entry in reversed(entries)
        if _event_matches(entry, normalized_level, normalized_search)
    ]
    shown = matched[:limit]
    return {
        "entries": shown,
        "shownCount": len(shown),
        "matchedCount": len(matched),
        "totalBuffered": len(entries),
        "droppedEvents": 0,
        "revision": 0,
        "order": "newest-first",
        "available": status["available"],
        "error": status["error"],
        "directory": status["directory"],
        "logFile": status["logFile"],
        "offline": True,
    }


def existing_report(root: str | os.PathLike[str]) -> str:
    """Build a bounded saved-log-only report without creating files or hooks."""
    status = existing_status(root)
    latest_text: list[str] = []
    context: dict[str, Any] = {}
    warnings: list[str] = []
    log_file = status["logFile"]
    if log_file:
        path = Path(log_file)
        data = bytearray()
        # Spend the fixed read budget on the newest data first, then prepend
        # any older rotation content so the displayed tail remains ordered.
        for candidate in (path, Path(f"{path}.1"), Path(f"{path}.2")):
            try:
                with candidate.open("rb") as stream:
                    stream.seek(0, os.SEEK_END)
                    size = stream.tell()
                    take = min(size, 16 * 1024 - len(data))
                    if take <= 0:
                        break
                    stream.seek(-take, os.SEEK_END)
                    data = bytearray(stream.read(take)) + data
            except (FileNotFoundError, PermissionError, OSError):
                continue
        latest_text = bytes(data).decode("utf-8", errors="replace").splitlines()[-60:]
        for line in latest_text:
            try:
                entry = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(entry.get("context"), dict):
                context.update(entry["context"])
            if entry.get("level") in {"WARNING", "ERROR"}:
                rendered = f"{entry.get('timestamp', '?')} {entry.get('level')}: {entry.get('message', '')}"
                if entry.get("traceback"):
                    rendered += "\n" + str(entry["traceback"])
                warnings.append(rendered)

    app_version = context.get("appVersion", context.get("appversion", "unknown"))
    report = "\n".join(
        [
            "Joey D's Waypoints diagnostics — saved logs only",
            "No live app snapshot is available; the Waypoints helper is not connected.",
            f"Generated: {_utc_now()}",
            f"App version: {_safe_text(app_version, 200)}",
            "",
            "Last saved context:",
            json.dumps(context, ensure_ascii=False, indent=2, sort_keys=True),
            "",
            "Saved-log status:",
            json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True),
            "",
            "Recent saved warnings and errors:",
            "\n\n".join(warnings[-10:]) if warnings else "None recorded in the saved tail.",
            "",
            "Recent saved log tail:",
            "\n".join(latest_text) if latest_text else "Unavailable.",
        ]
    )
    if len(report) > MAX_REPORT_CHARS:
        suffix = "\n... [diagnostic report truncated]"
        report = report[: MAX_REPORT_CHARS - len(suffix)] + suffix
    return report


__all__ = ["Diagnostics", "existing_events", "existing_report", "existing_status"]
