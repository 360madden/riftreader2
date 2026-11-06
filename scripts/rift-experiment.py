#!/usr/bin/env python3
"""One supervised RIFT-Lab pulse, using the installed V1 console as an adapter."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import uuid

from experiment_core import run_experiment


def read_json(path, with_hash=False):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate property: {key}")
            result[key] = value
        return result
    with Path(path).open("rb") as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise ValueError("Plan/config exceeds 65536 bytes")
    value = json.loads(data, object_pairs_hook=unique)
    return (value, hashlib.sha256(data).hexdigest().upper()) if with_hash else value


class LabAdapter:
    def __init__(self, reference, config_path, root):
        self.reference = Path(reference).resolve()
        sys.path.insert(0, str(self.reference / "tools" / "riftreader_workflow"))
        self.game = importlib.import_module("game_session")
        self.console = importlib.import_module("vm_console")
        self.readback = importlib.import_module("guest_readback_gate")
        self.config, self.config_hash = read_json(config_path, with_hash=True)
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "runs").mkdir(exist_ok=True)
        self.stop_path = self.root / "STOP"
        self.vmx = Path(self.config["vmx"])
        self.identity_session = self.console.CommandScopedVmIdentity(
            self.vmx, 5905, self.console.DEFAULT_VMRUN)
        self.stop_check = lambda: False
        owner = self
        class StoppableConsole(self.console.ConsoleController):
            def pulse(self, *args, **kwargs):
                # run_pulse resumes its review latch; a previously requested stop must survive that.
                if owner.stop_check():
                    self.pause()
                    raise InterruptedError("Stop requested before input")
                return super().pulse(*args, **kwargs)
        self.ctl = StoppableConsole(
            self.root / "controller", self.identity_session,
            lambda: self.console.connect(self.vmx, 5905))
        self.run_dir = None
        self.review_note = None
        self.previous = None

    def identity(self):
        return self.identity_session(), self.game.game_binding(self.game.sample(self.config))

    def prepare(self, key, hold_ms):
        self.console.validate_pulse(key, hold_ms)
        if self.ctl.state().get("pending"):
            raise ValueError("Release is pending; use recover before preparing another trial")
        experiment_id = uuid.uuid4().hex
        review_dir = self.root / "reviews" / experiment_id
        self.ctl.artifact_dir = review_dir
        observation = self.game.observe(self.ctl, self.config, review_dir)
        vm, game = self.identity()
        plan = {"schemaVersion": 1, "experimentId": experiment_id, "key": key,
                "holdMilliseconds": hold_ms, "expectedVmIdentity": vm,
                "expectedGameBinding": game,
                "reviewedCaptureId": observation["observation"]["id"],
                "configSha256": self.config_hash}
        plans = self.root / "plans"
        plans.mkdir(exist_ok=True)
        path = plans / f"{experiment_id}.json"
        with path.open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, indent=2)
        # A new reviewed plan is the explicit way to clear a prior stop request.
        self.stop_path.unlink(missing_ok=True)
        return {"plan": str(path), "screen": str(review_dir / "screen-motion.png"),
                "reviewExpiresAfterSeconds": self.console.MAX_CAPTURE_AGE,
                "inputSent": False}

    def sample(self, after=False):
        deadline = time.monotonic() + 12
        while True:
            if self.stop_path.exists():
                raise InterruptedError("Stop requested")
            envelope = self.game.sample(self.config)  # Includes fresh foreground/epoch checks.
            observation = envelope["observation"]
            expected = {"expectedMachineName": observation["machineName"],
                        "target": {**observation["target"], "processName": "rift_x64"}}
            try:
                sample = self.readback.validate_readiness_sample(
                    envelope, self.config["sourceAddress"], expected)
                if not sample["playerDataUsable"]:
                    raise ValueError("Player data unavailable")
                if not after or (sample["scanSequence"] > self.previous["scanSequence"] and
                                 sample["sourceSampledAt"] > self.previous["sourceSampledAt"] and
                                 datetime.fromisoformat(sample["acquisitionStartedAtUtc"]) > self.released_utc):
                    return {"validatedAtHostUtc": datetime.now(timezone.utc).isoformat(),
                            "validatedAtHostMonotonicNs": time.monotonic_ns(),
                            "sample": sample, "envelope": envelope}
            except (self.console.Blocked, ValueError):
                if not after:
                    raise
            if time.monotonic() >= deadline:
                raise ValueError("No new post-release readback within 12 seconds")
            time.sleep(.05)

    def capture_before(self):
        self.ctl.artifact_dir = self.run_dir
        result = self.sample()
        self.previous = result["sample"]
        modules = (self.game, self.console, self.readback,
                   importlib.import_module("vm_console_windows"),
                   importlib.import_module("guest_game_gate"),
                   importlib.import_module("scene_text_detector"),
                   importlib.import_module("frame_motion_gate"))
        result["adapterSourceSha256"] = {
            str(Path(module.__file__).resolve()): hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest().upper()
            for module in modules}
        result["runnerSourceSha256"] = {
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest().upper()
            for name in ("rift-experiment.py", "experiment_core.py")}
        result["timing"] = {
            "stimulusClock": "host-monotonic-and-UTC",
            "sampleClock": "guest-source-clock-with-acquisition-UTC-and-host-receipt",
            "crossMachineTimingUncertaintySeconds": None,
            "limitation": "UTC ordering assumes aligned host/guest clocks; not precise stimulus/sample synchronization."}
        return result

    def pulse(self, key, hold_ms, capture_id, stop_requested):
        self.stop_check = stop_requested
        done = threading.Event()
        def watch_stop():
            while not done.wait(.01):
                if stop_requested():
                    self.ctl.pause()
                    return
        watcher = threading.Thread(target=watch_stop, daemon=True)
        watcher.start()
        try:
            args = SimpleNamespace(key=key, hold_ms=hold_ms, reviewed_capture=capture_id,
                                   scene="in-world", text_entry="closed", review_note=self.review_note)
            event = self.game.run_pulse(self.ctl, self.config, self.run_dir, args)
            self.released_utc = datetime.fromisoformat(event["keyUpSentAtUtc"])
            return event
        finally:
            done.set()
            watcher.join(timeout=1)

    def capture_after(self):
        return self.sample(after=True)

    def stop(self):
        self.stop_path.touch(exist_ok=True)
        return self.ctl.pause()

    def recover(self):
        return self.ctl.recover()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", default=r"C:\rift modding\RiftReader")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("artifacts/experiments"))
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--key", choices=("w", "a", "s", "d"), required=True)
    prepare.add_argument("--hold-ms", type=int, default=100)
    run = commands.add_parser("run")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--review-note", required=True,
                     help="Confirm the displayed fresh screenshot is in-world with text entry closed")
    commands.add_parser("stop")
    commands.add_parser("recover")
    args = parser.parse_args()
    try:
        adapter = LabAdapter(args.reference, args.config, args.root)
        if args.command == "stop":
            result = adapter.stop()  # Does not wait on the input mutex.
        else:
            with adapter.console.ControlMutex(adapter.vmx):
                if args.command == "prepare":
                    result = adapter.prepare(args.key, args.hold_ms)
                elif args.command == "recover":
                    result = adapter.recover()
                else:
                    plan = read_json(args.plan)
                    if plan.get("configSha256") != adapter.config_hash:
                        raise ValueError("Configuration changed since preparation")
                    if len(args.review_note.strip()) < 12:
                        raise ValueError("Review the screenshot and supply a short scene/text-entry note")
                    # Validate ID before deriving a path. Core validates all remaining fields.
                    if not isinstance(plan.get("experimentId"), str) or len(plan["experimentId"]) != 32 or any(
                            char not in "0123456789abcdef" for char in plan["experimentId"]):
                        raise ValueError("Invalid experiment ID")
                    adapter.run_dir = adapter.root / "runs" / plan["experimentId"]
                    adapter.review_note = args.review_note
                    result = run_experiment(plan, adapter, adapter.run_dir, adapter.stop_path.exists)
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") in (None, "completed") else 2
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({"status": "blocked", "error": str(error) or type(error).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
