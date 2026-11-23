"""Replay SHA-pinned physical RR2A1 Lua snapshots beside a native XYZ bracket.

Unbound RR2A1 is a real Lua API reference, but no nonce, freshness or movement
semantics are established. No process access or gameplay input occurs here.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import compare_physical_player_brackets as native
from scripts import compare_physical_player_context_pair as context
from scripts.physical_rift import valid_host_name
from scripts import replay_physical_player_state as native_state

PREFIX = b"RR2A1|"
SUFFIX = b"|ENDRR2A1"


def require(ok, reason):
    if not ok:
        raise ValueError("physical-rr2a1-" + reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def exact_json(raw):
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=context._unique_pairs,
                      parse_constant=lambda _: require(False, "nonfinite-json"))


def health_candidate(fields):
    """Return an internally valid RR2A1 HP pair or unavailable; never infer damage."""
    if not isinstance(fields, dict):
        return None
    current, maximum = fields.get("health"), fields.get("healthMax")
    if not isinstance(current, dict) or not isinstance(maximum, dict):
        return None
    if current.get("status") != "ok" or maximum.get("status") != "ok":
        return None
    a, b = current.get("value"), maximum.get("value")
    if (type(a) not in (int, float) or type(b) not in (int, float)
            or not math.isfinite(a) or not math.isfinite(b)
            or a < 0 or b <= 0 or a > b):
        return None
    return {"current": a, "maximum": b}


def lua_health_trend(frames):
    """Describe adjacent observed Lua HP candidates, without inferring combat."""
    pairs = list(zip(frames, frames[1:]))
    compared = missing = changed_maximum = rises = drops = steady = 0
    transitions = []
    skipped = 0
    for old, new in pairs:
        gap = max(0, new["sequence"] - old["sequence"] - 1)
        skipped += gap
        first, second = old["health"], new["health"]
        if first is None or second is None:
            missing += 1
            continue
        if first["maximum"] != second["maximum"]:
            changed_maximum += 1
            continue
        compared += 1
        delta = second["current"] - first["current"]
        if delta == 0:
            steady += 1
            continue
        if delta < 0:
            drops += 1
        else:
            rises += 1
        transitions.append({
            "fromSequence": old["sequence"],
            "toSequence": new["sequence"],
            "beforeCurrentCandidate": first["current"],
            "afterCurrentCandidate": second["current"],
            "maximumCandidate": first["maximum"],
            "deltaCurrentCandidate": delta,
            "intermediateFramesUnobserved": gap,
        })
    return {
        "status": "candidate-only",
        "adjacentObservedPairs": len(pairs),
        "comparablePairs": compared,
        "unavailablePairs": missing,
        "maximumChangedPairs": changed_maximum,
        "changedPairs": rises + drops,
        "decreasePairs": drops,
        "increasePairs": rises,
        "unchangedPairs": steady,
        "unobservedIntermediateFrames": skipped,
        "transitions": transitions,
        "qualification": ("Same-epoch advancing Lua observations show raw HP candidate "
                          "differences, not damage, healing cause, atomic frame timing, "
                          "nonce-bound RR2R1 or independently validated native semantics."),
    }


def compare_native_health(lua_report, native_report):
    """Screen source-pinned, same-owner *non-atomic* HP candidate agreement."""
    identity, owner = lua_report["identity"], native_report.get("target")
    host = identity.get("host")
    require(isinstance(owner, dict)
            and valid_host_name(host) and valid_host_name(owner.get("hostName"))
            and owner["hostName"].casefold() == host.casefold()
            and owner.get("processId") == identity["processId"]
            and str(owner.get("processStartUtcTicks")) ==
                str(identity["processStartUtcTicks"])
            and str(owner.get("executableSha256", "")).upper() ==
                identity["executableSha256"].upper()
            and native_report.get("selfKeyCandidate") ==
                str(int(lua_report["luaPlayerIdCandidate"][1:], 16)),
            "native-health-owner-mismatch")
    health = native_report["candidateValues"]["vitals"]["health"]
    current, maximum = health.get("current"), health.get("maximum")
    samples = native_report.get("healthSampleCandidates")
    stable = (health.get("status") == "calculated-candidate"
              and type(current) is int and type(maximum) is int
              and 0 <= current <= maximum and maximum > 0
              and isinstance(samples, list) and len(samples) >= 2
              and all(type(value) is int and value == current for value in samples))
    available = [row["health"] for row in lua_report["luaHealthCandidates"]
                 if row["health"] is not None]
    matches = (sum(row["current"] == current and row["maximum"] == maximum
                   for row in available) if stable else 0)
    different = len(available) - matches if stable else 0
    return {
        "status": "candidate-only",
        "agreementScreen": ("unavailable" if not stable or not available
                            else "all-equal" if different == 0 else "different"),
        "luaAvailableFrames": len(available),
        "nativeStableCandidate": stable,
        "matchingFrames": matches,
        "differingFrames": different,
        "nativeHealthCandidate": ({"current": current, "maximum": maximum}
                                  if stable else None),
        "nativeSummarySha256": native_report["summarySha256"],
        "luaScanIndexSha256": lua_report["sourceSha256"]["scanIndex"],
        "qualification": ("Same-process candidate-only health value screen, not atomic "
                          "capture, independently timestamped Lua production, "
                          "nonce-authenticated RR2R1 or changed-state proof."),
    }


def replay(index_path, native_summary_path):
    index_path = Path(index_path)
    index, index_sha = context.load(index_path)
    request_path = index_path.parent.parent / "request.json"
    request, request_sha = context.load(request_path)
    require(index.get("schemaVersion") == 1
            and index.get("evidenceKind") == "native-typed-inline-capture/1"
            and index.get("marker") == "RR2A1|"
            and index.get("status") in ("complete", "partial")
            and request.get("marker") == "RR2A1|"
            and index.get("requestSha256") == request_sha
            and index.get("request") == request
            and isinstance(index.get("candidates"), list), "invalid-scan-receipt")

    bracket, native_sha, _, _ = native.verified_bracket(native_summary_path)
    identity = bracket["identity"]
    target = request["target"]
    require(valid_host_name(identity.get("host"))
            and identity.get("processId") == target.get("processId")
            and int(identity.get("processStartUtcTicks", "0")) == target.get("processStartUtcTicks")
            and identity.get("executableSha256") == target.get("executableSha256")
            and index.get("identity", {}).get("processId") == target["processId"]
            and index["identity"].get("processStartUtcTicks") == target["processStartUtcTicks"]
            and index["identity"].get("executableSha256") == target["executableSha256"],
            "native-lua-process-identity-mismatch")
    expected_player = "u" + format(int(bracket["selfKeyCandidate"]), "016X")
    frames = []
    for candidate in index["candidates"]:
        if candidate.get("status") != "complete":
            continue
        filename = candidate.get("snapshotFile")
        require(isinstance(filename, str) and
                filename.startswith("capture-") and filename.endswith(".snapshot.json")
                and "/" not in filename and "\\" not in filename, "invalid-snapshot-name")
        snapshot, digest = context.load(index_path.parent / filename,
                                        candidate.get("snapshotSha256"))
        require(snapshot.get("evidenceKind") == "native-memory-snapshot/1"
                and snapshot.get("status") == "complete"
                and snapshot.get("identity") == index["identity"]
                and isinstance(snapshot.get("chunks"), list), "invalid-snapshot")
        chunks = []
        for piece in snapshot["chunks"]:
            require(piece.get("status") == "success"
                    and piece.get("requestedByteLength") == 4096
                    and piece.get("bytesRead") == 4096, "missing-snapshot-bytes")
            raw = base64.b64decode(piece["bytesBase64"], validate=True)
            require(len(raw) == 4096 and sha(raw) == piece.get("bytesSha256"),
                    "snapshot-chunk-hash-mismatch")
            address = int(piece["address"], 16)
            require(not chunks or address == chunks[-1][0] + 4096, "noncontiguous-chunks")
            chunks.append((address, raw))
        require(bool(chunks), "empty-snapshot")
        data = b"".join(raw for _, raw in chunks)
        pos = int(candidate["markerAddress"], 16) - chunks[0][0]
        require(0 <= pos < len(data) and data[pos:pos + len(PREFIX)] == PREFIX,
                "marker-address-mismatch")
        end = data.find(SUFFIX, pos + len(PREFIX))
        require(end >= 0 and end + len(SUFFIX) - pos <= 4096, "incomplete-frame")
        frame = data[pos:end + len(SUFFIX)]
        observed = exact_json(frame[len(PREFIX):-len(SUFFIX)])
        require(observed.get("schemaVersion") == 1
                and observed.get("addonVersion") == "0.1.0"
                and type(observed.get("sequence")) is int
                and observed["sequence"] > 0
                and type(observed.get("epoch")) is int
                and observed["epoch"] > 0
                and observed.get("player") == {"status": "ok", "value": expected_player},
                "invalid-lua-frame")
        clock = observed.get("clock", {})
        require(clock.get("status") == "ok"
                and type(clock.get("value")) in (int, float)
                and math.isfinite(clock["value"]), "invalid-lua-clock")
        xyz = {}
        for axis, field in (("x", "coordX"), ("y", "coordY"), ("z", "coordZ")):
            reading = observed.get("fields", {}).get(field, {})
            require(reading.get("status") == "ok"
                    and type(reading.get("value")) in (int, float)
                    and math.isfinite(reading["value"]), "unavailable-lua-xyz")
            xyz[axis] = reading["value"]
        frames.append({"sequence": observed["sequence"], "epoch": observed["epoch"],
                       "clock": clock["value"], "xyz": xyz,
                       "health": health_candidate(observed.get("fields")),
                       "snapshotSha256": digest,
                       "frameSha256": sha(frame)})
    require(len(frames) >= 2, "insufficient-complete-frames")
    frames.sort(key=lambda f: f["sequence"])
    require(len({f["sequence"] for f in frames}) == len(frames)
            and len({f["epoch"] for f in frames}) == 1
            and all(b["clock"] > a["clock"] for a, b in zip(frames, frames[1:])),
            "nonadvancing-or-mixed-lua-frames")
    native_xyz = bracket["lastPositionCandidate"]
    maxima = {axis: max(abs(f["xyz"][axis] - native_xyz[axis]) for f in frames)
              for axis in ("x", "y", "z")}
    return {
        "schemaVersion": 1,
        "evidenceKind": "amd-physical-rr2a1-native-xyz-comparison/1",
        "status": "candidate-only",
        "identity": identity,
        "luaProtocol": "RR2A1-unbound",
        "luaPlayerIdCandidate": expected_player,
        "luaFrameCount": len(frames),
        "luaEpochCandidate": frames[0]["epoch"],
        "firstSequence": frames[0]["sequence"],
        "lastSequence": frames[-1]["sequence"],
        "firstClockCandidate": frames[0]["clock"],
        "lastClockCandidate": frames[-1]["clock"],
        "nativePositionCandidate": native_xyz,
        "luaPositionCandidates": [f["xyz"] for f in frames],
        "luaHealthCandidates": [{"sequence": f["sequence"], "health": f["health"]}
                                for f in frames],
        "maxAbsCoordinateDifferenceCandidate": maxima,
        "luaHealthTrendCandidate": lua_health_trend(frames),
        "sourceSha256": {"scanIndex": index_sha, "scanRequest": request_sha,
                         "nativeBracketSummary": native_sha},
        "frameEvidence": [{"sequence": f["sequence"], "clockCandidate": f["clock"],
                           "snapshotSha256": f["snapshotSha256"],
                           "frameSha256": f["frameSha256"]} for f in frames],
        "qualification": ("Independent Lua API and native source values in the same "
                          "pinned process epoch, not nonce-bound, atomic, passive-fresh, "
                          "action-associated movement or restart proof"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-index", type=Path, required=True)
    parser.add_argument("--native-bracket", type=Path, required=True)
    parser.add_argument("--native-state-summary", type=Path,
                        help="Optional SHA-replayed same-process native HP baseline; candidate only")
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args(argv)
    try:
        require(not options.output.exists() and not options.output.is_symlink(),
                "output-exists")
        result = replay(options.scan_index, options.native_bracket)
        if options.native_state_summary is not None:
            result["nativeHealthComparison"] = compare_native_health(
                result, native_state.verified_state(options.native_state_summary))
        with options.output.open("x", encoding="utf-8", newline="\n") as out:
            json.dump(result, out, indent=2, allow_nan=False)
            out.write("\n")
        print(json.dumps({"status": result["status"], "frames": result["luaFrameCount"],
                          "sequence": [result["firstSequence"], result["lastSequence"]],
                          "maxAbsDelta": result["maxAbsCoordinateDifferenceCandidate"],
                          "output": str(options.output)}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, json.JSONDecodeError,
            base64.binascii.Error) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
