"""Replay a recorded strict 480-second observer run; never assess current freshness."""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re
from pathlib import Path
import stat
import sys


class Invalid(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Invalid(reason)


def load_bytes(path, limit):
    path = Path(path)
    # Refuse links and Windows junctions on every component, before reading.
    for part in (path, *path.parents):
        info = part.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, 'st_file_attributes', 0) & 0x400), 'link-or-reparse')
    require(path.is_file() and path.stat().st_size <= limit, 'invalid-file-size')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, 'invalid-file-size')
    return data


def parse(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate-json-key')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(Invalid('nonfinite-json')))


def when(value):
    require(isinstance(value, str), 'invalid-time')
    date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(date.tzinfo is not None, 'timezone-required')
    return date.astimezone(timezone.utc)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'invalid-number')
    return value


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, 'invalid-integer')
    return value


def ticks_string(value):
    # The reader summary explicitly serializes ticks as decimal strings.
    require(isinstance(value, str) and value.isascii() and value.isdigit(), 'invalid-reader-ticks')
    return int(value)


def text(value):
    require(isinstance(value, str) and bool(value.strip()), 'invalid-identity-string')
    return value


def digest(value):
    require(isinstance(value, str) and re.fullmatch(r'[0-9a-fA-F]{64}', value) is not None, 'invalid-sha256')
    return value.lower()


