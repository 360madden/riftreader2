# Self-contained API reference migration

RiftReader2 now owns the offline implementation of the player API reference
previously obtained from RiftReaderApiProbe. **Lab 1 installed-addon and live
RR2R1 acceptance passed on November 6; Lab 2 and physical RIFT loaded-addon
acceptance remain pending.** See the [Lab 1 evidence and limits](../validation/self-contained-lab1-live-acceptance-2026-11-06.md).
This implements Joey's November 6 decision that
current tools and applications use RiftReader2 rather than the older checkout.
Native telemetry remains the intended primary source when qualified; API
observations are independently labeled validation references or fallbacks.

## Contract and consumer audit

The package adds [RR2R1](../../contracts/addon/reference-v1.md), without changing
RR2A1's six-field observation or RR2L1's wrapper. RR2R1 uses the same reader nonce
and adds its own schema, sequence and clock epoch. Source clock and player lookup
bracket `Inspect.Unit.Detail`; absent/invalid values stay explicit. Reload clears
binding. Rebind clears the old reference; epoch and player changes clear retained
frames. The nonce is a load/session challenge, not authentication or a build ID.

| Current consumer | Required observation/evidence | Migration |
| --- | --- | --- |
| Prefix scout, immediate neighborhood and inline snapshot capture | Exact marker, private readable region coverage, bounded acquisition, request/bundle hashes, PID/start/build identity before/after | Allowlisted request `marker: "RR2R1|"`; captured manifest records marker. Legacy omitted marker is retained for historical compatibility. |
| `inspect-typed-wire` | Two distinct chronological snapshots, same PID/start/build, expected nonce, same player and clock epoch, advancing sequence and source clock, explicit XYZ states, conflict/malformed detection | `--session-id` selects RR2R1 exclusively; reports retain protocol, addon, nonce, epoch, all fields and source hashes. Omission selects historical RRAPIVAL2 only. |
| `inspect_typed_resource.py` | Strict schema and chunk hashes, expected nonce, player/epoch, typed Mana/ManaMax or Power with explicit unavailable/invalid states | `--session-id` selects RR2R1; omitted nonce is historical replay. |
| Current two-run capture, run assessment and Mana comparison | Exact reader/request/archive closure, selected snapshot timing, same process/player/nonce/epoch across phases, advancement and declared comparison window | Capture requires a reviewed reader hash and nonce and requests RR2R1. Assessors propagate and validate the binding. No legacy runtime fallback. |
| `plan_typed_scout_snapshots.py` | Report marker and bounded candidate ranges | Understands both allowlisted markers; does not promote prefixes into observations. |
| `host_trial_typed_inline_archive.ps1` | Published reader hash, exact own-process marker bytes, two capture manifests and archive closure | Defaults to RR2R1, requires an explicit reader SHA, forwards the selected marker to archive verification. Synthetic capture only. |
| Managed receiver and reader launcher | Source-hashed ownership receipt, lab-specific private config, delivery receipt time, independent host readiness validation | RR2-owned `scripts/observation_receiver.py`; launcher defaults to `.local/two-lab-movement/<lab>-receiver.json`. An existing old receiver fails the ownership check. |
| Old `rift-experiment.py` adapter | Previously imported V1 console/game/readback code | Retired with an explicit pointer to the RR2 controller workflow. It sends no input. |

The 15 player fields are numeric `coordX`, `coordY`, `coordZ`, `health`,
`healthMax`, `mana`, `manaMax`, `power`, `combo`, `planar`, `planarMax`; boolean
`combat`, `dead`, `mounted`; and string `zone`. Current reference consumers do
not use the old target record, text-entry placeholder or autonomous-input flag.
No ability readiness, costs, effective target, facing or LOS is inferred from
this wire. The separate unfinished casting work remains separate.

The old `validation.lua` was read to identify its API names and field types.
A bounded search of the older checkout found no LICENSE/COPYING file establishing
reuse permission. No legacy implementation was copied; the reference producer
and receiver were implemented in RR2. Historical source paths in saved evidence
remain provenance and are not rewritten or treated as current dependencies.

## Offline use

Build the current CLI/reader, retain its SHA-256, and use a newly bound reader
nonce. The capture wrapper does not bind the addon or send game input:

```powershell
python scripts/capture_current_typed_reference.py --lab lab1 --reader PATH_TO_REVIEWED_RR2_READER --reader-sha256 SHA256 --session-id NONCE
python scripts/assess_typed_wire_runs.py --before-run RUN_01 --after-run RUN_02 --cli src/RiftReader2.Cli/bin/Release/net10.0/RiftReader2.Cli.dll --maximum-run-gap-seconds 15 --session-id NONCE --output NEW_OUTPUT
python scripts/inspect_typed_resource.py --snapshot SNAPSHOT --resource mana --session-id NONCE --output NEW_REPORT
```

The previous cached reader hash is a historical binary, not accepted for RR2R1
capture. Its wrapper routes an explicitly supplied reviewed current reader
through the staged acquisition path. Capture success returns original bytes;
it does not establish field qualification or current loaded addon source.
Two advancing snapshots prove advancement in covered scope, not global uniqueness
or wall-clock freshness. Apply receipt timing and a declared pairing window;
never equate the game frame clock to host UTC.

## Installed acceptance and removal boundary

No installed addon, service, private configuration, VM or RIFT process was changed
by this migration. The reviewable addon candidate is exactly seven files under
`addon/RiftReader2`: `RiftAddon.toc`, `wire.lua`, `producer.lua`, `reference.lua`,
`live.lua`, `guidance.lua`, `main.lua`, with package version 0.2.0.

The next requested authorization is a **Lab-1-only** backup-first synchronization
of those seven files to `C:\Users\mrkoo\OneDrive\Documents\RIFT\Interface\AddOns\RiftReader2`,
disabling RiftReaderApiProbe in that lab, and one separately reviewed `/reloadui`.
Any nonce entry uses a permitted reviewed route; prior rejected input routes
remain unavailable. This note is a concrete proposal, not authorization to act.
Other addons, especially RRECollector, remain under their owners' control.

After authorization, retain exact installed hashes, prove the old probe is
disabled, acquire fresh PID/start/build and reader nonce, and demonstrate two
chronological same-player RR2R1 acquisitions with advancing sequence/time.
Run strict inspection and the relevant Mana/Power/native comparisons on those
RR2-only bytes, with explicit limits. Verify reload clears old binding and
restart invalidates old process evidence; a real game restart requires its own
authorization and is not implied by a UI reload.

**RiftReaderApiProbe can safely be removed from a target only after that target
passes these disabled-probe acceptance checks and its consumers use RR2R1.**
Removing it from every installation requires acceptance on each installation.
The old source checkout can be archived after current receiver ownership/config
has been migrated and no current entry point resolves its source path; retained
historical evidence may still require its saved files for explicit historical
replay. Do not delete historical evidence as part of this migration.
