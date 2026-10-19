# Native player fields: partial discovery and handoff

Recorded 2026-10-19. Joey requested native position and health/resource
discovery using Lua as reference, including ordinary game restart validation,
then requested a handoff during the first live pass. That discovery request
remains authorized and incomplete. No native gameplay field was promoted.

## What was actually observed

One read-only capture completed at 05:45:07–05:45:09 UTC. It used the existing
`WindowsNativeMemorySession`, exact process epoch/build checks, raw bytes, and
fresh typed Lua observations before and after acquisition. The bounded walk
attempted 64 objects at depth at most three; its queue was truncated. It is a
partial player-linked neighborhood, not a complete scan of the process.

| Item | Evidence |
|---|---|
| Executable SHA-256 | `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD` |
| Guest | `DESKTOP-8632QPL`; `C:\RIFT_TRANSFER\RIFT\rift_x64.exe` |
| RIFT process | PID `11620`; start `2026-10-19T04:35:29.3755454Z`; UTC ticks `639279813293755454` |
| Main module | `0x7FF6B6EE0000`; size `62611456` |
| Player | `u035400012FA2D207` |
| Observer | `3e945dd0-d4e2-424c-b97e-ae074ed93bb4` |
| VM | `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`; host PID `54820`; start FILETIME `134368524235244532` |
| Capture | `f4515ac11b6943b98e33402aa176fd24` |

Typed Lua sequence advanced `8219 -> 8226` in observer generation `4`, with the
same process and player identity across the capture.

The candidate root `[rift_x64+0x32E0200]` resolved to owner `0x216ECFE06A0`.
That heap address is session evidence only. The float32 values were:

| Owner offset | Native | Typed Lua |
|---|---:|---:|
| `0x320` | 7297.3583984375 | 7297.3598632812 |
| `0x324` | 876.28692626953125 | 876.28997802734 |
| `0x328` | 3054.29248046875 | 3054.2900390625 |

This is stationary agreement within 0.004, not displacement or restart proof.
The historical health seeds `owner+0x298`, `+0x2A0`, and `+0x2A8` returned int32
`6619244`, `64`, and `114`, respectively; none matched Lua health `18208`.
The historical level seed `+0x290` also failed. Do not reuse those old offsets.

Offline analysis of 53 successful retained windows found zero exact health
`18208` matches as aligned int32, float32, or float64. Power `100` produced 15
int32 hits at seven unique addresses, mostly text or structural constants;
there were no float32/float64 matches. One weak follow-up path is
`owner -> [owner+0x3F8] -> [registry+0x2A0] + 0x3B0`, with alias through
`registry+0x2A8` and final offset `0x398`. Nearby repeating 104/100/108 records
suggest identifiers, so this is not a resource field. The truncated capture
does not establish absence of health/resource fields elsewhere.

The typed reference is `RiftReaderApiProbe` 0.6.0 / `RRAPIVAL2`, acquired through
the unchanged V1 GuestObserver. It reported health/max `18208/18208`, raw
power `100`, combo `0`, planar `1`, and planarMax `3`. Mana/max, combat, dead,
and mounted were unavailable. Unavailable is not zero or false. There is no
observed power maximum; ReaderBridge's synthesized resourceMax=100 is not an
oracle. Installed typed-addon source files were not hash-verified in this pass.

One supervised `w` pulse of 100 ms completed at approximately 05:46:20 UTC:
experiment `51119cca3e6b4c1e97121c075a4b6895`. Its retained `input.json` records
`releaseSent=true`; controller state has no pending release. ReaderBridge API
coordinates changed from `(7297.359863,876.289978,3054.290039)` to
`(7296.399902,876.320007,3054.379883)`. No native read was captured after this
pulse. This is API/input evidence only. No health/resource variation or game
restart was attempted before the handoff request.

## Retained local evidence

