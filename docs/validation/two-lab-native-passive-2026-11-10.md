# Two-lab native retrieval and stationary comparison — 2026-11-10

**Scope:** Live RIFT sessions on verified **AMD-DESKTOP**, RR2 branch `codex/modular-foundation`. No movement/turning input was sent during this validation. Both RIFT instances were restarted and logged in by Joey before the checks. Current build SHA256: `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.

## Results

| Independent target | Lab 1 | Lab 2 |
| --- | --- | --- |
| RIFT process PID / start UTC ticks | `10212` / `639299232170344957` | `7956` / `639299232410008447` |
| VMware PID | `54080` | `41676` |
| Managed agent instance | `7c96cf40a89a48aaa8dd4946ad6d0703` | `b41c2781ec0e467390fb417e84c602a9` |
| Live XYZ candidate (X, Y, Z) | (7324.007, 874.2586, 3050.951) | (6984.172, 845.1351, 3280.5132) |
| Current HP/resource candidates | HP 9010/9010; mana 3980/3980; energy unavailable | HP 10635/10635; energy 100/100; mana unavailable |
| Actor planar-angle candidate | 89.36176375° | 110.97544695° |
| Two new samples | 18:57:21.347–18:57:41.435 UTC | 18:57:23.075–18:57:43.153 UTC |
| Horizontal displacement / actor matrix change / scalar-field changes | 0 / 0 / 0 | 0 / 0 / 0 |

Each lab successfully retrieved separately source-hashed native XYZ, actor-pose and smoothed-scalar reports. The saved pairs passed the existing **same-game, same-VM, same-agent, same-player, advancing-timestamp** offline comparator against their *actual* retained reports. The differing readout SHA256s rule out identical readout-file reuse; they do **not** establish that underlying candidate memory is passively fresh.

**Exact readouts**, ignored by Git and preserved on AMD-DESKTOP:
- `artifacts/rr2-lab1-passive-before-20261110-1411.json` SHA256 `13591C5B25199F68E259F6C469BD3F96B4119FBDBD6120971858AF8BABFEC43D`; `artifacts/rr2-lab1-passive-after-20261110-1411.json` SHA256 `C6A543C8198B836006414FDCDA90A8361BB2B3A799764DC977AFA5EBC4504617`.
- `artifacts/rr2-lab2-passive-before-20261110-1411.json` SHA256 `FCDADE4243CD3D6C2A55D2E51C7BF7D860E62A8AB64F1949408320DB58A61FFE`; `artifacts/rr2-lab2-passive-after-20261110-1411.json` SHA256 `FCDAD3CB10516EF92469FA908EA0F4BB5D80210AF38311FA0DE4E183575CCA96`.

## Live operational evidence

- Capture-only `observe_target.py` passed in both labs with current RIFT process/window identity, source screenshot SHA, and verified cleanup; Lab 1 ~5.4 s, Lab 2 ~4.7 s. These are capture transport results, not live screenshot approval for future input.
- RR2 addon installation `addon_sync.py check --target all` passed for host, Lab 1, and Lab 2 without file changes.
- Host Lab 1 receiver started, Lab 2 receiver reused. A SHA-pinned **Lab 1 bounded 600-second reader** started, with PID 11612, nonce `ea37b82053c94102ba5c55ed662ff724`, scheduled expiration **18:51:56 UTC**. Its new receiver frames advanced (observed sequence 138), but the addon was **unbound**; no fresh addon-scoped player XYZ was claimed. Lab 2 had no newly launched reader in this validation.
- The Lab 1 LuaPad close control was visually identified from a new screenshot crop at source coordinates (454,141), but the reviewed input plans expired before authorization; **no click/key/input was sent**. No review deadline was extended. `desktop_capture_vmware_host` separately returned `DESKTOP_TREE_UNSETTLED`; the quarantine was not cleared.
- Lab 1 managed controller was gracefully handed off and restored; final authenticated postflight: connected, ready, disarmed, zero keys down, no recovery required, same game identity. Lab 2 remained on its separately verified ready/disarmed controller.

**Next practical trial:** Prefer Lab 2 for a fresh, timely screenshot-reviewed addon bind; its saved screen has less obstructive UI than Lab 1. If current input review cannot be completed within the unchanged gate, stay read-only. Then obtain one controlled turn with independently advancing addon XYZ and candidate actor-pose before/after; body-facing semantics and general navigation remain unqualified. Never reuse expired nonces or reviews.
