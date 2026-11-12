# RR2 physical player-state offline replay — 2026-11-12

**Host:** independently verified `[Environment]::MachineName = AMD-DESKTOP`.
**Scope:** `C:\work\riftreader2` only; physical-RIFT historical evidence replay; no new process reads or game input.

## Practical result

`scripts/replay_physical_player_state.py` replays the existing composite
`collect_physical_player_state.py` receipt without accessing a live process.
It verifies all three original source SHA-256 hashes, exact process/build/module/self
owner, per-sample chronological ordering, sample counts and native candidate
projections. Vitals burst evidence must also match its pinned original source.
The optional `--after` comparison requires distinct, chronologically ordered
same-epoch receipts and returns XYZ/available health deltas as **candidates only**.
It never fills in an unavailable resource.

### Reproduction

```powershell
cd C:\work\riftreader2
C:\Python314\python.exe scripts\replay_physical_player_state.py --summary artifacts\physical-state-20261112-1117-69312\summary.json
```

- Original retained physical receipt SHA-256: `D3775E79CD374AE0C7E9B55CC84B6309B9CD489AAB35558D29B573C5880363C2`.
- Independent replay: `artifacts/physical-state-20261112-1117-69312/independent-replay.json`, SHA-256 `3551754840AB15F97289EC6A0531726252536451D4B20290051F698B02F82F49`.
- Original captured epoch: historical AMD-DESKTOP PID `69312`, ticks `639300936028818696`, executable SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`. **Not** a current-PID assertion.
- Focused `unittest` suites: **28/28 passed** (19 replay and pair cases; 9 original collector tests). Negative checks include rehashed-but-inconsistent source values, changed owner, time reversal, tampered source, mismatched burst digest, overlap and unavailable health.
- The RRE-owned discovery handoff was consumed read-only at SHA-256 `606df5b0ca7f05ea347618887f647a94c046b12c30d7a685f732e608b29a7b88`: no newly ready ROOT/TARGET/ORIENT locator imported; no RRE file edited.

**Qualification:** offline retained-source consistency only. Does not establish live freshness, atomic sampling, Lua nonce binding, target identity, movement causation or restart recovery. For RRE manager: use this result/commit as the RR2-owned verification path; prioritize genuinely new ready discovery instead of repeating static disassembly.