All paths below are relative to `C:\work\riftreader2\artifacts\field-discovery`.
They are ignored local evidence, not files available from a fresh Git clone.

- `runs/f4515ac11b6943b98e33402aa176fd24/report.json`: raw reads, pointer paths,
  identities, before/after typed Lua, source/tool hashes and truncation.
  SHA-256 `BDE8C8E127BB2A7D8694A7F112A4B81A3684D13E4A4A4836D2225761B9A3F428`.
- Its sibling `receipt.json`: host delivery, compressed report and hash/length
  binding. The watcher verified decompression, length and SHA before saving.
- `harness/Program.cs`, `harness/FieldLab.csproj`: finite disposable capture
  helper. Source SHA-256
  `88AC0268B6E7D4F18F377D382CC7F58FD27549F39B8DCBD76CE700EFE4096660`.
- `media/RiftReader2.FieldLab.exe`: actual successful capture executable,
  SHA-256 `EDC47203B3819CD55575906982429E88BE4C90109A7F03F1EB0EBBFC8B2DBF23`.
- `media/plan.json`: exact build/root; `build-media.py`, `rr2-fields.iso` and
  `media-receipt.json`: byte-verified delivery media. Delivery credentials remain
  private under ignored artifacts; never copy them into tracked files or chat.
- `experiments/runs/51119cca3e6b4c1e97121c075a4b6895/`: result, input release,
  fresh API receipts, identity checks and reviewed screenshots.
- `baseline-reference.json`, `final-receipt.json`, `config.json`,
  `guest-console.py`, `watch.py`: local resumption aids. Saved receipts are stale
  after this run and cannot authorize new input or provide live identity.
- `probe-analysis.json`: decoded XYZ deltas, typed-search counts and candidate
  paths; SHA-256
  `82799F05DA1571962DF05DBC55123630714663F9DDF81C263D7EA172DDB97A78`.

The helper was published with self-contained/single-file settings and
`IncludeAllContentForSelfExtract=true`. It finds `plan.json` beside
`Environment.ProcessPath`, not the extraction directory. Earlier packaging
attempts produced no accepted capture. Publishing added temporary lockfile
changes through project references; those changes were inspected and reverted.
No production source, dependency, V1 source or global setting changed.

## Same-process evidence recovered on resumption

On October 19 at 08:27 UTC, a read-only review found **two additional earlier
completed captures** under ignored artifacts that the initial handoff did not
summarize. They were acquired at 05:57:46 UTC and 06:00:00 UTC, after the
supervised movement, with native float32 XYZ
`(7296.40381, 876.31891, 3054.37769)` versus typed Lua
`(7296.39990, 876.32001, 3054.37988)`. Both retained successful root stability
rereads, exact process PID/start/build, and advancing Lua sequences. The earlier
05:45 native owner window did **not** record a root stability reread. The new
reports are under `runs/9bc1e57264794516b21a8ccb86d2f80c/` and
`runs/dc5968ef8b634cca819cfb9919a23ad0/`; their exact SHA-256 are
`3FA7A587035B2C4C83176EBFDC8F9ED2F913D036C87D9916100E994EC0A2B51F`
and `D30F0CCFB1DC06647B370A487BE8DB772B5787DD8A0E1D78184F0CBF0A676FAD`.

The tracked [replay workflow](../reference/native-field-evidence.md) assessed
all three captures as `movement-consistent-stability-unverified` and
`candidate-only`, keeping restart and update claims unassessed. Its ignored
report is `artifacts/field-discovery/candidate-review-20261019.json` with
SHA-256 `4EBC1409422AB97AF5C5895DBB6AEF4A3F88047F1E76A0369323ED09A34FCAC5`.
At 08:22 UTC the live host receiver again observed the same RIFT PID/build,
player and post-movement Lua coordinates, with a new observer instance. That
is fresh Lua/host evidence; no new native capture, health variation, or game
restart was performed during this review. The VMware config at 08:24 UTC had
the field-lab ISO selected, rather than the earlier recorded original DVD.
Do not reuse a prior receipt as live identity or assume that observer/control
state remains unchanged.

