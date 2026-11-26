"""Small, explicit test lanes for repository-only Codex Cloud navigation work.

This runner does not discover live tests, build Windows native readers, install
packages, contact RIFT, or use a local registered native-reader bundle.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LANES = {
    "planning": (
        "tests.test_waypoint_local_plan",
        "tests.test_waypoint_navigation_candidate",
    ),
    "adoption": (
        "tests.test_waypoint_destination_plan",
        "tests.test_waypoint_candidate_adoption",
    ),
    "progress": (
        "tests.test_waypoint_progress",
        "tests.test_waypoint_marker_progress",
        "tests.test_waypoint_route_library",
        "tests.test_waypoint_seed_feedback",
    ),
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=(*LANES, "all"), default="all")
    args = parser.parse_args(argv)
    # Isolate host-installed tools so the simulated target fixtures cannot
    # inherit a real Windows reader or sibling RiftWorld registration override.
    env = os.environ.copy()
    for name in ("RR2_NATIVE_READER", "RR2_RIFTWORLD_ROOT", "RR2_RIFTWORLD_PYTHON",
                 "RR2_RIFTWORLD_UPSTREAM"):
        env.pop(name, None)
    env["RR2_PHYSICAL_TOOLS_ROOT"] = "debug"
    selected = LANES if args.lane == "all" else {args.lane: LANES[args.lane]}
    print(f"RR2 repository-only checks: Python {sys.version.split()[0]}; "
          "no live acceptance claimed.", flush=True)
    for lane, modules in selected.items():
        print(f"== {lane} ==", flush=True)
        try:
            result = subprocess.run([sys.executable, "-B", "-m", "unittest", *modules],
                                    cwd=ROOT, env=env, check=False, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as error:
            print(f"{lane}: blocked: {error}", file=sys.stderr)
            return 2
        if result.returncode:
            print(f"{lane}: failed ({result.returncode})", file=sys.stderr)
            return 1
    print("Selected repository-only checks completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
