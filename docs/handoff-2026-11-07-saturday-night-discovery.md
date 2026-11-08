# Saturday-night RR2 discovery — November 7, 2026

Authoritative checkout: `C:\work\riftreader2` on **AMD-DESKTOP**, branch
`codex/modular-foundation`. LEGION is a separate laptop, not this checkout.
This continues the earlier 17:26 EST discovery close; it does not resume any
old timed job or grant a new RRE lab window.

## Verified outcomes

| Capability | Live evidence | Qualification |
| --- | --- | --- |
| Player-context CLI values | Lab1 PID6820, level raw41, combat raw0/false, target getter zero/null; acquisition 7.771 ms | Raw candidates; no changed-state/API/restart proof |
| Native stats | Lab1 20 typed selectors, 40 ordinary/unbuffed raw values | One current-process capture; semantics/freshness unqualified |
| Buff grouping input `signed DWORD[state+0x80]` | Lab1 28/28 readable, all +1; Lab2 24/24 readable, 21 +1 and 3 zero | Raw grouping input only, NOT stack or List result |

All captures checked process start and exact game SHA
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
Lab1 PID6820/start639296903905448486; Lab2 PID10612/start639296904548843022.
These are capture identities and must be reacquired, not reused as future locators.

Source receipts:
- `artifacts/native-player-context-20261107/runs/lab1/af0aded499db4368947aa4090836c17b/samples.json`, SHA `476EBCAC9CA63AB0CC2388C42B55A0B9C7A63BCE4014B1453CA4102B3A08BA38`
- `artifacts/native-current-stats-20261107/runs/lab1/6ddf27ca482f412bbbabee782a734d73/samples.json`, SHA `A987B7E120E33F48E4B6B42E58B7DDA6365CC3013CFC3BB4CF4F5D3637353E6C`
- `artifacts/native-buff-state80-20261107/runs/lab1/5f8c4839eff34d0b89e37a284be44d3a/samples.json`, SHA `A13AC29264010536AE370E9FA43A2FE70670421A51E0B059445837413D8B2A77`
- `artifacts/native-buff-state80-20261107/runs/lab2/ce0a661fc5d947ad886ee378dab10f5b/samples.json`, SHA `1E5224EBEC44A567E5CCCACC77B7C6107892271DAA22DA00143961EC4CAE2A0A`

## Implemented and checked

- `scripts/sample_current_native_player_context.py` now emits a limited
  `values` JSON projection. It retains candidate/status markers, process
  provenance, and lossless string target IDs; no raw pointer fields are promoted.
  Two focused Python tests passed; Lab1 live command exited0.
- `CurrentBuildBuffSeedCandidateReader.cs` now reads and anchors signed
  `stateDword80` independently of existing `stateDword88`/timing paths.
  It supplies `raw-candidate`, `null`, or `unavailable` rather than zero defaults.
  C# focused suite: **19/19** passed.
- `scripts/sample_current_native_buff_seeds.py` validates signed input and
  preserves old reports lacking these new fields. It pins the new executable,
  size **117741408**, SHA
  `A70BD1259DAEC131898C638D3D4D540086C6195015AFA33BA262E5CA9CEE8B04`
  at `artifacts/native-buff-state80-20261107/publish/RiftReader2.Live.exe`.
  Both labs acquired and validated a fresh report.
- An independent review caught a downstream import regression before commit.
  `sample_current_native_buff_definitions.py` now selects separately pinned
  legacy seed, new signed-input seed, or timing reader according to source SHA.
  Historical source compatibility is preserved; **7/7** focused Python buff
  validation/reader-selection tests passed. This is not live acceptance of
  the buff-definitions workflow with the new seed.

No gameplay input, addon reload, game/VM restart, controller start, RRE source
change, debugger, injection, or game-memory write occurred. The native reader
was staged in each guest as needed; first-run transfers took longer because
`guestReaderReused=false`. Workbridge reported zero running jobs at the close
check. No broad test-suite claim or GitHub push is made by this record.

## Discovery boundaries and next useful steps

1. Derive independent native buff groups from the same **ordered, admitted**
   rows using existing visibility gates and this `state+0x80` input.
   Group key: signed `Dword08` plus unsigned discriminator: `Qword48` on
   typed0743 special selector; otherwise `Qword28` if signed state80 positive;
   otherwise zero. First admitted group row chooses representative.
   Unknown admission or missing keys => unavailable; do not silently drop rows.
2. Stack sentinel `AB9AACF9` is not zero or one. Do not consume API-owned
   scratch tree `2F62CA8`; only an independently proved admitted-group
   aggregate can support a future fallback.
3. Equipment-range route is typed0274 -> mapping026E -> resident0280,
   **not** adjacent type037D. Exact Stage-A selector, loaded field0 mapped
   key and final0280 object binding remain unknown; implement raw seed before
   any numeric range projection.
4. Energy variant candidates `15/100` (Razorbeast) and `15/40`
   (Cadence) are distinct. Historical API matches do not select a live
   winner. Preserve child order and explicit unavailable states.

Continue under current AGENTS.md: root alone owns live input, serialize shared
lab/heavy jobs, preserve exact-build/epoch/STOP/release boundaries and RRE repo
ownership. Full-game restart and changed-state qualification remain pending.