## Live same-build restart and health sweep (October 19, 2026)

At 08:54:02–08:54:06 UTC, the retained unmodified field-lab executable on the
RIFT-Lab guest completed a bounded read-only health scan in the original RIFT
process (PID `11620`). Source:
`artifacts/field-discovery/runs/d8d0c66fdb954d6590962e529f3858a3/report.json`,
SHA-256 `2D2120DCC8E2986BB284F3401B6EBBB7E49BBC0790E3B4AD1E3A144910B676B9`.
The scan enumerated 9,392 regions, read exactly 1,073,741,824 bytes with zero
recorded failures, found 126 values equal to Lua health 18,208 (119 int32,
7 float64, 0 float32), and stopped at the 1 GiB budget. The trusted reference
remained health/max `18208/18208` and raw power `100`; no health or power
change was induced. The replayed health-hit review is
`artifacts/field-discovery/health-hit-review-20261019.json`, SHA-256
`7BFE375CDD8A3F58A73672334FC0F8257519E1919CB97F26A74C209B209E3884`.
It reduced 126 hit addresses to 104 nearby-address groups; eight groups had
three nearby int32 matches and some matched a user-supplied level hint 45 and
the Lua raw power value 100. These structures are **not** qualified health
fields: they can be replicated/cache/serialized observations.

The game then exited via the visually reviewed ordinary in-game Exit Game
dialog. The live receiver explicitly observed `riftProcessCount:0` and
foreground Glyph at 09:10 UTC. Glyph's already authenticated Play button
launched RIFT again, and Atank entered the world; no VM restart or forced
process kill was used.

