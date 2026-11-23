"""Check repository Markdown links and count missing, ignored local evidence."""

import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\]\(([^)]+)\)")
EXTERNAL_OR_ANCHOR = re.compile(r"^(?:https?://|#|[a-z]:)", re.IGNORECASE)


def ignored_artifacts(root, paths):
    if not paths:
        return set()
    # Git's index keeps tracked artifacts required even if an ignore rule also matches.
    encoded = b"".join(path.encode("utf-8") + b"\0" for path in sorted(paths))
    # On Windows an empty value restored through os.environ can be absent from
    # native inheritance. Git requires the empty entries in GIT_CONFIG_COUNT.
    result = subprocess.run(["git", "check-ignore", "-z", "--stdin"], cwd=root,
                            input=encoded, capture_output=True, env=os.environ.copy())
    if result.returncode not in (0, 1):
        raise ValueError("Could not check Git ignore rules for local artifacts.")
    return set(result.stdout.decode("utf-8").split("\0")) - {""}


def check_links(root):
    root = Path(root).resolve()
    documents = [root / name for name in ("README.md", "AGENTS.md", "artifacts/README.md")]
    for name in ("docs", "samples", "addon", "contracts"):
        documents.extend(sorted((root / name).rglob("*.md")))

    present = 0
    missing = []
    missing_artifacts = []
    artifacts = root / "artifacts"
    for document in documents:
        for target in LINK.findall(document.read_text(encoding="utf-8-sig")):
            if EXTERNAL_OR_ANCHOR.match(target):
                continue
            target = target.split("#", 1)[0]
            path = (document.parent / target.replace("\\", "/")).resolve()
            if path.exists():
                present += 1
                continue
            error = f"Broken link in {document.relative_to(root)}: {target}"
            if path != artifacts and path.is_relative_to(artifacts):
                missing_artifacts.append((path.relative_to(root).as_posix(), error))
            else:
                missing.append(error)

    ignored = ignored_artifacts(root, {path for path, _ in missing_artifacts})
    missing.extend(error for path, error in missing_artifacts if path not in ignored)
    if missing:
        raise ValueError("\n".join(missing))
    return present, len(missing_artifacts)


def main():
    try:
        present, missing_local = check_links(ROOT)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    print(f"Checked {present} present repository links. "
          f"{missing_local} links refer to absent Git-ignored local artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
