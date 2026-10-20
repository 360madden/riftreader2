# Targeted health/resource snapshot planning

The goal is to replace repeated gigabyte-scale value scans with small,
identity-bound read-only acquisitions of **previously identified candidates**.
This is a request preparation and evidence-retention workflow, not a live
scanner or a health-field qualifier. The native reader already exists as
RiftReader2.Live snapshot-native (see [memory discovery](memory-discovery.md)).

## Prepare from saved evidence

The host-side script is scripts/plan-targeted-health-snapshot.py (Python
3.14, standard library only). It loads one completed health-scanning field-lab
report, the matching two-epoch marker-layout review, and a **fresh**
GuestObserver host receipt. It reuses the strict retained-report parser and
the exact SHA-256 hashes of recorded hit contexts. The receipt must be
no more than four seconds old when the plan is generated, with advancing
typed Lua, exactly one RIFT process, and the identical PID, process-creation
ticks, executable SHA-256 and player identity recorded in the saved source.

In PowerShell from C:\work\riftreader2:

    python scripts/plan-targeted-health-snapshot.py --health-report artifacts/field-discovery/runs/NEW_EPOCH_RUN/report.json --cross-epoch-review artifacts/field-discovery/health-cross-epoch-shapes-20261019.json --receipt artifacts/field-discovery/receiver/latest.json --root-rva 0x32E0200 --level-hint 45 --request-out artifacts/field-discovery/targeted-01.request.json --manifest-out artifacts/field-discovery/targeted-01.manifest.json --receipt-out artifacts/field-discovery/targeted-01.receipt.json

Use **new** output names. All three outputs must be in one existing
directory and absent; they are published with same-directory, no-overwrite
hard links and best-effort rollback if a publication operation fails.
No automatic retries, overwrites, process memory reads, game input, or
network actions occur in this host script.

Only the single validated layout replicated in the two historical process
epochs is eligible. Up to 16 groups can be selected (default 8); each
requests exactly 80 bytes from first_health_hit-16 through
first_health_hit+63. Candidate selection and range order are
deterministic. The manifest pins the raw health report SHA-256, saved
cross-epoch review SHA-256, the exact copied receiver receipt SHA-256,
observed Lua references, old source references, expected byte hashes and
marker offsets, and the exact target identity.

The generated request JSON uses the existing contract
native-memory-snapshot-request/1. To acquire real data, run the current
published RiftReader2.Live.exe snapshot-native in the **RIFT guest** using
the request and a fresh, absent output name. Its Windows reader rejects a
stale PID/start/build; it does not rediscover or rebase stale heap addresses.
Preserve native return status, raw chunks, error/partial status, exact output
SHA-256, and fresh typed Lua before and after acquisition. Ranges can become
unreadable during a process epoch. Do **not** interpret failed reads as zero.

## What matching values cannot prove

The source Oct 19 reports found five repeated health+power+level marker
layouts in the current game epoch. These are plausible **copies**, not a
unique health pointer path. Lua health equaled maximum and raw power was
100 both before and after the searches. Re-reading these windows at unchanged
values establishes neither current versus maximum health nor native resource
meaning. Qualification needs observed changes, repeated targeted comparisons,
contradiction checks, and a locating method that survives process restarts.
The old absolute addresses must be discarded if RIFT restarts.

See the [targeted-plan validation record](../validation/targeted-health-snapshot-plan-2026-10-19.md)
for the exact generated request, test counts, VM optical-disc limitation and
restoration evidence. The disposable guest ISO and an **unexecuted** PowerShell
lab runner remain under ignored artifacts/field-discovery/targeted-snapshot/;
they are not validated runtime deployment components.

When genuine guest snapshot reports become available, the existing .NET CLI
can now [audit individual targeted windows and compare two changed-state
audits](targeted-health-audit.md). This analysis reuses the strict native
snapshot loader, retains process/receipt hashes and missing-byte coverage,
and does not automatically qualify cached or replicated fields.
