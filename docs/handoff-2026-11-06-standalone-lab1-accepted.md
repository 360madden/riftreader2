---
kind: riftreader2-restart-handoff
project: RiftReader2
repository: 'C:\work\riftreader2'
branch_at_checkpoint: codex/modular-foundation
checkpoint_date_et: 2026-11-06
priority: standalone-first
state: lab1-rr2r1-source-acceptance-passed
resume_from:
  - AGENTS.md
  - docs/status.md
  - docs/handoff-2026-11-06-standalone-lab1-accepted.md
  - docs/validation/self-contained-lab1-live-acceptance-2026-11-06.md
  - docs/reference/self-contained-api-reference.md
input_replay: forbidden-unless-newly-requested
remote_push: not-performed-in-this-checkpoint
---

# HANDOFF — standalone RR2 runtime, Lab 1 source accepted (Nov 6, 2026)

**This supersedes the PRE-RELOAD operational state** in
[the earlier Nov 6 handoff](handoff-2026-11-06-self-contained-live-acceptance.md).
Keep the earlier handoff as a chronological historical receipt, but **DO NOT**
use its "no reload/bind" statement as current state. Joey clarified that the
attempted game interaction **worked** and that a delayed "try again" message
must **NOT** cause another attempt.

## Objective and decisions

- **Standalone first.** Remove all operational reliance on the old
  `C:\rift modding\RiftReader` checkout and legacy `RiftReaderApiProbe`.
  Both remain read-only references and historical replay sources; copying
  relevant implementation ideas selectively is acceptable, but do not rewrite
  their repositories or destroy retained evidence.
- Defer broader game-memory discovery while completing/verifying the standalone
  runtime. RR2's hybrid Lua, .NET, Python, controller, and receiver code own their
  runtime operations; strict `RR2R1` nonce selection must never silently fall
  back to `RRAPIVAL2`.
- Record coherent checkpoints with **timely safe local commits**. At each
  meaningful boundary refresh `docs/status.md` and, when a session can pause
  or a target changes, a durable handoff. Preserve unrelated user edits.
- **No more retry** of the already completed Lab 1 `/reloadui` or
  `/rr2guide bind`. A new explicit request and a fresh reviewed input gate
  would be needed for any further game action.

## Exact completed milestones

| Item | Evidence and scope |
| --- | --- |
| Workbridge | `0.16.4-dev` ready, `C:\work` root, 36 command/coordination slots. This is **not** 36 reasoning agents. |
| Git code | `f034fc47a48bd586df06f8fbd111c710a56c8524`: live XYZ wrapper now requires a valid `RR2R1` nonce / marker, no implicit legacy protocol. 30/30 Windows focused tests passed, py_compile passed. The workflow still has an **obsolete native movement profile**; do not use for live movement. |
| Git evidence | `e5b103f146e292f85b7f0d06475dd1905b4cc6a0`: records Lab 1 self-contained live acceptance and limitations. |
| Addon deployment | RR2 package 0.2.0, seven source files verified on physical, Lab 1, Lab 2 installations by `python scripts/addon_sync.py check --target all`. Installed file parity is **not** loaded-addon acceptance. |
| Legacy probe | `RiftReaderApiProbe/RiftAddon.toc` absent on both VM disk paths. Disabled-copy source hash `71FF7C66626C1740B22DEA8AACFAAED20CBE1C83AF69DB73A42ADC352276269C`. Do not delete old sources/evidence. |
| Reviewed Lab 1 input | Exactly **one** `/reloadui` at 2026-11-06T23:42:47Z (UI loading at 46% observed); exactly **one** `/rr2guide bind lab1 ...` at 23:49:05Z (chat acknowledged `Bound lab1; manual feedback only.`). Input released; controller restored connected/ready/exclusive/disarmed/idle, no sampled keys down. **No game/VM restart**. |
| Own reader/reference | Current RR2 `RiftReader2.Live.exe` SHA `1A97D39BB0769E450B80E9EE0D802447713195AA682C0858CEB6F96F114319F6`, 117,270,368 bytes. Two native-memory captures of RR2-produced `RR2R1|` frames, eight verified snapshots each. Strict .NET cross-run assessment **64/64 advanced** within the 15 s pairing window (source sequence **413 to 431**, same nonce/player/epoch). Python Mana 3980/3980; Power explicitly unavailable. |
| Receiver host services | On-demand RR2-owned receiver preflight `scripts/ensure_receiver.py --lab all` started host receivers and immediate second call **reused** them. Lab 1 PID **13208**, endpoint `192.168.56.1:49813`; Lab 2 PID **49220**, endpoint `192.168.56.1:49923`. These PIDs are **checkpoint-time only**; independently reacquire later. `feedFreshness: not-verified` for **both** receivers, despite separate Lab 1 RR2R1 capture PASS. |

