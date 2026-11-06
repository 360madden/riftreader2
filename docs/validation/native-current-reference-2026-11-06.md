# Fresh current-build independent API reference — November 6, 2026

**Outcome: ADVANCING IN THE DECLARED PAIRING WINDOW.** Two fresh bounded,
read-only Lab-2 scans recovered current `RRAPIVAL2` frames from the exact game
epoch. The strict offline inspector found 15 advancing cross-run pairs out of
20. This establishes a fresh independent Lua/API reference in covered memory;
it does not qualify native player, vitals, ability, cooldown or cast fields.

## Exact acquisition

- Lab 2 retained VM identity and passed the VM-specific cached-credential/session
  preflight. RIFT remained PID `9752`, start ticks `639294897826627677`, SHA-256
  `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
- Reader SHA-256 was
  `1C89D8B29A9A3A523D6B6A32F7F0DAC4E972454B5F4C3C3BD8F3C7F803F5E3C7`.
  Each scan was bounded to 512 MiB, 30 seconds, 32,768 regions, 128 markers
  and eight copied neighborhoods, starting at `0x10000`. The runs were eight
  seconds apart. No game input, addon bind/reload, game restart or VM restart
  occurred.
- Run 1 was `partial: byte-budget-exceeded`, examined 536,870,912 bytes and
  saved five snapshots from six markers. Run 2 had the same bounded partial
  result and saved four snapshots from five markers. Their UTC intervals were
  `12:12:11.541430–12:12:12.254294` and
  `12:12:21.049233–12:12:21.842859`.
- Returned ZIP SHA-256 is
  `25108197E6575E992F80570845E06F56C4697AA7BC38CB7115C0BAD5E4D1B4D2`.
  The existing strict archive verifier checked the exact target, reader,
  requests, indexes, snapshot links and chunk bytes before publishing originals.

## Strict source result

The new offline run assessor invoked the existing `inspect-typed-wire` command
for every cross-run snapshot combination. It binds every assessed snapshot to
its run index by exact SHA-256, then applies the timing bound to the exact
selected snapshots rather than their enclosing run indexes. The selected
snapshot gap was **9.529867 s**, inside the explicitly declared **15 s**
comparison window; the run-index envelope gap was 8.794939 s and is retained
only as context. Fifteen pairs were
`advanced-in-covered-scope`; five were correctly blocked as
`source-clock-or-sequence-not-advanced` because one run-2 heap copy retained an
older frame.

The selected latest advancing pair was `capture-05-to-capture-04.json`:

| Field | Before | After |
| --- | ---: | ---: |
| Sequence | 145708 | 145727 |
| `Inspect.Time.Frame` | 74147.8359375 | 74157.421875 |
| Player unit | `u035400012DFEB5BC` | `u035400012DFEB5BC` |
| API XYZ | 7182.080078125 / 821.26995849609 / 3135.419921875 | unchanged |

The corrected `assessment-v3/summary.json` SHA-256 is
`FD27257F5CB13EA3F53A4E8C0024EEDE432F6C9A53D5E64B9A08AD0C9640EE53`.
Exact ignored evidence is under
`artifacts/native-current-reference/runs/lab2/9d2c5dc13cca4937bca0bec967b1f45a/`.

## Implementation and checks

- `scripts/capture_current_typed_reference.py` owns fresh identity, pinned-reader
  staging, two bounded scans, return SHA verification and strict archive recovery.
- `scripts/assess_typed_wire_runs.py` publishes all strict cross-pair diagnostics
  plus a no-overwrite summary with the caller-declared pairing window.
- Focused validation passed **21/21 Python** tests (new assessor plus strict
  archive verifier), **19/19 .NET** typed-wire inspector tests, Python bytecode
  compilation and historical current-build replays. Adversarial coverage proves
  a short run-index gap cannot hide an out-of-window selected snapshot pair, and
  malformed inspector schema/status/shape fails closed. The fresh retained run
  was reassessed offline without another live scan.

## Limits

Both native scans were partial by their declared byte budget. Advancing producer
sequence and source clock do not prove wall-clock synchronization, global frame
uniqueness or absence outside covered bytes. Unchanged XYZ does not establish
movement response or passive native freshness. The API player ID is not linked
to the current vitals `unitKey`; this result must not promote HP/Energy or any
Mana, ability, cooldown or cast candidate. Absolute frame addresses are valid
only for this process epoch.
