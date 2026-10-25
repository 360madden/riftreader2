"""Export closed XYZ panel sessions and their offline audits; no live access."""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.review_position_panel import read_file, require, review_session, sha

MAX_SESSIONS = 8
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_FILES = 8192


def json_bytes(value):
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _check_location(directory: Path):
    for part in (directory, *directory.parents):
        require(not part.is_symlink() and not part.is_junction(),
                "Linked evidence/output directories are not supported")


def _write_verified(path: Path, data: bytes):
    with path.open("xb") as stream:
        require(stream.write(data) == len(data), "Incomplete export write")
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == data, "Export copy differs")


def export_sessions(session_dirs: list[Path], output: Path) -> dict:
    require(1 <= len(session_dirs) <= MAX_SESSIONS, "Select between one and eight sessions")
    output = Path(output).absolute()
    _check_location(output)
    require(output.parent.is_dir() and not output.exists(), "Output must be a new directory under an existing parent")
    output = output.parent.resolve(strict=True) / output.name
    sources = []
    for directory in session_dirs:
        directory = Path(directory).absolute()
        _check_location(directory)
        directory = directory.resolve(strict=True)
        require(directory.is_dir(), "Session must be a directory")
        require(directory not in sources, "Duplicate session directory")
        require(not output.is_relative_to(directory) and not directory.is_relative_to(output),
                "Output must be separate from input sessions")
        sources.append(directory)

    # Bound the input set before asking the reviewer to read any report bodies.
    total_size = 0
    selected = []
    for directory in sources:
        names = {"panel-session.json", "panel-events.jsonl"}
        for entry in directory.glob("read-*.json"):
            names.add(entry.name)
            require(len(names) <= MAX_FILES, "Too many session files")
        for name in names:
            path = directory / name
            require(path.is_file() and not path.is_symlink() and not path.is_junction(),
                    "Missing or linked evidence file")
            total_size += path.stat().st_size
            require(total_size <= MAX_INPUT_BYTES, "Selected sessions exceed 64 MiB")
        selected.append(names)

    payload = {}
    summaries = []
    copied_size = 0
    for index, (directory, selected_names) in enumerate(zip(sources, selected), 1):
        review = review_session(directory)
        expected = {"panel-session.json": review["sessionSha256"],
                    "panel-events.jsonl": review["journalSha256"], **review["reportSha256"]}
        require(set(expected) == selected_names, "Session file set changed during review")
        prefix = f"session-{index:02d}"
        for name, digest in expected.items():
            data = read_file(directory / name)
            copied_size += len(data)
            require(copied_size <= MAX_INPUT_BYTES, "Input grew beyond 64 MiB")
            require(sha(data) == digest, "Source changed after its audit")
            payload[f"{prefix}/originals/{name}"] = data
        payload[f"{prefix}/review.json"] = json_bytes(review)
        summaries.append({"session": prefix, "reviewStatus": review["status"],
            "reportCount": len(review["reportSha256"]), "findingCount": len(review["findings"]),
            "epochCount": len(review["epochs"]), "sessionSha256": review["sessionSha256"],
            "journalSha256": review["journalSha256"]})

    has_findings = any(item["findingCount"] for item in summaries)
    status = "exported-with-findings" if has_findings else "exported-recorded-checks-passed"
    description = (
        "XYZ panel sessions — saved evidence export\n\n"
        "Each session includes byte-identical original reports and a new offline audit.\n"
        "Behavioral failures are retained and listed, never filtered out.\n"
        "This export does not establish a new game restart, deployment, Lua agreement,\n"
        "movement causation, rendered UI state, or general reliability.\n"
        "Candidate-only; exact-build checks apply; patch recovery remains deferred.\n\n"
        "Only panel-session.json, panel-events.jsonl and referenced read reports are copied.\n"
        "Other source-directory files are excluded. Original evidence is not redacted.\n"
        "checksums.json pins payload files; complete.json pins package.zip, which also\n"
        "contains checksums.json. A finished export requires a valid complete.json and\n"
        "no INCOMPLETE.txt marker. Verify the recorded hashes before relying on a copy.\n"
    )
    payload["README.txt"] = description.encode("utf-8")
    rows = "".join(
        f'<tr><td>{html.escape(item["session"])}</td>'
        f'<td>{html.escape(item["reviewStatus"])}</td><td>{item["reportCount"]}</td>'
        f'<td>{item["findingCount"]}</td>'
        f'<td><a href="{item["session"]}/review.json">Audit</a></td></tr>'
        for item in summaries)
    payload["report.html"] = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>XYZ evidence review</title><style>'
        'body{max-width:960px;margin:40px auto;padding:0 20px;font:17px/1.6 system-ui;'
        'color:#183040;background:#f6f9fb}pre{white-space:pre-wrap}'
        'td,th{text-align:left;padding:10px;border-bottom:1px solid #c8d4de}'
        'a{color:#075b8c}table{border-collapse:collapse}</style>'
        '<h1>XYZ evidence review</h1><p>' + html.escape(status) + '</p>'
        '<table><tr><th>Session</th><th>Recorded checks</th><th>Reports</th>'
        '<th>Findings</th><th>Evidence</th></tr>' + rows + '</table><pre>' +
        html.escape(description) + '</pre></html>\n').encode("utf-8")
    payload["summary.json"] = json_bytes({"schemaVersion": 1,
        "contractVersion": "xyz-panel-export/1", "status": status,
        "qualification": "candidate-only", "sessions": summaries,
        "reviewerSha256": sha(read_file(ROOT / "scripts/review_position_panel.py")),
        "exporterSha256": sha(read_file(Path(__file__))), "liveActionsPerformed": False})
    checksums = {name: {"byteLength": len(data), "sha256": sha(data)}
                 for name, data in sorted(payload.items())}
    payload["checksums.json"] = json_bytes({"schemaVersion": 1, "files": checksums})

    for directory, expected_names in zip(sources, selected):
        current_names = {"panel-session.json", "panel-events.jsonl"}
        for entry in directory.glob("read-*.json"):
            current_names.add(entry.name)
            require(len(current_names) <= MAX_FILES, "Too many session files")
        require(current_names == expected_names, "Session file set changed after review")

    # Reserve one new directory. An interrupted write deliberately remains
    # incomplete and is never reused or presented as a successful export.
    output.mkdir()
    (output / "INCOMPLETE.txt").write_text("Export has not completed. Do not treat as accepted evidence.\n", encoding="utf-8")
    for name, data in sorted(payload.items()):
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_verified(target, data)
    archive_path = output / "package.zip"
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    with zipfile.ZipFile(archive_path) as archive:
        require(set(archive.namelist()) == set(payload), "Archive member set differs")
        for name, data in payload.items():
            require(archive.read(name) == data, "Archive payload differs")
    archive_data = archive_path.read_bytes()
    receipt = {"schemaVersion": 1, "contractVersion": "xyz-panel-export-completion/1",
        "status": status, "archive": "package.zip", "byteLength": len(archive_data),
        "sha256": sha(archive_data), "payloadFiles": len(payload), "sessions": summaries,
        "liveActionsPerformed": False}
    _write_verified(output / "complete.json", json_bytes(receipt))
    (output / "INCOMPLETE.txt").unlink()
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = export_sessions(args.session_dir, args.output)
        print(json.dumps(result))
        return 2 if result["status"] == "exported-with-findings" else 0
    except (ValueError, OSError, KeyError, TypeError, OverflowError, zipfile.BadZipFile) as error:
        print(f"XYZ export rejected: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
