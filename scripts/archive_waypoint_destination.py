"""Export a verified offline Waypoints destination as a transferable archive."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.waypoint_candidate_adoption import _adoption_digest
from scripts.waypoint_destination_plan import (
    SCHEMA, _archive_local_path, _archived_route_result, _hash, _read,
    replay_destination_archive,
)
from scripts.waypoint_navigation_candidate import inspect_candidate
from scripts.waypoint_progress import write_json_atomic
from scripts.waypoint_view_bundle import bundle_asset


PATCH_FILES = {
    "telara-fly": {"geometry", "placements"},
    "riftworld-scene": {"geometry", "scene"},
    "riftworld-watch-pillar": {"base", "map", "geometry", "body", "traversal", "outbound", "return"},
}


def _source(path, sha256):
    path = _archive_local_path(path, "invalid-destination-archive-source-path")
    if (not isinstance(sha256, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", sha256)
            or _hash(path) != sha256.upper()):
        raise ValueError(f"destination-archive-source-hash-mismatch: {path.name}")
    return path, sha256.upper()


def _source_document(source):
    path, expected = source
    document, digest = _read(path)
    if digest != expected:
        raise ValueError(f"destination-archive-source-changed: {path.name}")
    return document


def _relative_source(descriptor, reference):
    value = reference["path"]
    if Path(value).anchor or PureWindowsPath(value).anchor:
        raise ValueError("destination-archive-patch-dependencies-must-be-relative")
    return _source(os.path.normpath(descriptor.parent / value), reference["sha256"])


def _patch_sources(source, document):
    path, _ = source
    provider = document["source"]["provider"]
    references = document["files"]
    if document.get("schema") != "riftworld.patch/1" or set(references) != PATCH_FILES.get(provider):
        raise ValueError("unsupported-destination-archive-patch-files")
    sources = [source]
    for role, reference in references.items():
        member = _relative_source(path, reference)
        if role == "base":
            base = _source_document(member)
            if base["source"]["provider"] != "riftworld-scene":
                raise ValueError("destination-archive-watch-base-must-be-a-scene")
            sources.extend(_patch_sources(member, base))
        else:
            sources.append(member)
        if role == "scene":
            geometry = _source_document(member)["geometry"]
            if geometry["file"] != "scene.obj":
                raise ValueError("destination-archive-scene-geometry-is-not-local")
            sources.append(_relative_source(member[0], {"path": geometry["file"], "sha256": geometry["sha256"]}))
    return sources


def _archive_inputs(plan, native_context):
    if (plan.get("schema") != SCHEMA or plan.get("status") != "adoptable"
            or plan.get("destinationCovered") is not True or plan.get("inputSent") is not False
            or plan.get("currentRouteChanged") is not False):
        raise ValueError("destination-archive-requires-a-complete-offline-adopted-plan")
    if "preparation" in plan["inputs"]:
        raise ValueError("destination-archive-export-requires-a-saved-patch-and-build-plan")

    candidate = _source_document(_source(**plan["candidate"]))
    inspect_candidate(candidate)
    route = _source_document(_source(**plan["adoptedRoute"]))
    adoption = route["candidateAdoption"]
    if (adoption["integritySha256"] != _adoption_digest(route) or adoption["candidateId"] != candidate["candidateId"]
            or adoption["direction"] != "forward" or candidate["status"] != "complete"):
        raise ValueError("destination-archive-adopted-route-does-not-match-candidate")

    context = native_context or plan.get("nativeContext", {}).get("path")
    if context is None:
        raise ValueError("supply --native-context for a plan that predates saved context paths")
    sources = {}

    def include(name, source):
        if sources.setdefault(name, source) != source:
            raise ValueError("destination-archive-conflicting-members")
        return name

    patch_source = _source(**plan["inputs"]["patch"])
    patch = _source_document(patch_source)
    patch_files = _patch_sources(patch_source, patch)
    patch_root = Path(os.path.commonpath([source[0].parent for source in patch_files]))
    patch_names = {source[0]: include("patch/" + source[0].relative_to(patch_root).as_posix(), source)
                   for source in patch_files}

    navigation = _source(**plan["inputs"]["build"])
    build = _source_document(navigation)
    if set(build["files"]) != {"navmesh", "preparedObj"}:
        raise ValueError("unsupported-destination-archive-navigation-files")
    build_name = include("navigation/navigation.json", navigation)
    for reference in build["files"].values():
        member = bundle_asset(navigation[0].parent, reference["path"])
        include("navigation/" + member.relative_to(navigation[0].parent).as_posix(),
                _source(member, reference["sha256"]))

    receipts = []
    for index, reference in enumerate(adoption["sourceReceipts"]):
        source = _source(**reference)
        if source[0] in patch_names:
            receipts.append(patch_names[source[0]])
        else:
            receipts.append(include(f"evidence/receipt-{index}{source[0].suffix}", source))
    replay = {
        "catalog": include("destination/catalog.json", _source(**plan["inputs"]["catalog"])),
        "build": build_name, "destination": plan["destinationId"], "from": plan["requestedStartXYZ"],
        "nativeContext": include("evidence/context.json", _source(context, adoption["zoneContextSha256"])),
        "nativeReceipts": receipts, "nativeStart": adoption["nativeIndices"][0],
        "nativeEnd": adoption["nativeIndices"][-1], "candidateStart": adoption["candidateIndices"][0],
        "candidateEnd": adoption["candidateIndices"][-1],
        "searchExtent": candidate.get("plannerResult", {}).get("searchExtent"),
        "expected": _archived_route_result(candidate, route, include_geometry=True),
    }
    patch_info = {"path": patch_names[patch_source[0]], "patchId": patch["patchId"],
                  "geometrySha256": patch["files"]["geometry"]["sha256"]}
    return sources, patch_info, replay


def export_archive(plan_path, output_directory, *, native_context=None, **toolchain):
    plan_path = _archive_local_path(plan_path, "invalid-destination-archive-plan-path")
    output = _archive_local_path(output_directory, "invalid-destination-archive-output-path")
    if output.exists():
        raise ValueError("destination-archive-output-exists")
    plan, plan_sha = _read(plan_path)
    sources, patch, replay = _archive_inputs(plan, native_context)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".rr2-export-", dir=output.parent) as scratch:
        staged = Path(scratch) / "bundle"
        staged.mkdir()
        archive = staged / "waypoints-destination.zip"
        replay_bytes = (json.dumps(replay, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        replay_sha = sha256(replay_bytes).hexdigest().upper()
        with ZipFile(archive, "x", compression=ZIP_DEFLATED) as writer:
            for name, (path, _) in sorted(sources.items()):
                writer.write(path, arcname=name)
            writer.writestr("replay.json", replay_bytes)
        handoff = {"archive": archive.name, "sha256": _hash(archive), "bytes": archive.stat().st_size,
                   "patch": patch, "replayInputs": "replay.json", "replayInputsSha256": replay_sha,
                   "sourcePlanSha256": plan_sha,
                   "contents": {name: digest for name, (_, digest) in sources.items()}, "availability": "local-only"}
        write_json_atomic(staged / "handoff.json", handoff)
        verification = replay_destination_archive(staged / "handoff.json", Path(scratch) / "verification", **toolchain)
        if _hash(plan_path) != plan_sha or any(_hash(path) != digest for path, digest in sources.values()):
            raise ValueError("destination-archive-sources-changed-during-export")
        if output.exists():
            raise ValueError("destination-archive-output-exists")
        staged.rename(output)
    return {"status": "exported", "ownerHost": verification["ownerHost"],
            "archive": str(output / archive.name), "archiveSha256": handoff["sha256"],
            "handoff": str(output / "handoff.json"), "verifiedResult": verification["verifiedResult"],
            "inputSent": False, "currentRouteChanged": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True, help="Completed offline destination plan.json")
    parser.add_argument("--out-dir", type=Path, required=True, help="Fresh local archive directory")
    parser.add_argument("--native-context", type=Path, help="Original context file for older plans")
    parser.add_argument("--riftworld-root", type=Path)
    parser.add_argument("--riftworld-python", type=Path)
    parser.add_argument("--riftworld-upstream", type=Path)
    args = vars(parser.parse_args(argv))
    plan, output = args.pop("plan"), args.pop("out_dir")
    try:
        report = export_archive(plan, output, **args)
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error), "inputSent": False,
                          "currentRouteChanged": False}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
