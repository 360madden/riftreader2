"""Regression checks for link validation from a partial evidence checkout."""

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts import check_repository_links


ROOT = Path(__file__).resolve().parents[1]


class RepositoryLinkTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(prefix="rr2-doc-links-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git("init", "--quiet")
        (self.root / "artifacts").mkdir()
        self.write(".gitignore", "/artifacts/*\n!/artifacts/README.md\n")
        self.write("artifacts/README.md", "# Local evidence\n")
        self.write("AGENTS.md", "# Instructions\n")

    def git(self, *arguments):
        environment = {key: value for key, value in os.environ.items()
                       if key not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
        result = subprocess.run(["git", *arguments], cwd=self.root, env=environment,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def write(self, file, text):
        path = self.root / file
        path.write_text(text, encoding="utf-8")
        return path

    def test_ignored_evidence_can_be_absent_in_a_clean_checkout(self):
        self.write("README.md", "[guide](artifacts/README.md#local-evidence)\n"
                                "[capture](artifacts/observation-café.json)\n"
                                "[another reference](artifacts/observation-café.json)\n")
        self.assertEqual(check_repository_links.check_links(self.root), (1, 2))
        self.write("artifacts/observation-café.json", "{}\n")
        self.assertEqual(check_repository_links.check_links(self.root), (3, 0))

    def test_missing_tracked_artifact_still_fails(self):
        self.write("README.md", "[release fixture](artifacts/fixture.json)\n")
        fixture = self.write("artifacts/fixture.json", "{}\n")
        self.git("add", "-f", "artifacts/fixture.json")
        fixture.unlink()
        with self.assertRaisesRegex(ValueError, "Broken link in README.md: artifacts/fixture.json"):
            check_repository_links.check_links(self.root)

    def test_missing_unignored_artifact_still_fails(self):
        self.write(".gitignore", "/artifacts/*\n!/artifacts/README.md\n!/artifacts/guide.md\n")
        self.write("README.md", "[guide](artifacts/guide.md)\n")
        with self.assertRaisesRegex(ValueError, "Broken link in README.md: artifacts/guide.md"):
            check_repository_links.check_links(self.root)

    def test_path_that_leaves_artifacts_still_requires_a_repository_file(self):
        self.write("README.md", "[missing](artifacts/../missing.md)\n")
        with self.assertRaisesRegex(ValueError, "Broken link in README.md: artifacts/../missing.md"):
            check_repository_links.check_links(self.root)

    def test_check_preserves_empty_values_in_git_environment_configuration(self):
        self.write("README.md", "[capture](artifacts/missing.json)\n")
        environment = {**os.environ, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "rr2.test",
                       "GIT_CONFIG_VALUE_0": ""}
        # Restore an empty configuration in an isolated Python process, as tests or callers can do.
        script = (
            "import os, sys\n"
            "from scripts.check_repository_links import check_links\n"
            "os.environ['GIT_CONFIG_VALUE_0'] = ''\n"
            "assert check_links(sys.argv[1]) == (0, 1)\n"
        )
        result = subprocess.run([sys.executable, "-B", "-c", script, str(self.root)],
                                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
