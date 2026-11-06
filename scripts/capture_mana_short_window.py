"""Coordinate API-before, native Mana, and API-after read-only evidence.

The operation composes already reviewed acquisition tools. It sends no game
input and does not reload or restart RIFT. Two bounded typed-reference captures
surround one exact-owner native resource probe, then the offline assessor applies
the caller-declared gap. This is deliberately a baseline operation; a Mana
stimulus belongs to a separately reviewed experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.assess_mana_short_window import assess
from scripts.capture_current_typed_reference import capture
from scripts.inspect_typed_resource import ResourceInspectionError, inspect, require_session_id, require_reference_binding
from scripts.probe_native_unit_manager import run as probe_owner


EVIDENCE = ROOT / "artifacts/native-mana-short-window/runs"
PINNED_SOURCES = (
    "scripts/capture_mana_short_window.py",
    "scripts/capture_current_typed_reference.py",
    "scripts/probe_native_unit_manager.py",
    "scripts/probe_native_mana_descriptor.py",
    "scripts/inspect_typed_resource.py",
    "scripts/assess_mana_short_window.py",
    "scripts/native_mana_candidate.py",
)


class ManaCaptureError(ValueError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _pins() -> dict[str, str]:
    return {name: _sha(ROOT / name) for name in PINNED_SOURCES}


def _require_pins(expected: dict[str, str]) -> None:
    if _pins() != expected:
        raise ManaCaptureError("coordinator-source-changed-during-run")


def _reports(capture_summary: dict, session_id: str | None = None) -> list[dict]:
    output = Path(capture_summary["output"])
    snapshots = sorted((output / "recovered").glob("run-*/*.snapshot.json"))
    reports = []
    for snapshot in snapshots:
        try:
            report = inspect(snapshot, "mana", session_id)
            if session_id is not None:
                require_reference_binding(report.get("selected"), session_id)
            reports.append(report)
        except ResourceInspectionError as exc:
            if session_id is not None and str(exc) != "no-complete-frame-in-covered-scope":
                raise
            # The strict typed capture may retain stale static marker strings or
            # incomplete candidates. At least one complete usable frame remains
            # mandatory below; malformed snapshots are never converted to data.
            continue
    if not reports:
        raise ManaCaptureError("capture-has-no-complete-mana-frame")
    if session_id is not None:
        bindings = {(row["selected"]["epoch"], row["selected"].get("playerUnitId")) for row in reports}
        if len(bindings) != 1:
            raise ManaCaptureError("capture-reference-epoch-or-player-conflict")
    return reports


def _identity(value: dict) -> tuple:
    identity = value.get("target") or value.get("identity")
    if not isinstance(identity, dict):
        raise ManaCaptureError("operation-identity-missing")
    return (identity.get("processId"), identity.get("processStartUtcTicks"),
            identity.get("executableSha256"))


def run(reader: Path, reader_sha256: str, descriptor: Path,
        descriptor_sha256: str, maximum_gap_seconds: float,
        *, session_id: str | None = None, capture_fn=capture, probe_fn=probe_owner) -> dict:
    if not 0 < maximum_gap_seconds <= 300:
        raise ManaCaptureError("maximum-gap-seconds-out-of-range")
    if not descriptor.is_file() or _sha(descriptor) != descriptor_sha256.upper():
        raise ManaCaptureError("descriptor-review-sha256-mismatch")
    require_session_id(session_id)
    source_pins = _pins()
    token = uuid.uuid4().hex
    output = EVIDENCE / token
    output.mkdir(parents=True, exist_ok=False)
    (output / "source-pins.json").write_text(
        json.dumps(source_pins, indent=2) + "\n", encoding="utf-8", newline="\n")

    before_capture = capture_fn("lab1", reader, reader_sha256, session_id)
    _require_pins(source_pins)
    before_reports = _reports(before_capture, session_id)
    before = max(before_reports, key=lambda row: row["selected"]["sequence"])
    before_path = output / "api-before.json"
    before_path.write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8", newline="\n")

    native = probe_fn("lab1", resource_record=True)
    _require_pins(source_pins)
    native_path = Path(native["output"]) / "review.json"
    if not native_path.is_file():
        raise ManaCaptureError("native-owner-review-missing")

    after_capture = capture_fn("lab1", reader, reader_sha256, session_id)
    _require_pins(source_pins)
    after_reports = _reports(after_capture, session_id)
    after = min(after_reports, key=lambda row: row["selected"]["sequence"])
    after_path = output / "api-after.json"
    after_path.write_text(json.dumps(after, indent=2) + "\n", encoding="utf-8", newline="\n")

    if (_identity(before_capture) != _identity(native)
            or _identity(native) != _identity(after_capture)
            or before_capture.get("vmIdentity") != native.get("vmIdentity")
            or native.get("vmIdentity") != after_capture.get("vmIdentity")):
        raise ManaCaptureError("vm-or-game-identity-changed-across-phases")
    assessment = assess(before_path, native_path, descriptor, after_path, maximum_gap_seconds, session_id)
    assessment_path = output / "assessment.json"
    assessment_path.write_text(
        json.dumps(assessment, indent=2) + "\n", encoding="utf-8", newline="\n")
    _require_pins(source_pins)
    result = {
        "schemaVersion": 1,
        "status": assessment["status"],
        "output": str(output),
        "assessmentSha256": _sha(assessment_path),
        "evidence": {
            "apiBeforeCaptureOutput": str(Path(before_capture["output"]).resolve()),
            "apiBeforeCaptureSummarySha256": _sha(Path(before_capture["output"]) / "summary.json"),
            "apiBeforeArchiveSha256": before_capture.get("archiveSha256"),
            "apiBeforeReaderSha256": before_capture.get("readerSha256"),
            "apiBeforeResourceReport": str(before_path.resolve()),
            "apiBeforeResourceReportSha256": _sha(before_path),
            "nativeOwnerEvidence": str(Path(native["output"]).resolve()),
            "nativeOwnerReview": str(native_path.resolve()),
            "nativeOwnerReviewSha256": _sha(native_path),
            "nativeReaderSha256": native.get("readerSha256"),
            "nativeWorkflowSha256": native.get("workflowSha256"),
            "nativeProbeSha256": native.get("probeSha256"),
            "descriptorReview": str(descriptor.resolve()),
            "descriptorReviewSha256": descriptor_sha256.upper(),
            "apiAfterCaptureOutput": str(Path(after_capture["output"]).resolve()),
            "apiAfterCaptureSummarySha256": _sha(Path(after_capture["output"]) / "summary.json"),
            "apiAfterArchiveSha256": after_capture.get("archiveSha256"),
            "apiAfterReaderSha256": after_capture.get("readerSha256"),
            "apiAfterResourceReport": str(after_path.resolve()),
            "apiAfterResourceReportSha256": _sha(after_path),
            "assessment": str(assessment_path.resolve()),
        },
        "sourcePins": source_pins,
        "phaseOrder": ["api-before", "native-owner", "api-after"],
        "maximumGapSeconds": maximum_gap_seconds,
        "gapSemantics": "host snapshot acquisition timestamps around native observation; API frame clock is independently required to advance but is not assumed synchronized",
        "gameInputSent": False,
        "reloadOrRestartUsed": False,
        "qualification": assessment["qualification"],
    }
    (output / "summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reader", required=True, type=Path)
    parser.add_argument("--reader-sha256", required=True)
    parser.add_argument("--descriptor", required=True, type=Path)
    parser.add_argument("--descriptor-sha256", required=True)
    parser.add_argument("--maximum-gap-seconds", type=float, default=180.0)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args(argv)
    try:
        result = run(args.reader, args.reader_sha256, args.descriptor,
                     args.descriptor_sha256, args.maximum_gap_seconds, session_id=args.session_id)
        print(json.dumps(result))
        return 0
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:240]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