**Lab 1 live identity at acceptance (historical, reacquire):**
RIFT PID `11672`, process start ticks `639296016581575957`;
`rift_x64.exe` SHA `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`;
VM PID `48444`, VNC port `5905`. The bound nonce is a past
session observation, **not** a reusable challenge for new experiments.

**Retained source-hashed evidence:**

- `docs/validation/self-contained-lab1-live-acceptance-2026-11-06.md`
- `artifacts/native-current-reference/runs/lab1/cc85d8178cdd4c6ba944caf23cae240d/`
- `artifacts/validation/rr2r1-lab1-live-assessment-20261106-b/summary.json`
- `artifacts/standalone-acceptance/lab1-reload-command-review-20261106-b/`
- `artifacts/standalone-acceptance/lab1-bind-rr2r1-20261106-b/`
- `artifacts/addon-sync/20261106T235511Z-622e7872/lab1-result.json`

## What is **NOT** established

1. **Not full cross-target standalone acceptance:** Lab 2 and physical PC have
   checked files, but no separately verified loaded-source `RR2R1` acceptance.
   No Lab 2 or physical input/reload/bind is authorized by this handoff.
2. **Not a live receiver feed:** Both RR2-owned host receivers are running, but
   freshness is `not-verified`. Never infer player telemetry from process
   existence, receiver reuse, or stored packets.
3. **Not full telemetry qualification:** No independent changed-state native
   HP/Mana/XYZ semantics, continuous 480 s freshness, or full RIFT process
   restart recovery was demonstrated by the two captures.
4. **Not movement readiness:** `run_xyz_workflow.py` protects `RR2R1` but still
   references an obsolete native profile and lacks certain final pre-input
   nonce gates. Do not activate it.
5. **Not a push:** This session's new commits are local. No GitHub push was
   performed by this handoff. Keep branch/remote history intact.
6. **No receiver-pin fix:** An experimental scratch/Linux branch computed the
   wrong pin for Windows line endings; **do not merge it**. The authoritative
   Windows `scripts/observation_receiver.py` already matches
   `scripts/ensure_receiver.py`'s original SHA pin.

## Recommended next batch (no game input needed)

1. **P0 — runtime dependency audit:** Search RR2 current entry points for
   runtime paths, imports, subprocesses or implicit fallbacks involving the old
   RiftReader checkout / `RRAPIVAL2` / old probe. Separate explicit historical
   replay from live use; keep the obsolete movement profile disabled.
2. **P0 — safe startup/freshness:** Review `ensure_receiver.py` and current
   launch/observation path; implement focused tests for receiver identity,
   ownership and advancing `RR2R1` feedback. Do not equate readiness with a PID.
3. **P1 — strict consumer closure:** Confirm every current CLI/script/GUI consumer
   uses RR2-owned producer and exact nonce; complete any remaining optional
   legacy-default replacement only where actually runtime-facing.
4. **P1 — offline regression:** Run targeted `RR2R1` contract/decoder/receiver
   tests plus Git diff/whitespace checks; reserve full gate for broad code changes.
5. **Later, ONLY on explicit new request:** Fresh identity/review and loaded-addon
   acceptance independently on Lab 2 and physical PC. New reader nonce required;
   no automatic replay of Lab 1 commands or any previous `/reloadui`.

**Restart instructions:** Open repo `C:\work\riftreader2`; read `AGENTS.md`,
`docs/status.md`, this handoff and latest 10 commits. Inspect `git status`,
both current receiver identities and source hashes **read-only**. Prefer
independent offline work toward standalone operation; only act on RIFT UI/game
with fresh target-specific authorization. Commit narrowly scoped verified code
and documentation checkpoints as they become significant. Update this handoff
or write the next dated one before leaving a partially resolved integration.
