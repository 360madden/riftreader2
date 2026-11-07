"""Summarize observed sequential tool calls without inferring model reasoning time."""
import argparse
from collections import Counter
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import sys

MAX_MS = 2 * 60 * 60 * 1000
MAX_CALLS = 1000


def milliseconds(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= MAX_MS:
        raise ValueError("duration must be a finite number between zero and two hours")
    return value


def utc(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a UTC string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() != timedelta(0):
        raise ValueError("timestamp must have a UTC offset")
    return result


def summarize(trace):
    if (not isinstance(trace, dict) or type(trace.get("schemaVersion")) is not int
            or trace["schemaVersion"] != 1 or not isinstance(trace.get("clockScope"), str)
            or not trace["clockScope"].strip()):
        raise ValueError("expected schemaVersion 1 and one nonempty clockScope")
    calls = trace.get("calls")
    if not isinstance(calls, list) or not 1 <= len(calls) <= MAX_CALLS:
        raise ValueError("expected 1 to 1000 sequential calls")
    required = trace.get("requiredPhases")
    if (not isinstance(required, list) or not required
            or any(not isinstance(p, str) or not p for p in required)
            or len(set(required)) != len(required)):
        raise ValueError("requiredPhases must contain distinct nonempty phase names")
    jobs, gaps, counts, phases, errors = {}, [], Counter(), set(), []
    phase_rows = {}
    previous = first = None
    total = 0
    for index, call in enumerate(calls):
        if not isinstance(call, dict) or call.get("clockScope", trace["clockScope"]) != trace["clockScope"]:
            raise ValueError("calls must belong to the trace clockScope")
        for key in ("phase", "tool", "jobId"):
            if not isinstance(call.get(key), str) or not call[key]:
                raise ValueError(f"call requires {key}")
        start, end = utc(call["dispatchUtc"]), utc(call["resultReturnUtc"])
        if end < start or previous is not None and start < previous:
            raise ValueError("backward or overlapping sequential call timestamps")
        first = start if first is None else first
        if (end - first) / timedelta(milliseconds=1) > MAX_MS:
            raise ValueError("trace exceeds two hours")
        if previous is not None:
            after_phase = calls[index - 1]["phase"]
            gaps.append({"afterCall": index - 1, "beforeCall": index,
                         "afterPhase": after_phase, "beforePhase": call["phase"],
                         "class": "within-phase" if after_phase == call["phase"] else "phase-transition",
                         "observedGapMs": (start - previous) / timedelta(milliseconds=1)})
        previous = end
        total += milliseconds(call["roundTripMs"])
        status, code, pending = call.get("status"), call.get("exitCode"), call.get("completionPending")
        if (status not in {"running", "passed", "failed", "cancelled", "timed_out", "interrupted", "error"}
                or code is not None and type(code) is not int or type(pending) is not bool):
            raise ValueError("invalid job status, exitCode or completionPending")
        if status in {"failed", "cancelled", "timed_out", "interrupted", "error"} or call.get("error"):
            errors.append({"call": index, "jobId": call["jobId"], "status": status})
        jobs[call["jobId"]] = call
        phases.add(call["phase"])
        counts[call["tool"]] += 1
        row = phase_rows.setdefault(call["phase"], {"indices": [], "counts": Counter(),
                                    "jobs": {}, "errors": [], "start": start})
        row["indices"].append(index)
        row["counts"][call["tool"]] += 1
        row["jobs"][call["jobId"]] = call
        row["end"] = end
        if errors and errors[-1]["call"] == index:
            row["errors"].append(errors[-1])
    incomplete = [job for job, call in jobs.items() if not
                  (call["status"] == "passed" and call["exitCode"] == 0
                   and call["completionPending"] is False)]
    missing = sorted(set(required) - phases)
    child = trace.get("childStages", [])
    if not isinstance(child, list) or len(child) > MAX_CALLS:
        raise ValueError("childStages must be a bounded list")
    stages = []
    for stage in child:
        if not isinstance(stage, dict) or not isinstance(stage.get("phase"), str) or not stage["phase"]:
            raise ValueError("child stage requires a phase")
        stages.append({"phase": stage["phase"], "wallMs": milliseconds(stage["wallMs"])})
    success = not (errors or incomplete or missing)
    span = (previous - first) / timedelta(milliseconds=1)
    per_phase = []
    for phase, row in phase_rows.items():
        indices = row["indices"]
        contiguous = indices[-1] - indices[0] + 1 == len(indices)
        unfinished = [job for job, call in row["jobs"].items() if not
                      (call["status"] == "passed" and call["exitCode"] == 0
                       and call["completionPending"] is False)]
        per_phase.append({"phase": phase, "callCount": len(indices), "callCounts": dict(row["counts"]),
                          "firstCall": indices[0], "lastCall": indices[-1], "contiguous": contiguous,
                          "observedSpanMs": (row["end"] - row["start"]) / timedelta(milliseconds=1)
                          if contiguous else None,
                          "completionObserved": not (unfinished or row["errors"]),
                          "incompleteJobs": unfinished, "failedObservations": row["errors"]})
    return {"schemaVersion": 1, "clockScope": trace["clockScope"], "success": success,
            "callCount": len(calls), "callCounts": dict(counts), "jobCount": len(jobs),
            "observedSpanMs": span, "workflowElapsedMs": span if success else None,
            "toolRoundTripTotalMs": total, "observedOrchestrationGaps": gaps,
            "observedOrchestrationGapTotalMs": sum(g["observedGapMs"] for g in gaps),
            "phaseTransitionGapTotalMs": sum(g["observedGapMs"] for g in gaps
                                             if g["class"] == "phase-transition"),
            "withinPhaseGapTotalMs": sum(g["observedGapMs"] for g in gaps if g["class"] == "within-phase"),
            "phases": per_phase,
            "incompleteJobs": incomplete, "failedObservations": errors, "missingPhases": missing,
            "childStages": stages,
            "timingScope": "Round trips and observed return-to-dispatch gaps are separate observations; "
                           "phase labels classify gaps, not their causes or intentional poll backoff; "
                           "gaps are not model reasoning time. Child durations use their own clock; "
                           "no cross-clock subtraction or alignment is performed."}


def read_trace(path):
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("trace exceeds 2 MiB")
    return summarize(json.loads(path.read_text(encoding="utf-8-sig")))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args(argv)
    try:
        result = read_trace(args.trace)
        summaries = [("trace", result)]
        if args.compare:
            other = read_trace(args.compare)
            comparable = result["success"] and other["success"]
            result = {"schemaVersion": 1, "success": comparable, "trace": result, "compare": other,
                      "comparison": {"callCountDelta": other["callCount"] - result["callCount"],
                                     "workflowElapsedDeltaMs": (other["workflowElapsedMs"]
                                         - result["workflowElapsedMs"]) if comparable else None}}
            summaries.append(("compare", other))
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2, allow_nan=False)
            output.write("\n")
        for label, row in summaries:
            print(f"{label}: {'PASS' if row['success'] else 'INCOMPLETE/FAILED'}; "
                  f"{row['callCount']} calls / {row['jobCount']} jobs; observed span "
                  f"{row['observedSpanMs']:.1f} ms; tool round trips "
                  f"{row['toolRoundTripTotalMs']:.1f} ms; observed orchestration gaps "
                  f"{row['observedOrchestrationGapTotalMs']:.1f} ms "
                  f"(phase transitions {row['phaseTransitionGapTotalMs']:.1f} ms, "
                  f"within phase {row['withinPhaseGapTotalMs']:.1f} ms)")
        print("Gaps do not identify reasoning time; child durations are reported separately.")
        return 0 if result["success"] else 1
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        print(f"Timeline rejected: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
