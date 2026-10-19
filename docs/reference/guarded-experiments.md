# Supervised experiments

`scripts/rift-experiment.py` performs one reviewed RIFT-Lab movement/turning
pulse and retains before/after evidence. It is a small Python adapter over the
unchanged V1 VM console, game-session guards, and GuestObserver readback. It
does not add a service or a gameplay automation system. V1 source stays in
`C:\rift modding\RiftReader`; Python must have its existing lab dependencies.

Use the installed lab Python and a private local game-session configuration:

```powershell
$python = 'C:\rift modding\VMs\RIFT-Lab\controller-env\Scripts\python.exe'
$config = 'artifacts/experiment-validation/config.json'
& $python scripts/rift-experiment.py --config $config prepare --key w --hold-ms 100
# Inspect the returned screenshot, then use its returned plan path within 45 s.
& $python scripts/rift-experiment.py --config $config run --plan PLAN.json --review-note 'Fresh screenshot: in world, clear ground, chat input closed.'
& $python scripts/rift-experiment.py --config $config stop
& $python scripts/rift-experiment.py --config $config recover
```

The configuration follows V1 `game_session.py`: exact VMX, receiver observation
path/source IP, expected guest machine, game path/build SHA, frame probe, and
existing visual profile. Keep it under ignored `artifacts/`; the runner hashes
the exact bytes it parses. The current lab example is local evidence, not a
portable installation default. The GuestObserver and receiver must already be
running with fresh foreground game observations.

The only keys are `w/a/s/d`, with holds of 20–250 ms. A plan binds the config,
VM process/start/log epoch, game process/start/path/build/window, receiver and
observer instances, and a fresh reviewed screenshot. Existing experiment
directories are never reused. Frame/guest freshness and identity are checked
again before input. Visual indicators supplement explicit screenshot review;
native text-entry state is unknown.

`stop` persists a latch without waiting for the input mutex. The runner checks
it before input and polls it during the pulse; key release is attempted in
`finally`. `recover` uses the original tool's pending-release recovery, which
does not send to a changed VM identity. A new `prepare` clears a stop latch;
pending releases must first be recovered. Hard process termination, VM failure,
or transport loss can prevent delivery of key-up. A sent release is transport
evidence, not proof of the game's key state.

Outputs under `artifacts/experiments/` contain plans, reviewed screenshots,
single-use run directories, `result.json`, and V1 companion artifacts. In
particular, `input.json` retains low-level attempt/release evidence even when
the V1 call fails after input and the top-level pulse result is unavailable.
Reports retain source hashes, identity checks, raw receipts, cancellation and
recovery results. Never infer field qualification from a completed run.

Stimuli use host monotonic time and UTC; addon observations retain their source
clock, guest acquisition UTC, and host receipt time. The after-sample must
advance and start acquisition after release by UTC. Cross-machine clock skew
is unmeasured, so this is coarse before/after evidence, not precise latency or
velocity measurement. Current reference coordinates come from V1 ReaderBridge
API observations; they are not native coordinate-field evidence.

See the [validation record](../validation/experiments-2026-10-19.md).
