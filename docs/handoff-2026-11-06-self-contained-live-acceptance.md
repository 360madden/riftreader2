# Handoff: self-contained Lab 1 live acceptance — 2026-11-06

Joey requested this handoff and a stop while the first live acceptance was in
progress. **Do not continue the live operation until he asks to resume.** Work
in `C:\work\riftreader2`; read `AGENTS.md`, `docs/status.md`, and
`docs/reference/self-contained-api-reference.md` first. Preserve the existing
substantial uncommitted Mana/casting work and the Git index; do not reset, clean,
or commit unrelated changes. The last checked index SHA-256 was
`4B2C8E46873DD7C27931CCDAE5DB783D29156D877D5C5764BAF3DDAD44B4238E`.

## User decisions

- Joey authorized a Lab-1-only backup, RiftReader2 addon sync, disabling
  RiftReaderApiProbe, **one** `/reloadui`, nonce binding, and bounded read-only
  live acceptance, preserving other addons and existing work.
- Lab 1 and Lab 2 were found to have the same OneDrive account fingerprint and
  the same addon path. Joey expressly approved proceeding despite possible later
  propagation, then clarified that propagation to the other lab is **desired**
  so both labs are near identical for testing. He noted OneDrive updates can be
  very delayed. Do not claim propagation without independent verification.
- His authorization for a reload and nonce binding was specifically for Lab 1;
  no Lab 2 reload or game input has been authorized by this exchange. His final
  instruction was to create this handoff and stop.

## Completed before stop

1. Revalidated all seven reviewed source-addon hashes against
   `artifacts/validation/rr2-selfcontained-20261106-review.json`. Published
   reader SHA-256 was
   `1A97D39BB0769E450B80E9EE0D802447713195AA682C0858CEB6F96F114319F6`.
2. Lab 1 doctor was ready. The controller reported connected, ready, disarmed,
   idle, no inputs down, and RIFT foreground. Its observed game identity was
   PID `7164`, start ticks `639294897866244204`, executable SHA-256
   `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
   VM PID was `48444`. **These are historical observations; reacquire them.**
3. Created and hash-verified a Lab 1 local backup of all six preexisting RR2
   addon files and the old probe manifest at
   `C:\Users\mrkoo\AppData\Local\RiftReader2\acceptance-backups\5122637e63c04a39af410b01bf1d2b00`.
   Host receipt:
   `artifacts/validation/rr2-lab1-addon-backup-8a23ae43/backup.json`.
4. Ran `scripts/addon_sync.py sync --target lab1`. Result: success, all seven
   installed RR2 source hashes matched; `RiftAddon.toc`, `reference.lua`,
   `live.lua`, and `main.lua` changed. The sync script retained its own backups.
   Receipt: `artifacts/addon-sync/20261106T151221Z-d302b8a2/lab1-result.json`.
5. In Lab 1, moved only the old addon's `RiftAddon.toc` to
   `C:\Users\mrkoo\OneDrive\Documents\RIFT\Interface\AddOns\RiftReaderApiProbe\RiftAddon.toc.rr2-disabled-1c7a97246555420d86a9a389d4e6da88`.
   Verified the original manifest path was absent and the renamed copy and
   independent backup both had SHA-256
   `71FF7C66626C1740B22DEA8AACFAAED20CBE1C83AF69DB73A42ADC352276269C`.
   Receipt: `artifacts/validation/rr2-lab1-disable-probe-2de09548/disable.json`.
   The disable operation was already in flight when Joey requested stop; it
   finished and its result was checked before writing this handoff.

**No `/reloadui`, nonce binding, current RR2R1 live scan, gameplay input or
live acceptance occurred.** The already running game may still have the old
probe and old RiftReader2 Lua loaded; changing files does not establish loaded
state. Lab 2 propagation has not been checked since the writes. Other addons were
not intentionally changed. Same-account OneDrive propagation can occur later.

## On resume

Reacquire VM/game PID, start ticks, build SHA, foreground and exclusive
controller/queue state; do not reuse the observations above as live state. Check
Lab 1 installed hashes and probe-manifest absence, the backup and disabled-copy
hashes, and independently check Lab 2's installed files/manifest state. Any
OneDrive delay or mismatch is evidence to report, not proof of current loaded
Lua. Inspect current addon sync and reference workflows and preserve all
unrelated addons and SavedVariables.

Joey already authorized the **one Lab 1 reload and nonce binding** described
above. Use the existing reviewed console/controller flow with fresh identity,
screenshot, exclusive ownership and verified cleanup. The prior Lab 2 GUI-bind
execution was rejected by tool safety checks before invocation; its rejected
route remains unavailable and must not be bypassed. If a required operation is
rejected or no permitted binding route is available, report the exact blocker
and preserve the current state. Do not silently change or reset controllers,
leases, VMs, or game processes.

After successful permitted reload/binding, use the current RR2 reader and a
fresh nonce to capture at least two chronological, same-player RR2R1 references
on the exact current build with the old probe disabled. Exercise strict .NET and
Python consumers and the relevant native comparison while preserving explicit
unavailable/invalid values, receipt timing and scope limits. A real game restart
requires separate authorization. Until this acceptance passes, do not claim the
old probe can safely be removed from any target or that native fields are newly
qualified. The earlier offline tests and full-gate whitespace limitation are in
`docs/validation/self-contained-api-reference-2026-11-06.md`.
