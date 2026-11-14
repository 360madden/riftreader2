from pathlib import Path
import datetime as dt
import os
import threading
import time

import pytest
from scripts import waypoint_cli_protocol as p


def message(server, rid, command='status', deadline=None):
    return dict(version=1, sessionId=server.session_id, host=server.descriptor['host'],
                pid=server.descriptor['pid'], processStart=server.descriptor['processStart'],
                requestId=rid, command=command, arguments={},
                deadlineUtc=(deadline or (p._now() + dt.timedelta(seconds=10))).isoformat())


def submit(server, rid, **kwargs):
    p._write_once(server.path / 'requests' / (rid + '.json'), message(server, rid, **kwargs))


def response(server, rid):
    return p._read(server.path / 'responses' / (rid + '.json'))


def test_discovery_rejects_stale_epoch_and_ambiguous(tmp_path, monkeypatch):
    first = p.LocalSessionServer(root=tmp_path)
    second = p.LocalSessionServer(root=tmp_path)
    with pytest.raises(p.CliError, match='Multiple'):
        p.resolve_session(root=tmp_path)
    monkeypatch.setattr(p, '_process_start', lambda pid: 'different')
    assert p.discover_sessions(root=tmp_path) == []
    first.close()
    second.close()


def test_deferred_duplicate_and_completion(tmp_path):
    server = p.LocalSessionServer(root=tmp_path)
    submit(server, 'one')
    calls = []
    def dispatch(op, args, rid):
        calls.append(rid)
        return p.Deferred()
    server.poll(dispatch)
    server.poll(dispatch)
    assert calls == ['one']
    assert (server.path / 'accepted' / 'one.json').exists()
    assert not (server.path / 'responses' / 'one.json').exists()
    assert server.complete('one', {'ok': True, 'data': {'done': True}})
    assert not server.complete('one', {'ok': True})
    assert response(server, 'one')['data'] == {'done': True}


def test_priority_expiry_malformed_and_dispatch_error(tmp_path):
    server = p.LocalSessionServer(root=tmp_path)
    submit(server, 'a')
    submit(server, 'z', command='stop')
    submit(server, 'expired', deadline=p._now() - dt.timedelta(seconds=1))
    p._write_once(server.path / 'requests' / 'bad.json', {'version': 1})
    calls = []
    def dispatch(op, args, rid):
        calls.append(rid)
        if rid == 'a':
            raise RuntimeError('busy')
        return {'ok': True}
    server.poll(dispatch)
    assert calls == ['z', 'a']
    assert response(server, 'expired')['error']['code'] == 'expired'
    assert response(server, 'bad')['error']['code'] == 'invalid-request'
    assert response(server, 'a')['error']['code'] == 'dispatch-error'


def test_client_timeout_after_acceptance_and_no_redispatch(tmp_path):
    server = p.LocalSessionServer(root=tmp_path)
    errors = []
    def client():
        try:
            p.request(server.descriptor, 'move', {}, timeout=.15, request_id='same')
        except p.CliError as exc:
            errors.append(exc.code)
    thread = threading.Thread(target=client)
    thread.start()
    for _ in range(100):
        if (server.path / 'requests' / 'same.json').exists():
            break
        time.sleep(.005)
    server.poll(lambda *args: p.Deferred())
    thread.join()
    assert errors == ['outcome-unknown']
    assert server.complete('same', {'ok': True})
    assert p.request(server.descriptor, 'move', {}, request_id='same')['ok']


def test_wrong_identity_and_nonfinite_are_rejected(tmp_path):
    server = p.LocalSessionServer(root=tmp_path)
    bad = message(server, 'wrong')
    bad['processStart'] = 'stale'
    p._write_once(server.path / 'requests' / 'wrong.json', bad)
    (server.path / 'requests' / 'nan.json').write_text('{"arguments":{"x":NaN}}')
    server.poll(lambda *args: pytest.fail('invalid request dispatched'))
    assert response(server, 'wrong')['error']['code'] == 'invalid-request'
    assert response(server, 'nan')['error']['code'] == 'invalid-request'


def test_busy_result_and_poll_limit(tmp_path):
    server = p.LocalSessionServer(root=tmp_path)
    for i in range(p.MAX_PER_POLL + 1):
        submit(server, f'r{i:02}')
    server.poll(lambda *args: {'ok': False, 'status': 'busy', 'error': {'code': 'busy'}})
    assert len(list((server.path / 'responses').glob('*.json'))) == p.MAX_PER_POLL
    assert response(server, 'r00')['status'] == 'busy'


def test_transport_accepts_maximum_measured_route_response_but_stays_bounded(tmp_path):
    identity = {'runtimeIdentity': {'machine': 'AMD-DESKTOP',
                'gameBuildSha256': 'a' * 64, 'unitKey': '18446744073709551615'}}
    points = [[('Point ' + str(i)).ljust(80, 'x'), float(i), float(i)] for i in range(500)]
    measurements = [
        {'version': 1, 'kind': 'native-loaded-unit-position',
         'position': {'x': point[1], 'y': 800.0, 'z': point[2]},
         'identity': identity, 'source': 'C:/work/riftreader2/artifacts/' + 's' * 220,
         'observedAtUtc': '2026-11-13T23:16:00.123456+00:00',
         'subjectKey': '18446744073709551615', 'entityAddressDecimal': '140737488355320',
         'sourceSha256': 'b' * 64, 'qualification': 'q' * 160}
        for point in points]
    result = {'document': {'waypoints': points, 'heights': [800.0] * 500,
                           'pointMeasurements': measurements},
              'points': [{'number': i + 1, 'name': point[0], 'x': point[1], 'z': point[2]}
                         for i, point in enumerate(points)]}
    path = tmp_path / 'large-response.json'
    p._write_once(path, result)
    assert path.stat().st_size > 262144
    assert p._read(path) == result
    with pytest.raises(ValueError, match='message too large'):
        p._write_once(tmp_path / 'too-large.json', {'value': 'x' * p.MAX_BYTES})
