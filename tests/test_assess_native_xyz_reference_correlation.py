"""Offline synthetic RR2R1/native correlation gate tests."""
from copy import deepcopy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import assess_native_xyz_reference_correlation as c
from tests.test_project_xyz_track import fixture as native_fixture


def build():
    native = native_fixture()
    for row in native["observations"]:
        row.update(unitKey="1", unitIdCandidate="u0000000000000001",
                   ownerIdentityStatus="player-component-chain-anchored")
    typed = {"schemaVersion": 1, "evidenceKind": "typed-wire-snapshot-inspection/1",
             "operation": "inspect-typed-wire", "status": "advanced-in-covered-scope",
             "identity": native["identity"].copy(), "source": {}, "selected": {}}
    for stage, index, sha, wire in (("before", 0, "A"*64, "C"*64),
                                    ("after", 1, "B"*64, "D"*64)):
        n = native["observations"][index]
        f = {"address": "0x1234", "wireSha256": wire, "sequence": index + 1,
             "frameTime": index + 1, "playerUnitId": "u0000000000000001",
             "protocol": "RR2R1", "addon": "RiftReader2", "source": "rift-api",
             "sessionId": "a"*32, "epoch": 1,
             "xyz": {axis: n[axis] for axis in "xyz"},
             "fields": {"coord" + axis.upper(): {"status": "ok", "value": n[axis]} for axis in "xyz"}}
        typed["selected"][stage] = f
        typed["source"][stage] = {
            "status": "complete", "snapshotSha256": sha,
            "startedAtUtc": n["startedAtUtc"], "completedAtUtc": n["completedAtUtc"],
            "candidateLimitExceeded": False, "malformedCompleteCount": 0,
            "candidates": [{**{k: f[k] for k in
                                ("address", "wireSha256", "sequence", "frameTime", "playerUnitId")},
                            "kind": "valid"}]}
    return native, typed


def assess(n, t, **kwargs):
    options = dict(native_sha="E"*64, typed_sha="F"*64, before_snapshot_sha="A"*64,
                   after_snapshot_sha="B"*64, max_lag_seconds=1, tolerance=.01)
    options.update(kwargs)
    return c.assess(n, t, **options)


class CorrelationTests(unittest.TestCase):
    def test_correspondence_and_explicit_limits(self):
        result = assess(*build())
        self.assertEqual(result["status"], "api-influenced-coordinate-correspondence")
        self.assertEqual([p["nativeIndex"] for p in result["pairs"]], [1, 2])
        self.assertIn("not rescanned", result["limitations"][0])
        self.assertIn("no independent passive freshness", result["qualification"])

    def test_disagreement(self):
        n, t = build()
        n["observations"][1]["x"] = 5
        self.assertEqual(assess(n, t)["status"], "api-influenced-coordinate-disagreement")

    def test_fail_closed_bindings_sequence_and_unavailable_xyz(self):
        mutations = (
            lambda n, t: t["identity"].update(processId=999),
            lambda n, t: t["identity"].update(processStartUtcTicks=999),
            lambda n, t: t["identity"].update(executableSha256="F"*64),
            lambda n, t: t["selected"]["after"].update(sessionId="b"*32),
            lambda n, t: t["selected"]["after"].update(epoch=2),
            lambda n, t: t["selected"]["after"].update(playerUnitId="u0000000000000002"),
            lambda n, t: t["selected"]["after"].update(sequence=1),
            lambda n, t: t["selected"]["after"]["fields"]["coordX"].update(status="unavailable"),
            lambda n, t: t["selected"]["before"].update(protocol="RRAPIVAL2"),
            lambda n, t: t["source"]["before"].update(snapshotSha256="F"*64),
            lambda n, t: t["source"]["before"].update(candidateLimitExceeded=True),
            lambda n, t: n["observations"][0].pop("unitKey"),
            lambda n, t: n["observations"][1].update(x=float("nan")),
        )
        for mutate in mutations:
            n, t = build()
            mutate(n, t)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                assess(n, t)

    def test_stale_or_duplicated_pair_and_thresholds_fail(self):
        n, t = build()
        with self.assertRaises(ValueError):
            assess(n, t, max_lag_seconds=.00001, before_snapshot_sha="B"*64)
        with self.assertRaises(ValueError):
            assess(n, t, tolerance=-1)
        t["source"]["after"]["completedAtUtc"] = "2026-11-08T00:00:00.100Z"
        t["source"]["after"]["startedAtUtc"] = "2026-11-08T00:00:00Z"
        with self.assertRaises(ValueError):
            assess(n, t)

    def test_cli_hash_closes_snapshot_files_and_reports(self):
        n, t = build()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            before, after = root/"before", root/"after"
            before.write_bytes(b"snapshot-before")
            after.write_bytes(b"snapshot-after")
            t["source"]["before"]["snapshotSha256"] = c.digest(before)
            t["source"]["after"]["snapshotSha256"] = c.digest(after)
            native, typed = root/"native.json", root/"typed.json"
            native.write_text(json.dumps(n), encoding="utf-8")
            typed.write_text(json.dumps(t), encoding="utf-8")
            args = ["--native", str(native), "--typed", str(typed),
                    "--before-snapshot", str(before), "--after-snapshot", str(after),
                    "--native-sha256", c.digest(native), "--typed-sha256", c.digest(typed),
                    "--max-lag-seconds", "1", "--tolerance", ".01"]
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(c.main(args), 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "api-influenced-coordinate-correspondence")
            before.write_bytes(b"changed")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(c.main(args), 2)


if __name__ == "__main__":
    unittest.main()
