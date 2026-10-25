"""One screenshot-reviewed button click through the existing coordinated controller.

The rectangle is in captured client pixels. This positions at its center and
requires guest-side position/window checks; it does not identify a spell itself.
"""
from pathlib import Path
from types import SimpleNamespace
import argparse
import json
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_xyz_workflow as w


def run(config, output, rectangle, *, before_action=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    cfg, profile, _ = w.read_config(Path(config))
    guard = w.HostGuard(cfg, profile, output)
    state = guard.status()
    w.save(output / 'initial-status.json', w.sanitize(state))
    w.require(state['guest'].get('targetedClickVersion') == 1, 'Guest upgrade required')
    w.require(state['guest']['target']['isForeground'], 'RIFT must be foreground')
    rectangle = list(rectangle)
    w.require(len(rectangle) == 4 and all(type(v) is int for v in rectangle), 'Invalid rectangle')
    x, y, width, height = rectangle
    target = state['guest']['target']
    w.require(0 <= x and 0 <= y and 4 <= width <= 128 and 4 <= height <= 128
              and x + width <= target['clientWidth'] and y + height <= target['clientHeight'],
              'Button is outside the reviewed client')
    w.save(output / 'intent.json', dict(clickTarget=dict(zip(('x', 'y', 'width', 'height'), rectangle)),
                                      target=target, meaning='operator-reviewed button; no automatic spell recognition'))
    q = w.AccessQueue(guard.plan['database'])
    queue_state = q.status()
    resource = next(v for v in queue_state['resources'] if v['name'] == guard.plan['resource'])
    w.require(not resource['blocked'] and resource['holder'] is None and
              not any(v['state'] in ('queued', 'active', 'cleanup') for v in queue_state['requests']),
              'Control queue is occupied')
    rid = 'targeted-click-' + uuid.uuid4().hex[:12]
    q.submit(rid, 'targeted-click', 'C', {resource['name']: resource['epoch']},
             ttl_ms=30000, max_ms=120000, estimated_ms=1000)
    grant = q.dispatch()
    w.require(grant and grant['request_id'] == rid, 'Control grant unavailable')
    client = w.ControlClient(w.HostConfig.load(Path(guard.plan['configPath'])),
                            access={k: grant[k] for k in ('request_id', 'token')})
    done = threading.Event()
    lease_failed = threading.Event()

    def heartbeat():
        while not done.wait(8):
            try:
                q.heartbeat(rid, grant['token'])
            except Exception:
                lease_failed.set()
                return

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    succeeded = False
    try:
        capture = w._capture(client, output / 'before')
        print(json.dumps(dict(intendedRectangle=rectangle)), flush=True)
        note = w.read_review(capture, timeout=40)
        if before_action is not None:
            before_action()
        guard.status()
        w.require(not lease_failed.is_set(), 'Control lease lost')
        q.heartbeat(rid, grant['token'])
        w._arm(client, output / 'before/capture.json', note, output / 'arm.private.json')
        result = w._action(client, SimpleNamespace(arm=output / 'arm.private.json', keys='',
            hold_ms=100, mouse_button='left', dx=0, dy=0, wheel=0, click_target=rectangle,
            output=output / 'action.json'))
        outcome = result['result']['result']
        w.require(outcome['deliverySucceeded'] and outcome['releaseSucceeded']
                  and not outcome['targetLost'] and not outcome['stateUncertain'], 'Click rejected or delivery uncertain')
        w._capture(client, output / 'after')
        succeeded = True
    finally:
        try:
            w.save(output / 'stop.json', w.sanitize(client.request('/api/stop', method='POST', payload={})))
        finally:
            done.set()
            thread.join()
            q.finish(rid, grant['token'], 'succeeded' if succeeded else 'failed', ['single reviewed targeted click'])
        w.save(output / 'final-status.json', w.sanitize(guard.status()))
    return dict(deliveryVerified=True, gameResponseVerified=False, output=str(output.resolve()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'artifacts/xyz-workflow.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target', nargs=4, type=int, required=True, metavar=('X', 'Y', 'WIDTH', 'HEIGHT'))
    args = parser.parse_args()
    print(json.dumps(run(args.config, args.output, args.target)), flush=True)
