"""Offline verification of saved native-vs-Telemetry Lua zone frames.

Read-only saved-file replay. It never attaches to RIFT or asserts that Lua
source clocks are synchronized to host UTC. Both independently implemented
publishers are observations inside one process, not world-instance authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift
from scripts.compare_physical_player_context_pair import load

HOST = "AMD-DESKTOP"
SHA_1179 = "DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01"
PREFIX, SUFFIX = b"RIFTTLM1|", b"|ENDRIFTTLM1"
SESSION = re.compile(r"[0-9a-f]{32}\Z")
ZONE = re.compile(r"z[0-9A-F]{16}\Z")


def require(ok, reason):
    if not ok:
        raise ValueError("telemetry-zone-replay-" + reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def _unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, "duplicate-json-key")
        out[key] = value
    return out


def exact_json(raw):
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                      parse_constant=lambda _: require(False, "nonfinite-json"))


def _stamp(value):
    return physical_rift._utc_tick_order_key(value)


def _native(path, meta, target):
    require(meta.get("source") is not None and
            Path(str(meta["source"])).name == path.name, "native-source-path")
    record, sha = load(path, meta.get("sha256"))
    require(record.get("status") == "complete", "native-source-status")
    row = record["observation"]
    identity = row["identity"]
    require(identity.get("processId") == target["processId"]
            and str(identity.get("processStartUtcTicks")) ==
                str(target["processStartUtcTicks"])
            and identity.get("executableSha256", "").upper() == SHA_1179
            and identity.get("executablePath") == target["executablePath"],
            "native-process-epoch-or-build")
    values = physical_rift._native_values("zone-context", record)
    require(values["status"] == "available-candidate"
            and values["zoneIdCandidate"] == meta.get("zoneIdCandidate")
            and values["startedAtUtc"] == meta.get("startedAtUtc")
            and values["sampledAtUtc"] == meta.get("completedAtUtc"),
            "native-zone-projection")
    require(_stamp(values["startedAtUtc"]) <= _stamp(values["sampledAtUtc"]),
            "native-reversed-interval")
    return values, identity, sha


def _frame(raw, row, player):
    require(len(PREFIX) + len(SUFFIX) < len(raw) <= 32_768
            and raw.startswith(PREFIX + b"{") and raw.endswith(SUFFIX),
            "wire-envelope")
    doc = exact_json(raw[len(PREFIX):-len(SUFFIX)])
    require(type(doc) is dict
            and doc.get("schemaVersion") == 4
            and doc.get("addon") == "Telemetry"
            and doc.get("addonVersion") == "0.5.0"
            and doc.get("source") == "rift-api"
            and doc.get("status") == "observed"
            and doc.get("playerId") == player,
            "frame-schema-or-player")
    sid, epoch, seq, clock = (doc.get(key) for key in
                              ("sessionId", "epoch", "sequence", "frameTime"))
    require(type(sid) is str and SESSION.fullmatch(sid)
            and type(epoch) is int and epoch > 0
            and type(seq) is int and seq > 0
            and type(clock) in (int, float) and math.isfinite(clock) and clock >= 0,
            "frame-source-clock-or-generation")
    telemetry = doc.get("playerTelemetry")
    zone = telemetry.get("zone") if isinstance(telemetry, dict) else None
    require(isinstance(telemetry, dict)
            and telemetry.get("status") == "observed"
            and telemetry.get("id") == player
            and isinstance(zone, dict) and zone.get("status") == "observed"
            and type(zone.get("id")) is str and ZONE.fullmatch(zone["id"]),
            "frame-zone-unqualified")
    seen_at = zone.get("sampledAt")
    require(type(seen_at) in (int, float) and math.isfinite(seen_at)
            and 0 <= seen_at <= clock and clock - seen_at <= 10,
            "frame-zone-source-clock-invalid")
    name = zone.get("name")
    require(name is None or (type(name) is str and
            0 < len(name) <= 128 and not any(ord(c) < 32 for c in name)),
            "frame-zone-name-invalid")
    require(row.get("seq") == seq and row.get("epoch") == epoch and
            row.get("session") == sid and row.get("clock") == clock and
            row.get("zoneId") == zone["id"], "frame-index-projection")
    return {"seq": seq, "epoch": epoch, "session": sid, "clock": clock,
            "zoneId": zone["id"], "zoneName": name, "sampledAt": seen_at,
            "sha256": digest(raw)}


def replay(summary_file, *, max_capture_seconds=15):
    require(type(max_capture_seconds) in (int, float) and
            math.isfinite(max_capture_seconds) and 0 < max_capture_seconds <= 60,
            "invalid-duration-limit")
    filename = Path(summary_file)
    report, report_sha = load(filename)
    target = report.get("target")
    require(report.get("schemaVersion") == 1 and
            report.get("evidenceKind") == "physical-native-telemetry-zone-bracket-candidate/1"
            and report.get("status") == "matching-candidates" and
            report.get("sameProcessEpoch") is True and
            isinstance(target, dict) and target.get("hostName") == HOST and
            type(target.get("processId")) is int and target["processId"] > 0 and
            str(target.get("processStartUtcTicks", "")).isdecimal() and
            str(target.get("executableSha256", "")).upper() == SHA_1179,
            "summary-owner-or-schema")
    native = []
    for label in ("nativeBefore", "nativeAfter"):
        require(isinstance(report.get(label), dict), "missing-native-bound")
        suffix = "before" if label == "nativeBefore" else "after"
        native.append(_native(filename.parent / f"native-{suffix}.json",
                              report[label], target))
    left, right = native
    require(left[1] == right[1], "native-module-or-player-epoch-changed")
    player = f"u{int(left[0]['selfKey']):016X}"
    require(left[0]["selfKey"] == right[0]["selfKey"] and
            left[0]["rawZoneKey"] == right[0]["rawZoneKey"] and
            left[0]["childStatus"] == right[0]["childStatus"] and
            left[0]["childKey"] == right[0]["childKey"] and
            left[0]["zoneIdCandidate"] == right[0]["zoneIdCandidate"],
            "native-zone-bracket-changed")
    generation = report.get("selectedPublisherGeneration")
    if generation is not None:
        require(type(generation) is dict
                and set(generation) == {"sessionId", "epoch"}
                and type(generation["sessionId"]) is str
                and SESSION.fullmatch(generation["sessionId"]) is not None
                and type(generation["epoch"]) is int
                and generation["epoch"] > 0,
                "selected-publisher-generation-invalid")
        survey = report.get("scopeSurvey")
        require(type(survey) is dict
                and survey.get("status") == "scoped-candidate"
                and type(survey.get("scopes")) is list,
                "selected-publisher-survey-unavailable")
        selected = [row for row in survey["scopes"]
                    if type(row) is dict
                    and row.get("startAddress") == survey.get("selectedStartAddress")]
        require(len(selected) == 1
                and selected[0].get("topSession") == generation["sessionId"]
                and selected[0].get("topEpoch") == generation["epoch"],
                "selected-publisher-survey-mismatch")
    passes = report.get("passes")
    require(type(passes) is list and len(passes) == 2, "pass-count")
    frames = []
    intervals, excluded_counts = [], []
    for i, entry in enumerate(passes, 1):
        require(isinstance(entry, dict) and
                type(entry.get("readBytes")) is int and
                0 < entry["readBytes"] <= 128 * 1024 * 1024 and
                type(entry.get("failedChunks")) is int and
                entry["failedChunks"] >= 0 and
                type(entry.get("hits")) is int and 0 < entry["hits"] <= 50 and
                type(entry.get("frames")) is list and
                2 <= len(entry["frames"]) <= entry["hits"],
                "pass-inventory")
        started, ended = _stamp(entry.get("startedAtUtc")), _stamp(entry.get("completedAtUtc"))
        require(started <= ended, "scan-reversed-interval")
        intervals.append((started, ended))
        rows, excluded = [], 0
        for n, row in enumerate(entry["frames"], 1):
            require(type(row) is dict, "frame-index-row")
            if "sha" not in row:
                if row.get("error") == "nonselected-publisher-generation":
                    require(generation is not None
                            and set(row) == {"addr", "seq", "epoch", "session",
                                             "clock", "zoneId", "wire",
                                             "excludedSha256", "error"}
                            and type(row["addr"]) is str
                            and re.fullmatch(r"0x[0-9a-f]+", row["addr"]) is not None
                            and type(row["wire"]) is str
                            and Path(row["wire"]).name == f"frame-{n:02d}.wire",
                            "excluded-frame-index-invalid")
                    excluded_path = (filename.parent / f"pass-{i:02d}" /
                                     f"frame-{n:02d}.wire")
                    require(excluded_path.is_file()
                            and not excluded_path.is_symlink(),
                            "excluded-wire-source-unavailable")
                    raw_excluded = excluded_path.read_bytes()
                    require(digest(raw_excluded) == row["excludedSha256"],
                            "excluded-wire-sha-mismatch")
                    details = _frame(raw_excluded, row, player)
                    require((details["session"], details["epoch"]) !=
                            (generation["sessionId"], generation["epoch"]),
                            "selected-source-frame-illegally-excluded")
                    excluded += 1
                    continue
                require(set(row) == {"addr", "error"} and
                        row.get("error") in ("incomplete", "schema-or-player-zone", "invalid-json-or-frame"),
                        "unverified-frame-rejection")
                continue
            require(type(row.get("addr")) is str and
                    re.fullmatch(r"0x[0-9a-f]+", row["addr"]) is not None and
                    type(row.get("wire")) is str and
                    Path(row["wire"]).name == f"frame-{n:02d}.wire",
                    "frame-index-source-path")
            path = filename.parent / f"pass-{i:02d}" / f"frame-{n:02d}.wire"
            require(path.is_file() and not path.is_symlink(), "wire-source-unavailable")
            raw = path.read_bytes()
            require(digest(raw) == str(row.get("sha", "")).upper(),
                    "wire-source-sha-mismatch")
            details = _frame(raw, row, player)
            if generation is not None:
                require((details["session"], details["epoch"]) ==
                        (generation["sessionId"], generation["epoch"]),
                        "source-publisher-generation-mismatch")
            rows.append(details)
        if generation is not None:
            require(type(entry.get("excludedSourceFrameCount")) is int
                    and entry["excludedSourceFrameCount"] == excluded,
                    "excluded-source-frame-count-mismatch")
        excluded_counts.append(excluded)
        require(len(rows) >= 2, "not-enough-decoded-frames")
        frames.append(rows)
    order = [left[0]["sampledAtUtc"], passes[0]["startedAtUtc"],
             passes[0]["completedAtUtc"], passes[1]["startedAtUtc"],
             passes[1]["completedAtUtc"], right[0]["startedAtUtc"]]
    stamps = [_stamp(x) for x in order]
    require(all(a < b for a, b in zip(stamps, stamps[1:])),
            "native-and-scan-time-order")
    elapsed = (stamps[-1][0] - stamps[0][0]).total_seconds() + (
        stamps[-1][1] - stamps[0][1]) / 10_000_000
    require(elapsed <= max_capture_seconds, "capture-window-exceeded")
    seen = {}
    for x in frames[0] + frames[1]:
        key = x["seq"]
        if key in seen:
            require(seen[key] == x, "conflicting-retained-sequence")
        seen[key] = x
    ordered = sorted(seen.values(), key=lambda x: x["seq"])
    require(len({(x["session"], x["epoch"]) for x in ordered}) == 1,
            "source-session-or-epoch-changed")
    require(all(x["clock"] < y["clock"] for x, y in zip(ordered, ordered[1:])),
            "source-clock-nonadvancing-or-mixed")
    new = [x for x in frames[1] if x["seq"] > max(v["seq"] for v in frames[0])]
    require(len(new) >= 1 and report.get("sourceClockProgression") == "advancing" and
            report.get("newSourceSequenceCount") == len(new),
            "no-new-advancing-source-frames")
    require(all(x["zoneId"] == left[0]["zoneIdCandidate"] for x in ordered),
            "native-versus-lua-zone-mismatch")
    require(all(x["zoneName"] == ordered[0]["zoneName"] for x in ordered),
            "inconsistent-lua-zone-name")
    return {
        "schemaVersion": 1,
        "evidenceKind": "physical-native-telemetry-zone-offline-replay/1",
        "status": "matching-candidates",
        "processId": target["processId"],
        "processStartUtcTicks": str(target["processStartUtcTicks"]),
        "executableSha256": SHA_1179,
        "playerUnitId": player,
        "zoneIdCandidate": left[0]["zoneIdCandidate"],
        "luaZoneNameCandidate": ordered[0]["zoneName"],
        "sourceSessionId": ordered[0]["session"],
        "sourceEpoch": ordered[0]["epoch"],
        "firstSourceSequence": ordered[0]["seq"],
        "lastSourceSequence": ordered[-1]["seq"],
        "savedFrames": [len(rows) for rows in frames],
        **({"selectedPublisherGeneration": generation,
            "excludedPublisherFrames": excluded_counts}
           if generation is not None else {}),
        "uniqueSourceSequences": len(ordered),
        "newAdvancingSourceFrames": len(new),
        "maxLuaZoneSourceAgeSeconds": max(x["clock"] - x["sampledAt"] for x in ordered),
        "hostObservationSpanSeconds": round(elapsed, 4),
        "nativeSourceSha256": [left[2], right[2]],
        "evidenceSummarySha256": report_sha,
        "worldInstanceStatus": "unavailable",
        "qualification": ("Source-SHA-replayed native and independently implemented Lua "
                          "publisher candidate values agree within one verified process "
                          "epoch and ordered host acquisition bracket. Not atomic; Lua "
                          "source frame clock is not synchronized to host UTC; no "
                          "publisher authentication, world-instance or route clearance.")
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--max-capture-seconds", type=float, default=15)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output:
            require(not args.output.exists() and not args.output.is_symlink(),
                    "output-exists")
        result = replay(args.summary, max_capture_seconds=args.max_capture_seconds)
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as f:
                json.dump(result, f, indent=2, allow_nan=False)
                f.write("\n")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:240]}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