def verify(run, pin_path, reader_path):
    run = Path(run).absolute()
    pin = parse(load_bytes(pin_path, 1024 * 1024))
    reader = parse(load_bytes(reader_path, 1024 * 1024))
    summary = parse(load_bytes(run / 'summary.json', 1024 * 1024))
    ledger = load_bytes(run / 'samples.jsonl', 16 * 1024 * 1024)
    require(integer(summary['schemaVersion']) == 1 and integer(pin['schemaVersion']) == 1, 'schema')
    integer(summary['acceptedSamples'], 2)
    integer(summary['transientUnavailableReads'])
    for obj, keys in ((pin['reader'], ('processId', 'processStartUtcTicks')), (pin['gameIdentity'], ('processId', 'processStartUtcTicks')), (pin['receiver'], ('processId', 'processStartUtcTicks')), (reader, ('readerPid', 'gamePid')), (reader['receiver'], ('pid', 'processStartUtcTicks')), (summary, ('readerPid', 'gamePid'))):
        for key in keys:
            integer(obj[key], 1)
    require(reader['status'] == 'reader-running-postflight-verified' and reader['vmIdentityStable'] is True and reader['inputSent'] is False, 'reader-summary-status')
    require(summary['status'] == 'passed' and summary['reason'] is None and summary['schemaVersion'] == 1
            and summary['sourceQualification'] == 'observer-side-480s' and summary['observerSideNoInputOnly'] is True, 'not-passed')
    require(hashlib.sha256(ledger).hexdigest() == digest(summary['ledgerSha256']), 'ledger-hash')
    require(number(summary['durationRequiredSeconds']) >= 480 and number(summary['expiryMarginSeconds']) >= 45
            and 0 < number(summary['maxAllowedGapSeconds']) <= 4.5, 'invalid-budgets')
    expiry = when(reader['expiresAtUtc'])
    require(expiry == when(summary['expiresAtUtc']), 'expiry-mismatch')
    r, g, recv = pin['reader'], pin['gameIdentity'], pin['receiver']
    require(pin['lab'] in ('lab1', 'lab2'), 'invalid-lab')
    require(isinstance(r['nonce'], str) and re.fullmatch(r'[0-9a-f]{32}', r['nonce']) is not None, 'invalid-nonce')
    for value in (r['instanceId'], r['sourceAddress'], recv['instanceId'], g['executablePath']):
        text(value)
    for value in (r['executableSha256'], g['executableSha256'], reader['readerSha256'], reader['gameSha256'], pin['receiptSha256'], summary['ledgerSha256']):
        digest(value)
    for obj, key in ((recv, 'executableSha256'), (reader['receiver'], 'configSha256')):
        if key in obj:
            digest(obj[key])
    require(pin['lab'] == reader['lab'] == summary['lab'] and r['nonce'] == reader['nonce'] == summary['readerNonce']
            and r['processId'] == reader['readerPid'] == summary['readerPid']
            and int(r['processStartUtcTicks']) == ticks_string(reader['readerStartUtcTicks'])
            and r['executableSha256'].lower() == reader['readerSha256'].lower()
            and g['processId'] == reader['gamePid'] == summary['gamePid']
            and int(g['processStartUtcTicks']) == ticks_string(reader['gameStartUtcTicks'])
            and g['executableSha256'].lower() == reader['gameSha256'].lower()
            and recv['processId'] == reader['receiver']['pid']
            and int(recv['processStartUtcTicks']) == int(reader['receiver']['processStartUtcTicks']), 'pin-reader-mismatch')
    rows = [parse(line) for line in ledger.splitlines()]
    require(len(rows) == summary['acceptedSamples'] and len(rows) >= 2, 'sample-count')
    require(rows[0]['elapsedSeconds'] == 0 and rows[-1]['elapsedSeconds'] == summary['observedSeconds']
            and number(summary['observedSeconds']) >= summary['durationRequiredSeconds'], 'duration')
    raw_dir = (run / 'raw').absolute()
    previous = initial = None
    first_ns = first_capture = previous_ns = previous_received = None
    max_arrival = max_capture = max_drift = 0.0
    scopes = {}
    paths = set()
    for index, row in enumerate(rows):
        require(type(row['index']) is int and row['index'] == index, 'index')
        elapsed = number(row['elapsedSeconds'])
        s = row['sample']
        path = Path(s['rawReceiptPath']).absolute()
        require(path.parent == raw_dir, 'raw-path-outside-run')
        require(path not in paths, 'duplicate-raw-path')
        paths.add(path)
        data = load_bytes(path, 4 * 1024 * 1024)
        require(hashlib.sha256(data).hexdigest() == digest(s['rawReceiptSha256']), 'raw-hash')
        receipt = parse(data)
        obs = receipt['observation']
        require(integer(receipt['schemaVersion']) == 1 and integer(obs['schemaVersion']) == 1, 'receipt-schema')
        received = when(receipt['receivedAtUtc'])
        received_ns = integer(receipt['receivedMonotonicNs'])
        require(expiry > received + timedelta(seconds=summary['expiryMarginSeconds']), 'receipt-expiry')
        capture = when(obs['capturedAtUtc'])
        if first_ns is None:
            first_ns, first_capture = received_ns, capture
        else:
            monotonic_gap = (received_ns - previous_ns) / 1e9
            utc_gap = (received - previous_received).total_seconds()
            # Receipt age at each acceptance is at most two seconds; its variation
            # can therefore add up to two seconds to the acceptance gap.
            require(0 < monotonic_gap < summary['maxAllowedGapSeconds'] + 2 and utc_gap > 0, 'receipt-time-gap')
            require(abs(utc_gap - monotonic_gap) <= .250, 'receipt-clock-disagreement')
        require(abs((received_ns - first_ns) / 1e9 - elapsed) <= 2, 'receipt-elapsed-disagreement')
        # Compare elapsed spans, allowing a fixed guest/host clock offset. The
        # 4.5 s tolerance conservatively accommodates variation in the original
        # 2.25 s transport-age bound plus recorded host-clock disagreement.
        require(abs((received_ns - first_ns) / 1e9 - (capture - first_capture).total_seconds()) <= 4.5, 'capture-span-disagreement')
        previous_ns, previous_received = received_ns, received
        target = obs['target']
        for value in (s['player'], s['readerInstance'], s['receiverInstance'], s['sourceAddress'], target['executablePath']):
            text(value)
        for value in (s['readerExecutableSha256'], target['executableSha256'], s['target']['executableSha256']):
            digest(value)
        for obj, keys in ((obs, ('sequence',)), (s, ('outerSequence', 'addonSequence', 'addonEpoch', 'readerProcessId', 'readerProcessStartUtcTicks')), (target, ('processId', 'processStartUtcTicks')), (s['target'], ('processId', 'processStartUtcTicks'))):
            for key in keys:
                integer(obj[key], 1)
        require(receipt['receiverInstance'] == s['receiverInstance'] == recv['instanceId']
                and receipt['sourceAddress'] == s['sourceAddress'] == r['sourceAddress']
                and obs['instanceId'] == s['readerInstance'] == r['instanceId']
                and obs['nonce'] == s['readerNonce'] == target['readerSessionNonce'] == r['nonce']
                and s['lab'] == pin['lab'] and s['readerProcessId'] == r['processId']
                and s['readerProcessStartUtcTicks'] == r['processStartUtcTicks']
                and s['readerExecutableSha256'].lower() == r['executableSha256'].lower(), 'receipt-identity')
        for key in ('processId', 'processStartUtcTicks', 'executablePath', 'executableSha256'):
            require(str(target[key]).lower() == str(s['target'][key]).lower() == str(g[key]).lower(), 'target-identity')
        require(obs['readerStatus'] == 'running' and obs['sequence'] == s['outerSequence']
                and when(obs['capturedAtUtc']) == when(s['capturedAtUtc'])
                and when(receipt['receivedAtUtc']) == when(s['receivedAtUtc']), 'receipt-fields')
        choices = []
        for name, binding, fresh, selection in [('riftReader2', 'bound', 'fresh', 'selected'), ('fastObservation', 'bound-scoped', 'fresh-scoped', 'selected-scoped')]:
            block = obs.get(name) or {}
            if block.get('bindingStatus') == binding and block.get('freshnessStatus') == fresh and block.get('selectionStatus') == selection and block.get('scan', {}).get('completed') is True:
                require(integer(block['schemaVersion']) == 1 and integer(block['observation']['schemaVersion']) == 1, 'selected-schema')
                scan = block['scan']
                require(scan.get('status') == 'complete' and integer(scan.get('plannedBytes'), 1) == integer(scan.get('scannedBytes'), 1) and integer(scan.get('regionCount'), 1) > 0, 'invalid-scan')
                if name == 'fastObservation':
                    require(scan.get('scope') == 'candidate-regions' and block.get('provenance') == 'recent-full-scan-anchored-candidate-regions/1', 'invalid-fast-scope')
                require(0 <= number(block['lastAdvanceAgeMilliseconds']) < number(block['freshnessTimeoutMilliseconds']), 'source-age')
                require(integer(block['candidateSequence'], 1) == integer(block['observation']['sequence'], 1) and integer(block['candidateEpoch'], 1) == integer(block['observation']['epoch'], 1), 'candidate-mismatch')
                choices.append((name, block))
        require(choices, 'no-selected-source')
        if len(choices) == 2:
            a, b = (item[1]['observation'] for item in choices)
            require(a['epoch'] == b['epoch'] and a['player'] == b['player'], 'source-conflict')
            apos = (a['sequence'], number(a['clock']['value']))
            bpos = (b['sequence'], number(b['clock']['value']))
            require((apos[0] < bpos[0] and apos[1] < bpos[1]) or (apos[0] > bpos[0] and apos[1] > bpos[1]) or (apos == bpos and a == b), 'source-conflict')
            if bpos[0] > apos[0]:
                choices.reverse()
        name, block = choices[0]
        selected = block['observation']
        scope = 'whole-readable-private' if name == 'riftReader2' else block['scan']['scope']
        provenance = 'nonce-bound-complete-process-scan/1' if name == 'riftReader2' else block['provenance']
        require(scope in ('whole-readable-private', 'candidate-regions') and s['sourceScope'] == scope and s['sourceProvenance'] == provenance, 'scope')
        scopes[scope] = scopes.get(scope, 0) + 1
        require(selected['player']['status'] == selected['clock']['status'] == 'ok'
                and selected['player']['value'] == s['player'] and selected['epoch'] == s['addonEpoch']
                and selected['sequence'] == s['addonSequence'] and number(selected['clock']['value']) == number(s['addonClock']), 'selected-fields')
        for axis in 'XYZ':
            field = selected['fields']['coord' + axis]
            require(field['status'] == 'ok' and number(field['value']) == number(s['xyz'][axis.lower()]), 'coordinates')
        if initial is None:
            initial = s
            require(expiry > when(s['receivedAtUtc']) + timedelta(seconds=summary['durationRequiredSeconds'] + summary['expiryMarginSeconds']), 'initial-expiry')
        require(s['player'] == initial['player'] and s['addonEpoch'] == initial['addonEpoch'], 'player-epoch')
        drift = math.hypot(s['xyz']['x'] - initial['xyz']['x'], s['xyz']['z'] - initial['xyz']['z'])
        max_drift = max(max_drift, drift)
        require(drift <= .05, 'drift')
        if previous:
            old, old_elapsed = previous
            arrival = elapsed - old_elapsed
            capture = (when(s['capturedAtUtc']) - when(old['capturedAtUtc'])).total_seconds()
            require(0 < arrival < summary['maxAllowedGapSeconds'] and 0 < capture < summary['maxAllowedGapSeconds'], 'gap')
            require(s['outerSequence'] > old['outerSequence'] and s['addonSequence'] > old['addonSequence'] and s['addonClock'] > old['addonClock'], 'advancement')
            max_arrival, max_capture = max(max_arrival, arrival), max(max_capture, capture)
        previous = s, elapsed
    require(set(raw_dir.iterdir()) == paths, 'raw-file-set')
    require(expiry > when(rows[-1]['sample']['receivedAtUtc']) + timedelta(seconds=summary['expiryMarginSeconds']), 'final-expiry')
    for key, value in [('maximumGapSeconds', max_arrival), ('maximumAcceptanceGapSeconds', max_arrival), ('maximumCaptureGapSeconds', max_capture)]:
        require(math.isclose(number(summary[key]), value, abs_tol=1e-7), 'summary-gap-mismatch')
    return {'scope': 'offline-artifact-consistency-only', 'status': 'consistent-recorded-output', 'recordedObserverStatus': 'passed', 'expiryBasis': 'receipt timestamps, not observer wall-clock', 'sourceGateReplay': 'selected-output consistency only; anchor, live admission, VM provenance, clock skew, and artifact authenticity unverified', 'fullScopeBasis': 'riftReader2 block classification; recorded full scan has no scope field', 'samples': len(rows), 'scopes': scopes, 'maximumAcceptanceGapSeconds': max_arrival, 'maximumCaptureGapSeconds': max_capture, 'maximumPlanarDrift': max_drift}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--source-pin', type=Path, required=True)
    parser.add_argument('--reader-summary', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.run, args.source_pin, args.reader_summary), sort_keys=True))
        return 0
    except (Invalid, ValueError, KeyError, TypeError, OSError, OverflowError, AttributeError) as error:
        print(json.dumps({'scope': 'offline-artifact-consistency-only', 'status': 'inconsistent-recorded-output', 'reason': str(error)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

