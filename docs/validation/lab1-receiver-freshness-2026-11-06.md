# Lab 1 receiver freshness — November 6, 2026

The stale guest configuration was removed through a fixed-file, content-free
cleanup helper, and a second fresh cached-credential guest session confirmed
absence with no unexpected reader. A fresh reader, one reviewed rebind and
strict receiver samples then demonstrated an advancing Lab 1 feed.

## Cleanup discrepancy and resolution

Fresh nonce-bound VMware Tools checks, native `fileExistsInGuest`, Windows
PowerShell 5 and a fresh Store PowerShell 7.6.9 child all saw the original
411-byte file. The user's interactive PowerShell saw it absent. This rules out
stale copied receipts and a simple PowerShell-version difference. Activation
or filesystem-view differences remain the likely explanation; the exact
Windows mechanism was not proven. Evidence is under ignored
`artifacts/receiver-migrations/cleanup-investigation-44c5dc92c0c94aa08c76cd2d9cd80245`
and `cleanup-ps7-8190a73f9f454011a80595a93acfcb5d`.

The earlier embedded shell cleanup had been rejected by execution review. The
narrower `scripts/cleanup_lab1_staging.py` passed execution review: it has a
fixed Lab 1 path, stable VM and cached-login checks, no active reader, no
recursive delete, no content reads, path/reparse/length checks and exclusive
native-handle deletion only after validation. It does not send game input.
`lab1-fixed-cleanup-20261106/summary.json` recorded deletion; the second
`lab1-fixed-cleanup-verify-20261106/summary.json` recorded already absent.
Both are under `artifacts/receiver-migrations/`. Cleanup code: `c6eb446`.

## Live result

- Exact game PID 11672, start ticks `639296016581575957`, SHA256
  `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
- Reader PID 7108, start ticks `639296120990298738`, SHA256
  `662E4E6CC546E9BF0592CC7D647261F4B781152E6FF1106D154DCEE5B62ED538`;
  nonce `fc54b8ac1a0d43369449feee88752189`. The reader is bounded to expire
  at 2026-11-07 01:49:59 UTC (November 6, 8:49:59 PM Eastern).
- Receiver PID 5840/start `639296090706474389`; exact receiver, reader,
  VM/game, source and nonce pins passed the existing strict feedback gate.
- The managed controller completed verified STOP/shutdown before console
  ownership. One separately reviewed open-chat operation and exactly one
  `/rr2guide rebind lab1` with the new nonce completed. The after-screen
  acknowledged `Rebound lab1; waiting for the new reader.` Both execution
  receipts confirmed release. No reload, movement, casting or Lab 2 input.
- The successful collection accepted **12 samples across 8.934671 seconds**:
  outer sequence **236→247**, addon sequence **13664→13682**, source clock
  **10706.1357421875→10715.3857421875**, same player
  `u035400012FA2D678` and addon epoch 1. This collection selected
  `whole-readable-private` source scope and had zero transient read failures.
  An earlier collection stopped at `live-receipt-unavailable` and was retained
  separately; no gate was relaxed. A new bounded collection succeeded.
- Independent replay checked all retained raw receipt hashes and strict
  sequence/clock/capture advancement. Summary SHA256:
  `8D062AA5DF2342CD467A9DA816146E2CD66B969495384B499C0F203BE85887F2`.
- Controller restored as PID 64320, generation
  `d3f5021244604dba97e0214310e5ab16`; standard managed receipt/source checks
  passed. It was connected/ready, initial cleanup verified, disarmed/idle,
  no sampled held inputs, exclusive console reservation, zero in-flight work.
  Queue generation 5210 was unblocked/unheld with no pending requests.

Evidence root: `artifacts/receiver-migrations/`. Reader launch is
`lab1-freshness-reader-20261106-b`; shutdown is `lab1-console-handoff-b`;
reviewed input is `lab1-chat-prep-d` and `lab1-rebind-prep-b`; pin is
`lab1-current-feed-pin.json`; successful samples and replay are
`lab1-feed-advancement-b/summary.json` and `independent-verification.json`.

## Checks and limits

`python -m unittest tests.test_cleanup_lab1_staging tests.test_movement_feedback tests.test_addon_command_console -q`
passed **89 tests** (exit 0). Independent source review found no blocking issue
in the bounded cleanup. The full repository gate was not repeated for this
small helper/live-evidence slice; other development was active concurrently.

This is observed short-window advancing regular receiver telemetry. It does
not establish 480-second qualification, full-game restart recovery, native
field semantics or a separate RR2R1 typed-reference assessment. The bounded
reader's expiry ends this run; do not call its later cached packets fresh or
reuse its nonce. Lab 2 freshness remains unverified. Reacquire every identity
and honor the existing owner and STOP/release gates for future work.