New guest process: PID `8356`, start `2026-10-19T09:11:06.5141458Z`
(UTC ticks `639279978665141458`), executable SHA-256 unchanged:
`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
Prior PID/start: `11620`/`639279813293755454`. GuestObserver's instance
`8a948623-f4ff-4353-a0c1-80522dc312f3` survived the game restart;
typed generation changed from `1` to `2`. Fresh typed sequences `78 -> 84`
were captured around the native reader.

At 09:13:17 UTC, the existing field-lab executable and same root RVA
`0x32E0200` resolved to a different heap owner
`0x220BF9406A0` (previous `0x216ECFE06A0`). A root reread remained stable.
Native float32 XYZ at offsets `0x320/0x324/0x328` was
`(7296.40380859,876.31890869,3054.37768555)`; fresh typed Lua gave
`(7296.39990234,876.32000732,3054.37988281)`, all axes within 0.004.
The new report is
`artifacts/field-discovery/runs/4ebbe9ee91c148c4a05466ebb9049d25/report.json`,
SHA-256 `07DB7E70D98EA102FE0939A9CD89C1153FA8A0D0318B5E431B90D3BC3766415F`.
Its health search scanned 977,739,776 bytes, recorded zero read failures
and 128 exact matches, stopping at the hit limit before full coverage.
The restarted-epoch health review is
`artifacts/field-discovery/health-hit-review-restarted-20261019.json`,
SHA-256 `B4FFC8E98A9D63A4E9FBD1F2DCD1F1F8F4001C19F532680ED18941219D53C849`,
with 111 clusters. Health/max and raw power were unchanged, so these matches
cannot distinguish authoritative gameplay fields.

The five-capture replay
`artifacts/field-discovery/position-cross-epoch-candidate-20261019.json`
(SHA-256 `FCE6D04ABAE44A6FE6689EAA434FD5DB9C3F37E2039F0776804E64BBED053ED8`)
reports `same-build-candidate-observed`, two distinct process epochs, and
several independent root rereads with matching Lua. The historical first
window lacks a root stability reread, so its movement assessment remains
`movement-consistent-stability-unverified`. All reports remain
`candidate-only` and retain their source hashes; this does not independently
establish semantics, update survival, or invalid-old-epoch request rejection
for this particular field. All full-size evidence remains ignored local
artifacts; V1 source was not changed.

## Follow-up: bounded cross-epoch health shape comparison

The read-only offline comparator was added after the restart capture,
using precisely the two retained health scan reports above. It validated
each source and selected context hash and compared only repeated marker
layouts with typed health/max and raw power references (plus optional visual
level hint 45). Of 104 and 111 previously reviewed health-hit groups, 10
and 7 respectively contained informative marker layouts. One layout
appeared **8 times in the old epoch, 5 in the new**: level 45 at -8,
health-or-max 18,208 at 0/+8/+16 and raw power 100 at +40/+44 relative
to the first hit. Multiple independent occurrences make these
**potentially replicated caches/copies**, not a confirmed unique field.
No health/power variation was observed.

Replay output (ignored):
`artifacts/field-discovery/health-cross-epoch-shapes-20261019.json`,
SHA-256 `6C3CD09B59F34F92A78B42D85DEF677A31B5C3A595C443E0EAA37E413C9E81BD`.
The new [comparison procedure](../reference/native-field-evidence.md)
is `candidate-only`, no cross-epoch health-field qualification.
This was offline work with no new VM/game input or native capture.

## Resume after the recorded restart

Reacquire **current** process, VM and typed API identity before every live
capture. First focus on distinguishing current health versus healthMax and raw
power by genuinely changed-state references; use small saved candidate
regions and content hashes before requesting any larger scan. Catalog
meaning, locator, ordinary-restart, and update claims independently. A
separate invalid-old-epoch follow-pointer negative check remains untested in
this pass. Do not reuse any of the historical absolute heap addresses.

## Original pre-restart handoff (historical)

1. Inspect current Git/status and actual VM state. Launch the installed
   GuestObserver and host receiver only when needed; reacquire fresh typed Lua
   and exact VM/game identities. The previous observer/receiver/watcher were
   stopped, and the original `RIFT-TypedObserver-017c.iso` is restored and
   connected. RIFT was left logged in on the Sanctum bridge.
2. Start with root RVA `0x32E0200`, offsets `[0x320]` and terminal float32 XYZ
   bytes, using the pointer semantics in the [memory guide](../reference/memory-discovery.md).
   Capture the changed position and another reviewed movement state against
   fresh Lua. Preserve raw chain reads and disagreements. Do not treat these
   saved offsets as qualified merely because the root resolved once.
3. Narrow the owner-linked registry (`owner+0x3F8`) and its component array
   (`registry+0x78`) before extending a generic walk. Inspect the baseline's
   retained windows first. Search typed health/resource candidates, then vary
   their Lua reference values safely. Current health equals max, so a constant
   match cannot distinguish either field. Preserve the raw `power` meaning.
4. Freeze candidate RVA/offset paths, restart RIFT normally, reacquire the new
   PID/start/build/module base and Lua identity, and resolve the same paths.
   Record old-epoch rejection separately from new-epoch resolution. Only then
   add appropriately scoped catalog assessments. Update survival remains a
   separate question even if game restart passes.
5. Update this record and [status](../status.md); run the appropriate gate if
   application behavior changes. Do not add another framework or service.

Useful V1 reference sources, unchanged:
`C:\rift modding\RiftReader\docs\recovery\post-update-root-candidate-2026-10-14.md`
and `docs\analysis\2026-04-14-post-update-anchor-drift-report.md` under that same
repository. The first supplied the same-build position seed; the second supplied
the failed historical health seeds. Neither establishes V2 qualification.

The original pre-restart handoff used documentation, link and Git checks. The prior full application
gate remains the one recorded in [current status](../status.md); it was not rerun
for this documentation-only change or used to claim completion of live discovery.
All 201 relative documentation links and `git diff --check` passed for this handoff.
