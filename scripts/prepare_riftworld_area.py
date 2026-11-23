"""Prepare a RiftWorld area for Waypoints using the local toolchain."""

import argparse
import json
from pathlib import Path
import sys


def _navigation_descriptor(build, upstream, output):
    descriptor = Path(build["buildDirectory"]) / "navigation.json"
    if Path(build["pipelineCheckout"]) == upstream:
        return build, descriptor

    # A cache hit is keyed by input hashes, so it can name an older checkout.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.waypoint_destination_plan import _reference, _relocate_navigation_build

    copied = _relocate_navigation_build(_reference(descriptor), output / "navigation-build", upstream)
    return {**build, "buildDirectory": str(copied.parent), "pipelineCheckout": str(upstream)}, copied


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("request", "source-index", "receipt", "handoff"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--allow-partial-navigation", action="store_true", required=True)
    args = parser.parse_args(argv)

    # The planner runs this child in the selected RiftWorld checkout.
    world = Path.cwd().resolve()
    sys.path.insert(0, str(world))
    from riftworld import preparation
    from riftworld.core import content_id, read_json, sha256, write_json
    from riftworld.navigation import DEFAULT_UPSTREAM, build_navigation
    from riftworld.preparation import prepared_navigation_handoff
    from riftworld.storage import ensure_processing_space

    if Path(preparation.__file__).resolve() != world / "riftworld/preparation.py":
        raise ValueError("RiftWorld preparation was loaded from an unexpected checkout")
    receipt, handoff_path = args.receipt.absolute(), args.handoff.absolute()
    if receipt == handoff_path or any(path.exists() or path.is_symlink() for path in (receipt, handoff_path)):
        raise ValueError("Preparation receipt and handoff require distinct new paths")

    scene_store = world / "cache/scenes"
    patch_store = world / "data/patches"
    preparation_root = world / "cache/rr2-preparations"
    source_index = args.source_index.resolve(strict=True)
    # RiftWorld keys preparation lookups by semantic IDs, but its receipts
    # contain absolute references and exact hashes. Keep those receipts local
    # to their input and storage paths while sharing the large geometry caches.
    binding = content_id({
        "sourceIndex": str(source_index),
        "sourceIndexSha256": sha256(source_index),
        "sceneStore": str(scene_store.resolve()),
        "patchStore": str(patch_store.resolve()),
        "preparationRoot": str(preparation_root.resolve()),
    })
    preparation_store = preparation_root / binding
    navigation_cache = world / "cache/navigation"
    for destination in (scene_store, patch_store, preparation_store,
                        navigation_cache, receipt.parent, handoff_path.parent):
        ensure_processing_space(destination)
    handle = preparation.prepare_area(
        read_json(args.request), source_index,
        scene_store=scene_store, patch_store=patch_store, preparation_store=preparation_store,
        allow_partial_navigation=args.allow_partial_navigation,
    )
    patch = handle.patch
    profile = read_json(args.profile) if args.profile is not None else {}
    upstream = (args.upstream or DEFAULT_UPSTREAM).resolve()
    try:
        build = build_navigation(
            patch.geometry_path, navigation_cache, bounds=tuple(patch.document["requestedBounds"]),
            profile=profile, upstream=upstream, coverage=patch.document["coverage"],
            context={"patchId": patch.patch_id, "sourceWorld": patch.document["sourceWorld"],
                     "coordinates": patch.document["coordinates"]},
        )
        build, descriptor = _navigation_descriptor(build, upstream, handoff_path.parent)
    except (OSError, ValueError, RuntimeError, SystemExit) as error:
        navigation = {"requested": True, "status": "build-failed",
                      "failure": {"stage": "build", "type": type(error).__name__, "message": str(error)}}
        write_json(receipt, {**handle.run, "navigation": navigation})
        raise

    navigation = {"requested": True, "status": "built", "build": build}
    write_json(receipt, {**handle.run, "navigation": navigation})
    handoff = prepared_navigation_handoff(
        handle, request_path=args.request, profile_path=args.profile,
        navigation_descriptor=descriptor,
    )
    write_json(handoff_path, handoff)
    print(json.dumps({"status": "prepared-area", "preparationId": handle.preparation_id,
                      "receipt": str(receipt), "handoff": str(handoff_path)}))


if __name__ == "__main__":
    main()
