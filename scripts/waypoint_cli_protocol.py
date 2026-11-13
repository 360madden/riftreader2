"""Local, file-backed request transport for an already running waypoint helper."""
from __future__ import annotations

import ctypes
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import socket
import time
import uuid

VERSION = 1
MAX_BYTES = 262144
MAX_PER_POLL = 16
_ID = re.compile(r'^[A-Za-z0-9_-]{1,80}$')


class CliError(Exception):
    def __init__(self, code, message, hint=None, exit_code=1):
        super().__init__(message)
        self.code, self.message, self.hint, self.exit_code = code, message, hint, exit_code


class Deferred:
    """Dispatcher will call complete after an asynchronous operation finishes."""


def _host():
    return socket.gethostname().upper()


def _process_start(pid):
    """Return a stable process-creation token, or None when it cannot be checked."""
    try:
        if os.name == 'nt':
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                return None
            try:
                creation, exit_time, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
                if not kernel.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel_time), ctypes.byref(user_time)):
                    return None
                return str((creation.dwHighDateTime << 32) | creation.dwLowDateTime)
            finally:
                kernel.CloseHandle(handle)
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, ValueError, IndexError):
        return None


def _root(helper, root):
    if not _ID.fullmatch(helper):
        raise CliError('invalid-helper', 'Invalid helper name')
    # A packaged terminal/desktop launch can redirect LOCALAPPDATA while its
    # pythonw child sees the ordinary path. Keep discovery stable across both.
    user_local = Path.home() / ('AppData/Local' if os.name == 'nt' else '.local/share')
    base = Path(root) if root is not None else user_local / 'RiftReader2' / 'helpers'
    return (base / helper).resolve()


def _valid_id(value):
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _read(path):
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('message too large')
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError('message too large')
    return json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite number')))


