# Strict 480-second live-reader freshness observer

This is a **read-only, observer-side** qualification tool. It requires an already
running, independently authorized and bound reader, a matching current-epoch
reader postflight summary and a source pin. It **does not** launch/rebind a
reader, control the guest/VM, submit a queue request, arm the controller, or
send input. It cannot prove that other operators sent no input.

## Before starting

1. Verify the target game, reader, and receiver identities and that the reader
   nonce is the one just bound in the addon UI. Rebinding or reusing evidence
   from an expired nonce does not qualify a later reader.
2. Obtain the exact current-epoch source pin from
   `scripts/build_live_source_pin.py` after its own fresh receipt checks. Keep
   the matching reader-launch/postflight `summary.json` with it. Do not
   substitute an old receipt, pin, or summary.
3. Keep the player stationary and make sure input ownership is externally
   controlled; the observer itself does not hold or enforce a no-input lease.
4. Require **more than 525 seconds** remaining before reader expiry (480
   observed seconds plus a continuing 45-second margin). A reader started too
   long ago must be renewed and rebound through the normal reviewed workflow.

## Run

Use a **new output directory path**. The observer creates that directory
exclusively and refuses to overwrite an existing evidence run.

```powershell
python scripts/observe_live_reader_freshness.py `
  --source-pin artifacts/current-reader/root-source-pin.json `
  --reader-summary artifacts/current-reader/reader-summary.json `
  --output-dir artifacts/current-reader/strict480-observer
```

The optional `--duration-seconds` defaults to **480** and cannot lower it.
It must have a valid same-epoch pin and receipt at every accepted sample.
The reader postflight and source pin are cross-checked for exact lab, reader
PID/start/SHA/nonce, target game PID/start/SHA, and receiver PID/start.

## Qualification and outputs

To pass, the tool requires:

- At least 480 seconds of observer time with strictly advancing receiver and
  addon sequence, addon clock, and receipt capture timestamp.
- Each consecutive accepted-sample **arrival gap** and original
  **capture-time gap** is strictly below 4.5 seconds.
- One addon epoch/player and stationary X/Z drift no greater than 0.05 units.
- More than 45 seconds of expiry margin while running and immediately
  before PASS; no blocked finalization longer than the observation gap.
- Strict pinned receipt validation through `movement_feedback.py`, including
  game/reader/receiver continuity and full-or-fast source gates.

The evidence directory contains `samples.jsonl`, its SHA-256 in
`summary.json`, and raw validated receipt files under `raw/`. The summary
reports both `maximumAcceptanceGapSeconds` and
`maximumCaptureGapSeconds`; the legacy `maximumGapSeconds` is the observer
acceptance gap. An exception produces a failed summary when output creation
has begun. Never promote a failed or interrupted run, a stale nonce, or a
PASS attached to another reader epoch.

**Scope limit:** `sourceQualification=observer-side-480s` verifies only
the observations of this tool during the interval. It does not establish
absence of external input, readiness of a managed controller, live movement
permission, facing matrix correctness, or native health/cooldown ownership.
No controlled movement should follow without a separate up-to-date managed
generation, exact queue/lease, STOP, fresh-UI and reviewed-input gate.

## Offline checks

```powershell
python -m unittest discover -s tests -p test_observe_live_reader_freshness.py -v
python -m unittest discover -s tests -p test_movement_feedback.py -v
python -m unittest discover -s tests -p test_build_live_source_pin.py -v
```
