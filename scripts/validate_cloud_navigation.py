"""Small, explicit test lanes for repository-only Codex Cloud navigation work.

This runner does not discover live tests, build Windows native readers, install
packages, contact RIFT, or use a local registered native-reader bundle.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
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
        "tests.test_waypoint_feedback_window",
        "tests.test_waypoint_feedback_replay",
    ),
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=(*LANES, "all"), default="all")
    parser.add_argument("--jobs", type=int, choices=range(1, len(LANES)+1), default=1,
                        help="number of independent repository-only lanes to run concurrently")

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
    def run_lane(item):
        lane, modules = item
        try:
            result = subprocess.run([sys.executable, "-B", "-m", "unittest", *modules],
                                    cwd=ROOT, env=env, check=False, timeout=180,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, errors="replace")
        except (OSError, subprocess.TimeoutExpired) as error:
            return lane, 2, str(error)
        return lane, int(result.returncode != 0), result.stdout

    # Fixed lane order in the report, even when the workers finish out of order.
    # No live tests or overlapping output directories are admitted by this runner.
    with ThreadPoolExecutor(max_workers=min(args.jobs, len(selected))) as pool:
        results = list(pool.map(run_lane, selected.items()))
    for lane, code, output in results:
        print(f"== {lane} ==", flush=True)
        print(output, end="" if output.endswith("\n") else "\n", flush=True)
        if code:
            print(f"{lane}: failed or blocked ({code})", file=sys.stderr)
    if any(code for _, code, _ in results):
        return max(code for _, code, _ in results)
    print("Selected repository-only checks completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