def _write_once(path, value):
    raw = json.dumps(value, allow_nan=False, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    if len(raw) > MAX_BYTES:
        raise ValueError('message too large')
    temp = path.with_name('.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('xb') as stream:
            stream.write(raw)
        os.link(temp, path)  # atomic publication, never replace an existing message
    finally:
        temp.unlink(missing_ok=True)


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _valid_descriptor(d, base):
    try:
        sid = d['sessionId']
        path = Path(d['path'])
        return (d['version'] == VERSION and _valid_id(sid) and d['host'] == _host()
                and path.resolve() == (base / sid).resolve() and path.parent.resolve() == base
                and isinstance(d['pid'], int) and d['pid'] > 0
                and d['processStart'] is not None and _process_start(d['pid']) == d['processStart'])
    except (KeyError, TypeError, ValueError, OSError):
        return False


def discover_sessions(helper='waypoints', root=None):
    base = _root(helper, root)
    if not base.is_dir():
        return []
    found = []
    for child in base.iterdir():
        if not child.is_dir() or child.is_symlink():
            continue
        try:
            descriptor = _read(child / 'session.json')
            if _valid_descriptor(descriptor, base):
                found.append(descriptor)
        except (OSError, ValueError, TypeError):
            continue
    return sorted(found, key=lambda item: item['sessionId'])


def resolve_session(session_id=None, helper='waypoints', root=None):
    sessions = discover_sessions(helper, root)
    if session_id is not None:
        sessions = [item for item in sessions if item['sessionId'] == session_id]
    if not sessions:
        raise CliError('session-not-found', 'No live waypoint helper session found', exit_code=3)
    if len(sessions) != 1:
        raise CliError('ambiguous-session', 'Multiple waypoint helper sessions are running', 'Specify a session ID', exit_code=3)
    return sessions[0]


def request(session, operation, args, timeout=10, request_id=None):
    rid = request_id or uuid.uuid4().hex
    if not _valid_id(rid) or not isinstance(operation, str) or not operation or not isinstance(args, dict):
        raise CliError('invalid-request', 'Invalid request ID, operation, or arguments')
    try:
        path = Path(session['path'])
        if not _valid_descriptor(session, path.parent.resolve()):
            raise CliError('stale-session', 'Helper session identity is no longer valid', exit_code=3)
        deadline = _now() + dt.timedelta(seconds=timeout)
        message = {'version': VERSION, 'sessionId': session['sessionId'], 'host': session['host'],
                   'pid': session['pid'], 'processStart': session['processStart'], 'requestId': rid,
                   'command': operation, 'arguments': args, 'deadlineUtc': deadline.isoformat()}
        request_path = path / 'requests' / (rid + '.json')
        try:
            _write_once(request_path, message)
        except FileExistsError:
            old = _read(request_path)
            if any(old.get(k) != message[k] for k in ('sessionId', 'command', 'arguments')):
                raise CliError('duplicate-request-id', 'Request ID already belongs to a different request')
        until = time.monotonic() + timeout
        while True:
            response = path / 'responses' / (rid + '.json')
            if response.exists():
                result = _read(response)
                if result.get('requestId') != rid or result.get('sessionId') != session['sessionId']:
                    raise CliError('invalid-response', 'Response identity does not match request')
                return result
            if time.monotonic() >= until:
                accepted = (path / 'accepted' / (rid + '.json')).exists()
                raise CliError('outcome-unknown', f'Request {rid} timed out; outcome is unknown' + (' after acceptance' if accepted else ''), 'Use the request ID to inspect status', exit_code=5)
            time.sleep(min(0.05, max(0, until - time.monotonic())))
    except CliError:
        raise
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        raise CliError('transport-error', f'Local transport failed: {exc}') from exc


class LocalSessionServer:
    def __init__(self, helper='waypoints', root=None, launch_token=None):
        self.base = _root(helper, root)
        self.base.mkdir(parents=True, exist_ok=True)
        self.session_id = uuid.uuid4().hex
        self.path = self.base / self.session_id
        self.path.mkdir()
        for name in ('requests', 'accepted', 'responses'):
            (self.path / name).mkdir()
        start = _process_start(os.getpid())
        if start is None:
            raise CliError('process-identity-unavailable', 'Cannot establish helper process identity')
        self.descriptor = {'version': VERSION, 'sessionId': self.session_id, 'host': _host(),
                           'pid': os.getpid(), 'processStart': start, 'path': str(self.path)}
        if launch_token is not None:
            if not _valid_id(launch_token):
                raise CliError('invalid-launch-token', 'Invalid launch token')
            self.descriptor['launchToken'] = launch_token
        _write_once(self.path / 'session.json', self.descriptor)
        self.pending = {}
        self.seen = set()
        self.closed = False

    def _envelope(self, rid, command, result):
        if not isinstance(result, dict):
            result = {'ok': False, 'status': 'error', 'error': {'code': 'invalid-dispatch-result', 'message': 'Dispatcher returned an invalid result'}}
        return {'version': VERSION, 'ok': bool(result.get('ok', False)), 'status': result.get('status', 'completed' if result.get('ok') else 'error'),
                'sessionId': self.session_id, 'requestId': rid, 'command': command,
                'target': result.get('target'),
                'data': result.get('data'), 'error': result.get('error')}

    def complete(self, request_id, result):
        if request_id not in self.pending:
            return False
        command = self.pending[request_id]
        try:
            _write_once(self.path / 'responses' / (request_id + '.json'), self._envelope(request_id, command, result))
        except (TypeError, ValueError):
            _write_once(self.path / 'responses' / (request_id + '.json'), self._envelope(request_id, command, {'ok': False, 'status': 'error', 'error': {'code': 'invalid-dispatch-result', 'message': 'Dispatcher result is not valid bounded JSON'}}))
        del self.pending[request_id]
        return True

    def poll(self, dispatch):
        if self.closed:
            return
        candidates = []
        for path in (self.path / 'requests').glob('*.json'):
            rid = path.stem
            if not _valid_id(rid) or rid in self.seen or (self.path / 'responses' / path.name).exists():
                continue
            try:
                msg = _read(path)
                if not isinstance(msg, dict):
                    raise ValueError('request must be an object')
            except (OSError, ValueError, TypeError):
                msg = {}
            candidates.append((0 if str(msg.get('command', '')).lower() == 'stop' else 1, path.name, rid, msg))
        for _, _, rid, msg in sorted(candidates)[:MAX_PER_POLL]:
            self.seen.add(rid)
            cmd = msg.get('command')
            error = None
            try:
                if (msg.get('version') != VERSION or msg.get('requestId') != rid or
                    any(msg.get(key) != self.descriptor[key] for key in ('sessionId', 'host', 'pid', 'processStart')) or
                    not isinstance(cmd, str) or not cmd or not isinstance(msg.get('arguments'), dict)):
                    raise ValueError('Malformed request or session identity mismatch')
                deadline = dt.datetime.fromisoformat(msg['deadlineUtc'])
                if deadline.tzinfo is None or deadline <= _now():
                    error = ('expired', 'Request deadline has expired')
            except (KeyError, TypeError, ValueError):
                error = ('invalid-request', 'Malformed request or session identity mismatch')
            self.pending[rid] = cmd
            if error:
                self.complete(rid, {'ok': False, 'status': 'error', 'error': {'code': error[0], 'message': error[1]}})
                continue
            _write_once(self.path / 'accepted' / (rid + '.json'), {'version': VERSION, 'sessionId': self.session_id, 'requestId': rid, 'status': 'accepted'})
            try:
                result = dispatch(cmd, msg['arguments'], rid)
                if not isinstance(result, Deferred):
                    self.complete(rid, result)
            except Exception as exc:
                self.complete(rid, {'ok': False, 'status': 'error', 'error': {'code': 'dispatch-error', 'message': str(exc)}})

    def close(self):
        self.closed = True
        (self.path / 'session.json').unlink(missing_ok=True)
