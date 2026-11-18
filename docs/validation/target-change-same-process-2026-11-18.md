# Physical RIFT 1179: changed selected-target candidate in one process

**2026-11-18, 16:38 EST · RR2 / AMD-DESKTOP.** All newly acquired data came from read-only native readers. The user may have changed the target or location independently; RR2 issued **no** gameplay input, UI reload, focus change or process-memory write.

## Scope and observed sources

The same physical RIFT client identity was retained across samples: PID **77980**, process start ticks **639305214834918403**, build SHA-256 **DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01**, module base **140696817106944**, module size **63246336**, Atank self key **239816685251645959**.

| UTC time | Source | Saved candidate |
| --- | --- | --- |
| 2026-11-18 13:40:29 | native target-name | Key **9223372039555954076**, raw fallback name **Olivia Heln** |
| 2026-11-18 21:33:58 | native selected-position burst 2/2 | Key **9223372039304260624**, target XYZ **(7450.5947, 886.3292, 3047.1370)**, stable camera candidate |
| 2026-11-18 21:34:16 | native target-name | Same new key, raw fallback name **Cabalist Elsu** |
| 2026-11-18 21:34:36 | native facing/selected projection 2/2 | Same new key and XYZ, **zero difference** at recorded precision; normalized projected screen point ~(0.55442, 0.59288) |

The old and new names are **raw template-cache fallback text**, not independently checked localized UI labels. The newer facing projection also reports a candidate body-to-target angle; body heading and occlusion are not independently qualified.

## Reproduced comparison

A bounded **offline** Python verification reopened the four retained reports through RR2's strict native JSON parser, compared all native process identity members and self key, parsed both name reports via `physical_rift._native_values("target-name", ...)`, and checked that new selected-position and facing target keys match the new name's key. It also checked that the new target XYZ agree with the facing-pair XYZ within 0.01 native units. The verifier exited **0** with `status=changed-selected-target-candidates`, `sameProcessBuildPlayer=true`, and exact XYZ difference **0.0**. Workbridge receipt: `rr2_p1_target_correlate_1637`.

Ignored retained source reports and SHA-256:

- `artifacts/physical-native-target-name-dcdbffa57acf49618501569dd978a045.json` — **3E4F6C15C6AB87EFE9CC774A0047395A2E1C3767200152D979C949CDD99E80B9**
- `artifacts/physical-native-target-name-aedb992b441241f6bf3624f18e65e8a1.json` — **9E2F19B535904F265DB6143ACA78E84552A82FB22278FF510316A59A438C9A99**
- `artifacts/physical-native-selected-position-17c09d5b702d465ebece55933528dd51.json` — **9CF87B0E92E02F8F096A276EB339BF87751EB74957C35775C628DF9A294822F4**
- `artifacts/physical-native-facing-0605e295106241c4905fcb8ca59089bb.json` — **6D4680FB65BAEC4B16D935EB2392B6F0EB8EC8E83B46E840782B6DC80386C6F2**

## Qualification boundary

**Validated:** The guarded native target key and raw name candidate **changed between two observations in the same process epoch**, and three later independent readers agreed on the newer target key (two on its XYZ). This is stronger than unchanged same-process samples and is useful for prioritizing controlled freshness tests.

**Not validated:** The actual transition time (there is a multi-hour gap), selected-target API name equivalence, an intentionally controlled A → B → A round trip, instant refresh latency, game-rendered pixel alignment, long-term durability after a full game restart, or authoritative world/zone identity. No waypoint/movement authority follows. Next: a bounded user-selected A → B → A sequence with read-only before/after receipts, plus independent Lua/API comparison when available.
