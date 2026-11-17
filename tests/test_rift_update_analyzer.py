r"""Focused black-box tests for the standalone .NET 10 RIFT update analyzer.

Run after building the helper:
    C:\Python314\python.exe -m unittest discover -s tests -p test_rift_update_analyzer.py -v
"""
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
DLL = REPO / "tools" / "RiftUpdateAnalyzer" / "bin" / "Release" / "net10.0" / "RiftUpdateAnalyzer.dll"


class UpdateAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.hostname = socket.gethostname()

    def run_cli(self, *args, expected=0):
        self.assertTrue(DLL.is_file(), f"Build missing: {DLL}")
        completed = subprocess.run(
            ["dotnet", str(DLL), *map(str, args)],
            capture_output=True,
            text=True,
            timeout=40,
            check=False,
        )
        self.assertEqual(
            completed.returncode, expected,
            f"exit {completed.returncode} != {expected}\nstdout={completed.stdout}\nstderr={completed.stderr}",
        )
        return completed

    def write(self, path, content):
        path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def capture(self, name, *sources, max_files=None, max_bytes=None, expected=0):
        manifest = self.root / f"{name}.json"
        args = ["capture", "--expected-host", self.hostname]
        for group, path in sources:
            args.extend(["--source", f"{group}={path}"])
        args.extend(["--out", manifest])
        if max_files is not None:
            args.extend(["--max-files", str(max_files)])
        if max_bytes is not None:
            args.extend(["--max-bytes", str(max_bytes)])
        self.run_cli(*args, expected=expected)
        return manifest

    def compare(self, before, after, name="comparison", expected=0):
        output = self.root / f"{name}.json"
        self.run_cli("compare", "--before", before, "--after", after, "--out", output, expected=expected)
        return json.loads(output.read_text(encoding="utf-8"))

    def test_identical_content_has_zero_differences(self):
        root = self.write("source/config.json", '{"same":true}')
        before = self.capture("before", ("saved", root.parent))
        after = self.capture("after", ("saved", root.parent))
        result = self.compare(before, after)
        self.assertEqual(result["Deltas"], [])
        self.assertFalse(result["RuntimeRequalificationRequired"])

    def test_changed_added_removed_and_unchanged(self):
        source = self.root / "source"
        self.write("source/stable.txt", "stable")
        changed = self.write("source/change.txt", "old")
        removed = self.write("source/remove.txt", "gone")
        before = self.capture("before", ("saved", source))
        changed.write_text("new", encoding="utf-8")
        removed.unlink()
        self.write("source/add.txt", "added")
        after = self.capture("after", ("saved", source))
        result = self.compare(before, after, expected=1)
        self.assertEqual(
            {d["Key"]: d["Kind"] for d in result["Deltas"]},
            {"saved/change.txt": "modified", "saved/remove.txt": "removed", "saved/add.txt": "added"},
        )
        self.assertTrue(result["RuntimeRequalificationRequired"])

    def test_relocated_root_uses_stable_logical_paths(self):
        one = self.write("pre/saved/route.txt", "identical")
        two = self.write("post/saved/route.txt", "identical")
        before = self.capture("before", ("saved", one.parent))
        after = self.capture("after", ("saved", two.parent))
        self.assertEqual(self.compare(before, after)["Deltas"], [])

    def test_rejects_duplicate_groups_traversal_and_wrong_host(self):
        src = self.write("source/ok.txt", "x")
        self.run_cli(
            "capture", "--expected-host", self.hostname,
            "--source", f"saved={src.parent}", "--source", f"SAVED={src.parent}",
            "--out", self.root / "duplicates.json", expected=2,
        )
        self.run_cli(
            "capture", "--expected-host", self.hostname,
            "--source", f"saved={src.parent / '..' / 'source'}",
            "--out", self.root / "traversal.json", expected=2,
        )
        self.run_cli(
            "capture", "--expected-host", "NOT-THIS-HOST",
            "--source", f"saved={src.parent}",
            "--out", self.root / "wronghost.json", expected=3,
        )

    def test_rejects_tampered_hash_and_duplicate_manifest_key(self):
        src = self.write("source/data.txt", "data")
        before = self.capture("before", ("saved", src.parent))
        snapshot = json.loads(before.read_text(encoding="utf-8"))
        snapshot["Files"]["saved/data.txt"]["Sha256"] = "not-a-sha256"
        corrupted = self.root / "corrupt.json"
        corrupted.write_text(json.dumps(snapshot), encoding="utf-8")
        self.run_cli(
            "compare", "--before", corrupted, "--after", before,
            "--out", self.root / "badcompare.json", expected=3,
        )
        text = before.read_text(encoding="utf-8")
        item = json.dumps(snapshot["Files"]["saved/data.txt"])
        # The duplicate-key guard must not silently let a JSON parser overwrite facts.
        duplicate = text.replace('"Files": {', '"Files": {"saved/data.txt": ' + item + ",", 1)
        duplicated = self.root / "duplicated.json"
        duplicated.write_text(duplicate, encoding="utf-8")
        self.run_cli(
            "compare", "--before", duplicated, "--after", before,
            "--out", self.root / "dupcompare.json", expected=3,
        )

    def test_scan_limits_fail_closed(self):
        source = self.root / "source"
        self.write("source/a.txt", "1234")
        self.write("source/b.txt", "5678")
        self.capture("too-many", ("saved", source), max_files=1, expected=3)
        self.capture("too-big", ("saved", source), max_bytes=3, expected=3)

    def test_data_only_detection_and_executable_change(self):
        exe = self.write("before/game/rift_x64.exe", "same-binary")
        addon = self.write("before/addons/tool.lua", "old")
        before = self.capture("before", ("game", exe), ("addon-tool", addon.parent))
        postexe = self.write("after/game/rift_x64.exe", "same-binary")
        postaddon = self.write("after/addons/tool.lua", "new")
        after = self.capture("after", ("game", postexe), ("addon-tool", postaddon.parent))
        result = self.compare(before, after, "data-only", expected=1)
        self.assertFalse(result["GameExecutableChanged"])
        self.assertTrue(result["DataOnlyChangePossible"])
        postexe.write_text("different-binary", encoding="utf-8")
        changedexe = self.capture("changedexe", ("game", postexe), ("addon-tool", postaddon.parent))
        result = self.compare(before, changedexe, "binary-change", expected=1)
        self.assertTrue(result["GameExecutableChanged"])
        self.assertFalse(result["DataOnlyChangePossible"])

    def test_end_to_end_run_generates_four_artifacts(self):
        baseline = self.root / "prepatch"
        self.write("prepatch/game/rift_x64.exe", "game")
        self.write("prepatch/interface-saved/options.lua", "saved")
        self.write("prepatch/interface-addons/RiftReader2/main.lua", "addon-old")
        self.write("prepatch/waypoint-routes/route.json", "{}")
        game = self.write("live/rift_x64.exe", "game")
        iface = self.root / "Rift" / "Interface"
        self.write("Rift/Interface/Saved/options.lua", "saved")
        self.write("Rift/Interface/AddOns/RiftReader2/main.lua", "addon-new")
        routes = self.root / "routes"
        self.write("routes/route.json", "{}")
        out = self.root / "report"
        self.run_cli(
            "run", "--expected-host", self.hostname,
            "--baseline-dir", baseline,
            "--game-exe", game, "--interface-dir", iface,
            "--routes-dir", routes, "--out-dir", out, expected=1,
        )
        self.assertEqual(
            {p.name for p in out.iterdir()},
            {"before.json", "after.json", "changes.json", "REPORT.md"},
        )
        result = json.loads((out / "changes.json").read_text(encoding="utf-8"))
        self.assertEqual([(d["Key"], d["Kind"]) for d in result["Deltas"]],
                         [("addon-RiftReader2/main.lua", "modified")])
        self.assertIn("Selected sources and coverage", (out / "REPORT.md").read_text(encoding="utf-8"))
        self.run_cli(
            "run", "--expected-host", self.hostname,
            "--baseline-dir", baseline,
            "--game-exe", game, "--interface-dir", iface,
            "--routes-dir", routes, "--out-dir", out, expected=3,
        )


if __name__ == "__main__":
    unittest.main()
