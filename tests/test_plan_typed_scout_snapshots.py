"""Offline-only tests for exact-epoch scout → narrow snapshot planning."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.plan_typed_scout_snapshots import (
    PlanError, build_plan, main, publish_plan,
)

TARGET_SHA = "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD"
BUNDLE_SHA = "C34D1C9BC5EC134D50AE38FBE6A16D13B0DBAC9EC412D9C4F4714E3DDFD9876C"
ACTUAL_SHA = "87A67D74E2EC8E54530944B4C24893F605719D437F74A3F03FD81D367B9771F6"


def example() -> dict:
    target = {"processId": 6940, "processStartUtcTicks": 639284177321390013,
              "executableSha256": TARGET_SHA}
    return {
        "schemaVersion": 1, "evidenceKind": "native-typed-prefix-scout/1",
        "requestSha256": "A" * 64, "coverageContentSha256": "B" * 64,
        "implementation": {"bundleSha256": BUNDLE_SHA},
        "request": {
            "schemaVersion": 1,
            "evidenceKind": "native-typed-prefix-scout-request/1",
            "target": target,
        },
        "identity": {**target, "moduleBaseAddress": 140698495614976},
        "status": "partial", "reason": "byte-budget-exceeded",
        "marker": "RRAPIVAL2|",
        "scope": "committed-readable-nonguard-MEM_PRIVATE-at-or-after-startAddress",
        "startedAtUtc": "2026-10-24T16:42:13.4536214Z",
        "completedAtUtc": "2026-10-24T16:42:14.2549234Z",
        "prefixAddresses": ["0xD3DB230", "0xD6C0550", "0xD763500"],
        "coveredSpans": [{"baseAddress": "0xD2F0000", "byteLength": 536870912}],
        "holes": [],
    }


def pinned(data: dict) -> tuple[bytes, str]:
    original = json.dumps(data).encode("utf-8")
    return original, hashlib.sha256(original).hexdigest().upper()


class ScoutSnapshotPlanTests(unittest.TestCase):
    def test_produces_two_identical_exact_epoch_requests_for_three_hits(self):
        raw, sha = pinned(example())
        plan, req, req_bytes = build_plan(raw, sha)
        self.assertEqual(req["target"]["processStartUtcTicks"], 639284177321390013)
        self.assertEqual(req["evidenceKind"], "native-memory-snapshot-request/1")
        self.assertEqual(len(req["ranges"]), 3)
        self.assertEqual(req["ranges"][0], {
            "addressKind": "absolute-session-address",
            "address": "0xD3D9000", "byteLength": 28672,
        })
        self.assertEqual(plan["snapshot"]["totalRequestedBytes"], 86016)
        self.assertEqual(plan["snapshot"]["chunkCount"], 21)
        self.assertEqual(plan["windowPolicy"]["minimumTrailingBytesAtMarker"], 16384)
        self.assertEqual(plan["sourceScout"]["candidateAddresses"],
                         ["0xD3DB230", "0xD6C0550", "0xD763500"])
        self.assertEqual(plan["independentSamples"][0]["requestSha256"],
                         plan["independentSamples"][1]["requestSha256"])
        self.assertEqual(plan["independentSamples"][0]["requestSha256"],
                         hashlib.sha256(req_bytes).hexdigest().upper())
        self.assertLess(len(req_bytes), 65536)

    def test_original_report_pin_required(self):
        raw, _ = pinned(example())
        with self.assertRaisesRegex(PlanError, "does not match"):
            build_plan(raw, "0" * 64)
        with self.assertRaisesRegex(PlanError, "uppercase"):
            build_plan(raw, "a" * 64)

    def test_duplicate_json_object_key_fails_even_with_correct_hash(self):
        raw = b'{"schemaVersion":1,"schemaVersion":1}'
        with self.assertRaisesRegex(PlanError, "Duplicate JSON"):
            build_plan(raw, hashlib.sha256(raw).hexdigest().upper())

    def test_exact_process_identity_disagreement_fails(self):
        altered = example()
        altered["identity"]["processStartUtcTicks"] += 1
        raw, sha = pinned(altered)
        with self.assertRaisesRegex(PlanError, "identity disagree"):
            build_plan(raw, sha)

    def test_identity_invalidated_cannot_be_used_as_source(self):
        altered = example()
        altered["status"] = "identity-invalidated"
        raw, sha = pinned(altered)
        with self.assertRaisesRegex(PlanError, "not valid"):
            build_plan(raw, sha)

    def test_uncovered_window_is_rejected(self):
        altered = example()
        altered["coveredSpans"] = [{"baseAddress": "0xD3DB000", "byteLength": 4096}]
        raw, sha = pinned(altered)
        with self.assertRaisesRegex(PlanError, "no fully covered"):
            build_plan(raw, sha)

    def test_hole_intersecting_window_is_rejected(self):
        altered = example()
        altered["holes"] = [{"baseAddress": "0xD3DF000", "byteLength": 4096}]
        raw, sha = pinned(altered)
        with self.assertRaisesRegex(PlanError, "unreadable"):
            build_plan(raw, sha)

    def test_duplicate_and_noncanonical_candidates_fail(self):
        altered = example()
        altered["prefixAddresses"][1] = altered["prefixAddresses"][0]
        raw, sha = pinned(altered)
        with self.assertRaisesRegex(PlanError, "Duplicate reported"):
            build_plan(raw, sha)
        altered["prefixAddresses"][1] = "0x0D6C0550"
        raw, sha = pinned(altered)
        with self.assertRaisesRegex(PlanError, "canonical uppercase"):
            build_plan(raw, sha)

    def test_overlapping_candidate_windows_merge_and_remain_nonoverlapping(self):
        altered = example()
        altered["prefixAddresses"] = ["0xD3DB230", "0xD3DB333", "0xD3E1000"]
        raw, sha = pinned(altered)
        plan, req, _ = build_plan(raw, sha)
        self.assertEqual(plan["snapshot"]["rangeCount"], 1)
        self.assertEqual(req["ranges"][0]["address"], "0xD3D9000")
        self.assertEqual(req["ranges"][0]["byteLength"], 0xD000)

    def test_existing_output_directory_never_overwritten(self):
        raw, sha = pinned(example())
        plan, _, req_bytes = build_plan(raw, sha)
        with tempfile.TemporaryDirectory() as root:
            parent = Path(root)
            out = parent / "planned"
            publish_plan(out, plan, req_bytes)
            names = sorted(p.name for p in out.iterdir())
            self.assertEqual(names, ["plan.json", "sample-01.request.json", "sample-02.request.json"])
            self.assertEqual((out / names[1]).read_bytes(), req_bytes)
            self.assertEqual((out / names[2]).read_bytes(), req_bytes)
            first_sha = hashlib.sha256((out / "plan.json").read_bytes()).hexdigest()
            with self.assertRaises(FileExistsError):
                publish_plan(out, plan, req_bytes)
            self.assertEqual(first_sha,
                             hashlib.sha256((out / "plan.json").read_bytes()).hexdigest())

    def test_rejection_does_not_create_directory(self):
        altered = example()
        altered["marker"] = "NOT-RRAPIVAL2"
        raw, sha = pinned(altered)
        with tempfile.TemporaryDirectory() as temporary:
            input_path = Path(temporary) / "source.json"
            output_path = Path(temporary) / "plan"
            input_path.write_bytes(raw)
            with redirect_stderr(io.StringIO()) as errors:
                result = main(["--scout-report", str(input_path),
                               "--expected-scout-sha256", sha,
                               "--output-directory", str(output_path)])
            self.assertEqual(result, 2)
            self.assertIn("rejected", errors.getvalue())
            self.assertFalse(output_path.exists())

    def test_dry_run_saves_nothing_and_prints_plan(self):
        raw, sha = pinned(example())
        with tempfile.TemporaryDirectory() as temporary:
            input_path = Path(temporary) / "source.json"
            output_path = Path(temporary) / "not-created"
            input_path.write_bytes(raw)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(["--scout-report", str(input_path),
                               "--expected-scout-sha256", sha,
                               "--output-directory", str(output_path), "--dry-run"])
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(stdout.getvalue())["snapshot"]["rangeCount"], 3)
            self.assertFalse(output_path.exists())

    @unittest.skipUnless(
        (Path(__file__).resolve().parents[1] / "artifacts" / "update-recovery-20261023-01" /
         "rr2-scout-oct24-01-host.json").is_file(),
        "actual ignored live report is unavailable on this checkout")
    def test_actual_host_report_exact_sha_and_three_windows(self):
        source = (Path(__file__).resolve().parents[1] / "artifacts" /
                  "update-recovery-20261023-01" / "rr2-scout-oct24-01-host.json")
        plan, request, _ = build_plan(source.read_bytes(), ACTUAL_SHA)
        self.assertEqual(plan["sourceScout"]["originalReportSha256"], ACTUAL_SHA)
        self.assertEqual(plan["snapshot"]["rangeCount"], 3)
        self.assertEqual(request["target"]["executableSha256"], TARGET_SHA)


if __name__ == "__main__":
    unittest.main()
