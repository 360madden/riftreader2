# Actual-client addon validation

Date: 2026-10-18 (America/New_York). Scope: bare RR2A1 producer in one RIFT-Lab
session.

Joey explicitly requested use of the original V1 loopback VNC path for this
controlled gate. The existing V1 `lab_console.py`, VM console identity checks,
and mutex behavior were reused unchanged. No V1 application code was imported
into RiftReader2.

## Identified environment

- VM configuration:
  `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`.
- Host `vmware-vmx` process: PID 51176,
  start ticks `134368480287222354`.
- VM log epoch: `2026-10-19T01:47:08.781Z`.
- Guest character: Atank, level 45, stationary in Sanctum during the retained
  frame checks.

The addon ISO was opened in the guest and four files were copied through
Explorer into
`OneDrive\Documents\RIFT\Interface\AddOns\RiftReader2`:
`RiftAddon.toc`, `wire.lua`, `producer.lua`, and `main.lua`. The guest-visible
file list was checked. Guest file hashes were not collected or verified.

## Observed live result

RiftReader2 was enabled and `/reloadui` completed. Two retained console views
show complete RR2A1 frames from addon version 0.1.0:

| Evidence | Sequence | Frame clock | Selected observation |
|---|---:|---:|---|
| Frame A (`addon-v1-frame-a.png`) | 26 | 1109.16796875 | Health and maximum health 18208; combat unavailable. |
| Frame B (`addon-v1-frame-b.png`) | 58 | 1125.2628173828125 | Health and maximum health 18208; combat unavailable. |

Screenshots are retained locally under ignored `artifacts/live-validation/`;
fresh checkouts do not require these generated captures to pass validation.

The increasing sequence and frame clock establish that the producer advanced in
this identified session. The displayed RIFT UI also showed 18208/18208 health.
The screenshots are visual evidence; no automated extraction, guest content
hash, or independent executable-build hash was produced by this gate.

## Limits and next gate

This validates actual-client package loading, event/API compatibility, reload,
and advancing bare RR2A1 publication for this one session. It does not validate
native memory, combat availability, Lua-to-.NET transport, automated process
binding, reader freshness, process restart, update survival, or RR2L1.

[ADR 0004](../decisions/0004-nonce-bound-addon-transport.md) selects the next
nonce-bound wrapper. That later gate is now complete and recorded separately in
[nonce-bound live transport validation](live-transport-2026-10-18.md); this
record remains the earlier bare-RR2A1 evidence.
