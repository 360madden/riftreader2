# Current status

**16:38 EST NOVEMBER 8 — NAVIGATION CONTINUATION HANDOFF:** Compact [Markdown](handoff-2026-11-08-1638-navigation-continuation.md) and [JSON](handoff-2026-11-08-1638-navigation-continuation.json) preserve the proven earlier waypoints, later failed-closed attempts, occupied console mutex, test boundary, and next action. At handoff, both managed lab controllers were disarmed/idle and the shared queue unheld; no new game input.

**15:38 EST NOVEMBER 8 — PYTHON TEST-SUITE BOUNDARY:**
The focused `tests.test_addon_command_console`, `tests.test_run_movement_session`, and `tests.test_hold_review_lease` modules passed **134/134** in the repo's Python 3.14 virtual environment. The entire `unittest discover -s tests` run did **not** complete within 150 seconds; a bounded 50-second verbose attempt confirmed many modules progressing but at least two import errors (`test_addon_reference`, `test_guidance_addon`) because `lupa.lua51` is not installed in either `.venv` or system Python 3.14. Do not interpret the whole suite as green; isolated environment/dependency repair and later complete test run remain follow-ups. No dependency installs or game input performed by these tests.

**15:33 EST NOVEMBER 8 — LAB1 READER RELAUNCH VERIFIED; CONSOLE MUTEX OCCUPIED (NO GAME INPUT):**
Reconfirmed the executing machine is `AMD-DESKTOP`; both managed Lab1/Lab2 controller endpoints were independently verified healthy, idle, disarmed, with no desktop inputs down and no recovery flag. Shared navigation queue had no resource holders or granted/running requests. Relaunched the pinned quarter-renewal reader for Lab1 against exact unchanged game PID 8508/start-ticks/hash: reader PID 2444, nonce `c49f891d82014ea784ae26672b3a4795`, source SHA256 `048D6DF64377374BD39B05966A87CF933F7FD5C3CD6F19D5C96CD640B0B0912A`, receiver PID 54912, verified postflight; scheduled auto-expiry `2026-11-08T20:39:57.579Z`. Two fresh `addon_command_console prepare --ui-step open-chat` attempts independently refused with `controller-busy` (nonblocking shared Windows `ControlMutex`). Did not bypass the other console owner, collect a review capture, bind the new nonce, or send any game input. Repeat live work only after the owner releases the mutex; generate all fresh review/source pins and check reader/game identities again.

**15:26 EST NOVEMBER 8 — EXPIRED-LEASE CLEANUP ERROR PRESERVATION (OFFLINE):**
`execute_armed_session` now retains the original expired-lease failure if a subsequent queue finish also rejects the already-expired request, while still requiring STOP/released-state verification. STOP failure takes precedence over queue finish rejection; finish rejection following an otherwise successful run remains a hard error. Three targeted regressions added; combined movement-session/review-lease tests **53/53** pass with `git diff --check` clean. This corrects diagnostics and failure cleanup only; it does not grant a lease, bypass any freshness gate, or demonstrate new live movement.

**15:23 EST NOVEMBER 8 — GUARDED REVIEW-LEASE HELPER DIRECT-ENTRYPOINT FIX (NO MOVEMENT):**
Two Lab1 150ms S-key calibration preparations stopped safely before arming: each queue lease expired while awaiting reviewed input. The heartbeat-only `scripts/hold_review_lease.py` helper initially failed direct invocation with `ModuleNotFoundError: No module named 'scripts'`; its direct-entrypoint import path is now fixed. Direct `--help` succeeds and six focused tests pass, including a new subprocess regression. The live heartbeat path has not yet been retested.
Both aborted trial receipts report `armed=false`, `busy=false`, `desktopInputsDown=[]`, `recoveryRequired=false`; no movement pulse was sent. Next trial must start the heartbeat-only helper immediately after prepare, review the screenshot promptly, and remain inside the original absolute queue deadline. Do not extend that deadline or relax action-ready gates. The expired-lease cleanup double-traceback also remains an ergonomic follow-up.

**15:12 EST NOVEMBER 8 — LAB1 QUARTER-AGE ANCHOR RENEWAL LIVE TRIAL (NO MOVEMENT):**
Experimental full-scan renewal now starts at 2.5 seconds of the unchanged 10-second anchor age (previously 5 seconds); strict 6,250 ms remaining-age and all input/freshness gates are unchanged. The focused .NET 10 Live/Core suites passed **1,391/1,391**, native smoke passed, and the pinned single-file reader SHA256 is `048D6DF64377374BD39B05966A87CF933F7FD5C3CD6F19D5C96CD640B0B0912A`.
After the prior addon nonce refused a new reader (`Already bound; reload the UI`), the reviewed `/reloadui` cleared it. Reload reopened LuaPadModern and RR2 Casting, both hidden through separately screenshot-reviewed controls. Final Lab1 reader PID 1172, nonce `de88e7a2580a499589478b2ba8ca43f8`, bound to game PID 8508 on SHA256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`. Receiver verified advancing `fresh-scoped` XYZ and HP; no movement was sent.
The 80-second read-only sample at `artifacts/nav-quarter-renewal-20261108-02/live-freshness-sample.json` contains **81 unique envelopes**, 58 `fresh-scoped`, 22 meeting the unchanged strict action-ready budget (**27.2%**). Median scoped scan was ~255 ms; median full scan ~6,538 ms. This is evidence the experimental build operates live, **not** a matched-baseline proof that quarter-age renewal improves readiness over half-age renewal.
The registered Lab1 controller task was restarted under its existing ownership (a re-registration attempt refused the changed registration); `ensure_existing('lab1')` verified disarmed, not busy, zero desktop inputs down, exact VM/game identity. Final reader expires automatically at 20:20:35Z. Next: collect a matched baseline or a controlled bounded waypoint only with fresh strict action-ready evidence; retain the two unrelated untracked scripts.

**09:45 EST NOVEMBER 8 — TWO-LAB ASYNC FULL-SCAN DELIVERY-CADENCE MILESTONE (NO MOVEMENT):**
The pinned single-file .NET 10 async reader `ADBA0EC7047AB056934D52ADFB3F70E657C5C0D251F67A92EF756F413D8646AF` (118,019,936 bytes) runs exactly one background full scan while its single main writer continues scoped or explicitly unavailable receipts. .NET Live **992/992** and Core **380/380** passed. Both VMs' exact game/build/session admission and screenshot-reviewed `/rr2guide rebind` passed; both managed controllers were restored **ready/disarmed/idle/no held keys**. In independent 60s and 90s samples, Lab1 delivered **82 + 126** ordered HTTP200 frames (max gaps **1.026s / 1.073s**); Lab2 delivered **75 + 108** (max **1.012s / 1.441s**); **zero gaps >4.5s and zero missing sequences in 90s**. Both 600s readers terminated normally at 14:44:07Z (Lab1 seq889) and 14:44:17Z (Lab2 seq809). **Not a 480s movement pass:** Lab1 still had scoped/full-source gaps and 6GiB `read-failed`/time-budget errors; Lab2 scope was fresher, but native XYZ/movement eligibility remains unproven. The 256KiB chunk experiment was rejected live and reverted to 64KiB. Prior Lab2 480s observer failure remains strict FAIL due latest-only polling skip (seq963→967); sequence-preserving journal and 480s fresh observer are next. See [short handoff](handoff-2026-11-08-async-fullscan-cadence.md).

**08:21 EST NOVEMBER 8 — LAB2 LIVE READER + RR2-OWNED ADDON FEEDBACK WORKING (NO MOVEMENT):**
Hardened single-file .NET10 reader SHA256 `CEF295D4730234A022264B8453C70AECCCCF7A3A92127FFF8359759840ABA4AA` (118,011,744 bytes) completed an independent 90.012-second Lab2 smoke with **terminal receiver sequence 73, HTTP 200, no delivery error**; prior binary failed after 4.345 seconds with a guest file-access denial. The precise old handle conflict is still unproven. A fresh 900-second Lab2 reader PID 9832/nonce `20687e047cd94ffa83c19cd1896b26f7` passed exact game/build admission, with planned expiry 13:26:58.912Z. Screenshot-reviewed `/rr2guide rebind lab2` returned **`Rebound lab2; waiting for the new reader`**. Receiver confirmed the same new nonce, advancing outer sequence (309→347), advancing in-addon full sequence (99121→99186), source `bound`/`fresh`, HP `10635/10635`, and addon XYZ `(7182.460,820.520,3159.670)`. A source pin and CLI `--scope fast` retrieval returned `fresh-scoped` with ~618 ms receipt age, `snapshotOnly=true`, **`gameReady=false`**. This establishes live addon-backed retrieval, not native XYZ qualification, movement eligibility, or 480-second continuity. Lab2 controller was restored and independently verified ready/disarmed/idle/no keys; Lab1 controller remained ready/disarmed. Strict 480-second observation requires a reader with at least 525 seconds left after pin/console setup, so this session is too short by the time binding completed; use a new longer reader after the current one expires.

**07:49 EST NOVEMBER 8 — BOTH LABS’ REVIEWED CONSOLE TESTS; CONTROLLERS RESTORED (NO MOVEMENT):**
Lab2 current reader nonce `66362c2cb4c04aa4a919983ecf10f7fd` received the game's exact `Bound lab2; manual feedback only` confirmation after screenshot-reviewed VNC input. That establishes addon command acceptance, **not** fresh source-backed receipt: the last inspected Lab2 receiver frame remained sequence 4 from 12:28:53Z, predating binding. The nominal expiry was 12:48:49Z, but Lab2's final receiver receipt actually recorded termination at **12:28:53Z / 4.345 seconds**. Read-only guest stderr recovered the exact failure: `Live reader failed: Access to the path is denied.` followed by the same denial while saving termination. Receiver HTTP delivery succeeded. Freshness/movement acceptance was never established.
Lab1 new reader bind `7ece4f68298d4c1086887c2ca35e4d3b` was explicitly refused as `Already bound. Reload the UI before switching a new reader.` The reviewed `/reloadui` succeeded, but LuaPad’s startup panel then occupied the screen, so the protected chat-open review declined further input; this reader expired at 12:47:58Z unbound. The source-supported `/rr2guide rebind` (same lab, unused new nonce) was not attempted and should precede UI reload next time when already bound. Both managed controllers were gracefully restored and independently verified **connected / ready / disarmed / idle / no keys held**; VM/game processes unchanged. `C:\\work\\riftreader2\\.venv` now contains isolated pinned console requirements; project files and user untracked energy script remain preserved. [Small handoff](handoff-2026-11-08-lab-binding-refresh.md).

**08:02 EST NOVEMBER 8 — ATOMIC LIVE-SNAPSHOT HARDENING (OFFLINE ONLY):**
`LiveOutput.WriteAtomicAsync` now uses a per-write GUID temp and retries only transient destination access-denied/sharing/lock faults around the atomic replacement for at most one second, with cancellation and original-error-preserving cleanup. The Lab2 failure plausibly overlapped readiness polling or VMware copying `latest.json`, but the exact contending handle is **not proven**. Four Windows regression cases cover complete replacement, released/persistent exclusive locks and cancellation. Full .NET10 Live suite: **992/992 PASS**, no rebuilt reader deployed yet. Both controllers remain ready/disarmed.

**07:20 EST NOVEMBER 8 — LAB1 ADDON BOUND; LIVE FAST-SCOPED FEEDBACK VERIFIED (NO MOVEMENT):**
After a clean managed-controller stop and reviewed console input, `/rr2guide bind lab1 <reader nonce>` succeeded in game (`Bound lab1; manual feedback only`). The initially attempted `rebind` was rejected because no prior binding existed; the correct `bind` succeeded. Lab1 addon/receiver now match current RIFT PID 6820 and reader/receiver instances and deliver advancing source-backed HP and XYZ candidate observations (e.g. HP `9010/9010`, XYZ `(7450.370, 864.310, 2984.610)`). The Lab1 managed controller was restored and independently confirmed ready, disarmed, idle, and key-free; Lab2 remained unchanged.

Strict `scripts/read-live-receipt.py --scope fast` now explicitly selects the existing recent-full-scan-anchored, fresh candidate-region evaluator; default `--scope full` is unchanged and there is no fallback. Live Lab1 fast-scoped acceptance returned `fresh-scoped`, `snapshotOnly=true`, `gameReady=false` (receipt age ~814ms, anchor age ~7.68s), and focused CLI tests passed **18/18**. The full scan is intermittently expired while fast scans advance. The 60-second freshness-observer attempt failed closed because its mandatory minimum is **480 seconds**; sustained-freshness/movement eligibility remains **unproved** and needs a new bounded reader lasting beyond that window. No character movement, combat, VM lifecycle, reload, or controller safety bypass occurred.

**06:49 EST NOVEMBER 8 — BOTH LABS VALIDATED AGAINST CURRENT-BUILD NATIVE REFRESH BRANCH (READ-ONLY):**
The new pinned .NET10 reader (`E9F0A3F4EC45A1C9F565A8322DEFAA6CB62A674D3B6EE9A2B27C5A43262BFBF2`) ran the exact `sample-current-position-refresh-branch` command through the independent `--mode refresh-branch` wrapper. Lab1 PID 6820 / player `u035400012FA2D678` and Lab2 PID 10612 / player `u035400012DFEB5BC` both reported `flag=0`, `sourceGuardStatus=not-evaluated-flag-zero`, `sourceGuardEligible=null`, `status=guard-ineligible-candidate`, `passiveFreshness=unqualified`, and `movementEligible=false`. This is a sampled branch result, NOT evidence that all position writers were dormant; neither fresh XYZ nor facing has been established. Immutable native report SHA256: Lab1 `20B750912E661BD7BAA824F43CE9DD8448FD92A014A1196F1837BE3B2E334BFF`, Lab2 `7DF420C0071E01745D0470933EEE481021B29869CC8F1E51B16517C70BA70326` under `artifacts/native-xyz-lease-20261108-0213z-7b942e6a/runs/refresh-branch/{lab1,lab2}/`.

Lab2's first health probe correctly refused to publish after its 16-byte ownership check caught a changing revision/clock with stable true owner. Probe now pins only the actual 8-byte owner pointer, separately rechecks wrapper revision/clock, and fails closed on changed inputs. Live Lab2 retest succeeded with stable, type-checked *candidate* HP `10635/10635`, Energy `100/100`, and cached XYZ `(7182.457, 820.523, 3159.667)`. Lab1 receiver did receive a bounded live reader stream, but the addon remained `unbound` (`matching-challenge-not-found`), and the reader terminated at its 720-second deadline. Controller was busy; screenshot/console admission failed. **No movement, combat input, reload, or reboot was performed.** Python integration tests: **98/98 passed**. Next: obtain a fresh same-instance addon feedback pin before guarded movement; keep the flag-zero native branch as candidate-only.

**23:49 EST NOVEMBER 7 — EXACT 0x6136B0 GUARD + SECONDARY RENDER-POSITION CONSUMER MAPPED; 1303/1303 TESTS PASS:**
The read-only current-build refresh-branch candidate reader now verifies the
flag-branch source-component backlink and samples the exact `0x6136B0` operands:
source `+0x48` context pointer, signed nested `+0x24` value, and source
`+0x58` provider presence. It reports candidate eligibility separately from
writer execution; handle branch is explicitly not applicable, top-level flag
zero is not evaluated further, and missing operands remain unavailable rather
than zero. Self-source owner mismatch no longer publishes a source candidate.
The JSON contract is now v2 with lossless context hex and explicit
`sourceGuardStatus/sourceGuardEligible`. Focused branch tests passed **42/42**;
full .NET10 suite passed **1303/1303** (Live 923 + Core 380), Release.
The bounded actor/render path is now more precise: `0x613800` calls
`0x6996C0`, reads secondary cache `+0x88` via `0x698440` and transform
`+0x94` via `0x698410`, then passes them to `0x687320`. That routine adds
actor offsets and writes actor translation `+0x3BC/+0x3C0/+0x3C4`; this is a
downstream consumer of secondary cache, not an independent primary XYZ writer.
No live native read/deployment occurred. Both labs remain operationally ready,
but the latest readiness packet reports no advertised native-read lease
capability and Greeting Jimmy has not relinquished any live reader; live sample
remains blocked pending explicit cross-chat/foreign-reader quiescence and
separate admission. Continue bounded offline destination-matched writer tracing.

**23:28 EST NOVEMBER 7 — CURRENT-BUILD XYZ WRITER ROUTES DECOMPILED (STATIC ONLY):**
Focused Ghidra 12.1.2 headless analysis of exact executable SHA
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`
decoded 669 instructions / 2,614 instruction bytes across eight bounded
routines; ten related helper windows were also decompiled. The expanded
[writer-route evidence](reference/current-native-xyz-writer-evidence.md)
now documents both `0x6996C0` primary-cache update routes, the exact
`0x6136B0` alternate-provider predicate, and the `0x612EE0/0x6126F0`
conditional source-object path. Helper checks distinguish matrix/actor
transform consumers from primary component XYZ stores. The 49/49 historical
position-component cohort still had `+0x100=0` and `+0x108=0`, so neither
known update branch was eligible in those captures; this is historical, not
current runtime proof. Pseudocode exports are retained under
`artifacts/rea/ghidra-v5-pseudocode.txt` (SHA
`78ad0d1edb84eba9dcf309911c0117df17369f1ea0b85230608e1f248fea30b1`) and
`artifacts/rea/ghidra-v6-pseudocode.txt` (SHA
`2cb270ce303de75afab4e9721b80c2313988945d9ee32a53763bbacd0c42a35b`).
A separate instruction-level V7 dump (SHA
`ca66aca8543b4e2f0b70f7669025c0d3fe419c4a0864a7ae9832ac625e1ac530`)
confirms the register flow through `0x6A0040 -> 0x612EE0 -> 0x6126F0` and
the fallback `0x698460 -> 0x6996C0`; the fallback may re-enter the updater on
a selected component, but live pointer identity/recursion depth are unknown.
No live game/VM/process read, controller, input, addon, reload, deployment or
restart occurred. Current branch admission, actual writer execution, other
external writers, passive freshness, changed-state and full-game restart remain
unqualified. Next: continue bounded destination-matched store tracing offline;
any live branch sample requires fresh process/lease admission and cooperative
reader quiescence. See
[writer-route continuation handoff](handoff-2026-11-07-native-xyz-writer-route.md).

**LATE NOVEMBER 7 — XYZ BRANCH RETRIEVAL + TRACKING + CONTROLLER RECOVERY (SOURCE/host-only):**
Two milestone commits `9a62ced` (new leased `sample-current-position-refresh-branch`,
lossless wrapper schema2, per-segment XYZ delta counts and offline raw-orientation
comparison) and `641256c` (Windows closed-loopback-port 10035 table fallback)
are pushed. Root verified **28/28** registered CurrentBuild CLI sample command
lease callsites; prior agents and generic routes remain nonparticipants.
Full .NET Release **1273/1273 PASS**. Full Python under repo-local Lua5.1/lupa2.8
**2100 run, 2 skipped, 0 errors**: historical Mana source SHA remained pinned;
only synthetic test fixture isolation changed (commit `0ffb812`).
Retained Lab1 30-row XYZ replay has 29 equal admitted pairs and
zero unequal; cached candidates are NOT independently fresh or motion-qualified.
New host-only compact single-file reader SHA256
`C1D9B75DD09096E0C98101D4795E7C4B78A56F518310F34863D6FC2315EB9FDA`
(52,252,619 bytes) passed `--help` and synthetic native bundle smoke;
matching agent.zip SHA256 `94C92F693162BB6C9DA3D736F2975D7FC98D8E5AAABAA1361E07403236DB4692`
(46,807,306 bytes), ZIP integrity pass, **neither staged/deployed**.
Read-only current host probe confirms no TCP listeners on configured RR2
controller ports 49811/49921; foreign-reader state and guest agent capability
are UNKNOWN, so no controller start or game/VM input was attempted.
Greeting Jimmy shared a separate source-hashed review
`docs/xyz-jimmy-lease-review-2026-11-07-a087.md` (independent 40/40 Python,
51/51 .NET) confirming cooperative-lease limits, unbounded position/zone
cross-field skew, and no live admission. Preserve separate position and zone
candidate timestamps until controlled live skew/freshness evidence exists.
Root continuation in [short Markdown handoff](handoff-2026-11-07-xyz-tracking-root-v2.md)
and [machine JSON](handoff-2026-11-07-xyz-tracking-root-v2.json).

**21:23 EST NOVEMBER 7 — OFFLINE XYZ TRACK SEGMENTS + HOST PACKAGE:**
New `scripts/summarize_native_xyz_track.py` reuses the existing projector to
report source-hashed contiguous candidate path and net XYZ displacement, but
withholds totals across gaps/identity boundaries. Root + worker focused tests
**5/5 PASS**. Replay of retained Lab1 30/30 owner-key trace found 29 zero
sample-to-sample deltas, 0 candidate path/net displacement; that is NOT proof
of no physical motion or advancing source freshness. A new host-only agent.zip
(47,958,337 bytes, SHA256 `33E3BD0D42FD6F6AE3960B5CEDCA3C779F1E97F95F5673ABE47385F3DF47359D`)
packages the immutable DCFC17... reader and matching two-field descriptor for
the managed-fleet-20261029 root; archive CRC and payload hashes verified, **no
VM staging, agent update or live data**. The RR2 Lua baseline producer still
calls `Inspect.Unit.Detail` about every 0.5s regardless of reference nonce, so
unbinding does NOT establish API-quiet native XYZ freshness. Guarded
managed-lab launcher now offers opt-in `--require-native-read-lease`, requiring
exact integer v1 capability after restart; **24/24** focused offline tests
passed. It does not prove deployed binary identity or authorize maintenance.

**21:16 EST NOVEMBER 7 — IMMUTABLE XYZ READER HOST-ONLY RELEASE:**
New .NET10 single-file executable published at
`artifacts/native-xyz-lease-20261108-0213z-7b942e6a/publish/RiftReader2.Live.exe`,
SHA256 `DCFC17E18A4F361095B5701AB31CDF566664178781E0740FCC8969D2C61957FD`
(117966688 bytes); `--help` and synthetic host-only native-published smoke
passed (exact bundle hash, PE header, stale epoch/no-overwrite/sidecar checks).
Location-pair host wrapper now pins these bytes; no VM agent was replaced.
Complete .NET solution **1267/1267 PASS**. Full Python discovery **2076 run,
10 errors, 2 skips**: all ten share unchanged mana-screenshot reviewed owner-probe
SHA mismatch; focused XYZ Python264 run/262 pass/2 skip remains green.
Full format verification is blocked by already-minified ExperienceValues source
at HEAD (also newly edited lines); no broad reformat was performed.

**21:12 EST NOVEMBER 7 — XYZ NATIVE-READ COOPERATION (SOURCE ONLY):**
A machine-local, per-game-epoch cooperative `NativeReadFileLease` now gates the
current-build position, orientation, location-context, paired-position,
paired-zone, selected-target, vitals and zone-seed CLI readers plus persistent
guest native-vitals/native-xyz capture source. Exclusion is keyed by exact
PID/start/build SHA; lease scope includes session disposal. Combined Release
.NET tests **887/887 PASS** and selected XYZ Python tests **264 run, 262 passed,
2 skipped**. Real OS file-share contention and abrupt child-process release were
tested offline; a symlink-creation privilege failure left the new reparse
rejection test conditional, NOT exercised. **Not deployed or live accepted**:
older installed agents/readers do not cooperate. All 27 registered CurrentBuild CLI commands
and the newly guarded agent action body now participate in source, but generic/legacy native routes still bypass this lease. Keep all shared-lab
read/input owner coordination, exact-identity and STOP controls. Source-only
host launcher transport/guard hardening passed focused offline tests; no new guest binary was copied.
[Native-read handoff](handoff-2026-11-07-xyz-lease-greeting-jimmy.md).

**20:47 EST NOVEMBER 7 — INDEPENDENT PLAYER/TARGET RAW ZONE KEYS:**
New current-build read-only `CurrentBuildPairedZoneKeyCandidateReader` now
brackets separately owned 0294 `owner+0x150` raw keys for self and selected
target around the existing guarded paired XYZ acquisition. A matching key is
ONLY `matching-zone-key-candidate`; target-health absence preserves target XYZ
with zone unavailable. Public zone ID, world instance, atomic same-world
geometry and passive source freshness remain UNAVAILABLE. The bounded
`sample-current-paired-zone-key` command is registered in source but NOT
deployed or game-tested. Full Release .NET suite **699/699 PASS**; no gameplay
input, controller/agent restart or VM maintenance. A separate audit found the
standalone guest CLI does NOT share the current persistent agent's native-read
lane; exclusive cross-process acquisition is a live acceptance prerequisite.
No current resident agent/guest runner is claimed to honor a new lock.

**20:33 EST NOVEMBER 7 — XYZ MULTI-SOURCE AND FAST-TRANSPORT SOURCE CHECKPOINT:**
The exact-current-build native location, optional zone, selected-target pair,
raw orientation and offline reference-correlation commands/helpers are now
implemented or registered in source. The persistent guest `native-xyz` and
host `/api/native-xyz` routes reuse existing identity/authentication and the
native-read/action interlock; this is a **bounded one-shot candidate route**,
not deployed continuous telemetry. Final full Release .NET suite
**681/681 PASS**, after one unrelated pre-existing allocation-sensitive scanner
test failed intermittently (isolated1/1 and full retry681/681 both passed).
Python XYZ-family discovery **197 run, 195 passed, 2 skipped**, exit0;
focused fast-host 48/48 and guest dispatch/read-lane 32/32 passed synthetically.
The separately SHA-pinned BE2529... reader and earlier Lab1 receipts remain
unchanged; newly wired commands/agent endpoints have NOT been published to or
measured in a VM. Native-xyz zone is unavailable; ≥3s response is rejected
AFTER a blocking call, not actually canceled at3s. Guest/host clock tolerance
is ±5s, not measured synchronization. This current route is not qualified for
sustained sampling, locomotion feedback or restart durability.
A separate **HOST-ONLY** .NET10 single-file candidate release now exists at
`artifacts/native-xyz-location-pair-20261107/publish/RiftReader2.Live.exe`,
SHA256 `73AAA4AF4BE94F5D1A7BA60F0601972E3EEA9B32202B902B6FE0C46106AB2CA7`
(117815136 bytes), with successful `--help` smoke. It has NOT been copied to
any guest or swapped into the running fleet; the prior BE2529... pinned reader
remains the only newly accepted live Lab1 native XYZ binary.
Greeting Jimmy independently extended
`docs/xyz-jimmy-findings-2026-11-07-anchor-review-a086.md`: exact-build
0x6996C0 static cache-writer branches require a *different* source selector
metadata RVA `0x2F57918`. Retained Lab1 roots omit that RVA; no fresh
branch admission, actual writer execution or API-quiet window is established.
Do not treat conditional source+0xF8 as a universal player-world owner.
A new bounded read-only refresh-branch candidate reader now returns explicit
handle-branch unavailable, flag-source candidate, or guard-ineligible status,
without invoking native getters or claiming actual writer execution; 13
focused synthetic tests passed.
Greeting Jimmy and independent root peer checks now show two-lab historical
source-selector index46 with SELF slot46 absent; all known conditional
`0x6996C0` XYZ-writer branches are guard-ineligible in a rigorously checked
**49/49 pointer-selected position-component captures across seven historical
game epochs** (the narrower Jimmy original single-chunk subset was26/26).
The independent audit resolves the correct position chunk by entity selector,
component table and pointer even in multi-chunk reports; no parse/hash/backlink
errors or nonzero branch guards were found. These historical receipts do
not prove current runtime guards or absence of other engine writers.

**20:22 EST NOVEMBER 7 — CURRENT-BUILD XYZ TRACK WITH UNIT IDENTITY LIVE:**
[Operator guide](reference/current-native-xyz-tracking.md) and
[Greeting Jimmy shared coordination packet](handoff-2026-11-07-xyz-greeting-jimmy.md).
Root's newly published .NET10 reader SHA256
`BE252929D846AA0BB696D003116AB9D8ACAA23E5D411D68F913A92CD08919A5E`
(117757792 bytes, immutable `artifacts/native-xyz-unit-20261107/publish/`)
passed --help, 602/602 full Live .NET tests and 45/45 focused Python tests.
Lab1 newly copied that reader and returned **5/5** position samples under fresh
PID6820/start639296903905448486, build `1935A05C...`; all five sampled
the SAME owner key `u035400012FA2D678` and cached XYZ
`7450.3677,864.3101,2984.6113` over2.108s. Max read98.2754ms,
sample-start gap533.3391ms. Source receipt
`artifacts/native-current-sampler-20261105/runs/lab1/7d5b868c40664a0cb95e2c6ce0892cfb/samples.json`,
SHA256 `FC9DC02D1692BECA28ACF9F7F7A8B492D2AEC04A23FB87CC4CFF4495A4009772`.
A second NEW-reader Lab1 run completed **30/30** on the same sampled key
`u035400012FA2D678`, no XYZ change, 19.3873s span, max read375.6047ms
and maximum sample-start gap778.9411ms. Pinned guest reader was reused.
Receipt `artifacts/native-current-sampler-20261105/runs/lab1/d2d11975e54b41bf9155a90269c6703b/samples.json`,
SHA256 `254A4E86B80612A22957B46AE2E162FF9FA776779253115861B3AD2818B4E4AD`.
Cadence is measured, not promised; no changed-state/passive-freshness
qualification follows.
Earlier old-reader Lab1 run did15/15 in6.997s, source SHA98AA5218... but
did NOT expose unit keys. Offline track projection, XZ-planar/Y-vertical
distance, candidate velocity, relative-target geometry and raw orientation
descriptors now have synthetic tests; missing world/zone/clock evidence keeps
cross-source relative output unavailable. No input/controller/reload/restart
was used. **Native XYZ remains cached candidate data: no changed-state,
API-quiet passive refresh, uninterrupted player continuity, body heading or
current-build full-game restart qualification.** Greeting Jimmy independently
wrote a reviewed shared-repo report `docs/xyz-jimmy-findings-2026-11-07-anchor-review-a086.md`:
ordinary RR2 producer can call `Inspect.Unit.Detail` on a~0.5s game-time
cadence, which may refresh the same cached XYZ. Merely unbinding a reference
nonce does not establish an API-quiet interval. Root acknowledged this in the
shared packet and assigned branch-admitted cached-XYZ writer tracing. This
proves file-based coordination, not direct cross-chat message delivery.

**19:33 EST NOVEMBER 7 — TWO-LAB BUFF GROUPING INPUT LIVE:**
[Saturday-night discovery handoff](handoff-2026-11-07-saturday-night-discovery.md).
The new signed state+80 raw input was observed in all52 sampled buff nodes:
Lab1 28 values+1; Lab2 21 values+1 and three0. Both guest native captures
exited0 under fresh exact game identity, with no RIFT input/reload/controller.
The reader was SHA-pinned; C# focused19/19 and Python buff7/7 passed.
Legacy/new/timing source-reader selection was repaired after independent review.
Lab1 also yielded20 stat selectors/40 raw values on demand. Buff List/stack
grouping, live variant selection and restart/changed-state qualification remain
open; do not infer counts from sentinel or API scratch.

**19:21 EST NOVEMBER 7 — ON-DEMAND NATIVE PLAYER CONTEXT VERIFIED LAB1:**
`python -B scripts/sample_current_native_player_context.py --lab lab1`
now returns validated `values.level`, `values.combat`, and `values.target`
directly in structured JSON, retaining raw-candidate/status semantics and
process/build/receipt identity. Fresh Lab1 PID6820/start639296903905448486,
game SHA1935A05C..., observed level raw41, combat false/raw0, target getter
zero/unavailable; native acquisition7.771ms. Guest reader was hash-verified and
reused, not redeployed. Receipt:
`artifacts/native-player-context-20261107/runs/lab1/af0aded499db4368947aa4090836c17b/samples.json`
SHA476EBCAC9CA63AB0CC2388C42B55A0B9C7A63BCE4014B1453CA4102B3A08BA38.
Two focused projection tests passed; no input/reload/controller action. Values
remain candidates, without changed-state, API or full-game restart proof.

**18:53 EST — LAB1 MOUSE LIVE ACCEPTED; DISCOVERY AND RETRIEVAL FRAMEWORK:**
[Current mouse/setup continuation](handoff-2026-11-07-lab1-mouse.md).
Host vncdotool capture, reviewed pointer move, and reviewed Browse/Close clicks
succeeded;11 focused tests passed. Fresh same-SID canonical interactive login
resolved VMware's username-spelling mismatch without credential changes.
Button release/disconnect/mutex cleanup verified; controller absent and queue
blocked/unheld/no pending Lab1 request. No reload/cast/bind/deployment.
Joey clarified the product purpose: practical discovery PLUS reliable on-demand
retrieval of wide-ranging data. AGENTS.md now distinguishes findings, working
retrieval capabilities and outstanding qualification; refinement remains optional.
RR2 and RRE are parallel complementary efforts; the RRE repo is a valuable
framework information source, with separate ownership and explicit provenance.

**17:23 Eastern - CURRENT CONTINUATION AND VERIFIED CLEAN CLOSE:**
[Short native-discovery handoff](handoff-2026-11-07-1700-native-discovery.md).
All root lab jobs terminal. RRE0.2.3 CLI exit0/54records and explicit clean return
independently verified17:18:38; controller absent, queue BLOCKED/no holder.
Observed factors support20/21 positive range values conditionally; energy variants
remain explicit. Scheduled extended window ends17:26:48 Eastern. No new live
operation is pending; current phase is final findings/commits.

**SC625 TRIAL2 CLEAN RETURN VERIFIED17:06:12 Eastern.** Root checked exact
return/recovery SHA, controller absent, queue BLOCKED/no holder and matching VM.
Passive RR2 reads resumed; RRE offline, no new grant. Original CLI failure remains
failed despite successful acquisition/cleanup; BOM journal-parser fix/replay is
offline only. Receipt artifacts/lab2-rre-sc625-trial2-handoff-20261107/after.json.
[Use the shorter current continuation](handoff-2026-11-07-1700-native-discovery.md).
The older hold notices below are historical and resolved.

**17:05 Eastern - SHORT CONTINUATION:** [Current native-discovery handoff](handoff-2026-11-07-1700-native-discovery.md).
Lab2 remains HELD pending RRE explicit clean return; trial2 acquired/cleaned but
C# decode failed, no live retry. New direct range/energy factor reader verified
offline and ready after return. Current goal ends17:26:48 Eastern.

**ACTIVE SC625 TRIAL2 HOLD16:56-17:11 Eastern /21:56-22:11UTC.**
ALL RR2 Lab2 operations are HELD until explicit independently verified clean
return. Root16:56:12 checked controller absent, queue BLOCKED1/no holder and
matching VM identity; all RR2 native jobs terminal. Source fix84c711a separates
identity/output namespaces; reviewed0.2.2 DLL B8D297866CF92BD30F4A987E72D5CD6A6822AC1952D2AD8C960B9995D19CCC04,
helper4F3315324DF204D9C40F0477A65578B3126BA5C8DB74CFB159C9E9E739D95154,
all12 source/all5 release hashes verified. Before/release receipts:
`artifacts/lab2-rre-sc625-trial2-handoff-20261107/`. Scope: one fresh reviewed
manual Capture and one0.2.2 acquisition, unchanged Collector0.4.13, no new API
calls/deploy. Preserve strict54-record gate, STOP/releases, scoped cleanup and
process journals. No auto-retry, controller start, queue reset or forced release.
The prior failed trial remains failed. End time alone is not a return.

**16:49 Eastern - ALL40 STATS MATCH HISTORICAL API; RANGE INPUTS CAPTURED:**
Lab2 native20 pairs agree with the retained64-minute-earlier SC628 values.
Typed range config min5/max105 identifies Toggle Auto Attack special key;24
selected definitions yielded actual tags and Energy flags. The mode0 self-source
factor remains unobserved; raw entry5 is not a multiplier claim. RRE is offline
after verified SC625 failed-trial cleanup/return; no new window is granted.
[Receipts and next discriminator](handoff-2026-11-07-native-discovery.md).

**SC625 CLEAN RETURN VERIFIED16:41:03 Eastern; passive RR2 reads resumed.**
Root verified control-return.json and hash-bound recovery inventory: zero exact
UUID residual files and zero owned native processes, no unreadable native command
lines. Existing fleet-agent PID3252 was outside scope and untouched. Independently
checked controller ABSENT, queue BLOCKED1/no holder and matching VM identity.
Receipt `artifacts/lab2-rre-sc625-handoff-20261107/after.json`. Failed trial remains
FAILED/liveAdapterAccepted=false; original quarantine receipts unchanged. RRE is
OFFLINE until a new grant; no automatic retry, controller start or queue reset.
The hold/quarantine notices below are historical, resolved by this explicit return.

**SC625 FAILED TRIAL / LAB2 QUARANTINE - 16:37 Eastern.** Reader invocation
21:34:41-21:35:17Z exited2 (SessionError); guest cleanup reports missing snapshot
process journal/unverified residual. RRE reports identity/output filename collision
before native launch as likely cause. This is not a successful adapter acceptance.
ALL RR2 Lab2 operations remain HELD. RRE may perform only scoped exact-UUID
process/file recovery for f7dacbf40f9d4a6597edad723f5da20b and STOP/release cleanup;
no experimental retry, Capture or reload. Require raw recovery and explicit clean
return, independently verified before resuming. Failure receipts:
`C:/work/rre/artifacts/sc625-live-adapter-20261107-1627/acquisition/`.

**16:34 Eastern - SOUL RECALL CANDIDATE RECONCILED:** Fresh native base3600000ms
and typed modifier factor2/coefficient-300000ms reproduce3000.000244140625seconds,
equal to the historical API value. Separate capture times; no changed-state,
freshness or restart qualification. Lab2 native stats matched all10 retained API
baseline values. Sammie315 acknowledged the next queue and dispatched six lanes.
**LAB2 HOLD16:32-16:47 Eastern:** RRE SC625 exclusive window; no RR2 Lab2 operation
until explicit verified clean return. Reader0.2.1 amendment source/hash-verified.
[Current handoff](handoff-2026-11-07-native-discovery.md).

**16:05 Eastern — XP, ZONE AND MODIFIER CHECKPOINT:** Corrected Lab2 zone ID
matches the retained SC628 projected value; old wrong-address NULL claims are
withdrawn. XP raw candidates are Lab1 144585/245308/rested0, level41, and
Lab2 53375/289389/rested0, level43. Lab2 has one raw mode4 cooldown modifier;
its applicability and result remain unresolved. Six Sammie specialists and
a coordinator delivered stat selector/owner research; root implemented a stats
reader. First Lab1 capture subsequently passed: armor1163, attackpower20,
spellpower678, attackcrit20, spellcrit235; ordinary/unbuffed pairs equal. These
are raw candidates with no API/units/freshness/restart acceptance.
[Details](handoff-2026-11-07-native-discovery.md).

**LAB2 RETURNED CLEANLY — 2026-11-07 15:46:56 Eastern:** SC628 API field capture
completed and root verified return/mode. Passive reads may resume; controller
remains absent, queue BLOCKED/no holder. RRE awaits any new ownership window.
[Current ownership note](handoff-2026-11-07-lab2-rre-window.md).

**CURRENT DISCOVERY CONTINUATION — 2026-11-07 15:19 Eastern:**
[Short native-discovery handoff](handoff-2026-11-07-native-discovery.md) has the
working commands, verified results, accepted selected-target capture and remaining
time window. Preserve its practical discovery priority and existing owners/gates.
Joey extended the current goal by FOUR HOURS: new end17:26:48 Eastern today.

**LAB2 RRE WINDOW RETURNED CLEANLY:** Root verified return and actual mode at
14:51:45 Eastern. Passive native reads resumed; controller stays stopped,
queue BLOCKED/no holder. Prior addon/nonce assumptions require fresh evidence.
[Ownership transition and caveats](handoff-2026-11-07-lab2-rre-window.md).

**15:53 Eastern — ZONE SOURCE CORRECTED:** Earlier NULL receipts sampled wrong
RVA337EBF8. Four producer references prove336EBF8, so actual provider absence
was not established. Corrected reader passed12 focused cases. Lab2 candidate
`z0000000CB7B53FD7` matches the separately captured SC628 API zone ID; the
observations are minutes apart, not freshness/restart or producer-auth proof.
[Receipt and limitations](reference/native-player-context-candidates.md).

**15:00 Eastern — SELF NAME/CALLING CANDIDATES:** Names Trio/Bolinao captured
independently on Lab1/Lab2; Lab1 raw calling3 maps to mage on this build. Lab2
calling raw4 maps to rogue; Lab1 race key1/provider resident seed also completed.
Typed race cache/name-decoration followups underway. Checkpointf6cea6f committed
the name/zone readers and Lab2 buff followup (21 keys,11 names/10 unavailable).
[Player receipts and limits](reference/native-player-context-candidates.md).

**15:17 Eastern — TWO-LAB RACE/SHARD CANDIDATES:** Both labs yielded typed race
token mathosian and current-shard name Deepwood. Exact Inspect.Shard registration
was proved; raw lookup1704 is not a publicID. Localized race seed and raw experience
seed first captures are running. Independent current API/freshness/restart remain
open. [Receipts](reference/native-player-context-candidates.md).
User authorized cross-chat coordination; RRE historical packet/all7 source hashes
verified. A minimal future API field expansion is being prepared by its owner;
no new Lab2 window granted yet. [Online reference limits](reference/native-api-reference-research-2026-11-07.md).

**14:23 Eastern — LOADED FIELD FIX LIVE ON BOTH LABS:** Corrected a fixed file
ordinal assumption by validating/searching the complete loaded field table.
Lab1 all28 andLab2 all24 buff timing candidates captured, all durations0. No
active positive timers or API publication claimed. [Receipts](reference/native-buff-candidates-2026-11-07.md).

**14:19 Eastern — SOLE NATIVE BUFF LIST CANDIDATE:** Typed visibility read
excluded27 hidden-kind rows and passed Rested's ordinary-source candidate ID
b80000003086737D6. Grouping cannot suppress the sole passing object. This is
not independent API/UI acceptance. [Receipt](reference/native-buff-candidates-2026-11-07.md).

**14:05 Eastern — FIRST BUFF TIMER INPUTS LIVE:** All28 begins and reference
profiles captured; six tick durations are0, not active positive timers. The22
dynamic refs match065A, so the statically resolved float+24 path is the next
small capture. [Receipt and exact limits](reference/native-buff-candidates-2026-11-07.md).

**14:00 Eastern — BUFF DEFINITION NAMES LIVE:** All22 distinct keys typed/named,
all28 node relationships preserved/rechecked. Kind4 maps to Rested; kind1 includes
passive soul/talent effects. No API-selected name or visibility claim.
[Receipt](reference/native-buff-candidates-2026-11-07.md). First timing capture running.

**13:53 Eastern — NATIVE BUFF SEED LIVE:** Lab1 captured28 raw nodes in12.29ms;
27 kind1 are excluded by the List path, one kind4 remains a visibility candidate.
Three actual timer profiles captured. No API-visible count, name or timer values
claimed. [Receipt and next useful reads](reference/native-buff-candidates-2026-11-07.md).

**13:52 Eastern — RESTRICTION SHORTCUT CLOSED:** The self-owned restriction array
was empty, so its nonempty-array rejection cannot select variants. No full-engine
follow-up; winner remains unknown. Native buff telemetry is the next useful track.

**13:43 Eastern — LIVE COUNTEREXAMPLE CLOSES LEVEL SHORTCUT:** Effective41 and
typed exception/cache guards captured; all12 referenced definitions instead have
requiredLevelRaw0. No above-level first-variant exclusion applies. Guards matched
before/after; winner remains unresolved. [Receipts and limits](reference/native-ability-variants-2026-11-07.md).

**13:33 Eastern — ALL REFERENCED VARIANT DEFINITIONS RESOLVED:** Lab1 all12 and
Lab2 all16 keys typed/named with before/after ordered parent rechecks. Captured
Blight base cooldown8/30s, Splinter Shot zero-path/1500ms and On the Double0/40s
differences. Candidate inputs only; no selected-winner or learned claim.
[Receipts and next guards](reference/native-ability-variants-2026-11-07.md).

**13:26 Eastern — ORDERED ABILITY VARIANTS LIVE:** Lab1 captured six type078A
parent abilities, each with two typed0061 variant keys. Catalog122/119 names,
all43 filter rows named, zero decoder failures,16.22s span. No chosen-variant
claim. Lab2 independently captured eight parents/two typed keys each,134/121
names, zero decoder failures,23.25s span. Fresh possible-definition lookup running.
[Receipt and limits](reference/native-ability-variants-2026-11-07.md).

**13:20 Eastern — CAST FACTORY/COOLDOWN GATE DISCOVERIES:** Existing0650 definition
milliseconds feed a real primary-duration getter; the tick-snapshot0653 branch
belongs to the observed generic Use definition. [Factory findings](reference/native-cast-duration-factories-2026-11-07.md).
The cooldown Detail gate omits current fields when timerT is zero; baseline
zero values do not mean API remaining0. [Gate findings](reference/native-cooldown-static-followup-2026-11-06.md).

**13:18 Eastern — TARGET NUMERIC LEVEL50:** Fresh getter route chose the
alternate-secondary value50, superseding raw owner0. HP/XYZ/rawcombat preserved;
public/displayed level remains unverified. Eight focused cases passed.
[Receipt and limits](reference/native-player-context-candidates.md).

**13:13 Eastern — TYPED TARGET RAW CONTEXT:** Target owner0294 passed, raw level0
and combat byte0 captured with HP/XYZ retained. Raw level is not public/displayed
level; alternate component selection remains next. No self-presentation shortcut
or input. [Receipt and limits](reference/native-player-context-candidates.md).

**13:11 Eastern — MODE-SELECTED TARGET NAME:** Fresh mode1/formattingFlag0 anchors
support **Normal Practice Dummy** as the selected base-name candidate, with the
traced post-copy formatting bypassed. Capture36.257ms. Independent UI/API,
freshness and restart remain unverified. [Receipt](reference/native-player-context-candidates.md).

**13:07 Eastern — TARGET RAW FALLBACK NAME CAPTURED:** The guarded template cache
read returned **Normal Practice Dummy**, with typed record/name references and
stable target/provider/TLS/cache anchors, in34.713ms. Localization key1290053851
missed the resident dictionary; raw fallback is separate from active/API name.
Lab2 selected-target command independently returned honest unavailable/null fields
for its guarded zero target. [Receipts and limits](reference/native-player-context-candidates.md).

**13:03 Eastern — SELECTED-TARGET XYZ CANDIDATE:** The repository command passed
with the cached reader: target`u80000002CD0034D1`, XYZ7428.7246/863.526/2950.8438.
Exact-target ownership and position bytes were checked; no freshness, restart or
action qualification. Name-route diagnostic found template key1847420318 and
dynamic provider selector623; guarded cache-only name resolution is next.
[Receipt and limits](reference/native-player-context-candidates.md).

**12:46 Eastern — TARGET NAME BLOCKER RETAINED:** Optional name capture preserved
target health but found an empty alternate string leading to an unresolved
virtual fallback. No name candidate accepted. A bounded method-address capture
is running for static analysis; no invocation or branch bypass. Cached-position
owner core remains separate until used.

**12:30 Eastern — SELECTED-TARGET VITALS CANDIDATE:** The current guarded Lab1
target resolved to a native health candidate1224100/1224100 in13.2605ms; exact
full64 key/lookup/typed health/self-target checks passed. The repository command
also passed using the cached reader. No target/input change, Mana/Energy values
or action-preflight integration. [Receipts and limits](reference/native-player-context-candidates.md).

**2026-11-07 12:14 Eastern — SELF TARGET/LEVEL/COMBAT CANDIDATES:** The repository
sampler returned Lab1 level41/target`u80000002CD0034D1` in9.375ms andLab2
level43/zero target in10.957ms; both raw combat bytes0. Owner fingerprints,
branch guards, lookup and process checks passed. No target/input change or
Action-preflight integration. Optional screenshot corroboration was blocked
at dependency admission; no UI agreement is claimed. [Receipts and limits](reference/native-player-context-candidates.md).

**2026-11-07 11:49 Eastern — RAW RANGE/CONDITION INPUTS LIVE:** Lab2's repository
catalog captured134 rows/121 names/all54 nonzero-filter rows named, zero decoder
failures, span25.09s. New min/max float inputs retain raw bits; bounded condition
vectors exposed no ID1 and eight unlabeled ID4 entries. Adjusted/equipment range,
target readiness and positive stealth semantics are not accepted. No input or
owner change. [Receipts and limitations](reference/native-ability-ownership-findings-2026-11-06.md#raw-range-and-conditions--november7-1149-eastern).

**2026-11-07 — STANDALONE RUNTIME AUDIT (DOCUMENTATION-ONLY):**
[Handoff and bounded source audit](handoff-2026-11-07-standalone-runtime-audit.md).
RR2 owns the current reference/reader/receiver implementations; Lab 1 passed
64/64 advancing RR2R1 comparisons. Lab 2/physical loaded-source acceptance,
receiver-feed freshness, obsolete movement-profile closure and restart
qualification remain pending. No game input or code changes in this audit.

**2026-11-07 11:40 Eastern — REPOSITORY CATALOG COMMAND LIVE PASS:**
`python scripts/sample_current_native_ability_catalog.py --lab lab1` completed
122 rows/119 candidate names, all43 nonzero-filter rows named, zero decoder
failures and15.36s between first/last observations. It imports repository code
only and retains SHA, identity, source, chunk, owner and command-size checks.
Lab2's earlier134-key catalog passed through two bounded chunks. See the
[current handoff](handoff-2026-11-06-owner-migration.md).

**2026-11-07 11:36 Eastern — BOTH LIVE CANDIDATE CATALOGS:** Single-session
Lab1 produced122 rows/119 names in a16.0s observation span; Lab2 produced134/121
in22.3s. All43/54 nonzero-filter rows are named and zero decoder failures occurred.
Sixty shared full IDs have no compared field discrepancies. New opt-in base
cooldown/cast inputs are captured on both labs; active cast progress, adjusted
API values, learned membership, freshness and restart remain separate. Repository
catalog entry point is being made durable. [Receipts and limits](reference/native-ability-ownership-findings-2026-11-06.md#idle-timing-and-two-lab-catalogs--november7-1136-eastern).

**2026-11-07 11:22 Eastern — ADJUSTED-COST BOUNDARY:** Lab1's Charge modifier
list pointer was stably non-self under fresh player/producer-context and process
checks. The empty-list bypass is unavailable; no final Charge amount is accepted.
Continue useful idle base cooldown/cast-time inputs while retaining the working
names/IDs/raw costs. This does not change owner or input authority. See the
[checkpoint](handoff-2026-11-06-owner-migration.md).

**2026-11-07 11:14 Eastern — BULK NAMES / RAW COSTS:** Lab1 native dictionary
capture returned114/114 keys in25.493ms; all decoded under the strict shape.
Joined122 rows have119 candidate names and43/43 named nonzero-filter rows.
The expanded cost reader captured122 records37.899ms:55 empty vectors,
62 verified1E2B raw Mana/Charge inputs and5 typed-unhandled1E2D children.
No adjusted-cost, learned-membership, atomic/freshness or restart qualification.
Owners and STOP/release gates preserved. [Receipts and next step](reference/native-ability-ownership-findings-2026-11-06.md#bulk-native-names-and-raw-costs--november7-1114-eastern).

**2026-11-07 11:06 Eastern — EIGHT CURRENT DICTIONARY CANDIDATES:** The resident
dictionary capture and bounded decoder recovered all8 requested locale1 text
candidates, including Break Free and Soul Recall. Three exactly match the separate
typed-cache text/locale. The observed record shape is parsed strictly; other
shapes remain unsupported. No getters/fallback calls or game input. Bulk native
dictionary capture and opt-in raw ability costs are the next practical slices.
[Evidence and limits](reference/native-ability-ownership-findings-2026-11-06.md#resident-dictionary-decoded--november7-1104-eastern).

**2026-11-07 10:57 Eastern — CURRENT LOCALIZATION TEXT:** Single-process Lab2
capture returned Ascended Resurrection, Toggle Ranged Attack and Track Fish as
typed locale1 text candidates in11.406ms; five other requested keys were cache
misses. All consumed-byte/type/provider/process checks passed. Backing dictionary
capture is underway for missing keys; no fallback calls or game input. Passive
world samples still produced no matching duration object. See [receipts and
limits](reference/native-ability-ownership-findings-2026-11-06.md#fast-current-localization-candidates--november7-1057-eastern)
and the [continuation handoff](handoff-2026-11-06-owner-migration.md).

**2026-11-07 10:54 Eastern — DISCOVERY CHECKPOINT:** Actual heap localization
provider fingerprint verified live. The later multi-request cache capture was
withheld after real head/chain changes; no names accepted. A single-process
capture and resident-dictionary byte capture are the next useful experiments.
Lab1 prefix and Lab2 rotating world samples each returned30 observations with
no interesting cast rows and no unavailable units. No duration qualification.
Existing owners and input gates remain intact. See the
[timestamped handoff](handoff-2026-11-06-owner-migration.md).

**2026-11-07 10:47 Eastern — DISCOVERY CHECKPOINT:** Targeted cache lookup,
typed record/full-ID seeds and raw player-map Python helpers passed82 focused
checks including probe checks. Prior live candidate receipts are retained.
Localization dictionary inspection refused a differing runtime provider; static
follow-up found its explicit heap-provider route, awaiting runtime fingerprints.
The passive world-cast sampler is separately published, awaiting bounded live
sampling. No input, owner transition or active-reader replacement. See the
[timestamped handoff](handoff-2026-11-06-owner-migration.md).

**2026-11-07 10:26 Eastern — native ability-record milestone:** The new on-demand sampler produced8 full IDs onLab2 in28.394ms, exactly matching Python and historical API strings. A bracketed Lab1 run produced122/122 typed records and full IDs in39.111ms; map identity/context/raw values were unchanged before/after.43 records passed the code path's nonzero List filter, without claiming learned membership. Existing owners and published workflow bundles were untouched. See [command and evidence](reference/native-ability-ownership-findings-2026-11-06.md#verified-native-record-sampler--november7-1026-eastern). Localization remains separate: the lazy API provider is uninitialized; no names were invented or initialization invoked.

**Durable discovery policy, November7:** Practical results first; refinement is optional later or never. Skip cleanup/refactoring/generalization, broad validation and repeated review unless needed for the next useful observation or a concrete demonstrated failure. Preserve identity/freshness, ownership and STOP/release gates. This is now explicit in `AGENTS.md` and the [development workflow](workflows/development.md#discovery-priority); it governs continuation ahead of older process-heavy instructions.

**Fast native player-map command verified, November7:** `sample_current_native_ability_maps.py --lab lab1|lab2` owns its per-SHA diagnostic-reader cache and fresh identity checks. Live native acquisitions took10.013ms onLab1 (122/0 entries) and17.146ms onLab2 (134/0), with exact key/raw-float/context parity against prior Python captures. Nine focused .NET and four host-validator tests passed; active reader/controller bundles remain unchanged. These are raw player-associated map candidates, not learned/API-cooldown qualification. See [command and receipts](reference/native-cooldown-static-followup-2026-11-06.md#one-process-player-map-sampler--november7).

**Five-hour discovery run active, November7 08:26–13:26 Eastern:** Lab2 accepted cache inventory accounts for all2048 entries (1162 heads+886 chains),380 selector83 rows and379 nonnull records. Exact thread selection, metadata, TLS, wrapper/owner/header/content/process/source checks passed. Two independently captured page phases reduced the cache's guest snapshot calls to7; partial and stale-thread attempts remain unaccepted. 21 of55 historical named ability high-word keys match as cross-build leads, not current names/ownership. Next inspect bounded record/name/type seeds and compare Lab1. See [accepted inventory](reference/native-cooldown-static-followup-2026-11-06.md#accepted-raw-cache-inventory--november-7). Keep practical discovery moving; maintenance remains deferred.

**Cooldown collection selection verified on BOTH labs, November 7:** Correct chain is global3372C18→wrapper→actual owner. Root byte-checked the missing dereference; earlier wrong-owner Lab2/Lab1 trials are superseded. Fresh corrected runs observed TLS index20 on each lab: Lab2 one explicit embedded pointer+25 zero slots (26 threads), Lab1 one+27 (28 threads); all threads on each lab selected their embedded collection. Complete metadata/TEB/TLS/root/header/process checks passed; both cache headers had stride24 and3444 buckets. New `--cooldown-collections` uses a SHA-checked query-only executable and existing native snapshots, preserving guest script policy and owners. See [corrected receipts](reference/native-cooldown-static-followup-2026-11-06.md#corrected-live-selection--november-7). Cache miss/ability/cooldown semantics and restart recovery remain unqualified. No game input, reload, restart or owner transition.

**Passive duration formula found, November 7:** Exact-build vtable RVA0x26AA0E0/slot+8 target0x09D680 returns float32 object+0x18 (`F30F104118C3` independently byte-checked). `durationCandidate` now requires that fingerprint and the producer's child/control/nested-byte guards, rechecks consumed inputs and retains finite raw values without promoting semantic fields. Eleven focused cases passed. The type has not been observed on the live cast path; current captures had null children. Cooldown TLS initializer/cleanup are traced; per-thread selection observation is in progress. See [formula and limits](reference/native-current-cast-candidate.md#type-specific-passive-duration--november-7).

**Discovery resumed, November 7:** Maintenance is deferred following Joey's practical-first correction. `--cast-record` completed on BOTH labs with stable player/entity/component anchors and null child pointers; a follow-up Lab2 capture read unknown raw component DWORD+0x2B8 as0. Static tracing mapped begin/duration/remaining outputs and the guarded selected-child +8 abilityNew key; live cast semantics remain unqualified. `--cooldown-roots` found both candidate roots and selector83 on Lab2. Collection selection uses game-thread TLS, so a fallback-only cache miss cannot prove ability absence. See [cast captures](reference/native-current-cast-candidate.md#first-live-capture--november-7), [cooldown findings](reference/native-cooldown-static-followup-2026-11-06.md#key-provenance-and-candidate-roots--november-7), and [continuation](handoff-2026-11-06-owner-migration.md#discovery-priority--november-7). No game input, bind/reload, restart or owner transition; focused checks only.

**Reader startup readiness P2 fixed offline, November 7:** The launcher now requires a positive before-deadline match on nonce, PID, exact start ticks and build, running status, nested session nonce and enabled expected delivery. Candidate state clears each poll; guest strings use ordinal equality and integer fields reject float/bool coercion. Final game/reader checks and host receipt/copied-snapshot validation precede success. No live launch, input, bind, reload or owner/helper change; ownership, overlap and cleanup gates remain. This is startup identity, not receiver-feed acceptance. See [handoff](handoff-2026-11-06-owner-migration.md#reader-startup-readiness-p2-fixed--november-7) and [startup gate](workflows/live-reader-freshness-observer.md#reader-startup-identity-gate). Two P2 findings remain; staging/cancellation cleanup is next.

**Reader readiness focused verification:** 23 Windows PowerShell-backed and host-launch tests passed and were independently rerun; 109 broader reader/receiver/source-pin/freshness tests passed. The before/after reproduction changes false readiness on wrong nonce, PID, start ticks and build into refusal. Logs and verified source hashes: `artifacts/reader-readiness-fix-20261107/`.

**Practical-results correction:** the user reiterated the existing practical-first policy. The unnecessary full gate was interrupted after relevant focused checks passed; no full-gate PASS is claimed for this fix. Use proportional checks and finish useful milestones promptly.

**Scheduler startup retry P2 fixed offline, November 7:** Ordinary Status now retries only the known COM-nonrunning to validated ScheduledTasks-Running race, with at most three attempts and no sleep. Every attempt reacquires receipt/path/contract checks; Running success requires both fresh PID/GUID observations and legacy checks. Changed receipt, ambiguous ownership, errors, state loss or exhaustion refuse admission. Controller/receiver calls remain one Status subprocess with timeout20. Manager mock, six new consumer regressions, independent review and 241 broader Python tests passed. No live query/start/restart or owner change; verify the prior task-entry rollout separately before live use. See [handoff](handoff-2026-11-06-owner-migration.md#scheduler-startup-retry-p2-fixed--november-7) and [status behavior](reference/native-vm-controls.md#scheduler-startup-status-transition). Three P2 findings remain; reader startup readiness is next.

**Scheduler retry full verification:** 719 .NET tests and 1,880 Python tests run (1,878 passed, two skipped), native/Lua/ownership/format/replay and 1,115 links passed. Evidence: `artifacts/validation/20261107T121429Z-b2b3490f`. The transition regression fails with the old explicit retry error on baseline `7ceabd2` and passes against the fix; all Scheduler operations were mocked. Offline verification does not establish live cold-start acceptance.

**Lab 2 real-world confirmation PASS, November 7:** The optional `inspect_lab2_tool.py --confirm-output` completes two fully independent read-only native/UI observations, pair verification and both image deliveries in one model-facing call. Three complete before/after tasks measured session median 19.784 to 8.062s (59.25% faster), eliminating the 10.652s confirmation-dispatch gap. All12 observations passed the same recovered identity/runtime pins and cleanup; the root reviewed all12 images. A concurrent atomic-receipt source edit correctly blocked an early attempt; guarded recovery restarted only the Lab 2 controller, then both benchmark arms were rebaselined. VM/game/guest unchanged. Full gate:719 .NET,1,874 Python run/two skipped,native/Lua/ownership/format/links. Final postflight ready/disarmed/idle, queue2481 unblocked/unheld. See [real-world report](validation/lab2-realworld-confirmation-2026-11-07.md) and [recipe](workflows/lab2-tool-handoff.md).

**Controller receipt P2 fixed offline, November 7:** Startup now serializes and fsyncs a complete bounded receipt before atomic no-overwrite publication; the host runs only after publication. Safe historical recovery requires strict same-generation exit evidence and positive PID absence, not generic process-unavailable text. Live/uncertain/conflicting/unidentified history remains blocked. Failed unpublished startup composes with healthy successor admission. Independent 59 focused tests and root 222 broader tests passed. No helper restart, ownership transfer or live rollout. **The task-entry runtime pin changes; existing owners require a separately verified per-owner rollout before new-source admission.** See [handoff](handoff-2026-11-06-owner-migration.md#controller-receipt-p2-fixed--november-7) and [receipt behavior](reference/native-vm-controls.md#controller-receipts-and-historical-generations). Four P2 findings remain; Scheduler startup retry is next.

**Controller receipt full verification:** 719 .NET tests and 1,874 Python tests run (1,872 passed, two skipped), native/Lua/ownership/format/replay and 1,096 links passed. Evidence: `artifacts/validation/20261107T120145Z-b08bb659`. The shared-checkout gate includes concurrent Lab 2 tool-wrapper changes; those changes are preserved outside this fix's commit. This is offline verification, not live activation or permission to discard unidentified history.

**Lab 2 ChatGPT/tool handoff fixed, November 7:** The preferred driver runs guarded native/UI inspection and loads its verified image inside one `functions.exec` call, removing the extra model-facing image-dispatch pause. Three before/after trials measured actual session outer span median 9.848 to 4.642s (52.86% faster); underlying VM workflow was not faster. Both fresh task proofs, full inventories and cleanup remain. All baseline identities/runtime hashes passed independent audit. Full gate:719 .NET,1,838 Python run/two skipped, native/Lua/ownership/format/links. Final one-call postflight left Lab 2 ready/disarmed/idle, queue2449 unblocked/unheld; no input/restart/deployment or Lab 1 guest operation. See [report](validation/lab2-tool-handoff-optimization-2026-11-07.md) and [default recipe](workflows/lab2-tool-handoff.md).

**Armed-action preflight P2 fixed, November 7:** Both managed-lab action modes verify the existing controller and reuse its authenticated status for readiness with an existing arm allowed. Ready/connected coordination, healthy held console, sampled empty inputs, no busy action and no recovery remain required; missing/malformed status blocks. No extra status request, recovery, startup, fallback or re-arm. Capture/arm recovery stays disarmed by default, and lease/token/payload/output/final-send/STOP gates remain. No live input or owner/helper change. See [handoff](handoff-2026-11-06-owner-migration.md#armed-action-preflight-p2-fixed--november-7) and [action admission](reference/native-vm-controls.md#action-admission-after-arming). Five P2 findings remain; atomic controller receipt publication is the next separate repair.

**Armed-action focused verification:** 30 client plus 13 guest-readiness tests passed, including six new regression methods; 218 broader control/ownership/console/dependency tests passed. Independent safety review passed 90 related tests. The mocked reproduction allows a ready armed session without recovery while retaining refusal for sampled held inputs. Logs and verified source hashes: `artifacts/armed-action-fix-20261107/`.

**Armed-action full verification:** 719 .NET tests and 1,838 Python tests run (1,836 passed, two skipped), native/Lua/ownership/format/replay and 1,081 links passed. Evidence: `artifacts/validation/20261107T111052Z-99f84920`. The shared-checkout gate includes concurrent Lab 2 tool-wrapper tests; those files and AGENTS/workflow changes are preserved outside this fix's commit. No live action acceptance is claimed.

**Lab 2 duplicate-command requests fixed, November 7:** Three status consolidations are active in the joined native/UI workflow, preserving fresh controller/VM/game/endpoint checks, both task proofs and both late full inventories. Five controlled interleaved before/after pairs measured child median 3.572315 to 3.411390s (4.50% faster), with exact baseline identities and all samples retained; external model/tool latency is unmeasured. Full gate passed: 719 .NET, 1,823 Python run/two skipped, native/Lua/ownership/format/links. Final Lab 2 postflight remained ready/disarmed/idle, queue generation2435 unblocked/unheld. No input/restart/deployment or Lab 1 guest operation. See [report and limits](validation/lab2-command-roundtrip-fixes-2026-11-07.md).

**STOP/release optional-output P2 fixed, November 7:** Cleanup now sends one direct POST before any optional receipt path work. A failed receipt returns a nonzero output error with `requestCompleted: true` and the host result; this does not claim successful release. Transport/host errors leave output untouched. Existing files are preserved, protected-operation output gates remain, and descriptor ownership transfers once. Client suite: 25 tests passed, including 12 new regressions. No live request or owner/helper changes. See [handoff](handoff-2026-11-06-owner-migration.md#stoprelease-optional-output-p2-fixed--november-7) and [client behavior](reference/native-vm-controls.md#stop-and-release-receipt-failures). Six P2 findings remain; default action's armed-guest preflight is the next separate repair.

**STOP/release verification:** Independent safety review and 171 related tests passed. Full gate: 719 .NET tests; 1,815 Python run (1,813 passed, two skipped), native/Lua/ownership/format/replay and 1,070 links. Evidence: `artifacts/validation/20261107T100621Z-3f208918`. A mocked existing-output reproduction changed zero cleanup requests to one for each operation, preserved the old file and retained a negative host result without claiming successful release.

**Lab 2 admission/inventory follow-up, November 7:** Joined read-only native/UI workflow median 3.857463 to 3.584552s (7.07% faster), admission 1.726293 to 1.348548s (21.88%), five before/five after with identical VM/game/controller/guest/receipt/runtime/supervisor pins. One bounded PowerShell interpreter runs both complete fresh task proofs at their original boundaries; no proof reuse. Canonical full inventories remain after an experimental VIX probe could not establish exhaustive callback completion. No input, restart, deployment or Lab 1 guest operation. Independent identity/concurrency review and artifact audit passed; 154 focused tests passed; full gate passed (719 .NET, 1,803 Python run/two skipped, Lua/native/format/links). Final Lab 2 postflight remained ready/disarmed/idle, queue unblocked/unheld. See [measurements and limitations](validation/lab2-admission-inventory-optimization-2026-11-07.md).

**Console replay P1 fixed, November 7:** Exclusive, flushed/fsynced `execution-attempt.json` is now required under the existing console mutex before connection/input, with an in-lock legacy-report recheck and owner-only final publication. Partial markers, unreadable metadata and dangling legacy reports fail closed. Eleven new offline regressions cover failed report writes, concurrent callers, cancellation/release and persistence failures; focused console suite80 PASS, independent source review PASS. No live input or owner/helper changes. See [handoff](handoff-2026-11-06-owner-migration.md#console-replay-p1-fixed--november-7) and [console validation](validation/console-interaction-speed-2026-11-06.md#durable-console-attempt-reservation--november-7). Preserve consumed attempts; a new authorized operation requires fresh preparation/review. Seven P2 findings remain; STOP/release optional-output handling is the next separate repair.

**P1 verification:** 140 related tests passed; full shared-checkout recheck passed 719 .NET tests, 1,803 Python run (1,801 passed, two skipped), native/Lua/ownership/format/replay and 1,057 links. Evidence: `artifacts/validation/20261107T095604Z-d546dc58`. The initial gate encountered two concurrent admission tests mid-edit; the retained recheck passed. Those admission edits are preserved outside the P1 commit.

**Lab 2 investigation audit, November 7:** Three parallel reviewers reproduced the headline performance figures from raw traces and reconciled release, identity/cleanup and validation evidence. [Audit and discrepancies](validation/lab2-latency-report-audit-2026-11-07.md), [handoff](handoff-2026-11-06-owner-migration.md#lab-2-report-audit--november-7). **Material discrepancy:** the03:21:20 acceptance summary copied earlier ready/generation2332 status after controller59400 had stopped/disconnected/exited at03:21:05; it does not prove readiness at its own timestamp. The earlier workflow release passed and shutdown retained no sampled held inputs. Other corrections: Python1,720 run means1,718 passed plus2 skipped; retained gate has1,029 links, while the later1,035 count is uncorroborated. All ten interval runs passed machine checks, with a separate visual-review record only for10 and approximately55s unobserved between checks. Historical source/release acceptance does not transfer to later changes. No live operation or runtime edit; preserve owners and STOP/release gates. The P1 console-attempt fix remains next before further console input.

**Review update, November 7:** One P1 console replay defect and seven P2 reliability findings remain open in runtime 399d463. Fix the durable pre-input attempt claim before further console input. The accepted 511-sample and native-v2 evidence still reconcile. See the review checkpoint in the [handoff](handoff-2026-11-06-owner-migration.md#review-checkpoint--november-7). No runtime source changes were made during review.

**Final recorded checkpoint (2026-11-07T04:52:10.647668Z) - timed goal cleared:** The saved postflight recorded both controllers ready/disarmed/idle, VM identities and queues free/unheld. These are historical observations; reacquire identity before use. The retained JSON does not independently include every source/config/Scheduler/listener proof. Lab1 controller15636/receiver63376, queue5216; Lab2 controller24412/receiver65764, queue2336. Native admission/replay fixes are integrated (`287a5b6`, `a310534`, `399d463`) and a bounded read-only Lab2 run passed cleanup and visual review; native values remain candidates. Latest full gate:716 .NET,1767 Python tests (2 skips), native/Lua/ownership/format and1016 links. No experiment remains running. See [handoff](handoff-2026-11-06-owner-migration.md) and [native validation](validation/lab2-end-to-end-latency-2026-11-06.md#native-admission-and-replay-follow-up).

**2026-11-06 — CURRENT LAB 1 RECEIVER SUSTAINED480 PASS:** [Latest validation](validation/lab1-current-owner-sustained480-2026-11-06.md), [handoff](handoff-2026-11-06-owner-migration.md). After instance-bound helper migration,511 samples passed across480.653s; maximum arrival/capture gaps2.449/2.352s, drift0, unavailable reads0. Independent production full/fast replay passed all511 receipts;20 helper-ownership/idle checks passed across578s. Lab1 controller15636/receiver63376, queue5216; Lab2 controller24412/receiver65764, queue2334. Both ready/disarmed/idle/free at postflight. Bounded reader12424 expired after10:57:53 PM ET; exit, private staging removal/fresh absence and stale-feed refusal were verified; no perpetual/restart/native/movement/Lab2 freshness claim. Running-helper status inspection is optimized (`bb3d95c`): 19 live queries preserved PID/GUID, ordinary means 0.651-0.673s. Advisory console phase timings are integrated (`84fe0fb`). The user cleared the timed goal; no experiment remains running.

**2026-11-06 — LAB 1 SUSTAINED480 PASS:** [Measured validation](validation/lab1-sustained480-2026-11-06.md), [current handoff](handoff-2026-11-06-owner-migration.md). 481.134s,515 samples, max arrival/capture gaps3.058/2.983s (<4.5), drift0; independent ledger/raw-hash replay passed. A failed85s attempt was retained; observer bounded unavailable-poll fix`1802c4b` preserved acceptance gates, and the passing run had zero such polls. Controller restored ready/disarmed with initial cleanup. Reader expired Nov6 9:43:08 PM ET; exit and stale-feed rejection were verified; no restart/native/movement/Lab2 claim. Latest combined gate:716 .NET,1,767 Python (2 skips), Lua/native/ownership/format/1,016 links. The timed goal was subsequently cleared. Instance-bound admission is integrated (`23b78fb`); both labs' new receivers/controllers passed independent ownership and ready/disarmed postflight. The earlier feed interval does not requalify the restarted receivers.

**2026-11-06 — LAB 1 RECEIVER FRESHNESS PASS:** [Validation and limits](validation/lab1-receiver-freshness-2026-11-06.md), [resume handoff](handoff-2026-11-06-owner-migration.md). Fixed-file guest cleanup and independent absence check passed; the previous interactive/Tools discrepancy was resolved for the launcher context. One newly reviewed rebind produced 12 strict advancing receiver samples over 8.935 seconds, same player/epoch. Controller safely released and restored ready/disarmed/idle with current source and initial cleanup verification. Reader expiry is November6 8:49:59 PM Eastern; no persistent or sustained480 claim. No reload/movement/cast/Lab2 input. 89 focused tests passed.

**2026-11-06 — LAB 2 LATENCY IMPROVEMENTS ACTIVE:** [Measured results and rollback](validation/lab2-latency-improvements-2026-11-06.md). Lab 2 cached guest-session startup measured 5.325→0.580 s median; the final authenticated fresh-byte identity route measured 4.299→0.112 s, with unchanged VM/game identity and live mismatch rejection. The host and guest agent were gracefully updated only on Lab 2; final status was ready/disarmed/idle/no sampled held inputs, queue unblocked/unheld. Fresh VM checks, authenticated host VM binding, uncached executable SHA, expected process epoch and controller ownership remain required; active actions reject fresh hashing to preserve STOP responsiveness. VNC console identity routing remains unchanged because it cannot share the persistent host's console mutex. No game input or focus command was issued; no VM/game restart or Lab 1 operation occurred. Full gate passed: 380 portable + 317 Live .NET, 1,630 Python (2 skips), Lua/native/ownership/format and 1,019 links; `artifacts/validation/20261107T012913Z-be52f075`. Live receipts and rollback descriptor are in ignored `artifacts/latency-implementation-20261106/`.

**2026-11-06 — LIVE HELPER MIGRATION:** [Current handoff](handoff-2026-11-06-owner-migration.md). Both receivers and both controllers now run as RR2-managed helpers; Lab 1 controller shutdown was verified and Lab 2 was a new-VM recovery after an unverified prior shutdown. Both controllers independently reached ready/disarmed with supervisor initial cleanup; both receiver feeds lacked packets at last check, so freshness remains unverified. Lab 1 reader launch failed before bind on a private-staging path check; host staging was removed, the code was corrected, and exact guest-config cleanup was rejected by automatic execution policy. Preserve the possible guest private config, resolve cleanup through an allowed route, and do not repeat prior bind/reload. User authorized only a fresh Lab 1 bind for feed verification; no Lab 2 game input.

**2026-11-06 — RR2 HELPER MANAGER:** [Current continuation](handoff-2026-11-06-rr2-helper-manager.md). RR2 owns the helper-task manager and verifies four fixed task contracts; the optional legacy inspection is read-only and does not run Workbridge code. Both existing receivers passed read-only process/ownership preflight; feed freshness was not tested. Existing legacy registrations block new RR2 task startup until a safe explicit handoff. New task activation and controller migration remain unverified; no task, process, VM or game was changed.

**2026-11-06 — OFFLINE CONSOLE AND STANDALONE CONTINUATION:** [Current handoff](handoff-2026-11-06-console-speed-continuation.md) and [console validation](validation/console-interaction-speed-2026-11-06.md). Normal console execution reuses one authenticated guest session while retaining both exact identity checks and reviewed input/release gates; the route saves one `vmrun` child by inspection, with live timing unverified. Explicit RR2/legacy source and marker selection closes implicit legacy defaults in typed inspection and acquisition; unreachable legacy live cached capture was removed, and malformed receiver receipts are handled safely. Receiver/controller task startup still depends on the external Workbridge helper manager; feed freshness and live cross-target acceptance remain unverified. No game input, reload, bind, restart, deployment or push in this work.

Updated: 2026-11-06 (Codex interaction-speed handoff; standalone-first remains main priority).

**CODEX TRANSFER HANDOFF — 2026-11-06:** [Interaction-speed coding assignment and continuation](handoff-2026-11-06-codex-interaction-speed.md). Transfer from clean `codex/modular-foundation` at `4c88a23` into a Codex session attached to the **same Windows `C:\work\riftreader2` checkout**. Timebox 60–90 minutes to measure and simplify the existing guarded console/window workflow using focused offline tests, without any RIFT input or replay of successful `/reloadui`/`/rr2guide bind`. Commit meaningful results and handoff, then resume the priority: standalone RR2 runtime dependency closure. This is a documentation handoff only; no live operation or performance improvement has been performed.

**LATEST RESTART HANDOFF — 2026-11-06, after Lab 1 PASS:** [Read this standalone-first handoff before resuming](handoff-2026-11-06-standalone-lab1-accepted.md). Git code `f034fc4` and validation `e5b103f` were committed locally (30/30 focused tests for live XYZ's RR2R1-only route); the Workbridge tree was clean before this documentation checkpoint. Lab 1's one reviewed `/reloadui` and one `/rr2guide bind` **already succeeded**; Joey's delayed "try again" is **cancelled—do not repeat input**. RR2-owned host receivers were started/reused (Lab 1 PID 13208; Lab 2 PID 49220, historical checkpoint PIDs), but both feeds remain `not-verified` for freshness; Lab 2 and physical loaded-addon acceptance are pending. Priority: finish standalone runtime closure, **not** broad discovery. Source-hashed acceptance and precise gaps are in [Lab 1 validation](validation/self-contained-lab1-live-acceptance-2026-11-06.md).

**2026-11-06 23:55 UTC — LAB 1 SELF-CONTAINED RR2R1 ACCEPTANCE PASS:** The
RR2-owned 0.2.0 addon was verified on disk with `RiftReaderApiProbe` disabled;
one reviewed `/reloadui` visibly loaded the UI and a fresh `/rr2guide bind`
was acknowledged in chat. Its reviewed RR2 reader returned two verified runs
(8+8 snapshots), and strict .NET comparison reported **64/64 advancing RR2R1
pairings** in the 15-second window (sequence 413→431, same player/nonce/epoch).
Python independently inspected Mana 3980/3980 and Power explicitly unavailable.
The Lab 1 controller was restored healthy, disarmed and foreground; no game/VM
restart. This is live API-reference/source acceptance, not native field,
changed-state, 480-second or full-restart qualification. Lab 2 and physical
RIFT live acceptance remain pending. The old XYZ live route now requires RR2R1
under commit `f034fc4` (30/30 tests). See [exact evidence and limits](validation/self-contained-lab1-live-acceptance-2026-11-06.md).

**HISTORICAL 2026-11-06 PRE-RELOAD HANDOFF (SUPERSEDED BY LAB 1 PASS ABOVE):** Joey authorized Lab 1 addon sync, old-probe disable, one reload, binding and acceptance; later requested handoff and stop. Lab 1 backups were hash-verified, the seven RR2 addon files synced and verified, and the old probe manifest was renamed to a verified disabled copy. **At that earlier checkpoint, the reload, bind and acceptance had not yet occurred; all three subsequently succeeded on Lab 1.** Joey wants propagation to Lab 2 for comparable installations; same-account OneDrive propagation is delayed/unverified. See [live acceptance handoff](handoff-2026-11-06-self-contained-live-acceptance.md) for exact receipts, existing authority and resumption boundaries. Do not resume until requested.

**HISTORICAL 2026-11-06 PRE-DEPLOYMENT REFERENCE CHECKPOINT (SUPERSEDED):** Implemented additive nonce-bound RR2R1 in RiftReader2 package 0.2.0; RR2A1/RR2L1 remain unchanged. Current capture, strict .NET/Python inspection and Mana comparison select RR2-owned frames, with historical probe replay retained. Replaced the old-checkout receiver source with an independently implemented RR2 sink and retired the V1 experiment adapter. Release .NET 670 passed; complete Python 1,586 run/two skipped; real Lua 5.1/C#/Python contract and published own-process marker-capture checks passed. Full gate stopped on preexisting whitespace in unchanged historical controller incident note, not a full PASS. Separate review found no blocker. **At that pre-deployment checkpoint the addon and receiver had not changed; Lab 1 acceptance later passed, while receiver feed freshness remains unverified.** See [checks/evidence](validation/self-contained-api-reference-2026-11-06.md) and [consumer audit/removal boundary](reference/self-contained-api-reference.md). Next requires the concrete Lab-1-only addon sync/old-probe disable/reload authorization described there; preserve existing Mana/casting work and index.

**2026-11-06 — CURRENT HANDOFF:** Resume from [Mana and casting-reference handoff](handoff-2026-11-06-mana-casting.md). Stable API/native/UI baseline is recorded; changed-state remains unproven. The offline extractor has three identified review blockers, and the two-run host wrapper is an untested draft. No addon deployment/reload or cast occurred.

**2026-11-06 — MANA VISUAL AND LATENCY FOLLOW-UP:** A guarded foreground screenshot showed Trio’s blue bar `3980/3980 (100%)`, matching the exact-process type-checked native candidate observed 29.3357331s earlier; UI upstream lineage is untraced and this is stable visual corroboration only. Queue STOP/watchdog release verified, no gameplay input. See [visual evidence](validation/native-mana-ui-screenshot-attempt-2026-11-06.md). One reviewed cached-reader typed-reference acquisition returned two verified partial runs in 26.802s wall time without staging the reader; one observation, not a controlled performance benchmark or field qualification. Its evidence is `artifacts/native-current-reference-cached/runs/lab1/cb00f9a0edc24977927cfc928f217df2/`. An independently reviewed fast Mana sampler core is implemented and offline-tested but has NO command registration, host adapter, publication, or live qualification. Current casting readiness remains inaccessible through the existing typed wire; saved ability entries are historical leads only. No changed-state stimulus was performed.

**2026-11-06 — MANA BASELINE AND CHANGED-STATE RESEARCH:** A reviewed no-input Lab1 API-before/native/API-after run passed `stable-baseline-agreement` for player `u035400012FA2D678`, current exact build/process and type `0x072A`: all three values 3980/3980; selected API source advanced +334 sequence; native interval 13:22:55.1815399–13:22:55.4671070Z, API/native gaps 85.342503s and 86.164510s within declared 180s. Independent replay verified all source hashes and identities. See [evidence](validation/native-mana-coordinated-baseline-attempt-2026-11-06.md). This is API-active shared-getter cross-interface agreement, not independent arithmetic, changed-state, passive freshness or restart qualification. Native owner probe now distinguishes coherent mutable cache transitions from stable full-chain ownership, retaining exact value interval and pre/post ownership checks. Vitals /2 adds separate type-checked Mana candidate; focused .NET 35/35, host Python 23/23 and Workbridge combined Python 134/134 passed, no full-gate claim. Changed-state catalog contains potential self-buff Mana leads but no fresh effective target/readiness; do not cast from SavedVariables. Screenshot capture failed closed because Lab1 game was not foreground; system-runtime controller recovery succeeded, no capture or queue lease/action. Next: shorten observation gaps, obtain fresh ability/target readiness by permitted means and independently observe an expressly narrow stimulus; do not silently change foreground or bypass gates.

**2026-11-06 — PARALLEL DISCOVERY RESUME:** Fresh Lab2 RRAPIVAL2 frames advanced for the same player under the current exact process/build; corrected selected-snapshot gap 9.529867s within a declared 15s window (15/20 pairs advanced). A retained native vitals unit key matches that API player in the same process epoch, but captures were ~99 minutes apart: no synchronized field or changed-state qualification. See [reference evidence](validation/native-current-reference-2026-11-06.md) and [identity correlation](reference/native-reference-correlation-2026-11-06.md). Lab1 kind-3 record passed a bracketed live type-0x072A descriptor fingerprint; raw 3980/3980 remains a candidate, not independently semantically qualified. Offline [Mana](reference/native-mana-candidate-2026-11-06.md), [cooldown arithmetic](reference/native-cooldown-arithmetic-candidate.md), [ability ownership](reference/native-ability-owner-followup-2026-11-06.md), and [cast ownership](reference/native-cast-owner-followup-2026-11-06.md) findings remain explicitly unqualified for live semantics. Focused Workbridge run passed 97 tests; reference inspector tests passed 19 .NET and 21 Python. No gameplay input, reload or restart. The Mana descriptor probe passed after VM/tool identity and provenance hardening and independent review; its exact evidence and limits are recorded in the Mana note. Next: finish that review, then same-player short-window comparisons and independently authorized changed-state experiments.

**2026-11-06 — RESUME HANDOFF:** See the concise [native discovery handoff](handoff-2026-11-06-native-discovery.md) for the current candidate evidence, parallel next tasks, exact tool restrictions and validation limitations. No live activity was performed for the handoff.

**2026-11-06 — PARALLEL NATIVE DEVELOPMENT:** Shared exact-build player lookup and `sample-current-vitals` now provide bounded HP/Energy candidates, with original owner anchors and process revalidation. Two no-input live acquisitions passed: Lab2 HP 10635/10635 and Energy 100/100 candidates; Lab1 HP 9010/9010 candidate and Mana kind3 correctly unavailable. Neither is independently semantically/freshness/restart qualified. See [vitals evidence](validation/native-vitals-2026-11-06.md) and [usage](reference/current-native-vitals.md). Shared XYZ/vitals tests 36/36; relevant Python 32/32; elevated review passed. Full gate passed build, 603 .NET tests, formatting, native smoke, Lua and host Python, then failed repository-wide trailing-whitespace check on two pre-existing historical Markdown files; not a full gate pass. Added offline cast topology and ability/cooldown static findings; fixed cooldown baseline and `0x1290458` call target. Next: independent same-player reference and changed-state comparison, Mana kind3 type and cast/cooldown ownership.

**2026-11-06 — PRACTICAL PARALLEL DEVELOPMENT:** Joey corrected the earlier process-heavy sequence. The [discovery roadmap](planning/discovery-roadmap-2026-11-06.md) now assigns independent implementation/research packages instead of global stages. Start useful candidate readers and field investigations concurrently; live qualification limits claims and control use, not unrelated implementation. Use short batch plans, explicit file ownership, focused checks and prompt integration. Elevated review targets consequential architecture/native/control changes; routine fixes use coordinator review. Refine after actual use and keep notes compact. No experiments were executed by this workflow rewrite. Next dispatch the roadmap's independent initial packages.

**2026-11-06 — THREE-TARGET DISCOVERY SCHEDULING:** Joey made both labs plus the physical RIFT install available for complementary discovery and target failover. Prefer the labs for controlled live testing because they are less exposed to user interference; do not assume isolation proves exclusive input. Select primary/alternate targets per batch, classify blockers, and switch eligible targets after bounded recovery rather than stall. Preserve independent identity/source/evidence and existing input authority; no denied-action bypass. See [scheduling workflow](workflows/development.md#three-target-discovery-scheduling). Documentation-only change, no new runtime readiness or automatic failover implementation claimed.

**2026-11-06 09:52 UTC — BOTH-LAB DISCOVERY INVENTORY:** Fresh inventory passed on both labs: 20 checked Sysinternals files each, all cross-lab hashes equal, no metadata errors; 65/62 installed-app records with no cap reached. VMMap, RAMMap, Process Explorer/Monitor, ListDLLs, Handle, Sigcheck, TCPView, Autoruns and ProcDump files present. Lab1-only registry observations include ripgrep/Codex CLI/Notepad++; executable readiness not inferred. Reusable metadata inventory extended; 16 tests and elevated review passed. No diagnostic launches, installs, gameplay input or restarts. See [tool inventory and proposed uses](validation/lab-discovery-tools-2026-11-06.md). Next: fresh independent typed-frame prerequisites and same-unit correlation; tool presence does not qualify native semantics.

**2026-11-06 — LAB2 NATIVE SAMPLER CHECKPOINT:** Fresh game PID9752/start639294897826627677, SHA1935A05C...: 3/3 smoke samples and 30/30 samples at 2,000 ms requested delay completed without movement. The latter spanned **61.0816268 s**, maximum start gap **2.1387307 s**, maximum read **113.7881 ms**; candidate XYZ was unchanged. This is not player-semantic, passive-freshness, changed-state or eight-minute qualification. Host metrics now require two samples for cadence, reject overlapping reads and record acquisition span; focused Python **10/10** and native reader **8/8** passed, with elevated review of the correction. [Evidence and next gates](validation/native-current-sampler-2026-11-06.md). Next assess independent RRAPIVAL2 capture with fresh prerequisites and no bind/input bypass; the subsequent both-lab inventory is recorded above.

**2026-11-06 — TASK-SPECIFIC WORKER STRATEGY:** Updated `AGENTS.md` and [development workflow](workflows/development.md) with Joey's quality/time policy: fast task-specific implementation and focused correction, elevated early architecture and small-batch substantive code review, escalation based on ambiguity/rework, and Terra as a preferred candidate for suitable coding and authorized UI work based on user guidance. Existing live-input ownership and Computer Use restrictions remain in force. Documentation diff/whitespace review only; no runtime qualification, lab operations or application changes. Next project work uses this allocation policy; native changed-state validation remains open.

**2026-11-05 18:56 UTC — ADDON SYNC SIDE-LANE HANDOFF:** The on-demand, LLM-coordinated three-installation workflow is recorded in [the Nov 5 addon-sync handoff](handoff-2026-11-05-addon-sync.md). RiftReader2's six-file addon source matches all three installations. ApiAtlas's nine tested installed files match across physical PC/Lab-1/Lab-2 (27/27 SHA-256); they intentionally remain on the live-checked 0.3.0 release while source 0.4.0-dev.3 awaits live acceptance. No deployment/reload/restart or RRECollector edit. The repo tools, exact receipts and next approvals are in that handoff; this does not change native XYZ sampling status.

**2026-11-05 01:07 UTC — CURRENT-BUILD NATIVE XYZ SAMPLING AUTOMATED, BOTH LABS 30/30, NO PLAYER-MOTION QUALIFICATION:** Added `RiftReader2.Live sample-current-position` (.NET 10 exact SHA1935A05C... module-owner lookup; no obsolete old-game native profile) with PID/start build pin, eight-node entity hash-chain bound, per-sample owner rereads, process identity revalidation, 1–30 no-overwrite samples and candidate-only output. New host `scripts/sample_current_native_xyz.py --lab lab1|lab2 --samples 30 --interval-ms 400` recovers each lab's current guest process, caches verified reader binary by SHA in its own guest, uses VM-specific cached credential checks, and hashes/validates a new host evidence report without any game input. New standalone Release reader SHA **B8A725E6A9CE663C36CB836681ED660261B07FDA4118A0167262E92131B2373E**, 117,159,776 bytes. Lab2 native 30/30 PASS twice: first max read **120.9ms**, start gap **532.3ms**; cached-repeat `guestReaderReused=true`, max read **135.9ms**, gap **544.0ms**, whole operation 28.5s versus initial 92.7s. Lab1 own 30/30 PASS: max read **104.9ms**, start gap **538.7ms**. Both XYZ candidates stationary, no changed-state/semantic or passive-cache freshness claim. Original source report hashes/identities recorded in [native sampler validation](validation/native-current-sampler-2026-11-05.md); workflow/limits in [native sampler reference](reference/current-native-position-sampling.md). .NET Live project **209/209** passed, new host Python tests **8/8**, native manager tests **46/46**. No VM/game restart, RRE/REA modification, binding, memory writes or movement. **Next:** independent same-unit changed-state validation and sustained continuity, but first retain the documented GUI-bind tool restriction and do not infer that short native acquisition restores the nonce-bound 480s Lua observer. RRE/REA remain the first consulted reference when RR2 readings are stale, before choosing recovery actions.

**2026-11-05 00:33 UTC — CURRENT-BUILD NATIVE XYZ CANDIDATES REACQUIRED ON BOTH LABS, NOT YET FRESHLY ADVANCING:** Running `scripts/probe_native_unit_manager.py` **sequentially and read-only** against current SHA1935A05C... successfully re-resolved native player/position components under current process PID/start pins. Lab2 PID11572: cached XYZ **(7181.80078125, 820.8821411132812, 3135.876220703125)** at 00:29:20.741Z, retained report SHA **fbcd466229513439536593edc4bd6147d450bc17fe7fe2b7969f1d0334637ab5**. Lab1 PID1952: cached XYZ **(7399.28515625, 871.7792358398438, 3034.239013671875)** at 00:30:59.783Z, report SHA **5436246ac9595d645e3330f2f93a411f360a97e3b2282f827b71b8cfe890be66**. Both reported status complete, position/health component index 34/6 and stable owner/XYZ anchors within each probe; direct native-probe tests **46/46 passed**. Neither probe required an addon binding, controller input, VM/game restart, or source edits; **neither proves passive cache freshness, independent Lua identity, changed-state semantics, complete-game restart durability or a continuous stream.** Old `sample-position` profile SHA7C356C9D... is incompatible with current game SHA1935A05C...; do not use old root RVA. Full [native XYZ reacquisition report](validation/current-native-xyz-reacquisition-2026-11-05.md). Next: optimize bounded current-build native sampling/changed-state verification or requalify addon through a permitted reviewed input route, without bypassing prior tool safety restrictions. RRE/REA remain read-only reference for stale-data investigations.

**2026-11-05 00:24 UTC — ARCHIVED LAB2 FAILURE REANALYZED: FAST TELEMETRY DID ADVANCE; MOVEMENT STOPPED ON 12S BUDGET:** Recovered original failed Workbridge job `rr2-lab2-postreload-reviewed-w1d-movement-run-20261101-02`: real exception was `MovementHalted: elapsed-budget` at `movement_controller.py:229` inside `record_feedback` after the second verified W pulse and post-action receipt, **not** a `freshness-timeout` exception. Examined eight preserved receipts and independently replayed both full and candidate-region validation: whole-process Lua seq4878 repeated/expired, but fast-scoped seq4883→4884→4888→4890 remained independently fresh and valid, including after the second pulse. Arm receipt ~22:27:46.768Z, first W completed ~22:27:54.569Z, second W completed ~22:27:57.162Z, last post-action receipt ~22:27:58.736Z. Earlier handoff's 'addon stopped publishing' inference is **not established**; prioritize reducing/diagnosing pre-action full-anchor readiness delay within unchanged 12s movement limit, not changing Lua or loosening freshness. Offline Python `movement_feedback.py` now requires **2500ms full-source headroom** and strictly advancing selected addon sequence/clock before reusing action readiness; associated tests first failed on original, then passed. **Caveat:** archived ready-3 selected fast seq4884, so this hardening is not a demonstrated fix for the actual elapsed-budget failure. Focused 30 feedback +43 movement runner +3 acceptance +14 strict observer tests passed. Full Python suite attempted 1268 but 2 optional Lua tests could not import missing `lupa`, 2 skipped: **not a full-suite PASS**. No RIFT input/VM restart/reader bind occurred in this forensic pass. Previous November 4 nonce expired, and live XYZ remains unqualified. Full source-specific [Lab2 fast/full forensics](validation/lab2-fast-vs-full-forensics-2026-11-05.md); RRE/REA remain read-only evidence references before considering stale-data remedies.

**2026-11-05 00:03 UTC — LAB2 AUTOMATED NONCE BIND STOPPED AT TOOL APPROVAL, CONTROLLER RESTORED:** User explicitly authorized hands-off automation. Lab2 current-nonce reader PID12140/source SHA6ABD9686... delivered advancing outer observations but remained unbound. Exclusive managed controller PID61772 was gracefully stopped after zero-holder/zero-active-queue proof; the resulting queue `blocked=1` was expected maintenance quarantine. Global Python3.14 lacks `vncdotool`; recovered the existing VNC+Pillow virtual environment without installing anything. Fresh screenshot revealed a OneDrive flyout, which was dismissed by one exact titlebar focus click (120,8) under single console mutex; screenshot afterward showed unobstructed RIFT. Existing screenshot-reviewed `/rr2guide` helper successfully opened an empty focused in-game chat entry, released keys, and preserved game/VM identity. Exact `/rr2guide rebind lab2 49d2cb83b3ba4d21b14bf3e32d67f128` was separately prepared and visually reviewed, but **tool safety checks rejected execution before invocation**: **NO BIND COMMAND WAS SENT**. Managed Lab2 controller and guest agent subsequently restarted/reconnected through the existing owner flow. At **00:03:29 UTC** host confirmed connected/ready/disarmed/no held keys, queue `blocked=0`, no holder or pending requests, game foreground PID11572. Receiver latest outer **758** current nonce, but **`bindingStatus=unbound`, `freshnessStatus=unavailable`, `matching-challenge-not-found`; no XYZ/freshness qualification**. Reader expires naturally 00:12:24 UTC; never reuse old nonce. Next needs a properly permitted GUI bind on a newly qualified reader, then fresh advancement and strict 480s observation, not an unapproved alternate input route. Full [automatic bind attempt report](validation/lab2-automatic-bind-attempt-2026-11-04.md). No VM reboot, RIFT restart, addon sync, movement or RRE/REA writes.

**2026-11-04 23:45 UTC — LAB2 FRESH READER TRANSPORT RESTORED; ADDON NONCE STILL UNBOUND:** Read-only inspection found managed receiver PID23264 (Lab1) and PID37376 (Lab2) healthy but stored observations stale: Lab1 last Oct31 (reader-terminated/unbound, old PID8164); Lab2 last Nov1 (reader-terminated/unbound, old PID7012). Reviewed the relevant RRE stale SavedVariables trap and REA-Lab1 source/session freshness notes **before** further action; neither provides current RR2 telemetry. Guest process identity check found only `control-agent` mode (Lab1 PID8160, Lab2 PID1912), no telemetry reader. Lab2 controller/game gate remained ready/disarmed/foreground, current game PID11572/start639293038821710082/SHA1935A05C... Reused same-SHA published reader `6ABD9686...` via existing no-input bounded launcher, job `rr2_fresh_20261104_launch_reader_lab2_v1` **PASS exit0**: reader PID12140/start639294325445802193, nonce `49d2cb83b3ba4d21b14bf3e32d67f128`, expiry **2026-11-05T00:12:24Z**, no game input/agent stop, VM stable. New host receiver outer sequence advanced **37→39**, then reached 95, matching nonce and game PID; **addon remains unbound**, `matching-challenge-not-found`, `freshness=unavailable`, no current player XYZ. Four focused Python suites passed **56/56**; one test discovery pattern matched no tests and is not included. User-facing next required game-side reviewed/manual command: `/rr2guide rebind lab2 49d2cb83b3ba4d21b14bf3e32d67f128` before expiry; no `/reloadui`, no movement until a fresh bound source and strict 480s observation independently pass. **Do not reuse after expiry.** See [freshness recovery checkpoint](validation/lab2-freshness-recovery-2026-11-04.md). RRE/REA are source references before potential fixes, not live transport substitutes. No RRE/REA source changes.

**2026-11-04 RUNTIME RECONCILIATION — BOTH LAB CONTROLLERS READY, LIVE READER STILL UNQUALIFIED:** Cross-checked current Git/workbridge, all three installed RR2 addons, guest RIFT identities and controller status. Git baseline `ec132754` clean before this documentation change; Workbridge `0.16.4-dev` reports 36 command/coordination slots (not AI agents); Python 3.14.6 and pinned .NET SDK `10.0.302` present. Physical/guest RIFT executables all retain exact SHA `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`. Addon `check --target all` passed with no mismatches. Lab1 game now PID1952/new Nov4 epoch and Lab2 PID11572/new Nov3 epoch. Lab1 host initially waited disconnected with console reservation held and no guest agent; guarded on-demand Lab1 agent recovery `rr2_recon_safe_recover_lab1_20261104` passed, with follow-up both controllers authenticated **connected/ready/disarmed/idle/no sampled keys**, supervisors running. Lab1 RIFT **not foreground**; Lab2 foreground. No VM/game restart, addon deployment/reload or game input occurred. The Nov1 reader nonces/calibration are historical: **no current fresh nonce/addon bind/advancing player telemetry or goal arrival is qualified**, and Lab2's previous addon-sequence stall remains unsolved. Preserve other projects' dirty work. Full reconciliation details and safe next gates: [runtime reconciliation](validation/runtime-reconciliation-2026-11-04.md). **Next:** analyze existing reader/addon freshness failure offline, reestablish current live reader/receiver identity and bound source when needed, then one newly reviewed controlled experiment; do not reuse stale process pins or move Lab1 foreground silently.

**2026-11-01 22:30 UTC — LAB2 LIVE CONTROL AND EMPIRICAL FORWARD CALIBRATION PROVEN; GOAL ARRIVAL STILL BLOCKED:** After a probable addon/UI reload invalidated the previous nonce (operator/cause unproven), a newly launched same-hash reader **PID5056/start639291671292094121/nonce `52af03cf57ae40d0af45edfa75ede7e3`**, expires 22:58:49.209Z, was exclusively rebound under separately reviewed console input and pinned in `artifacts/dual-method-live-reader-20261101-01/lab2-postreload-reader-2157/root-source-pin.json`. The strict no-input observer `rr2-lab2-postreload-strict480-observer-20261101-01` **PASSED exit0** over 480.698s/473 accepted samples, maximum acceptance gap 3.061921s and capture gap 2.956113s, stable Lab2 game PID7012/start639290507554340644/SHA1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8, stable player/epoch and no planar drift; summary SHA256 `76fdebfa97afb045a59b78ccc5983951ddcc0ac2dc7936275bdbe99a849e56c7`. A fresh screenshot-reviewed exclusive **A 100ms turn** `rr2-lab2-postreload-reviewed100ms-turn-run-20261101-01` **PASSED**: key down/up inserted, released, stable XYZ, `turn-input-completed`, heading **not** independently proven. Separately reviewed **W 150ms 1D calibration** `rr2-lab2-postreload-reviewed-w150-calibration-run-20261101-01` **PASSED** at 22:24:58 UTC: independent feedback from (7151.989746,827.989990,3166.149902) to (7152.449707,828.199951,3167.229980), **1.173939 horizontal units / +0.209961 vertical**, `calibrated`, delivery and release verified; profile `artifacts/dual-method-live-reader-20261101-01/lab2-postreload-reader-2157/reviewed-calibration-w-02-result/result.json`. Earlier S/W calibration prepares produced **no action** because review was deferred or preview formatting failed. The first 1D 1.5×-displacement goal lease expired before review; no action sent. The fresh reviewed second goal `rr2-lab2-postreload-reviewed-w1d-movement-run-20261101-02` did deliver/release **two W pulses (150ms, 89ms)** at 22:27:54/57, but **FAILED `elapsed-budget`** in its 12-second controller window and **did not prove arrival**; raw receiver outer sequence advanced 1594→1600 while addon candidate sequence **stalled at 4878**, became `freshness-timeout`/expired, and final position is unqualified. Forced STOP/final status shows ready, disarmed, no held keys, no recovery. Do not reuse the calibration endpoint or claim goal arrival until fresh advancing addon feedback and current XYZ are confirmed. **Next:** diagnose intermittent addon publication stall/reader scan latency under read-only checks; improve bounded feedback/reader resiliency offline, establish new live freshness as needed, and only then retry a separately reviewed bounded goal. All successful actions were through the managed exclusive controller/queue, without memory writes or bypassing expiry/freshness gates.

**2026-11-01 21:51 UTC — LAB2 FRESHNESS QUALIFIED; FIRST REVIEWED TURN STILL FAILS CLOSED:** Current Lab2 RIFT PID7012/start639290507554340644/SHA1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8 and reader PID9148/start639291633796439201/nonce `0ab0d98cdbdc41fba08b9698956e5792` (expires 21:56:19 UTC) were independently pinned/bound. The first strict480 observer failed after 252.66s/251 samples on Win32 299 and stale anchor; the second `rr2-lab2-postadapter-strict480-observer-20261101-02` **PASSED exit0**: 480.519s, 495 accepted samples, maximum acceptance gap 3.060s and capture gap 2.923s (<4.5s), stable identity, no observed planar drift. Evidence `artifacts/dual-method-live-reader-20261101-01/lab2-postadapter-reader-2055/strict480-observer-02/summary.json` SHA256 `0c4c64c9d2ad81a05f2b4c1dd7236ada1373574e86a73a3d5687030b0d231cac`; this is observer-side no-input qualification only. The managed controller was reconnected/ready/disarmed and Lab2 queue free/unblocked. A reviewed 100ms `A` turn was prepared four times; 01/02 review leases expired and were reclaimed, 03 reached `/api/arm` but its 45s capture had expired, 04 had a valid fresh screenshot and lease but **failed before arm on `live-receipt-not-fresh` / `movement-feedback-timeout`**. At 21:48:31 the receiver reported `unbound`, full scan complete with zero matching candidates and `fastObservation=null`; capture04 also visibly contains newly timestamped addon startup messages, suggesting an intervening UI reload (cause not established). **No turn/movement key was sent**. Queue cleanup confirmed request04 `failed`, resource generation2229 unblocked/holder-null, controller at 21:49:54 ready/disarmed/no keys/recovery. Capture metadata+image pin commit `7f080ef` and final reviewed arm ID pin commit `a306438` passed 53 focused tests, 20 managed host regressions and diff check. **Next:** investigate reload/freshness ownership, wait for current reader to expire before launching a new exact nonce (launcher forbids overlap), perform separately reviewed addon bind under an exclusive stopped-controller console handoff, requalify 480s, and promptly run one new screenshot-reviewed bounded turn only if every live gate still passes. A bounded 4KiB Win32-299 retry improvement is being evaluated offline; do not transfer qualification across reloads, reader nonces or game epochs.

**2026-11-01 21:06 UTC — ACTOR/RENDER MATRIX COMPOSITION REPLAY (OFFLINE ONLY):** Pure `scripts/probe_native_unit_manager.py::actor_render_pose_candidates` now accepts six bounded saved float32 position/actor/model/offset/render fragments, explicitly gates normal vs alternate render branch, composes row-major actor×model 3×3 and secondary-position XYZ + both actor offset triplets, and exposes matrix/XYZ error and finite/orthonormal/determinant diagnostics. It does **not** resolve pointers, read the process, infer verified character facing, or qualify freshness/restart. Four new synthetic cases reject reversed noncommuting rotations, malformed/nonfinite fields, and unsafe render-branch use; **46/46** native-unit Python tests PASS (`rr2-actor-render-native-tests-20261101-01`), `git diff --check` PASS (`rr2-actor-render-diff-check-20261101-01`), both exit0. The Lab2 controller remains intentionally stopped (`--no-auto-start status` returned WinError10061), no new reader nonce or live input. **Next:** commit this offline milestone, then reconcile the exclusive console handoff and managed generation before any fresh 480s observer or reviewed turn.

**2026-11-01 21:00 UTC — NON-STARTING LAB2 CONTROLLER STATUS CHECK:** Exact `scripts/control_client.py --config artifacts/control-fleet-live/lab2/host.json --no-auto-start status` ran through Workbridge job `rr2-lab2-controller-no-autostart-status-20261101-01` and failed exit1 with `transport-error / WinError 10061` (loopback controller endpoint actively refused connection). This is **expected while the controller remains deliberately stopped**, and confirms no current authenticated Lab2 host endpoint was available to inspect. `--no-auto-start` explicitly prevented on-demand helper startup; no controller/VM/game input, memory writes, restarts or queue resets. The canonical `AccessQueue.status()` itself uses a transactional expiry/quarantine sweep, so it was **not** invoked as a purportedly pure-read queue check. Do not call the normal auto-starting control CLI while the console handoff/queue quarantine is unresolved. The new strict owned-task adapter and observer are offline-verified only. Next safe live phase needs an explicit one-owner console-handoff close/reconciliation, on-demand managed controller/guest check, fresh Lab2 reader nonce/UI rebind and independently validated 480-second no-input observation; only then review one bounded stationary turn under the final protected lease.

**2026-11-01 20:58 UTC — MANAGED-GENERATION ADMISSION HARDENED (OFFLINE ONLY):** The targeted queue dispatch change `cf58306` prevents movement `acquire()` from granting a foreign lab's lease; rejected own requests are cancelled by the runner (`dfefca0`). Separate queued-cleanup pagination/identity fix `5da16d9` and managed-controller adapter `7ecba5b` were committed through the shared Workbridge journal with matching offline tests. New strict `scripts/managed_controller_receipt.py` now verifies **exactly one current UUID task generation**, non-stale process PID/start/image, exact nine authoritative `ensure_controller.RUNTIME_FILES` hashes, config/queue, controller task receipt schema and duplicate-key rejection, no exit/failure/stop request, and the real Workbridge **owned scheduled-task registration** (no implicit startup); `ManagedPinnedHost` and the plan writer call this at admission/reopen, while per-action checks remain bounded and additionally reject missing source hashes or stop requests. Runner still pins live operator-listener PID, VM, hostInstance/connection, supervisor, guest instance/target and exact receipt SHA. **20/20 managed runner tests** (`rr2-managed-strict-glue-owned-deny-tests-20261101-01`), **12/12 strict receipt tests** (`rr2-strict-managed-helper-final-tests-20261101-01`), **41/41 movement** (`rr2-strict-managed-movement-regression-20261101-01`), and **11/11 queue-runner** (`rr2-strict-managed-queue-regression-20261101-01`) PASS offline, plus targeted queue's **45/45** (`rr2-targeted-dispatch-queue-tests-20261101-01`). These tests do not establish an authorized or usable live controller: current reader nonce expired at 19:32 UTC, managed controller/source epochs have not been reverified after source changes, and no fresh 480-second observation or reviewed live action was run. No VM/game input, memory writes, restarts or unsafe approval bypass. **Next:** commit this hardening, perform read-only on-demand managed host/queue/STOP preflight, renew and separately bind an exact fresh reader, run strict observer, then independently review one bounded stationary turn only after all live gates pass.

**2026-11-01 20:35 UTC — DURABLE STRICT480 OBSERVER ADDED (OFFLINE ONLY):** New `scripts/observe_live_reader_freshness.py`, `tests/test_observe_live_reader_freshness.py` and [runbook](workflows/live-reader-freshness-observer.md) implement a reusable no-input-side observer for an exact new reader/game/receiver nonce. It enforces ≥480 observer seconds, strictly advancing validated raw receipt and addon clock/sequence, both <4.5s observer acceptance and capture-time gaps, ≤0.05 planar drift, stable player/epoch, ≥45s reader expiry margin even after final receipt processing, evidence JSONL+SHA/raw receipts and fail-closed summary. **14/14 focused offline tests PASS** (`rr2-observer-dual-gap-corrected-focused-tests-20261101-01`), plus **27/27 movement-feedback** (`rr2-observer-feedback-regression-20261101-01`) and **6/6 source-pin** (`rr2-observer-source-pin-regression-20261101-01`) regressions, all exit0. The earlier queue pagination and exact-grant fix was committed as `a03628e` following approval preflight commit `468e796`. **No live strict480 was run for the latest reader**: its nonce expired at 19:32 UTC; past PASS cannot transfer. No VM/game input, memory write or controller restart. Current blocker before any reviewed live turn is the managed-generation controller adapter and final-send lease guard; global `queue.dispatch()` can select another lab's request despite the exact-own-grant check, so treat the runner as offline-only pending targeted dispatch/lease reconciliation. Next: commit observer milestone, then implement/test managed adapter; only then safely renew/rebind a fresh reader and qualify it from scratch.

**2026-11-01 20:18 UTC — QUEUE PAGINATION AND EXACT-GRANT PRECHECK REPAIRED (OFFLINE ONLY):** Workbridge app permission was already **Allow all actions**; coordinator-owned small write, patch and commit tools worked without a new prompt (preflight commit `468e796`), unlike earlier stalled worker mutations. `scripts/run_movement_session.py::acquire` now scans up to 1,000 queue pages with advancing cursor, same-resource queued/active/cleanup detection, resource-row stability, exact own-grant token check and `queue.check`. **7/7 new pagination tests** and **41/41 existing movement-session tests** PASS via Workbridge jobs `rr2-queue-pagination-focused-tests-20261101-01` and `rr2-run-movement-regression-tests-20261101-01`, both exit0. This does **not** implement the current managed controller adapter, validate final send admission, or establish live movement readiness. New Lab2 reader nonce `9f9be25447634905883ead4af119713e` expired 19:32 UTC without its own strict 480s qualification; previous reader's PASS is nontransferable. No VM/game input, memory writes or controller restart during this milestone. **Next:** commit this focused code/test change; then implement managed-generation adapter and durable observer, launch/rebind a fresh reader and run strict480 before any reviewed turn.

**2026-11-01 18:45 UTC — ACTIVE HANDOFF CHECKPOINT; NEW LAB2 READER FRESH, STRICT480/ADAPTER PENDING:** On-demand new reader launch job `rr2-20261101-1831-lab2-renewed-reader-02` **PASS exit0**: Lab2 reader **PID1228/start639291547247093923**, nonce **`9f9be25447634905883ead4af119713e`**, instance `f573179e-0cb2-46b3-8be0-447266604c7d`, reader SHA `6ABD9686858F806E58FC0B181F004EA829129F2A03AA9FE0E72446333FBBFB2E`, expires **2026-11-01 19:32:04.7093923 UTC**. Game remains PID7012/start639290507554340644/SHA `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`; VM PID20020/start134379227430799559/logEpoch2026-10-31T12:19:03.105Z; receiver PID37376/start639290626470054030, instance `b7a900720fb14ee3b51811f9214bc3e3` at 192.168.56.1:49923. Preflight found **zero overlapping readers**, scan complete, no launcher input. Under the one exclusive stopped-controller console handoff, fresh reviewed open-chat and exact `/rr2guide rebind lab2 9f9be25447634905883ead4af119713e` execution **completed**, keys released, game/VM unchanged; after-screen visibly states **`RiftReader2: Rebound lab2; waiting for the new reader.`** Receiver independently reported **current-nonce full bound/fresh/selected** and **fast bound-scoped/fresh-scoped** at 18:34:06Z. New exact live source pin `artifacts/dual-method-live-reader-20261101-01/lab2-new-reader-1831/root-source-pin.json`, SHA `b7af3e10502bcc7b9161485e11897e8d2949d5275a208321e66793ec28f568f7`, builder job `rr2-20261101-1837-lab2-newreader-root-sourcepin-01` PASS. The **strict 480s** triple-advancing no-input observer is prepared, but as of this checkpoint no Workbridge job has been admitted for request `rr2-lab2-newreader-strict480-observer-20261101-01` (UNKNOWN_JOB); do **not** claim it passed or launch a reviewed turn. This new reader has enough time remaining; reconcile the pending observer tool admission using the **same** request ID and exact in-memory script, require full 480s+45s expiry preflight and signed/raw receipt ledger. During observer send NO gameplay input. Controller remains intentionally stopped and queue quarantine must be reconciled by a **fresh managed host startup only after console handoff**; `control_client status` auto-starts unless `--no-auto-start`. Runner still only supports stale legacy host-plan receipt; managed adapter/queue pagination/lease cleanup requires source edits plus offline negatives, with previous source mutation calls unjournaled/approval possibly hidden. No movement, cast, combat, injection, memory writes or unsafe input. Durable max-worker policy `fe8550a` in AGENTS.md; exact native owner triad `6386855`, actor/world row-major matrix `4b413bc`. Continue six complementary worker slots, but one live input owner. **Next:** (1) admit strict480 observer for this nonce and record PASS/FAIL; (2) preflight/apply and test managed adapter only through authorized Workbridge mutation journal, repair lease cleanup and global queue pagination; (3) on observer completion, reconcile managed host/disarmed/queue, then fresh UI review and at most one 100ms A/D stationary turn only if every gate passes; (4) update this handoff with exact outcomes. Earlier Lab2 480.057s PASS belongs exclusively to expired PID7044 nonce, not this new reader.

**2026-11-01 18:22 UTC — RENEWED LAB2 READER BOUND/FRESH; EIGHT-MINUTE REQUALIFICATION STILL BLOCKED:** The independently launched same-hash .NET reader PID7976/start639291508110952674, nonce `3f4eab0a737749e083456c163072f18c`, exact binary SHA `6ABD9686858F806E58FC0B181F004EA829129F2A03AA9FE0E72446333FBBFB2E`, expires **18:26:51.095 UTC**. Under sole exclusive console control, approved and screenshot-reviewed UI steps completed: `/reloadui`, hide both addon panels, open empty chat, then exact `/rr2guide bind lab2 3f4eab0a737749e083456c163072f18c` (execution `artifacts/dual-method-live-reader-20261101-01/lab2-bind-renewed-reader-refresh-02/execution.json`), with `inputSent=true`, `releaseSucceeded=true`, unchanged VM/game PID/start/SHA. The after-screen visibly says **`RiftReader2: Bound lab2; manual feedback only.`** At **18:19:46 UTC** the separate host receiver latest receipt showed current nonce, full scan **complete** (3,044,069,376 bytes), nine matching copies/one distinct payload, `selected/bound/fresh`, player `u035400012DFEB5BC`, addon epoch1 and advancing sequence. Console preparation briefly stalled before server admission; an initial bind review had a 312-character note versus the 256-character safety limit and was rejected **before input**; the later fresh-capture short-note review passed. The renewed reader was bound too late for a fresh **480s + 45s expiry-margin** window; the earlier 480.057s PASS belongs solely to the expired PID7044 nonce and is NOT inherited. Controller remains in a deliberate stopped/quarantined console handoff until explicitly reconciled; **no game movement, combat, cast or native memory write** occurred. A future reader nonce needs independently reviewed `/rr2guide rebind lab2 NEW_NONCE` with new source pin/strict window, or reviewed reload fallback if rebind fails closed. Managed controller adapter remains unimplemented because Workbridge source edits did not reach the mutation journal; never bypass approval, queue or freshness gates.

**2026-11-01 17:13 UTC — LAB2 480s FRESHNESS QUALIFIED; MOVEMENT ADAPTER PENDING:** Fresh .NET 10 Live reader passed **201/201** tests and used the exact Lab2 game PID7012/start639290507554340644/SHA1935A05C9DB6B1695884E24600F5C20A4BE8. The strict no-input observer (job `rr2-dual-method-lab2-strict480-observer-03-20261101`) passed **480.057s, 684 accepted simultaneous strictly advancing outer/addon samples, max gap 4.21128s (<4.5s), zero planar drift, stable player/epoch**; evidence `artifacts/dual-method-live-reader-20261101-01/lab2-strict480-evidence-03/summary.json` SHA256 `aa73ce1a9db19da6791769f95a17cf9319cc47313028345e4ab2c67d17249438`. This proves observer-side no-input qualification, not absence of other external input. The reader nonce `1ad131c6236043efa65ba8e1687e2f95` expired 16:14:53 UTC; **never reuse this reader/nonce or its expired source pin for a live turn.** Console handoff was recovered and disarmed; game input remains **blocked** because legacy `scripts/run_movement_session.py` consumes a stale `PinnedHost` plan incompatible with current managed controller generation. Build and offline-test a narrowly scoped managed-controller adapter with exact per-generation identity/queue validation, then relaunch/qualify fresh reader and review console before any finite ~100ms A/D turn. Prior Workbridge source-write/patch attempts hung; repo was clean at this checkpoint. Static native matrices and HP/Energy are still candidates, not changed-state-qualified.

**2026-11-01 14:40 UTC — DUAL-METHOD POLICY DURABLE; STATIC TARGET BRANCHES AND LIVE SOURCE PREFLIGHT:** The research policy is saved in tracked `AGENTS.md` by commit `86395ab`: combine exact-build offline disassembly with reviewed, finite, authorized live state-change experiments; never infer blanket no-input, and never bypass epoch/freshness/lease/STOP guards. The first native transform parser and HUD HP hardening were committed as `dfa41b2` (146/146 tests). An independent adversarial review found nonfinite secondary XYZ acceptance and missing cached-XYZ input-stability reporting; both were repaired and committed as `56a8ade` (**147/147 focused tests PASS**, job `rr2-native-transform-nonfinite-and-stability-regression-20261101-01`; diff check PASS). Exact-build static follow-up decoded `player.target` getter `0x5ECCA0`: direct fallback key `QWORD(QWORD(healthComponent+0x40)+0x20)`, conditional selection-component references at `+0x280/+0x288`, `+0x290/+0x298`, and eligible `+0x2A0`. Its helpers mutate internal caches/reference counts: **never call the getter inside a passive sampler**. The getter's canonical owner, branch behavior and target changes remain unverified; see [coordinate/native map](reference/native-current-coordinate-code-map.md). Independent addon parity preflight `scripts/addon_sync.py check --target all` **PASS** (job `rr2-dual-method-lab2-preflight-addon-check-all-20261101-01`, PC/Lab1/Lab2 all clean) and `verify --target all` **PASS** (job `rr2-dual-method-lab2-preflight-addon-verify-all-20261101-01`, all three clean). **No gameplay input, reader deployment, nonce rebind or matrix-facing promotion at this checkpoint.** Next: publish repaired current reader, launch exact Lab2 reader, reviewed nonce bind, strict fresh 480s test, then one exclusive ~100ms turn + native/visual before/after if all guards pass.

**2026-11-01 14:30 UTC — SIX-TRACK EXECUTABLE RESEARCH + FRESH LAB2 NATIVE ORIENTATION CANDIDATE:** Joey's durable **dual-method static + controlled-live research** decision is committed in AGENTS.md (86395ab); no blanket no-input assumption. Six independent read-only specialist tracks and the coordinator reused the **full-file SHA-verified** exact-build saved PE (60,493,640 bytes; Workbridge SHA job rr2-exe-research-saved-copy-sha-20261101-01, exit0) and retained native snapshots. New static code facts: 0x612960 computes a 3×3 matrix from a quaternion, cached in the player-owned position component at +0x60/+0x94; a deeper resolved source stores the 36-byte matrix at +0xD4 followed by XYZ at +0xF8; conditional cached fallback means passive freshness remains unresolved. Cooldown 0x5A9440 iterates resolved 32-bit IDs and queries context timer floats via 0x5A7450; module roots 0x33624C8/0x3372C18 are identified, but conditional resolver ownership remains unknown. The native unit-parser's target is a dotted suffix; player.target reaches getter 0x5ECCA0, not yet decoded. [Coordinate/matrix source map](reference/native-current-coordinate-code-map.md), [HP/Energy/ability map](reference/native-current-client-code-map.md).

The existing native probe now reports **candidate-only dual 3×3 transforms** with an independent final reread of the 112 transform/XYZ bytes; the guarded HP screenshot helper rejects malformed numeric HP evidence. **146/146 focused Python tests PASS**, Workbridge rr2-exe-dual-method-native-transform-and-hp-tests-20261101-01 exit0, and git diff --check exit0. Three prior byte-exact native reports replayed structurally with first/second matrix angles Lab1 3.465055°/3.464628°, Lab2 32.810855°/32.810213°. **Fresh authorized Lab2** read-only probe rr2-exe-research-lab2-fresh-position-matrix-20261101-01 passed exit0: PID7012/start639290507554340644/exact SHA/player ID, observed 14:29:38.891UTC, final bytes stable, XYZ 7153.2227/825.9457/3162.8586, matrices **32.810855°/32.810213°**. Evidence artifacts/native-unit-manager/lab2/e97e390b580a4974be17113c579feef7/review.json SHA256 0C7257676FECA8D3F13500CA4465624418D0008C5E8FA35D015DF6597CE4FC27. **These are unchanged structural rotation candidates, NOT verified body facing, changed state, passive freshness or full-restart durability. No turn/input was sent.** Next dual-method experiment: establish a fresh current-epoch Lab2 reader/feedback source, then a reviewed, exclusive 100ms A/D stationary turn with native-before/after and independent visual check. Lab1's historical 480s FAIL and prior-epoch Lab2 source pin remain blocking for live movement; never bypass input gates.

**2026-11-01 13:49 UTC — SECOND LAB2 SAME-PROCESS VISUAL BASELINE PAIRS NATIVE HP AND TYPE-CHECKED ENERGY WITH HUD:** One combined, bounded pure-read `rr2-resume-lab2-fresh-typed-hp-energy-20261101-01` job passed exit0: exact PID7012/start/SHA, HP type `0x2C2`/revision66/66 and candidate **10,635/10,635**, kind4 Energy type `0x072B`/revision64/64 and native float32 candidate **100/100**. A fresh screenshot-only protected lease `rr2-resume-lab2-hp-energy-screenshot-20261101-01` passed exit0 with independent watchdog release; original BMP HUD was visually reviewed and again showed green **10,635/10,635** and purple **100/100**. HP screenshot skew **70.32s**, Energy skew **48.26s**. Exact hashes/timestamps in [Lab2 native HP/Energy ↔ HUD validation](validation/native-hp-screenshot-lab2-2026-11-01.md). **Both values stayed unchanged and the purple HUD label does not prove resource type on its own**: no advancing readings, tight synchronization, passive freshness, restart qualification, game input or writes. Lab1 480s historical FAIL remains unchanged.

**2026-11-01 13:44 UTC — FIRST SAME-PROCESS NATIVE HP ↔ INDEPENDENT HUD VISUAL MATCH ON LAB2:** On-demand controller+guest preflight reused a healthy, idle/disarmed Lab2 (job `rr2-resume-lab2-guest-agent-preflight-20261101-01`, exit0). New exact-build, type-`0x2C2`, stable native HP probe `rr2-resume-lab2-fresh-typed-hp-20261101-01` (exit0) observed **10,635/10,635** at 13:37:46.5355685UTC, PID7012/start639290507554340644/current SHA. The committed guarded screenshot helper `rr2-resume-lab2-hp-screenshot-20261101-01` (exit0) captured a separately rendered, foreground RIFT HUD at 13:38:33.036UTC, exactly matching PID/start/SHA; its green bar visibly reads **10,635/10,635 (100%)** for Bolinao [AFK], level43, and purple resource bar visibly reads **100/100 (100%)**. The screenshot lease completed with explicit STOP and independent watchdog release attestation; no gameplay input. Evidence SHA paths, visual review and limits in [Lab2 native HP/HUD validation](validation/native-hp-screenshot-lab2-2026-11-01.md). **This is one unchanged baseline, ~46.50s between sources, NOT advancing HP/Energy, passive freshness, atomic comparison, restart acceptance or Lab1 480s requalification.** Native HP remains candidate-only. The Lab1 historical FAIL is unchanged.

**2026-11-01 13:34 UTC — LAB2 HP SCREENSHOT HELPER OFFLINE-VERIFIED, LIVE CAPTURE NOT YET RUN:** The new opt-in `scripts/capture_lab_hp_screenshot.py` and `tests/test_capture_lab_hp_screenshot.py` provide an exact-build/native-HP-type/pinned-PID-and-start, read-only screenshot-only queue lease. It confirms game foreground and disarmed controller/guest, uses on-demand guest-agent prerequisites, validates exact grant/epoch and captured target, issues STOP, and waits for independent watchdog queue-cleanup attestation; no arm/action or game input. Six independent read-only specialist reviews found and motivated fixes to (1) require STOP `stopped=true` **and** `recoveryRequired=false`, (2) reject only **same-lab** pending queue work, leaving independent Lab1 work unconstrained, and (3) check 300s native-review freshness again immediately before/after capture. **104/104 offline Python tests PASS**, Workbridge job `rr2-hp-screenshot-integration-offline-tests-20261101-01`, exit 0 (screenshot+access-queue+watchdog+client); 11 screenshot-specific tests included, with negative STOP/queue/freshness scenarios. No live screenshot, process-memory read, controller or VM/game action occurred during this checkpoint. Existing Lab2 typed HP at 06:35 UTC is **expired** under the 300-second gate: next prepare/reuse Lab2 dependencies, perform a new authorized type-checked read-only HP probe, then promptly execute the guarded screenshot-only lease and inspect game UI without treating static equality as live HP qualification. Native Energy 100/100 remains an unqualified candidate; historic Lab1 480s freshness FAIL remains unresolved and its source fix is not deployed or requalified.

**2026-11-01 06:56 UTC — NATIVE ENERGY CURRENT-VALUE ARITHMETIC RECONSTRUCTED AND REPLAYED OFFLINE:** Exact installed PE getter `0x133F2C0..0x133F3A6` was extracted (`rr2-approved-energy-current-getter-pe-offline-20261101-01`, exit0) and independently fully disassembled; record base+0x20, max+0x24, rate+0x28, revision+0x34, wrapper clock+0x1C, game-clock global+0x33DC2B0 drive the signed32/float32 calculation. Native mismatch path **writes** cached revision/clock; pure-read `calculate_energy` rejects mismatches and dangerous signed-conversion/overflow domains, preserves each SSE float32 MULSS round and clamp order, and is gated on live Energy type `0x072B` and end-of-probe anchor stability. **38/38 synthetic native tests PASS**, `rr2-energy-calculator-38-focused-tests-20261101-01` exit0; independent disassembly audit found no material ordinary-domain defect and precision/boolean guards were incorporated. Saved SHA-verified read-only replay `rr2-offline-typed-energy-native-formula-replay-20261101-01` exit0 against the earlier **06:49:42 UTC** authorized Lab2 type-checked record computed elapsed217.1171875s, truncated rate adjustment -4342, **candidate current/max Energy 100/100**. No new live game read was needed for replay; this remains **unqualified** without time-aligned independent UI/API samples and distinct value changes. Detailed [source/evidence](reference/native-current-client-code-map.md). No controller screenshot, deployment, game input/writes or restart. Historic Lab1 long-run FAIL unchanged.

**2026-11-01 06:51 UTC — LAB2 ENERGY TYPE GUARD PROVEN IN EXACT PE AND PASSED LIVE, CURRENT ENERGY STILL UNQUALIFIED:** Starting from the earlier authorized kind4 Energy record vtable RVA `0x2D19498`, serialized exact-exe static jobs `rr2-approved-lab2-energy-vtable-getter-static-20261101-01`, `rr2-approved-lab2-energy-descriptor-initializer-static-20261101-01`, `rr2-approved-lab2-energy-type-getter-static-20261101-01` and `rr2-approved-lab2-energy-type-helper-static-20261101-01` (all exit0) prove descriptor getter `0x231BEB0` → initializer `0x232FDC0` → global `0x35AEB80` → descriptor vtable `0x2D1D420` → type getter `0x233E9B0` → helper `0x23354F0` with seed `0x2239C5`, yielding `(0x2DD59D90 ^ 0x9ABB)&0xFFFF = 0x072B`, exactly Energy's resolver type. Added pure-read kind4-only runtime metadata checks and fail-closed tests (**34/34 native Python tests**, `rr2-new-energy-type-guard-offline-tests-20261101-01`, exit0; no mana-type guess). Fresh **authorized Lab2** native probe `rr2-approved-lab2-typed-energy-20261101-01` passed exit0 at06:50UTC, same PID7012/start639290507554340644/installed SHA/playerID, Energy type `0x072B`, exact vtable/descriptor slot matches and post-read anchor rechecks, revisions **59/59**, raw base/max100/100, rate2000, type-checked raw candidate **NOT current-energy reading**. Evidence `artifacts/native-unit-manager/lab2/cb89bea7ed9e4d6a9d029d65b5a446b6/review.json`, SHA256 `CF1103CBFF83C4C0C3C1CDA6A0684C74581DD7AC283EF0776C06AF1B3F31B7DE`. [Exact source/type proof and all current status limits](reference/native-current-client-code-map.md). No new input, controller/screenshots, addon deploy, game write or restart. Next: native Energy time arithmetic and read-only UI correlation; fresh Lab2 screenshot-only lease helper is being developed/tested separately. Historical Lab1 480s FAIL still in force.

**2026-11-01 06:39 UTC — FIRST LAB2 TYPE-CHECKED HP CANDIDATE AND RAW ENERGY EVIDENCE; CONTROLLER SCREENSHOT STILL PENDING:** Joey explicitly authorized live **Lab2** access after the earlier approval rejection. The existing bounded, SHA/PID/start-pinned native guest reader ran twice without game input or memory writes: `rr2-approved-lab2-typed-hp-20261101-01` (exit0, completed06:35:43UTC) and `rr2-approved-lab2-untyped-resource-20261101-01` (exit0, completed06:37:12UTC). Both captured the **same client epoch** PID7012/start639290507554340644/build `1935A05C...4BE8` and native player key `u035400012DFEB5BC`, rechecked ownership and mutable inputs. First **type-checked HP record** matched the exact vtable/descriptor/type chain `0x2C2`, revision74/74, max/base 10635, and ordinary-case calculated **10,635/10,635 HP candidate**; its timestamp is06:35:29UTC. Second captured resource **kind4 Energy**, raw base/max **100/100**, rate2000, revision56/56, vtable RVA `0x2D19498`/candidate descriptor getter `0x231BEB0`, but the expected `0x072B` record-type fingerprint is **not proven**, so current Energy is NOT published. The two session snapshots are sequential, not atomic. Exact review paths and SHA256 hashes in [native code map](reference/native-current-client-code-map.md). The earlier Bolinao screenshot independently depicts 10,635HP but is not time-synchronized. A protected screenshot-only lease/cleanup helper and exact-PE resource fingerprint are being developed/reviewed; **no new controller capture or real-time API comparison yet**, no Lab1 typed capture, no restart/480s acceptance. The cooldown marshaller's current-build formulas for begin `T-D`, duration `D`, elapsed/remaining `T-gameClock` were independently recovered from saved native instructions and added to that code map; value-owning runtime pointers remain unknown.

**2026-11-01 04:41 UTC — DOWNSTREAM NATIVE COOLDOWN SOURCE TRACED OFFLINE, STILL NO LIVE ABILITY POINTER:** Fresh exact-SHA installed PE extractions `rr2-serialized-native-cooldown-and-cost-producers-20261101-01`, `rr2-serialized-cooldown-producer-expanded-code-20261101-01` and `rr2-serialized-native-cooldown-downstream-producers-20261101-01` establish that cooldown float producer **`0x5A5E40` spans three adjacent compiler unwind segments** and follows handle/native-manager/reference code. Its eligibility helper `0x1353620` checks expected ability-like child type **0x078A** from an object `+0x5F0` vector; downstream `0x5A6F20` walks another reference path and `0x5A9440` computes the secondary float through branch-dependent logic. Another related helper `0x5526F0` reuses current module selector **`0x2F57850`** for a health component, but the selector match alone does **not** prove cooldown/HP data sharing. The Energy cost getter `0x49F000` reads a different selector and conditionally consults kind-4 resource state. These functions mutate flags, output buffers or reference counts; no native helper was invoked. Updated [current native code map](reference/native-current-client-code-map.md) records call RVAs, source jobs and all unqualified ownership boundaries. **No live game/VM/controller operation, process-memory read, addon change, deploy, screenshots or 480-second tests.** Lab2 live validation still requires approval; native resource record types remain unproven.

**2026-11-01 04:38 UTC — PE FUNCTION-BOUNDARY TOOL HARDENED; NATIVE OWNER HYPOTHESES NARROWED:** Independent review identified malformed unwind/image entries that could have been falsely marked unique by the optional `--function-bounds` scanner. It now rejects invalid or overlapping virtual/raw PE sections, out-of-image/non-executable function spans, unmapped unwind targets and directory padding outside mapped virtual data; its byte-pattern instruction hits are explicitly `instructionBoundaryVerified=false`. The exact installed RIFT SHA again passes with **303,143 verified unwind entries and 12/12 unique candidate ranges**, with separate machine-code disassembly corroborating the 12 known field assignments (`rr2-serialized-current-ability-strict-pdata-reproduction-20261101-01`). **47/47 combined Python scanner/native resource tests PASS** (`rr2-offline-strict-pdata-native-gate-tests-20261101-01`), including malicious PE and speculative REX-prefix cases. Additional native analysis narrows cost-child vector to **unverified stack owner `[RSP+0x58] + 0x6D0`**, cooldown value producer to `0x5A5E40(RSI,R12D)` and castbar state to producer-filled stack locals; these function ranges may be compiler funclets rather than distinct owners. A bounded 103-leaf static search over `0x20F0000..0x20F6000` correctly matched HP type **0x02C2** but found no candidate for mana/energy **0x072A/0x072B** in that window; **inconclusive**, with resource type proof still pending (`rr2-serialized-resource-type-leaf-candidate-scan-20261101-02`). [Exact-build native map](reference/native-current-client-code-map.md) preserves evidence and next trace. **No live VM/game/controller operation, live process-memory read, screenshot, addon change, deployment or 480s reliability test.** Earlier live Lab2 typed-HP approval rejection remains respected.

**2026-11-01 04:30 UTC — ABILITY/COST/CASTBAR SOURCE-FUNCTION GROUPS AND REUSABLE OFFLINE .PDATA GATE:** Extended the exact-SHA, read-only `scripts/find_native_api_xrefs.py` with opt-in `--function-bounds` (strict PE32+ exception-directory bounds, explicit ambiguous/missing matches, no claim of live pointers). The installed executable's **303,143** unwind-function entries place all **12/12** distinctive field-name references in one unambiguous enclosing range: `idNew` in `0x995E5A..0x9962A6`; five cooldown fields in `0x996548..0x996639`; all Power/Mana/Energy cost references, including **both** `costMana` assignments, in `0x99664D..0x996E11`; two `uninterruptible` castbar references in **separate** `0x9B8347..0x9B84E2` and `0x9B84F0..0x9B88CD` functions. Native cost enumeration checks distinct type codes **0x1E29/0x1E2A/0x1E2C**, not the player resource's type `0x072A/0x072B`. An HP vtable pre-slot sanity read found a code pointer, **not** a usable RTTI Complete Object Locator shortcut; full resource record fingerprints remain pending. The native raw collector now timestamps unsupported kinds and explicitly fails on HP/resource record pointer alias. **42/42 combined Python native resource/scanner tests PASS** (`rr2-offline-pdata-and-resource-regression-tests-20261101-01`); installed PE reproduction PASS (`rr2-serialized-current-ability-pdata-reproduction-20261101-01`). See [native current client code map](reference/native-current-client-code-map.md). No live memory reads, game/VM/controller operations, addon changes or restart/480s qualification. Live Lab2 HP remains blocked by the declined approval.

**2026-11-01 04:24 UTC — CURRENT-BUILD NATIVE RESOURCES TRACED; OPT-IN UNTYPED COLLECTOR AND DEFENSIVE FRESHNESS GATE TESTED OFFLINE:** Exact installed PE SHA `1935A05C...` static disassembly confirms health component `+0x38` holds the resource wrapper and `+0x40 -> owner+0x168` selects kind **3 Mana/Charge** (resolver expected type **0x072A**) or kind **4 Energy** (resolver expected type **0x072B**). Corrected native **ManaMax getter to `0x133E050`** from the earlier mislabeled `0x133DE60`; EnergyMax is `0x133E450`. The current-build ability/cooldown/cost/castbar Lua-field builder xrefs are mapped but their native value-owning pointers are not verified. Added `scripts/probe_native_unit_manager.py --resource-record`: optional, SHA/PID/start-pinned, read-only raw candidate snapshots with resource kind, wrapper, reference, descriptor-getter candidate and later anchor rechecks. Until distinct record type fingerprints are established, **no current or max mana/energy is calculated or presented as trusted**, and other resource kinds are not-applicable. **31/31 Python native-probe synthetic tests PASS** (`rr2-offline-native-resource-candidate-tests-20261101-01`); separate **63/63 Python receipt/source-pin/receiver-dependency contract tests PASS** (`rr2-offline-reader-receipt-py-contracts-20261101-01`). Strengthened `FastObservationSession` to reject `Completed=true`/non-`complete` full scans as freshness anchors or renewals, and added synthetic partial-status and PID-reuse/start-time regressions; **201/201 .NET10 Windows Debug tests PASS** (`rr2-offline-fullscan-defensive-gate-dotnet-tests-20261101-01`). Detailed [resource/ability code map and probe contract](reference/native-current-client-code-map.md) retain RVAs, source job IDs, and qualification limits. **No game/VM operation, controller input or startup, live process-memory read, screenshot, addon edit, live deploy, or 480-second requalification occurred.** The previously declined live Lab2 typed-HP action remains stopped pending approval; old Lab1 sustained-freshness failure remains a FAIL despite the offline patch.

**2026-11-01 04:09 UTC — FAST→FULL READER FRESHNESS HANDOFF PATCHED OFFLINE; 200/200 .NET TESTS PASS:** Root independently confirmed with a specialist code review that the scoped fast tracker advanced while the full tracker stayed dormant, so the old 10s anchor turnover could trigger the existing 5s `observation-gap-requires-warmup` and reset a new private tracker. The source-only fix in `FastObservationSession.cs` / `Program.cs` snapshots a genuinely Fresh scoped continuity ticket before a full scan, promotes it **only after** the *new, completed, uniquely selected full-scan frame* advances matching PID/start/SHA/nonce/player/epoch/clock/sequence within the original gap/skew checks, then uses the same validated tracker for outgoing and saved full reports. A scoped sample completing after anchor expiry is withheld and cannot advance continuity; its mixed candidate IDs/hashes are cleared. Original **10s anchor, 5s freshness and 4.5s movement gate are unchanged**. Five new focused regression cases plus existing tests passed **200/200** in `rr2-offline-fresh-renewal-dotnet-tests-20261101-02` (exit0, net10.0-windows, Debug); no blocking defect found in independent read-only review. Retained source XREF job `rr2-static-api-text-xrefs-20261031-a` independently verifies current-build `energyMax` and `chargeMax` assignment RVAs **0x9BA204 / 0x9BA188**, not their player-owned resource data pointers. Historical ability cast/cooldown sample remains API-only and its source-build SHA unrecorded. Detailed [freshness repair/remaining gate](validation/lab1-fast-region-sustained-failure-2026-10-30.md) and [native resource xref map](reference/native-current-client-code-map.md) are updated. **This code is not deployed or live-validated**; old Lab1 480s FAIL remains in force. Native Lab2 typed-HP read still awaits approval following the earlier declined live tool call. No VM/game/controller input, service change, addon edit or new native live read in this checkpoint.

**October 31 ~22:03 EDT — GUARDED NATIVE HP TYPE/CALCULATION IMPLEMENTED; LIVE VALIDATION PAUSED AT APPROVAL:** Exact-SHA static tracing resolved the health record's virtual metadata path to accepted type `0x2C2` without executing game functions. `probe_native_unit_manager.py --health-record` now checks all four type fingerprints, captures the native clock, rejects revision/input inconsistency and computes only bounded ordinary-value HP candidates; **25 focused tests passed**, exit0 (`rr2-serialized-native-typed-health-tests-20261101-01`). Independent read-only review found no blocking defect. The earlier **Lab1 raw record** completed at 21:38:12EDT with base/max candidates **14830/14830**, matching revision9 and stable bracketed inputs, but it predates the type/clock checks and remains untyped—not a fresh qualified HP result. **No Lab2 health record or typed two-lab HP result is available yet.** The proposed typed Lab2 live command was rejected at the tool approval step and was not retried or bypassed; screenshot comparison remains unperformed. Updated [native health map](reference/native-current-client-code-map.md) preserves the exact type trace, raw-evidence hashes, test job and resumption boundary. Screenshot audit: reuse current-identity capture/queue primitives, not the old XYZ-profile guard; normal capture entrypoint supplies on-demand dependencies and watchdog cleanup must complete. Await approval for serial read-only Lab2/Lab1 runs and protected screenshots; no game input/restart, process-memory writes, addon edits or controller actions were performed by this continuation. Existing Lab1 sustained freshness failure is still unresolved.

**October 31 ~21:33 EDT / November 1 01:33 UTC — NATIVE SELF-KEY → PLAYER ENTITY → HP/POSITION COMPONENT LOOKUP PASSES BOTH LIVE LABS:** Exact-SHA static tracing resolved `player` through `module+0x33623E0 -> system+0x360`, decoded bare `u`+16-hex IDs via `_strtoui64`, and reconstructed the manager's tagged full-key hash lookup under `module+0x33624A8 -> manager+0x50`. New `scripts/probe_native_unit_manager.py` reuses the installed SHA-pinned native reader and fresh VM-specific cached-credential/identity workflow; fifteen focused synthetic tests pass. Both independently inspected current process epochs passed bounded native reads and end-of-run rechecks of every lookup path/ownership anchor. **Lab1** PID8164/start639290507142219120: native self ID `u035400012FA2D207`, entity `0x23D7D333610`, cached XYZ `(7415.63671875,863.5847778320312,2928.161376953125)` at 01:30:58UTC. **Lab2** PID7012/start639290507554340644: native self ID `u035400012DFEB5BC`, entity `0x2186DD41C10`, cached XYZ `(7153.22265625,825.9457397460938,3162.858642578125)` at 01:32:41UTC. Dynamic metadata indexes position34/health6 selected distinct component slots6/15 in both. These are **current-process native ownership candidates**, not qualified passive-fresh/restart-safe telemetry; IDs match prior records, not a newly sampled independent Lua reference. No addon query, controller start, game input, process-memory write, or game/VM restart. Exact evidence paths, raw request/report hashes, static source jobs and tests are in [native coordinate map](reference/native-current-coordinate-code-map.md); health wrapper path in [native health map](reference/native-current-client-code-map.md). New independent code review also identified a repeatable fast-anchor renewal/warming gap in the addon-backed reader (10s anchor; dormant full tracker plus reset scoped tracker); this is a concrete logic finding, **not yet a fixed or requalified 480s gate**. Next: type-check the selected HP record through pure reads, verify native/API values without circular cache refresh, repair/test freshness handoff, and qualify a full game restart.

**October 31 ~21:15 EDT — CURRENT-BUILD MODULE-ROOTED UNIT MANAGER LOOKUP CODE + BOTH-LAB HISTORICAL MEMORY CORROBORATION:** Serial read-only exact-SHA extraction of current `Inspect.Unit.Detail` located how it obtains the unit entity: native `+0x4A4750` retrieves a lazily initialized singleton from **module+0x33624A8**, `+0x69FFD0` performs a handle-keyed lookup under manager `+0x50`, then entity component metadata at **module+0x2F588A0** selects an entry from the unit's `+0x78` component table; that position component holds cached XYZ at `+0x48/+0x4C/+0x50` and refreshes via `+0x6996C0`. Exact retained main `.data` snapshots from both labs (~21:27 UTC, October 31, **not current live state**) independently read manager pointers **Lab1 `0x23D3FAB0D50` / Lab2 `0x21839E50EA0`** and selector index **34** in each, with full snapshot and chunk SHA checks. This establishes a **current-build native manager-to-XYZ lookup code path** and historical memory corroboration, but NOT the correct player handle, live player entity address, independently advancing coordinate source, or restart-safe locator. No old-build root was reused; no game, VM, controller, addon or process-memory mutation. Detailed code RVAs, snapshot PID/start, source hashes and follow-up gates are in [native coordinate map](reference/native-current-coordinate-code-map.md). Next: resolve the player unit handle through manager lookup, compare current-epoch native/typed-Lua XYZ independently in both labs, repair Lab1 480s freshness, and requalify after a full game restart.

**October 31 ~21:08 EDT — CURRENT-BUILD XYZ OBJECT OFFSETS AND HUNDREDTH QUANTIZATION VERIFIED OFFLINE:** After the parallel Windows PE-extraction requests stalled, serializing heavy Workbridge jobs returned precise read-only, exact-SHA current EXE bytes and independent objdump disassembly. Native `Inspect.Unit.Detail` accessor `+0x698460` first calls `+0x6996C0` and then returns `object+0x48`; the three float32 coordinates are `object+0x48/+0x4C/+0x50`. Adjacent `+0x6983F0` returns auxiliary `object+0x60`. The `+0x6996C0` routine actually compares and refreshes XYZ cache fields from an upstream entity source (`+0x612EE0` and on an alternate branch `+0x612B50`); direct passive reads of these offsets may be stale without refresh. Lua conversion helper `+0xA0E890` multiplies input by 100, calls a signed integer-rounding routine `+0x129C0F0`, then scales by float32 ~0.01; ordinary finite coordinates are therefore hundredth-quantized. A nearby XORPS sign mask applies to a **different supplemental stack value**, not XYZ. These are verified **object-relative code offsets**, still not a live current-build player-owner pointer or module-rooted locator, and do not repair Lab1 freshness. Retained exact-SHA passed jobs `rr2-single-serialized-helper-20261031-01`, `rr2-serialized-transform-constants-20261031-01`, `rr2-serialized-native-xyz-accessor-20261031-01`, `rr2-serialized-native-xyz-refresh-full-20261031-01`; detailed offsets/limits in [native coordinate code map](reference/native-current-coordinate-code-map.md). Updated AGENTS.md tool-concurrency policy after ~1,000-second multi-worker terminal stalls; causal explanation unproven. Next: trace upstream entity/player owner, recheck native value freshness in both labs under current PID/start/build, independently verify changed-state and full game restart. No game/VM/process/addon/controller mutations.

**October 31 ~21:00 EDT — PARALLEL CURRENT-BUILD NATIVE CODE RESEARCH, REPRODUCIBLE XREF TOOL AND FALSE-POSITIVE GUARD:** Six worker slots investigated current RIFT native XYZ code ownership/float conversion, alternate field consumers, HP/resource overlap, old API semantics and two-lab validation. The SHA-gated, read-only `scripts/find_native_api_xrefs.py` reproduced exact `Inspect.Unit.Detail` `coordX/Y/Z` native code references against installed SHA `1935A05C...`; all five synthetic PE tests and the installed-PE reproduction passed. The unit-associated getter at RVA `0x698460` yields a pointer consumed as three 32-bit lanes; **its player-owned module-rooted data address remains unqualified**. Strong-looking `pitch/roll/yaw` references near alternate XYZ code clusters may instead be **dimension item** rotations: original `Inspect.Dimension.Layout.Detail` exposes precisely those fields for placed items, not units. Treat that API-key collision as a negative control, not a native facing discovery. The independent gate audit reaffirms Lab1's 480s FAIL (298 not-fresh observations, 180 duplicates; worst 7.565s vs 4.5s requirement); no old-build XYZ profile, input or controller action is authorized by this research. Existing inspect/map/snapshot/search/compare/follow-pointer tools suffice for candidate validation once ownership is traced. New documentation and scanner commits `99e1867`, `6ada86f`, `d5a9cc4`; details in [native current coordinate code map](reference/native-current-coordinate-code-map.md). Next: finish exact-build owner/function decompilation, compare against advancing independent typed-Lua coords, diagnose freshness, qualify both labs after a full game restart. No RIFT/VM/process/addon modification during this offline research.

**October 31 ~20:45 EDT — CURRENT-BUILD NATIVE XYZ CODE ACCESS DISCOVERED (DATA OWNER UNQUALIFIED):** Read-only SHA-pinned PE scan found unique `coordX/Y/Z` literal RVAs `0x26D1FC4/0x26D1FCC/0x26D1FD4`, their `Inspect.Unit.Detail` code assignments at `0x9BA9C8/0x9BA9F7/0x9BAA23`, and a common native component accessor at RVA `0x698460`. Offline disassembly confirmed that accessor's returned pointer is read as three adjacent 32-bit lanes (first 8 bytes into XMM6, third from `+0x08`) then each lane is processed by helper `+0xA0E890` before Lua X/Y/Z assignment. This is a genuine **current-build code path**, not a qualified live player pointer or stable module-root locator. More code references and next tests are in [native coordinate code map](reference/native-current-coordinate-code-map.md); independent current-epoch two-lab/changed-state and restart validation remains required. No VM/game/addon/process or controller action was taken.

**October 31 ~19:35 EDT — CURRENT-BUILD FULL-EXE OFFLINE HEALTH DECOMPILATION; LIVE HP STILL UNQUALIFIED:** Verified the complete 60,493,640-byte RIFT PE64 with SHA `1935A05C...`, imported it into a new ignored Ghidra project and decompiled the current Health/HealthMax getters plus their ref-counted resolver/release helpers. HealthMax returns resolved component `+0x50`; Health computes from `+0x48/+0x50/+0x60/+0x68/+0x6C/+0x70` and calls a second arithmetic leaf RVA `0x133B150`. The resolver validates type-like `0x2C2`; the full path is not yet a player-owned module-rooted address, nor does it qualify live HP. See [current native code map](reference/native-current-client-code-map.md) and ignored exact Ghidra output. Bounded HP machine-code slices were independently disassembled in cloud; **the entire EXE was not uploaded**. Old-build XYZ pointer remains unqualified on current SHA; trace `coordX/Y/Z` string xrefs and use established native-first read-only validation. No game/VM/process/addon edits.

**October 31 ~17:34 EDT — TWO-LAB MAIN-IMAGE CAPTURE COMPLETE; HP STILL UNQUALIFIED:** The new scripts/capture_native_image_roots.py reused map-native/snapshot-native and pinned the exact game PID/start/SHA plus native-reader binary SHA. Both labs captured all 6,903,392 bytes of the committed/readable, non-guard MEM_IMAGE .data section: Lab1 43 mapping ranges, Lab2 41, zero excluded bytes, 1,686/1,686 successful 4 KiB reads each. Verified ignored evidence: artifacts/native-module-roots/lab1/31698603c86a445b8736a2435caf6a92/ (snapshot SHA256 8A42DF19375EBF6B139B61244C4B08909A9D986C67F7B5940BA7818D6EA10E91) and lab2/6adb062aee0843c98c7ea804cb2c86cb/ (SHA256 74651FA7937E7DB12CBCBC3E4605B2B795285F47E034386D4B139CB8A5F654C9). The existing CLI find-pointers searched one hop (max field offset 2048) for all 12 old HP-shaped targets, with no truncated index: Lab1 0/2 target matches, Lab2 two roots for 1/10 targets at RVAs 0x3363BF8 (+0x688) and 0x3364DE8 (+0x588). A live exact-epoch follow-pointer re-resolved both Lab2 roots, but their terminal first int32 was now 365256408, not HP 10635; this rejects promotion as a stable current-health source, and ownership/deeper heaps remain unproven. Direct VNC screenshots were denied by the correctly held controller mutex; the protected controller capture API demanded a navigation lease and was not bypassed. Both controllers are connected, ready and disarmed; Lab1's sampled desktopInputsDown included mouse-left, while Lab2 was empty. No game input, process writes, addon edits, queue reset or VM/game restart. Six focused image scope tests passed at first capture; continue with a fresh independently reviewed XYZ/HP/resource source and changed-state ownership, not another static HP guess.

**October 31 ~15:32 EDT — WRITABLE RIFT IMAGE SECTION MAPPED ON BOTH LABS; EXISTING POINTER ENGINE REUSED:** New `scripts/plan_native_module_scopes.py` performs read-only, exact-PID/start/SHA-gated PE header inspection (four offline tests passed), with sanitized guest error evidence and no game-process memory access. Both clients share executable SHA `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`, image size **63,164,416 bytes**, and one writable main-executable section **`.data` RVA `0x2F56000`, virtual size 6,903,392 bytes (raw file size 4,242,432), flags `0xC0000040`**. ASLR differs: Lab1 module `0x7FF7698E0000`, writable section `0x7FF76C836000`; Lab2 module `0x7FF678A10000`, section `0x7FF67B966000`. SHA-verified JSON evidence under ignored `artifacts/native-module-scopes/lab1/9c73ccdb1f9245ac8ae13bd330f5f803/` (SHA256 `784C43F4CB1C159E81CBD015C885C54C403B851C177AD5FC18F0325E2C56D8E3`) and `lab2/a791ec9f85e4442b83578ed9afa5be9b/` (SHA256 `83FC49BF10D2FFEC08FCB12985DEF3BC3232AE9466C150B2E01D969A72814688`). Crucial code discovery: `MemoryDiscovery.FindPointerChains` and CLI `find-pointers` **already support 64-bit module-rooted candidate pointer chains** on retained snapshots; do not build a redundant scanner. Next stage is to intersect this PE scope with actually readable `MEM_IMAGE` regions and capture bounded source bytes with existing native snapshot support before the offline pointer search. No live player-owned pointer, native HP or movement has yet been qualified.

**October 31 ~15:22 EDT — EXTENDED NATIVE HP CONTEXT + PASSIVE SOURCES CHECKED; LUA/UI CACHE SUSPECT, COMBAT LOG OFF:** The reread helper now supports bounded 0–1024-byte context padding and exact source-validated candidate-address selection (ten focused tests passed). With 256 bytes before/512 after the old 100-byte contexts, **2/2** remaining Lab-1 layouts and **10/14** Lab-2 layouts still matched; **no** known player unit ID appeared in tested LE/BE 64-bit, ASCII or UTF-16 encodings. Nearby printable strings include UI markup/SEQ, LibString, MessageViewer and zone text, so the surviving triplets are **UI/cache-suspect**, not proven game-engine health. Exact-epoch evidence: `artifacts/native-current-health/lab1/reread-a87cc6712c3a45c4895988bf2643ffc8/` and `lab2/reread-4464a17683054904bcd8b8414b33db6c/`. Four online research workers (two rounds) independently mapped historic native-memory precedent, RIFT identity/health semantics, passive combat-log events and module-rooted reverse-pointer techniques; sources and cautions are in [research notes](planning/native-telemetry-online-research-2026-10-31.md). New `scripts/inventory_passive_rift_sources.py` checked current game identity and both labs' nine expected + two configured document paths: only `Rift.cfg` was found in each. Both configs say `LogCombatConsole=False`, `CombatLogFileFlushInterval=0.500000`, `DocumentsDirectory=C:/Users/mrkoo/OneDrive/Documents/RIFT`; **no existing CombatLog.txt** or standalone telara.db at checked locations. Four inventory tests passed. Logging was **not** enabled; no Lua edits, game input, config writes, addon binding, process-memory writes or restart. Next: fresh independent XYZ vector seed and narrow writable-module-root pointer scopes; exact owner and changed-state evidence still missing.

**October 31 ~15:12 EDT — NATIVE HP CANDIDATE PERSISTENCE CHECKED IN BOTH LIVE LABS (NO PLAYER FIELD PROMOTED):** Added `scripts/reread_current_native_hp.py` and eight offline provenance/safety tests (all passed; four original scout tests also passed). The helper rereads SHA-verified scout contexts using exact game PID/start/build; it can call an already-running native reader or invoke a previously deployed, SHA-verified executable once when the reader session has expired. No Lua dependency, addon binding, gameplay input, game-memory write or VM restart. Of the earlier 39/26 structural neighborhoods, 37 Lab-1 and 24 Lab-2 distinct 100-byte regions met the stricter saved-context selector (nonoverlapping, 3,700/2,400 requested bytes). Full live rereads retained the level/65536/three-HP layout in **2/37 Lab-1** and **14/24 Lab-2** regions; **35/37** and **10/24** respectively lost it as surrounding bytes were overwritten. The survivors still read **18208** and **10635** in their three HP slots, but this is static equality, not player ownership, max-HP determination or proof across a game restart. Guest snapshot SHA256: Lab-1 `E7E5CC0865324B76F73BE2F868AD1FF55DEDAA2166828E8E743BE8DD9A551D8D`; Lab-2 `38E4A498F071E4B638ACDA9AD895D501F8FB89386601D8A02F055ED90F1302F9`. Ignored provenance: `artifacts/native-current-health/lab1/reread-67a34082ea3f4373a03998d0728863fd/` and `lab2/reread-cbb2d38855a243d4a640cc78733f776d/`. Next gate: find an independent player-owner/root relationship and changed-state correlation before native live integration; abilities/resources remain pending.

**October 31 ~14:42 EDT — NATIVE-FIRST PLAYER TELEMETRY PRIORITY + TWO-LAB READ-ONLY HP DISCOVERY:** Joey explicitly prefers direct native/game data to expanding the scaffolding Lua addon. This decision is now durable in AGENTS.md, and the six-stage [native-first telemetry roadmap](planning/native-first-telemetry-2026-10-31.md) records gates for HP, class resources, abilities/cooldowns/casts, .NET integration, and complete-restart recovery. New reusable scripts/scout_current_native_health.py invokes the existing unmodified RIFT-Lab Windows native scout via the identity-pinned cached guest session; it refuses wrong PID/start/game SHA, reader absence, stale known-build assumptions and malformed address input, and preserves SHA-verified read-only ZIP evidence. Four focused Python tests passed; actual embedded PowerShell passed AST parsing.

**Live result, not yet a usable HP locator:** Both labs' current game executable SHA **1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8** was verified in guest. Lab1 PID **8164**, start **639290507142219120**, seed HP **18208**, level **45**: high-private-memory native scout inspected **856,740,212 bytes**, stopped at **128** candidates (match cap), **39** unique neighborhoods had a triplet of HP int32 and matching level. Lab2 PID **7012**, start **639290507554340644**, seed HP **10635**, level **43**: inspected **1,073,741,824 bytes**, stopped at byte cap with **115** candidates, **26** corresponding HP-triplet/level neighborhoods. Both partial scans are real read-only native evidence, but **multiple candidate copies, no changed-state ownership proof and no current-build pointer locator** forbid promotion to trusted native HP. Earlier low-memory Lab1 pass hit 128 likely serialization/cache copies after only 3.95 MiB; the higher range deliberately avoids that confound. Ignored evidence under artifacts/native-current-health/lab1/05b1f99fd080434cbfabf660ee51a60a/, lab1/2adc2ce7c4db425194fedb9bb08eb700/, and lab2/98c31c70442a455ab676c6f6ad1a0bcf/. No input, casts, addon reload/sync, controller mutation, game restart or process-memory writes. This **does not** resolve the old-build native Power restriction, the Lab1 8-minute freshness failure, or provide direct abilities yet.

**October 31 ~14:19 EDT — BOTH LABS LIVE PLAYER DATA + CONTROLLERS VERIFIED (NO MOVEMENT):** The existing identity-checked `scripts/vm_console_native.py` screenshot and `scripts/addon_command_console.py` reviewed one-step workflow safely bound fresh read-only readers on both current RIFT clients. Lab-1 game PID **8164**, reader PID **2512**, nonce `43032b94b5364c84abce0bc1e8b27210`; Lab-2 game PID **7012**, reader PID **4300**, nonce `04bd19ebea5b43588bc6aa1e8adf3fa1`. Both in-game chat responses confirmed `Bound labN; manual feedback only` and command execution receipts confirmed input release. Lab-2's first reader (PID 2548) had terminated after a Windows partial-copy memory read (299); a new exact-binary, same-target reader was launched and verified before the reviewed bind. All six addon files had passed PC/Lab1/Lab2 installed-hash and local/pinned verification earlier that afternoon.

At **18:18:55 UTC**, independently identity-/nonce-pinned receivers PID **23264** (Lab1) and **37376** (Lab2) delivered strictly fresh **candidate-region** observations captured just **22 ms apart**; two advancing outer/addon sequence pairs were also verified separately for each lab. Lab-1 player `u035400012FA2D207` had HP **18208/18208** and XYZ **(7405.86, 863.58, 2931.48)**; Lab-2 player `u035400012DFEB5BC` had HP **10635/10635** and XYZ **(7153.22, 825.95, 3162.86)**. Both showed stationary XYZ across their short two-sample checks; combat remained unavailable. Full-scan freshness on Lab1 remained `warming`, but the independently bounded 512 MiB candidate-region source passed strict scoped freshness. Snapshot receipt SHA256: Lab1 `6a4cd199f45a6a865b5ec18f4013b7e6615a260980011b03600590b948e868e7`, Lab2 `e9dd500b9df9f8428b81277c111667e76d87853d0be422e4a979d80afcb35d36`. Evidence: ignored `artifacts/screenshot-current-20261031/lab1-bind-final-1758/`, `lab2-bind-1814/` under the same parent, and `artifacts/reader-current-20261031/`; final read-only Workbridge job `rr2-two-lab-live-final-snapshot-20261031-a`.

Both main-PC controller tasks were subsequently authenticated **connected/ready**, guest disarmed and idle, `desktopInputsDown=[]`, no recovery required, and the unchanged per-VM SQLite queue had **no holder, pending or active requests**. This verifies a live **point-in-time telemetry snapshot**, not a perpetually refreshing dashboard or qualified movement. **The earlier Lab-1 480-second freshness failure (maximum 7.565-second gap vs 4.5-second limit) is still unresolved.** Do not relax it or initiate movement without a new full-duration pass; recover absent services on demand, but never silently rebind the addon or reset the queue.

**October 31 ~12:03 EDT — LIVE TWO-LAB CONTROLLER + GUEST-AGENT RECOVERY VERIFIED:** The main-PC controller lifetimes are now owned by existing Workbridge managed-helper on-demand tasks rr2-controller-lab1 and rr2-controller-lab2 (Limited interactive user, unlimited lifetime, IgnoreNew, **no boot/logon trigger**), executing tracked scripts/controller_task_entry.py directly. Independent subsequent bounded jobs authenticated each API; controllers remained alive, held their per-VM console reservations and retained the existing SQLite coordination queue. Both VMware guests had RIFT running but no live control agent, despite stale Oct30 managed-fleet-20261029 launcher state. Exact guest release agent-362ecd5a1be3, launcher and game binary hashes, VM/machine identity, per-lab port and empty prior input journals passed. New tracked scripts/Ensure-GuestAgentTask.ps1 started each missing agent as a **triggerless, Limited/Interactive Windows Session 1** task. Fresh authenticated controller status on **both labs** returned host.connected=true, coordination ready, exclusive console held, agent disarmed/idle, no recovery required and desktopInputsDown=[]. Independent guest inspections confirmed task Running, zero triggers, PT0S unlimited lifetime and IgnoreNew policy; agent processes were PID **936** (Lab1) and **1912** (Lab2), while RIFT game PIDs were **8164/7012** and VMware PIDs **44308/20020** at this checkpoint (all time-scoped identities). scripts/ensure_guest_agent.py --lab all independently reused both healthy instances with no duplicate start. scripts/control_client.py now ensures the guest dependency for live capture, reviewed arm and action, while inert status and cleanup operations do not start an absent guest. Tests: 11 operational-dependency, 9 guest-agent/wiring and 8 control-client tests passed (28 total), plus Python compile and Windows PowerShell parse. **No game input, VM/game restart, lease reset or addon rebind occurred.** This verifies live control connectivity, **not** fresh addon/reader/player telemetry or Lab1's previously failed sustained freshness gate. See [operational dependency workflow](workflows/operation-dependencies.md) and [guest launcher reference](reference/guest-agent-launcher.md).

**October 31 ~11:28 EDT — HISTORICAL CONTROLLER CODE CHECKPOINT (superseded by the ~12:03 live recovery above):** Joey corrected the architecture: operations own their prerequisites; do not suggest a routine manual controller launch. Durable rule now in AGENTS.md and [operational dependencies guide](workflows/operation-dependencies.md). New shared `scripts/operation_dependencies.py`, tracked `scripts/controller_host_entry.py`, `scripts/ensure_controller.py`, and integration in `scripts/control_client.py` (per-lab fleet configs, `--no-auto-start` opt-out) probe existing endpoints, serialize same-lab starts, verify fresh VM identity and runtime/config hashes, preserve the existing SQLite coordination queue and disarmed startup, re-probe after launch, and refuse duplicates/stale identities. Ten focused unit tests passed. **Live controller recovery remains BLOCKED under Workbridge:** its bounded command-job containment is incompatible with the current controller's required uncontained lifetime. Direct detached launch rejected by the existing guard; a single on-demand Windows Task Scheduler trial also did not pass that guard, and the owned failed task was removed. Code now fails immediately with `persistent-launcher-unavailable-in-bounded-job`, never bypasses containment. Both RIFT clients were independently present earlier, but controller endpoints remain unavailable; no fresh player telemetry or movement verified. Next: provide a supported uncontained process-management launcher, then test actual two-lab startup and reader/receiver freshness without input. This is a safe partial milestone, not a completed player-dashboard recovery.

**October 31 ~10:17 EDT — three-installation Lua addon sync IMPLEMENTED and VERIFIED:** New `scripts/addon_sync.py` and `scripts/addon_sync_guest.ps1` implement `check|sync|verify` on the main Windows PC and either/both VMware labs; see [workflow](workflows/addon-sync.md). A current read-only check found all six Lab-1 files matching and pinned, all six main-PC files matching but unpinned, and Lab-2 `guidance.lua` **Offline** (identical to Lab-1's Oct30 failure). Main-PC copies were pinned; Lab-2's Offline placeholder was preserved under a unique same-directory backup after a failed-safe cross-directory backup attempt, and the exact source `guidance.lua` SHA256 184A9E86D9F493A147B521EF5D04AC02AFF8B8A2DBF948A91D11DD74132102CE installed/pinned. **Independent `verify --target all` succeeded, exit 0**: PC/Lab1/Lab2 all six hashes match the repo and are present, locally readable, not Offline and Pinned. Evidence: ignored `artifacts/addon-sync/20261031T141653Z-5eda9e63/`. User-submitted subsequent screenshot shows `Guidance Initialised` without a visible addon error, but not a newly measured reader binding/freshness gate. No gameplay input, VM lifecycle, or game reload was performed by sync. **The separate Lab-1 sustained telemetry freshness failure remains unresolved; do not resume movement until requalification.**

**October 30 ~17:26 EDT — optimized Lab 1 live scanner FAILS sustained movement-feedback gate:** Candidate-region optimized reader SHA256 A4F6D9329A25695006F23695D776A8904A48FFAD487BA82BBABC4868270DB860 was successfully launched as guest PID 14232, bound to current addon nonce c0aa788dc0b74abbac7150bd511842dd with reviewed released input; strict two-sample feedback and action-readiness gate passed. Host controller was safely restored as PID 11616 and ready/disarmed/idle with no held inputs. **The full 480-second no-input strict observation did NOT qualify**: 474 advancing accepted fast-scoped receipts, 298 temporary not-fresh polls, worst no-new-valid-receipt gap **7.5649 sec** vs <4.5sec required, despite fast-scan median/P95 **132/149 ms**. Stable game/player/epoch, no movement input. Evidence independently checked, SHA256 FAC29EF3E85931505253CA42DF51C38A220E11BDC46E73AC82A637079F1D367E. See [optimized Lab 1 live failure and recovery plan](validation/lab1-fast-region-sustained-failure-2026-10-30.md). Do not attempt movement until cause fixed and fresh 8-minute qualification passes.

**October 30, 16:57 EDT — new fast-region reader BUILT AND OFFLINE VALIDATED, NOT DEPLOYED:** New standalone Windows x64 bundle at ignored artifacts/two-lab-resume-20261030/fastcandidate-published-01/RiftReader2.Live.exe, SHA256 A4F6D9329A25695006F23695D776A8904A48FFAD487BA82BBABC4868270DB860 (old deployed bundle SHA 322241A4...). Exact SDK 10.0.302, locked restore, Release build (zero errors/warnings), 561 .NET tests, six focused fast-region tests, format, real Lua/C# contracts, 1155 Python tests (2 skipped), and PS5-compatible native smoke all passed. The normal PowerShell 7 validation wrapper could not run because pwsh is not installed/available, so equivalent sections were tested directly and the limitation documented. No VM binary changed or movement input issued. Lab 1 strict telemetry still FAIL after 16.214-sec warmup gap; new build has not yet proved any live improvement. See [fast candidate reader build checkpoint](validation/fast-candidate-reader-build-2026-10-30.md).

**October 30, 16:49 EDT — Lab 2 strict eight-minute telemetry PASS independently verified:** The full read-only 480-second observation produced 376 distinct advancing receipts, 946 valid polls, maximum no-new-receipt gap **4.036 seconds** (under the 4.5-second bound), scan p50/p95/max 776.814/867.699/1505.419 ms, stable player/epoch and zero observer input. Five transient not-fresh polls occurred; clock synchronization remains an assumption. The source artifact checksum and structural metrics passed independent verification. See [Lab 2 eight-minute feedback acceptance](validation/lab2-eight-minute-feedback-acceptance-2026-10-30.md). This does NOT qualify Lab 1's failed 16.214-second gap or live movement. At ~20:49Z both hosts were authenticated, connected, disarmed and idle with no held keys, but earlier reader epochs had expired and must not be reused.

**October 30, 16:23 EDT — both lab controllers/readers operational, no movement yet:** Exact Lab1/2 RIFT game PIDs9928/7220, private receivers24588/28860, new one-hour readers8120/7828, reviewed nonce binding, strict source pins and independently advancing samples verified. New detached identity/hash-pinned host controllers PID51076/57852, Session2/inJob=false, both guest-connected, console exclusive, separate SQLite resource, disarmed/idle with zero held keys. Lab2 eight-minute fixed no-input observation STARTED and not yet accepted. Lab1 second full 480s diagnostic again FAILED: 245/252 accepted, five warming observations and one incomplete scan; max strict receipt gap 16.214sec. Root-cause engineering opportunity: both active readers published Oct29 21:56 UTC BEFORE candidate-region fast scan source commits Oct30 03:15–03:43 UTC. New optimized binary still requires build, tests and live qualification; do not weaken freshness gates or perform movement. See [current two-lab controller/reader recovery](validation/two-lab-current-controller-and-reader-recovery-2026-10-30.md).

**October 30, 16:08 EDT — Lab1 full-source gap diagnosis:** Two independent no-input probes show receiver sequences 895–899 were delivered inside an apparent **18.18-second strict-acceptance outage** (outer 894→900). Guest reader stdout confirms six consecutive scan-complete, selection-selected, delivered-http-200 reports with **freshness=warming** between 20:02:03 and 20:02:16 UTC, followed by freshness=fresh at 20:02:18. Strict poll calls were fast (median 3.74ms, max23ms). This is upstream source freshness/warmup suppression, NOT a stalled receiver or proven memory-scan hang. A later 120s no-input window accepted 63 distinct new receipts with max 3.174s gap, showing intermittency rather than a permanent failure. The exact trigger of warmup remains unproved; instrument candidate sequence/reason without weakening source freshness gates or claiming a full 8min pass. See [freshness warmup investigation](validation/lab1-freshness-warmup-investigation-2026-10-30.md).

**October 30, 15:57 EDT — Lab1 controller recovered; 8-minute feedback NOT qualified:** 480s strict observation: 297 distinct receipts, 928 valid polls, 23 freshness misses; scan median/p95/max 1.03/1.53/2.09 sec; stable player/epoch and zero planar drift. Two observed missing-new-receipt gaps **5.043s and 4.542s** exceed 4.5s movement freshness target, each with receiver sequence delta +3; monitor miss vs delivery stall not proven. Do NOT lower movement gate. New identity/hash-pinned detached host PID51076 Session2/inJob=false is verified connected to RIFT PID9928, holding console mutex, coordination ready, disarmed/idle/zero inputs, no recovery needed. Strict Lab1 source continued advancing after host startup. Lab2 remains controller-offline and addon unbound. See [Lab1 feedback and controller checkpoint](validation/lab1-feedback-window-and-controller-2026-10-30.md).

**October 30, 15:45 EDT — two-lab telemetry milestone 1:** Both RIFT clients and guest game identities reconfirmed; both preexisting receivers are verified alive and directly reachable on their host-only IPs. Two new one-hour readers launched (Lab-1 PID 8120, Lab-2 PID 7828). Lab-1 reviewed bind succeeded and released input, selected nine candidate frames, and passed strict source pin/advancing-addon feedback; read-only 3-second smoke window passed. Eight-minute sustained observation STARTED, not yet accepted. Lab-2 reviewed rebind was refused by the addon because no prior binding was active; a later fresh screenshot showed hostile Sinister Devil/combat cues, so the separately prepared chat action was NOT executed. Host controllers remain intentionally offline for console maintenance; no movement trial or queue reset. See [Milestone 1 validation](validation/two-lab-telemetry-recovery-2026-10-30.md).

**October 30, 15:17 EDT — separate ChatGPT Chat telemetry audit dispatched:** The coordinator submitted a new message through the Windows ChatGPT desktop application's Riftreader2-project new-chat composer (UI submission confirmed; the assignment text appeared in the conversation). The assignment is saved under ignored artifacts/two-lab-resume-20261030/phase2-workers-20261030/desktop-chat-telemetry-assignment-20261030.txt (SHA-256 b15744f37ddf0224459cb86fc9ec1dc6390cd3efed6dade52ca31b25a37800ba). The delegated Chat-mode worker must use the **maximum available agents and subagents** (target lead plus six if supported), avoid cloud Codex CLI because usage is exhausted, audit Lab1/Lab2 telemetry and defensive-feedback in read-only mode, and not change VM/game state or shared Git sources. Expected output: ignored artifacts/two-lab-resume-20261030/phase2-workers-20261030/desktop-telemetry-audit-20261030.md. The coordinator retains gameplay input authority and integration/commit ownership. **Dispatch does not prove the review completed, how many subagents were available, or the actual selected model.** GPT-6 and Extra High were requested, and the worker was instructed to verify them.

**October 30, 14:25 EDT — LAB-1 ADDON LOAD ERROR REPAIRED AND VERIFIED LIVE:** After the snapshot rollback, Lab-1 guidance.lua in the OneDrive AddOns directory was an Offline/reparse placeholder, while the five other files and manifest matched the source checkout. Lab-2 had all six locally readable and matching checkout hashes. The Lab-1 repair preserved the defective placeholder under guidance.lua.offline-backup-6a5637e766fb, replaced only guidance.lua with verified bytes from addon/RiftReader2/guidance.lua (SHA-256 184A9E86D9F493A147B521EF5D04AC02AFF8B8A2DBF948A91D11DD74132102CE), and verified all six installed hashes, local OneDrive pins, and absence of Offline flags. Game PID 9928 / exact game start identity remained unchanged. The reviewed /reloadui completed with verified input release; a fresh screenshot displayed the ordinary Readiness/Casting UI without the prior error. A separate reviewed /rr2guide status produced **RR2 GUIDANCE UNBOUND** and its binding instruction in live game chat, proving guidance's slash handler loaded. This verifies addon load/status only, NOT a fresh current reader binding, position feedback, or movement. Lab 2's files were untouched. Canonical six-file source: Git-tracked addon/RiftReader2/. Evidence: ignored artifacts/two-lab-resume-20261030/lab1-guidance-repair-01/, lab1-guidance-reload-01/, lab1-guidance-status-01/, lab1-readable-addon-hashes.json, and lab2-readable-addon-hashes.json. No addon source change needed. For further movement: bind a current reader nonce, requalify position telemetry, then check live controller ownership and action gates.

**October 30 two-lab post-reboot diagnostic handoff (13:53 UTC):** Both guests passed their doctors with cached logins and Codex CLI 0.165.0. Guest process inventories succeeded (Lab-1 161; Lab-2 191) and showed **no RIFT process in either guest**. Lab-1's private controller host config was updated to its new VMX in RIFT-Lab-1 (Lab-2 unchanged); the static two-lab fleet now returns configuration-valid. BOTH authenticated host operator APIs still refuse connections (Lab-1 49811; Lab-2 49921); host controllers, game/agents and live feedback are **not ready**. The every-login cached credential fallback was previously fixed/committed at e1b9f1e; 40 focused tests passed. See [current two-lab movement handoff](workflows/two-lab-movement-resume-handoff-2026-10-30.md) and [superseding resume prompt](workflows/two-lab-movement-resume-prompt-2026-10-30.md). Historical Oct 29 Lab-2 arrivals are not current-run evidence.

**Post-reboot Lab-1 guest access restored (October 30):** VMX now resolves to
`C:\\rift modding\\VMs\\RIFT-Lab-1\\RIFT-Lab.vmx`. The guest session checks
its current cached-credential target on every login and falls back to the
explicit old-path Lab-1 cache only when absent (no credential export or rewrite).
`lab_codex.py doctor --lab lab1` passed with `status=ready`, guest login
available, Codex CLI `0.165.0`, VM PID `11164`, VNC `5905`. Independent
`lab_guest_probe.py --lab lab1` succeeded (161 guest processes) and confirmed
RIFT was **not** running. Controller API/agent readiness has not been retested;
this recovery verifies guest access, not the game controller.

**Pre-reboot Lab-1 controller recovery:** The October 30 VMware rollback to
`baseline-codex-connected-lab1-20261029` succeeded and the guest/Codex doctor
is ready. Lab-1 RIFT was absent and main-PC controller API `127.0.0.1:49811`
still refused connections. VNC 5905 was identified under the restored VMX
identity; older below references to a missing listener precede this rollback.
All VM/game/controller PIDs become stale after Joey's planned host reboot.
Read the [reboot handoff](workflows/lab1-controller-handoff-2026-10-30.md)
and [full incident report](validation/lab1-controller-recovery-incident-2026-10-30.md)
before recovery. No host controller was relaunched by the rollback.

**Resume package:** [Movement handoff](workflows/movement-handoff-2026-10-29.md)
and [researched resume prompt](workflows/movement-resume-prompt-2026-10-29.md).
Next priority: restore the Lab-1 main-PC controller and guest RIFT/agent
readiness, then repeat a bounded chosen-coordinate trial on safe terrain using
fresh bindings and calibrations.

**Fast feedback and chosen-coordinate follow-up — LAB-2 ACCEPTED; LAB-1
CONSOLE RECOVERY NEEDED:** The former ignored 6 GiB Lab-1 wrapper is replaced
by tracked [per-lab scan limits](../config/live-reader-scan-limits.json): 4 GiB
by default and 6 GiB for Lab-1. Anchored 512 MiB candidate-region observations
were measured at 155.45–175.69 ms (roughly 155–178 ms) in retained Lab-1
low (`artifacts/practical-movement-20261029/lab1-onegib-postturn-forward-run-01/feedback/next-1476-1477-receipt.json`, local evidence)
and high (`artifacts/practical-movement-20261029/lab1-onegib-postturn-forward-run-01/feedback/barrier-1473-1475-receipt.json`, local evidence)
receipts,
while the complete multi-gigabyte scan remains the fallback rather than being
removed. Lab-2 accepted a reviewed `rebind` to reader nonce
`9f9bbf86987d4b108a3218bcd47056dc` without `/reloadui`; the unchanged game
process identity is in the console execution receipt (`artifacts/practical-movement-20261029/lab2-headroom-rebind/execution.json`, local evidence),
and the successor reader then produced a bound
calibration result (`artifacts/practical-movement-20261029/lab2-headroom-wcal-run-02/result.json`, local evidence).

The current feedback-headroom and anchor-before-action ordering changes produced
two accepted Lab-2 paths. A straight reviewed run arrived after two W pulses
(208 ms total), ending 0.095 planar units from its chosen point
(result (`artifacts/practical-movement-20261029/lab2-reorder-forward2-run-01/result.json`, local evidence)).
A separate reviewed chain completed a 50 ms D turn without claiming heading,
then a fresh 150 ms W calibration, then two W pulses (263 ms total), ending
0.100 planar units from its chosen point
(turn (`artifacts/practical-movement-20261029/lab2-reorder-turnforward-turn-run-01/result.json`, local evidence),
calibration (`artifacts/practical-movement-20261029/lab2-reorder-turnforward-cal-run-01/result.json`, local evidence),
arrival (`artifacts/practical-movement-20261029/lab2-reorder-turnforward-goal-run-01/result.json`, local evidence)).
An independent repeat completed only its reviewed 50 ms D turn; the next
pre-input capture (`artifacts/practical-movement-20261029/lab2-reorder-repeat-cal-probe-01/capture/image.bmp`, local evidence)
showed nearby bears, so the calibration and forward stages were deliberately
not reviewed, armed or run. That safety stop remains valid. A later independent
repeat on cleared terrain completed a fresh reviewed 50 ms A turn, a post-turn
150 ms W calibration, and a calibration-derived 1.5-displacement forward goal.
It reported `ARRIVED` after two W actions (219 ms total), ending 0.061 planar
units from that point
(result (`artifacts/practical-movement-20261029/lab2-reorder-repeat2-goal-run-01/result.json`, local evidence)).
This establishes one independent repeat of the narrow reviewed
turn-calibrate-forward flow, not arbitrary-coordinate steering, changing-world
reliability or 3-D navigation.

A stronger Lab-2 trial fixed X/Z goal `(7139.149, 3191.491)` before a reviewed
20 ms D turn and kept that exact point through the fresh post-turn W calibration
and all three movement preparations
(pre-turn review (`artifacts/practical-movement-20261029/lab2-fixedgoal-turn-plan-01/review.json`, local evidence)).
The first two movement executions expired at the lease/pre-arm boundary without
an action artifact or input; both ended disarmed with no sampled input down
(run 1 final (`artifacts/practical-movement-20261029/lab2-fixedgoal-run-01/final-status.json`, local evidence),
run 2 final (`artifacts/practical-movement-20261029/lab2-fixedgoal-run-02/final-status.json`, local evidence)).
The third preparation preserved the same goal and reported `ARRIVED` after one
44 ms W pulse, ending 0.057 planar units away. Release succeeded, and final
status was disarmed, idle, recovery-free and showed no sampled input down
(accepted result (`artifacts/practical-movement-20261029/lab2-fixedgoal-run-03/result.json`, local evidence),
action (`artifacts/practical-movement-20261029/lab2-fixedgoal-run-03/action-1.json`, local evidence),
final status (`artifacts/practical-movement-20261029/lab2-fixedgoal-run-03/final-status.json`, local evidence)).
This proves one fixed-before-turn reviewed coordinate arrival in the retained
Lab-2 epoch; it does not establish arbitrary-coordinate routing or 3-D arrival.
An independent second fixed-goal workflow then selected X/Z
`(7138.650, 3192.951)` before another reviewed 20 ms D turn, preserved that
exact point through a fresh 150 ms W calibration, and reported `ARRIVED` after
one 52 ms W action. It ended 0.010 planar units from the goal; release succeeded,
and final status was disarmed, idle, recovery-free and showed no sampled input
down
(pre-turn review (`artifacts/practical-movement-20261029/lab2-fixedgoal-repeat-turn-plan-01/review.json`, local evidence),
calibration (`artifacts/practical-movement-20261029/lab2-fixedgoal-repeat-cal-run-02/result.json`, local evidence),
arrival (`artifacts/practical-movement-20261029/lab2-fixedgoal-repeat-goal-run-02/result.json`, local evidence)).
This is a second independent reviewed success in the same retained Lab-2
game/reader epoch. It improves repeatability evidence for this narrow planar
procedure, but still does not prove arbitrary goal selection, 3-D navigation,
changing-world reliability or operation on Lab-1.

The stalled-VNC cleanup fix at `3253ece` then completed and saved a new Lab-2
live capture through the patched client
(capture receipt (`artifacts/practical-movement-20261029/lab2-patched-console-capture-01/capture/capture.json`, local evidence)).
That is a Lab-2 console-path check only. Lab-1 still has no listener after its
reset and remains a separate recovery task; the Lab-2 result does not qualify
Lab-1's console.

Lab-1's reviewed 96 ms W pulse was delivered and released, and a later retained
fast observation placed the character at `(7417.4199, 2926.6099)`, 0.081 planar
units from fixed chosen point `(7417.5, 2926.62)`
(post-timeout observation (`artifacts/practical-movement-20261029/lab1-repeat-chosen-final-posttimeout-observe-01/next-2306-2307-receipt.json`, local evidence)).
The synchronous runner timed out before accepting that observation, so this is
physical arrival evidence, not an accepted movement result. After the later
Lab-1 reset, the latest host check found no VNC listener and three guest audits
found no RIFT process (latest audit (`artifacts/practical-movement-20261029/lab1-cold-game-audit-01/result-03.json`, local evidence));
Lab-1 therefore is not currently console/game ready. All arrival numbers above
are planar X/Z evidence for the exact retained game/reader epochs, not 3-D,
unattended navigation or patch-stable qualification. Next practical task:
restore Lab-1's console listener and game, then obtain a clean independently
reviewed repeat on safe terrain before expanding the steering workflow.

**Practical two-lab waypoint follow-up — BOTH PLANAR TRIALS ARRIVED:** With the
optimized reader, Lab-1 used its fresh W/Q calibration to reduce planar goal
distance from 0.648 to 0.071 units in two feedback-driven actions; Lab-2 used
its explicit S-only calibration to reduce planar distance from 1.003 to 0.011
units in two actions. Both results include verified release, STOP/disarm and a
distinct advancing stationary confirmation. These are planar X/Z arrivals,
not 3-D arrival evidence: Lab-2 was on a slope and its Y changed by about 0.64
units while the 1-D controller intentionally evaluated planar distance. See
the retained Lab-1 result (`artifacts/practical-movement-20261029/lab1-goal-run/result.json`, local evidence)
and Lab-2 result (`artifacts/practical-movement-20261029/lab2-goal-run/result.json`, local evidence).
The new addon files were installed on both guests without reloading the UI.
Lab-1 then accepted a reviewed live `rebind` to a successor reader without a
reload (execution (`artifacts/practical-movement-20261029/lab1-rebind-01/execution.json`, local evidence));
Lab-2's already-loaded addon did not expose the newly installed command until
`/reloadui`, as expected for changed Lua source. Lab-1's scan used a temporary,
ignored 6 GiB launcher wrapper after its readable-private-memory total crossed
the prior 4 GiB budget; this is an experiment-specific workaround, not durable
tracked configuration. The full repository gate passed; retained local evidence
is `artifacts/validation/20261030T001410Z-5b54bcb9`.

**Automated two-lab movement trial — PARTIAL LIVE RESULT:** Lab-1 completed one
bounded 2-D waypoint arrival using two feedback-driven pulses (147 ms total),
ending 0.119 units from its goal. STOP/disarm preceded an independently advancing
stationary confirmation. Its repeat stopped after one pulse when fresh feedback
became unavailable. Lab-2 qualified an explicit S-only 1-D calibration, but both
goal attempts stopped before arming; no Lab-2 arrival is accepted. All attempted
sessions released inputs and their queue leases. Reliable movement on both labs
remains unproved: Lab-2's acquisition outages included a 56.7-second interval.
Checkpoints through `1a07583` correct scan-interval timing, pre-arm readiness,
post-action acquisition barriers and released arrival confirmation. The final
movement code gate passed 549 .NET tests. A subsequent buffer-reuse optimization,
`2d38866`, passed 551 .NET tests and ran 1,068 Python tests (1,066 passed, two
skipped), plus native/Lua checks. It removes per-chunk accumulator allocations;
it has not been deployed to the labs, and its live effect remains unmeasured. See the
[movement trial report](validation/automated-movement-two-lab-2026-10-29.md)
for evidence, remaining acquisition work and final cleanup. Live input has ended;
the bounded journal finished, both temporary guest readers were stopped, and
both temporary receiver processes/listeners are absent. Terminal receipt hashes
and cleanup were independently verified at 22:02:53Z.
Both game processes remain running and their control hosts are connected/ready,
disarmed and idle, with no sampled desktop inputs down.

**Two-lab live guidance hour — ROUND TRIPS AND BOUNDED MOVEMENT VERIFIED:**
Both labs accepted separate reader bindings and displayed independently calculated
guidance using their own fresh game/reader/player identities. Lab-2 displayed a
changed calculation to the same destination after a reviewed 150 ms backward
pulse (5.00 to 5.62); Lab-1 reproduced this after a reviewed 150 ms forward pulse
(5.00 to 5.99). Exact calculations and cleanup are recorded in the
[hour report](validation/two-lab-guidance-hour-2026-10-29.md). Both pulses have
delivery, release, API displacement and normal queue/host cleanup evidence.
Movement-triggered invalidation remains unproved: result expiry preceded input.
The helper now uses a strictly newer post-input receiver observation instead of
a slow GuestOps recheck; one verified execution fell from 14.627 s to 2.347 s.
A transient stale-receipt follow-up retains the four-second deadline and never
retries input. Full gate: `20261029T194027Z-ab9a7a36` (540 .NET, 1,008 Python
run/1,006 passed/2 skipped, 110 Lua, 22 shared cases, two synthetic round trips).
Native lab Codex chats supplied guest-local checks and cross-lab arithmetic
reviews via the main coordinator. The live receiver was reused serially;
simultaneous live collection is not established by this experiment.
Both bounded readers subsequently terminated and the temporary receiver was
stopped. Final control hosts remain connected/ready, disarmed and idle, with no
held desktop inputs or queue holders; see the report's final cleanup evidence.

**Native Codex pipeline collaboration - OFFLINE BOUNDARIES VERIFIED:** Lab-1
traced installed observation production, Lab-2 traced guidance acceptance and
invalidation, and the coordinator relayed a cross-review. The resulting
focused Lua tests exercise exactly 10 seconds versus over, and exactly 0.5
coordinate units versus over, with an independently fresh observation. These
are offline source tests, not live movement or full-game restart proof. See
[pipeline review](validation/native-codex-pipeline-boundaries-2026-10-29.md).

**Native Codex complementary review - PASSED WITH LAB-1 FOLLOW-UP:** Both
guest chats completed concurrent read-only tasks and a coordinator-relayed
review. Lab-1 reported its guidance.lua offline/recall attributes despite a
running OneDrive process; Lab-2 checked installed guidance freshness logic and
the manifest/main startup dependency. These are disk/source observations, not
a live game test. One passive wait briefly returned `Task host changed during
passive read`; an exact-host read recovered the completed Lab-2 response. See
[review](validation/native-codex-complementary-review-2026-10-29.md).

**Native Codex addon inventory - LAB-1 FOLLOW-UP NEEDED:** At 17:37 UTC both
guest chats independently reported their Windows identities and no RIFT process.
Lab-2's installed TOC, guidance.lua and main.lua matched the main checkout at
`d9760e7`. Lab-1's TOC and main.lua matched, but its guidance.lua had a recall
attribute and was intentionally not opened or hashed. This is not a verified
read failure or proof of loaded addon state. See the
[native inventory](validation/native-codex-addon-inventory-2026-10-29.md).

**Browser Workbridge guest probe - BOTH LABS PASSED:** Normal ChatGPT in the
in-app browser launched two overlapping Workbridge jobs that independently
listed guest processes through VMware GuestOps, without invoking guest Codex.
Both returned exit 0 and the browser displayed the final report. Chrome showed
completed response-load errors even for a simple control; its underlying issue
is unresolved, while the in-app browser is a verified workaround. See
[the test](validation/browser-workbridge-codex-free-2026-10-29.md).

**Browser ChatGPT + Workbridge two-lab diagnostic - PARTIAL PASS:** A normal
browser ChatGPT chat submitted both existing `lab_codex.py doctor` commands via
Workbridge; separate overlapping jobs finished exit 0 with ready diagnostics
for the correct distinct labs. The browser's final answer and a follow-up failed
to render, so the coordinator verified actual job outputs independently. The
route uses VMware GuestOps and the installed Codex CLI for preflight; it does
not prove an independent guest AI task. See the
[comparison](validation/browser-workbridge-two-lab-2026-10-29.md).

**Native Codex two-lab teamwork - SIMPLE TASK PASSED:** The main-PC chat sent
read-only prompts to existing native remote chats in both labs. Each executed a
local command, reported its distinct machine name and calculated the same
guidance example. The main PC relayed Lab-1's result to Lab-2 for comparison;
Lab-2 agreed and supplied a stale-position counterexample. Initial tasks
overlapped; a narrow Lab-2 process check was corrected in a follow-up. This
proves a small native chat/task/handoff cycle, not automatic file sharing or
live RIFT readiness. See [verification](validation/native-codex-teamwork-2026-10-29.md).

**VM snapshot baselines - CREATED:** Both powered-on labs now have verified
named VMware snapshots, including memory; Lab-2's older snapshot remains.
The script uses cached encrypted-VM credentials through a private console and
independently lists the result. Both native Codex host reads passed afterward;
restoration has not been tested. See [lab snapshots](workflows/lab-snapshots.md).

**Sequential reboot check - BOTH CODEX HOSTS PASSED:** Lab-1 and Lab-2
automatically reconnected under their existing identities after fresh Windows
boots. Lab-2's first reboot exposed a competing packaged desktop server and
six HTTP 409 log rows; disabling its per-user `OpenAI.Codex` startup task,
as already done on Lab-1, resolved the observed conflict on a second reboot.
Both settled checks reported zero 409s and main-app exact-host reads succeeded.
User logon is required; game readiness was not verified. See the
[two-lab reboot check](validation/two-lab-codex-reboot-2026-10-29.md).

**Both native Codex hosts - LOGON START VERIFIED:** Lab-1 now uses
`RiftReader2-CodexRemote-Lab1`, an interactive limited logon task with an
Explorer handoff, matching Lab-2's architecture. A fresh Lab-1 reboot at
16:21:09Z produced automatic dispatcher and non-admin worker receipts; the
worker reported connected under the original Lab-1 environment ID. Main-app
exact-host reads succeeded for both labs. Lab-1 uses shorter delays and records
an already-online conflict without stopping an existing server. After an
earlier duplicate produced 409 warnings, Lab-1's package-specific Windows
startup task was disabled; the app remains available to open manually. The
final reboot and 105-second settled check showed no app duplicate or 409.
Both starts
require user logon; neither establishes game-control readiness. See the
[Lab-1 startup verification](validation/lab1-codex-autostart-2026-10-29.md).

**Lab-2 native Codex auto-start - VERIFIED AFTER REBOOT:** One per-user
interactive/limited scheduled task dispatches the existing native host via
Explorer after logon. On the 16:01:04Z reboot, the task fired automatically;
fresh dispatcher and worker receipts reported Session 1, non-admin,
`connected`, `RIFT-LAB-2`, and the existing native environment ID. Main-app
exact-host read passed. It requires `mrkoo` to log on; this is not a pre-login
service. RIFT and the guest control agent were not running. See the
[startup verification](validation/lab2-codex-autostart-2026-10-29.md).

**VM Windows names and repeated reboot - VERIFIED:** Both guests now report
`RIFT-LAB-1` and `RIFT-LAB-2`; final boots were 15:44:08Z and 15:45:07Z.
The main app successfully read each existing native Codex host after reboot.
Lab-2 required a normal signed-in Explorer-session host start; it then reported
connected under its existing environment ID and the earlier HTTP 409 did not
recur. Lab-2 automatic host startup is unverified. Name-bound control configs
were repaired, and successor main control hosts are running with reconciliation
required. RIFT and guest control agents were absent after the final reboot;
game-input readiness remains unverified. See the
[rename and reboot checkpoint](validation/vm-names-reboot-2026-10-29.md).

**Native Codex device connections - BOTH PAIRED; REMOTE READS VERIFIED:**
Both native guest daemons were already running and connected. Joey clarified
that the main PC was at code entry and the Allow error was inside a VM.
Exactly one native CLI pairing response per lab was privately passed to the
main app; successful remote-data reconciliation followed at 11:02 EDT for
Lab-1 and 11:12 EDT for Lab-2. Main-app host discovery and explicit
`read_thread` calls then returned existing remote data from both exact hosts
without tool errors at 11:14 EDT. Both have distinct environment IDs and
auto-connect enabled despite cloned Windows display names. Temporary private
codes were deleted. Initial host-not-found errors were registration races,
not persistent failures. No SSH, new chat, guest shell-execution test, RIFT
input or VM/game restart was used. The VM desktop Allow error itself remains
unclassified; the native CLI route supplied the working pairing mechanism.
New-job execution and reboot recovery remain unverified. See the
[pairing evidence and usage](validation/native-codex-remote-2026-10-29.md).

**Guest Codex project workflows - IMPLEMENTED AND VERIFIED IN BOTH LABS:**
Use `python scripts/lab_codex.py` for `doctor`, `dispatch`, `status`, `collect`,
`cancel`, `run` and `batch`. The ignored `.local/lab-codex.json` is configured
for the two existing guests. Main-PC source remains authoritative; jobs receive
selected frozen source files and return schema-checked, hash-bound reports.
No SSH, port, persistent service or global Codex change was needed.

The real sample batch ran both signed-in Codex CLI 0.165.0 installations in
parallel from clean source commit `47f8f2b`. Lab-1 reviewed the supplied guidance
source; Lab-2 reported matching SHA-256/lengths for all three installed sample
files. Independent review checked those reports and their task/input/VM/report
provenance. Repeated collections were identical, repeated status remained
terminal, and cancelling an already completed job was a no-op. Disposable
Windows process tests verify active cancellation and timeout cleanup of the
worker-owned CLI and its child. Both RIFT control hosts retained their exact
host/agent/VM/game identities and remained ready, disarmed and queue-idle.

Full implementation validation passed: 539 .NET tests, 999 Python tests run
(2 skipped), Lua/shared contracts, published smoke and 720 relative links.
Plan `861355c`, guest worker `9596b7f` and host workflow `47f8f2b` are committed.
See the [operator guide](workflows/lab-codex.md),
[live acceptance record](validation/lab-codex-workflows-2026-10-29.md), and
`artifacts/lab-codex-validation/live/summary.json`. The sample batch index is
`artifacts/lab-codex/batch-b241a27f-174d-479d-a905-63250cedb08e/batch.json`.
Jobs are read-only analysis/diagnostics; guest patch application, writable
repository synchronization and game-input coordination are not added by this
workflow. Continue actual project research with small explicit guest tasks.

**Two-lab native control fleet - LIVE VERIFIED:**
Both independent coordinated control hosts are connected, ready and disarmed.
Lab-1 uses agent `192.168.56.1:49810`, operator `127.0.0.1:49811`, guest
`192.168.56.128`, VNC 5905 and resource `vm:rift-lab-1`. Lab-2 uses agent
`192.168.56.1:49920`, operator `127.0.0.1:49921`, guest `192.168.56.129`,
VNC 5962 and resource `vm:rift-lab-2`. Windows refused the original Lab-2
49820 bind; the replacement pair was bind-tested and verified live.

Each host completed authenticated status, native RIFT screenshot capture,
normal queue cleanup and a managed graceful guest-agent restart. Reconnecting
one lab preserved the other lab's host, connection, VM and game identities.
Both finished ready, unarmed, not busy, recovery-free, with no sampled held
inputs, occupied queue resource or pending request. The new journals contain
zero arm/action/recover commands. This verifies connections, captures and one
reconnect per lab, not movement or automatic recovery after PC/VM restart.
Both VMware tabs are visible; Lab-2 was explicitly opened after a background
launch caused confusion about its running state.

Fleet preflight now permits cloned Windows machine names while keeping exact
per-host machine matching and distinct VM/IP/credential/endpoint guards.
The VM ownership query uses Windows' listener-filtered table classification
instead of its inconsistent passive TCP state field. Two diagnostic Lab-2
cycles did not fix that metadata; no further restart or weakened process
identity check was needed. Existing permitted `pythonw.exe` runs both hosts;
no firewall rule was changed. Both guest-local Codex CLI 0.165.0 read-only,
ephemeral diagnostic tasks completed successfully using the existing logins.

Current verified VMX/RIFT PIDs are Lab-1 `49392 / 6988` and Lab-2
`52072 / 11896`, with the same `1935...A4BE8` executable build. These supersede
the session identities in older checkpoints below. Lab-2's unreadable
OneDrive `guidance.lua` was also backed up, replaced, all six core files
hash-verified/pinned, and reloaded without the visible addon error.
Full source validation passed: 539 .NET tests, 973 Python tests run (2 skipped),
Lua/shared contracts, published smoke and 700 links. See the
[live validation and maintenance boundary](validation/control-fleet-live-2026-10-29.md)
and `artifacts/control-fleet-repair-20261029/reconnect-isolation-v3/`.

**Lab-1 Guidance load error - REPAIRED AND VERIFIED LIVE:**
The user's current screenshot showed `main.lua:6` indexing nil `Guidance`.
Installed TOC and five readable core files matched source; `guidance.lua` was
an unreadable OneDrive placeholder: Windows reported the cloud file provider
was not running. The placeholder was preserved under a unique backup name,
the exact repository guidance file installed and locally pinned, and all six
installed core hashes verified. No Lua fallback or source change was needed.
After the user reserved idle Lab-1, a guarded UI reload completed without the
error popup. `/rr2guide status` responded **RR2 GUIDANCE UNBOUND** plus its bind
instruction, proving the module and slash handler loaded. This is load/status
recovery, not a Lab-1 external guidance round trip. VM epoch stayed 68572;
current RIFT PID/start is `8388 / 639288504643259710`, same `1935...A4BE8` build.
Evidence: `artifacts/lab1-guidance-repair-20261029/`,
`artifacts/lab1-guidance-file-metadata-20261029/`, and
`artifacts/lab1-guidance-status-20261029-01/`. Input cleanup passed; RIFT remains
in world. Ordinary Casting/Readiness panels were hidden for command entry.

**Earlier fleet preflight checkpoint - SUPERSEDED BY LIVE VERIFICATION ABOVE:**
The original port-49712 control/telemetry collision was reproduced, and static
five-config fixtures passed before live migration. Lab-1/Lab-2 migration is now
verified; three/four/five active VM capacity and discovery throughput remain
unmeasured. See the
[current allocation](reference/native-vm-controls.md#multiple-vm-configuration-preflight).

**Lab-1 recovery — BACK IN GAME; GUEST OPERATIONS RESTORED:**
Joey's requested health check found a healthy game but wedged VMware GuestOps.
VMTools and VGAuth service restarts, an elevated installed-Tools Repair, and an
orderly Windows restart did not restore authenticated commands. Joey approved
restarting Lab-1; a complete orderly VM stop/start ended the old VM process and
restored GuestOps. This was the observed recovery step; the root cause is not
proved. The VM now has PID `68572`, native start ticks `134377147707331937`,
log epoch `2026-10-29T02:32:50.782Z`, VNC 5905.

Normal Glyph launch retained its saved login. RIFT returned as Atank (45) at
Thedeor's Circle, Sanctum after leaving the previous dimension during exit.
Fresh authenticated collections before/after loading show RIFT PID `8160`,
native UTC start ticks `639288387782122269`, executable
`C:\RIFT_TRANSFER\RIFT\rift_x64.exe`, SHA-256
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
Both VMware services are Running. Visible game samples were 50/46 FPS;
ReaderBridge 0.3.2 advanced 76 -> 304, Casting 0.2.3 advanced to 2843, and
Readiness loaded. The ordinary Daily Rewards popup was closed; addon panels
remain visible. All input is released. No gameplay action trial was run.

Repeated cached GuestOps collection/copy/cleanup passed. The broad addon-file
inventory exceeded its guest PowerShell time cap; a smaller launch inventory
and final exact game identity succeeded. Do not claim complete addon hashes,
field qualification, or a working external control host: the known configured
control-host endpoint still refuses connection. Evidence:
[validation checkpoint](validation/bidirectional-hybrid-2026-10-28.md),
`artifacts/bidirectional-20261028/lab1-health-check-after-restart-summary.json`.

**First live static hybrid round trip — LAB-2 PASS, INCLUDING EXPIRY:**
The addon source -> external calculation -> reviewed console delivery -> addon
display loop succeeded in Lab-2. Result 1 showed planar distance **5.00**,
**dX +3.00 / dZ +4.00 / dY +0.00** from an actual fresh API snapshot.
The addon chat accepted it with source age **1.797 seconds**, and the panel
showed about 2.1 seconds. A later no-input screenshot showed **UNAVAILABLE /
Source expired**, with active numbers removed. This is a post-limit expiry
observation, not exact threshold timing. Independent source/command/math/hash
and screenshot review passed.

Source epoch/sequence/clock/player were
`1 / 2568 / 30891.716796875 / u035400012DFEB5BC`. RIFT remained
`2700 / 639288075394270241`, build `1935...A4BE8`. The bounded reader is
`9384 / 639288371649316705`, nonce `ba60619b5e9549e8994db9e9bb571700`,
expiring automatically at `2026-10-29T03:19:24.9316705Z`. The receiver owns
`192.168.56.1:49712` (PID 24144/start `639288285817563485`). These are session
facts, not durable configuration. Evidence:
`artifacts/bidirectional-20261028/deferred-result-7fca06f4d8b04574ba4fc5c5334cfc41/`,
`lab2-result-expiry-01/`, and the validation checkpoint above.

The reviewed helper is committed as `b862c93`. It uses separate ordinary Hide,
Enter/open-empty-focused-chat and exact allowed-command steps. First Enter
may clear AFK only; a separately reviewed second Enter opened chat. Deferred
result intent pins destination/sequence/calculator before review, then computes
from a new authenticated receipt after review without relaxing age gates.
The old leading-slash focus assumption was rejected and retired.

The authoritative full helper gate passed: **539 .NET tests, 962 Python tests
(2 skipped), 110 Lua lifecycle/encoder checks, 22 existing shared Lua/C# cases,
two synthetic lab-bound Lua -> C# -> Lua guidance round trips**, Release
build/format, native smoke, deterministic replay and 685 relative links.
Evidence: `artifacts/validation/20261029T014842Z-76addab5/`, log
`artifacts/bidirectional-helper-final-gate-20261028.log`.

**Next useful increment:** one supervised manual movement checkpoint to verify
live result invalidation/recalculation, then independent Lab-1 reproduction.
One static Lab-2 case does not establish guidance across full-game restart,
second-lab delivery, routes, facing, camera projection or actions. Patch recovery
and direct Computer Use remain deferred.

**Two-lab hybrid roadmap — USER SCOPE UPDATE, OCTOBER 28:**
Joey authorized using **RIFT-Lab-1 and RIFT-Lab-2** for faster parallel
discovery and validation, superseding the earlier Lab-2-only restriction for
this work. The [saved combined prompt and roadmap](planning/bidirectional-hybrid-two-lab-roadmap.md)
defines complementary lab roles, separate identities/evidence/endpoints,
one input controller per lab, and the first useful demonstration: addon
coordinates -> external distance/direction calculation -> addon display.
The initial baseline/transport assessment is recorded in the feasibility document; current results and the next increment are above.
This update saves the plan; it does not claim a working return channel or
fresh Lab-1 validation. Existing game-input limits, patch-recovery and direct
Computer Use deferrals remain. Lab-2 Casting v0.4.0 acceptance is still pending.

**Casting HUD v0.4.0 — LAB-2 DEPLOYED/HASH-VERIFIED, LIVE INPUT CHECK PENDING:**
The dashboard and 20-choice/page ability picker now have draggable headers.
Main panel, picker and the separate RIFT-restricted Cast/Stop frames share one
viewport-clamped position. Valid positions persist in character evidence;
malformed saves fail safely and restoration waits for nonsecure game state and
valid viewport. The Header **Hide** button has raised contrast and foreground
layering after the user's v0.3.0 screenshot showed it too dark to read.
The original `/rr2cast` show-only slash handler now offers a color-coded CLI:
`help`, `status`, `info`, `show`, `hide`, `toggle`, `abilities`, `record`,
`position`, `move X Y`, and `reset`. Help explains the protected manual-click
requirement and that hostile-facing/LOS **remain UNVERIFIED**. No CLI command
casts, starts autoattack, automatically moves a character or retries a spell.
The TOC-driven title and once-per-load green-teal chat notice now say **0.4.0**.

**71 focused Casting tests and 904 repository-wide Python tests (2 skipped)
passed**, along with Lua 5.1 syntax and `git diff --check`; no C# source was
changed for this version. A guarded v0.4.0 deployment was installed **only in
RIFT-Lab-2**, after exact game process, VM identity, old-file, staged-file,
backup and source hash checks. Independent postflight matched all three
installed hashes, PID **2700**, and unchanged process start. The versioned
receipt is `artifacts/rr2-lab2-hud-deploy-20261028-07/`, run
`7c64061e50024a40be59e655e0f1e908`. Rollback was unnecessary; the verified
v0.3.0 guest backup remains. **No game input, reload or physical click was
sent.** Joey must type `/reloadui` in Lab 2 and check the drag handles, Hide,
`/rr2cast help`, picker position persistence and manual secure Cast/Stop
clicks. This deployment proves file installation, **not** runtime hit testing
or real secure click behavior. Resume from the
[October 28 Casting handoff](workflows/casting-handoff-2026-10-28.md), with
[controls and limitations](reference/casting-readout.md).

**Casting HUD v0.3.0 — PREVIOUS LAB-2 DEPLOYMENT/HASH-VERIFIED; TITLE SEEN IN USER SCREENSHOT:**
A professional two-column visual refresh replaces the mismatched glossy native
Cast/Stop buttons with flat restricted RIFT Frames styled consistently with the
other 40-unit controls. The 584 x 602 panel standardizes color, hierarchy,
spacing, typography and the 20-entry two-column picker; a protected action tray
remains separate from ordinary controls. **API READY** now names only verified
API-based gating. Distinct **FACING UNVERIFIED** and **LINE OF SIGHT
UNVERIFIED** chips prevent claims unsupported by the captured API evidence. The TOC-driven title and once-per-load colored chat notice report
**v0.3.0**. The last captured in-game documentation (from before the October 27 game
patch) provides XYZ but no general target-facing/yaw or hostile LOS flag; its
group-member-only `blocked` field does not prove generic hostile LOS. The
current build needs a fresh API evidence capture before implementing either.

All three addon files were installed **only in RIFT-Lab-2** after identity,
source/staging hash, verified guest backup and exact process checks. An
independent postflight verified the installed TOC/model/main SHA-256 under
`artifacts/rr2-lab2-hud-deploy-20261028-06/` (run
`17c9896ae6e642608adadda309b4f665`); PID **2700** and the exact
RIFT process epoch stayed unchanged. Rollback was unnecessary; no game input,
UI reload or live click verification occurred. **Joey must enter `/reloadui`**
and manually verify the title, chat notification, picker, Cast and Stop
clicks; an ensuing user screenshot confirmed the v0.3.0 title but showed Hide
too dim and did not establish chat notification or click dispatch. Source gates:
**61 focused Casting tests** and **894 Python tests (2 skipped) passed**;
no C# source changed in this increment. See
[the design and API constraints](reference/casting-readout.md).

**Casting HUD 0.2.4 — PREVIOUS DEPLOYMENT/HASH-VERIFIED IN RIFT-LAB-2;
POST-RELOAD CHECK SUPERSEDED BY v0.3.0:**
Version 0.2.3 added a TOC-derived version to the HUD title, once-per-load
teal-green General chat notification, foreground label layers and fail-closed
ability costs. A fresh read-only Lab-2 capture in
`artifacts/rr2-lab2-v023-readonly-capture-20261028-03/` **visibly confirms
`RR2 CASTING  v0.2.3` and readable HUD header/cards/secure-button row**.
The chat viewport did not contain the initialization message, and the
Abilities picker has not been opened in a reviewed screenshot.

A follow-up bug hunt found that restoring a previously selected ability
could throw when modern RIFT ability APIs were missing. Version **0.2.4**
guards lookup before `pcall` and checks nested ability/unit/time API tables
in the read model so saved load and subsequent updates fail closed.
The title and once-per-load colored chat notice automatically use 0.2.4.
The interaction remains manual-only; Cast/Stop secure-button protections
and historical combat ID provenance are unchanged.

All three 0.2.4 files were installed **only in RIFT-Lab-2** using cached
authenticated VMware Tools. Source, staging, installed and separate
postflight SHA-256 matched under
`artifacts/rr2-lab2-hud-deploy-20261028-05/`
(run `907ae3454c5f4de08dd087c6e3f3434d`).
Game PID 2700 and exact process epoch remained unchanged, input was
not sent, rollback was not required and a verified backup remains.
**Joey must run `/reloadui` after this 0.2.4 installation** and manually
open/check Abilities and observe the teal-green initialization notice.
A read-only screenshot can confirm visual layout, but not click interception.

**Repo-wide October 28 bug hunt:** parallel audits reviewed addon Lua,
native capture, reader/live state, desktop tooling and tests. Confirmed
issues fixed in source include VMware PowerShell argument limits, staged
XYZ execution without pre-creating its capture directory, truthful launcher
maintenance outcomes, safe fenced/paginated maintenance admission, an
exception-safe position-read gate, finite wall-motion math, bounded profile
file reads and incomplete native scout snapshot status.
Independent gates passed: 519 .NET tests, 892 Python tests (2 skipped; 59
focused Casting and 12 guest-launcher tests), 108 Lua checks + 22 real-Lua/C#
cases, Release build and formatting, native publish, deterministic CLI
replay, 637 relative links and diff whitespace. See the [full bug-hunt findings](validation/rr2-bughunt-2026-10-28.md).
The combined `scripts/validate.ps1` launcher was unavailable via Workbridge;
these were separate checks. Guest maintenance admission was subsequently
fenced, paginated and guarded against heartbeat-start failures. Remaining
follow-ups include typed-scout staging cleanup, maintenance lease budget,
stationary wall-contact semantics and live visual/picker qualification.

**Casting HUD 0.2.1 — PREVIOUSLY DEPLOYED TO LAB-2 (HISTORICAL):**
Replaced the dense one-text-block panel shown in Joey's screenshot with a readable
status header, separate target/ability fields, four metric cards, trial outcome,
24-per-page flat-button ability picker, and aligned restricted Cast/Stop controls.
Hide now hides the secure buttons too when out of protected combat; `/rr2cast`
restores the full interface. Exact-target dodge is visible without promoting it
to a damage hit. Raw capture, identity checks and manual-only macros are unchanged.
Full validation passed: 514 .NET tests, 866 Python tests (two skips), Lua/contracts,
format, published-native smoke and 636 links. Evidence:
`artifacts/validation/20261028T030141Z-6aa9d0b8/`.
On Oct 27 evening ET, installed all three 0.2.1 source files **only in RIFT-Lab-2**,
using cached authenticated VMware Tools. Source/guest SHA-256 matched independently
at installation and in a second postflight; unchanged model Lua included. Guest
RIFT PID 10672, start 2026-10-28T01:25:39Z, new executable SHA
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
Previous files were hash-verified in a guest Public Documents backup; temporary
staging files were removed. Receipts: `artifacts/casting-lab2-ui-20261028-01/`.
That installation involved no game input, reload, restart or screenshot at
the time. An October 28 read-only capture later provided the 0.2.1
visual baseline. A subsequent 0.2.2 post-reload capture showed the new Cast
caption but revealed blank/dim labels, motivating 0.2.3 foreground layering.

**RIFT EXECUTABLE UPDATED — LAB-2 LUA SOURCE RECOVERED, NATIVE FIELDS PENDING:**
Lab-2 runs the October 27 `rift_x64.exe` with a new SHA-256. The current
RiftReader2.Live reader was staged separately; exact-process `inspect-native`,
64-byte module-header capture and 6,932-region native map succeeded. Old XYZ
and power profiles failed closed at runtime (exit 2, no stale reports).
**New:** Two time-separated 512 MiB bounded scans recovered four original
28,672-byte typed API snapshots. All four strict offline cross-run comparisons
reported `advanced-in-covered-scope`, stable player `u035400012DFEB5BC`,
sequence 14436/14437 -> 14545/14546, and Lua-source player position
**(7160.759765625, 821.2099609375, 3156.1499023438)**. The installed
Lab-2 API Probe 0.6.0 `validation.lua` matches its documented SHA. This is
fresh **Lua data**, not native XYZ, pointer stability or a movement test.
[Patch validation](validation/rift-lab2-patch-2026-10-27.md) and
[post-patch typed source proof](validation/lab2-typed-inline-postpatch-2026-10-27.md).
Read-only Lab-2 screenshot access was recovered for the 0.2.1 Casting HUD;
other addon behaviors and native-field semantics remain unverified.

**New-build native XYZ scout — 10 STRUCTURAL CANDIDATES, NO FIELD PROMOTION:**
`scout-values-native` in Lab-2 searched 256 MiB of high `MEM_PRIVATE` with
fresh Lua player X reference. It published 23 SHA-verified context snapshots;
19 still contained X on copy, and 10 had nearby float32 Y/Z exactly at
`X+4`/`X+8` within ±0.02 of the earlier Lua values. Five exact-epoch 76-byte
contexts reread later were byte-for-byte unchanged. A third typed API run
advanced the same player's sequence to **16731/16732** while Lua XYZ remained
stable; four more strict cross-run comparisons passed. Multiple copies and no
observed movement still block authoritative native-XYZ classification.
An attempted `vmrun -interactive` diagnostic failed before publication;
no screenshot or desktop control was established. See
[native XYZ candidate validation](validation/lab2-native-xyz-candidates-2026-10-27.md).

**Updated casting addon — DEPLOYED; RANGED-REACH HIT VERIFIED:**
Normal Chat worker preflight selected Light's Decree from the real API catalog;
the coordinator deployed matching addon hashes and used guarded helpers for two
separate 60s recordings. First attempt was dodged. After reviewing that evidence,
the second confirmed 402 Life damage on the exact selected dummy from a constant
5.179 derived coordinate distance, Power 100 -> 80 -> 100, and 12.006s effective
cooldown recovery. Other-dummy area hits were excluded; successful trial had no
autoattack events. The prior 0.2.0 panel was live-verified, not the 0.2.1 HUD. See the
[result and limitations](validation/casting-ranged-2026-10-26.md); export:
`artifacts/exports/casting-ranged-20261026-01/`. All input released, controller idle.
No source changes, full-game restart claim, health-loss test or patch recovery.
The later 0.2.1 addon displays exact-target dodge/avoidance distinctly;
raw evidence never promoted it to damage. Earlier undeployed notes below are history.

**Normal Chat worker workflow — TWO-WORKER TRIAL VERIFIED:**
An independent casting reviewer and workflow-doc writer ran concurrently through
Workbridge with separate file ownership. Both wrote local completion receipts;
the coordinator reviewed the results and guide diff. Casting review found no
concrete regression and passed 41 focused tests; live layout is still unverified.
The [worker recipe and task brief](workflows/workbridge.md) now use bounded inputs,
one writer per file, completed checks and a last-written result file, avoiding
dependence on browser final-response rendering. Evidence:
`artifacts/chat-workers-20261026-02/`. Documentation checks passed; no source or
live-game changes in this follow-up. No measured usage/speed saving is claimed.

**Casting range/timing readout — CHAT WORKER IMPLEMENTED, COORDINATOR VERIFIED:**
A normal Chat worker used Workbridge to add selected-ability API range min/max,
cast time and channel state to the existing panel. Missing/nonfinite numbers stay
unknown; only explicit zero cast time means instant. No additional API calls or
readiness/secure-casting changes. The coordinator reviewed the three-file patch;
full gate passed: 514 .NET tests, 861 Python passes/two skips (41 focused casting
tests), contracts, formatting, native smoke and 625 links. Evidence:
`artifacts/validation/20261026T055835Z-891717ad/`; worker record:
`artifacts/chat-worker-casting-20261026-01/`.
Not deployed or live-layout verified. Controls moved down 48 UI units: obtain
fresh screenshot targets before live clicks. Next: deploy the pending addon
increment and perform the separately scoped ranged-ability/cooldown test.
Patch recovery and health-loss testing remain deferred.

**Addon API reuse — IMPLEMENTED AND OFFLINE VALIDATED:**
Casting addon 0.2.0 uses the SpellDump batch List/Detail pattern and retains the
full known-ability inventory, with Cast-picker filtering kept separate. Independent
code informed by Rift Meter adds healing/overhealing outcomes and raw mitigation
fields; exact caster/ability/target IDs still gate each result. No third-party code
or libraries were imported. Offline replay preserves the prior 118-damage dummy
hit, seven events and two cooldown events. Full gate passed: 514 .NET tests,
858 Python passes/two skips (38 focused casting tests), contracts, formatting,
native publish smoke and 625 links. Evidence: `artifacts/validation/20261026T051331Z-5fd1d67f/`.
New healing/overhealing behavior is not live-qualified or deployed. No game input
was performed for this increment; patch recovery and health-loss testing stay deferred.

**Rift Meter review — COMBAT API REUSE:**
Inspected installed Rift Meter 1.2 source. It confirms modern combat `abilityNew`,
caster/target attribution, damage/healing and avoidance/mitigation events, plus
unit/pet owner lookup. Preserve raw events before its name fallback, pet merging,
combat-session filtering or display calculations. See the
[reuse findings](reference/riftmeter-api-reuse.md). No game input or addon changes.

**SpellDump review — API-FIRST ABILITY INVENTORY:**
Inspected both guest SpellDump implementations without changing them. Their
ability collection uses `Inspect.Ability.New.List()` plus one batch
`Inspect.Ability.New.Detail(ids)` call. SpellDump2 exposes range, costs, cast time,
channel/ground-target/stealth flags and descriptions; its offensive categories
are heuristics and must not replace the complete raw catalog. See the
[reuse findings](reference/spelldump-api-reuse.md). Next casting work should reuse
this catalog before further ability selection/testing. No additional game input.

**Casting readout — LIVE DUMMY HIT VERIFIED:**
The [detailed handoff and result](workflows/casting-handoff-2026-10-26.md) preserves
code, deployment, raw evidence, failed attempts and exact continuation steps.
A reviewed Aggressive Block click produced 118 damage to the selected Normal
Practice Dummy with exact player/target/modern ability IDs. The 60s capture has
565 samples: Power 100 -> 80 -> 100, health unchanged at 18208, effective cooldown 1.5s
with Begin/End separated by 1.514s. Out-of-range blocking and later melee readiness
were observed; explicit Stop autoattack ended follow-on attacks. Combat abilityNew
fixed the legacy-ID mismatch; names alone never qualify a hit. Files were hash
verified through cached-login VMware Tools. Raw result: `artifacts/casting-20261025-01/trial-evidence-04/`.
Full gate passed: 514 .NET tests, 849 Python passes/two skips, contracts, format,
native publish smoke and 619 links. Evidence: `artifacts/validation/20261026T045106Z-525cce97/`.
Final additional ID-conflict regression: focused casting suite 30/30 passed.
The narrow final guard is deployed as deploy-11; successful trial used deploy-10.
Export: `artifacts/exports/casting-dummy-20261026-01/` (report, JSON, CSV, evidence ZIP).
No casting restart, ranged/channel, moving-target or general facing/LOS claim.
Next practical increment: a separately scoped ranged ability/cooldown test.
Patch recovery and controlled player-health-loss tests remain deferred.

**Power normal interface/catalog — IMPLEMENTED AND LIVE VERIFIED:**
The [normal live JSON snapshot](reference/power-data-interface.md) now includes
independent `nativePower` values, exact identity, freshness and unavailable/expired
clearing. The 12-second guest run published 16 fresh 100/100 readings, then cleared
them on termination; Lua remained unavailable rather than inheriting native data.
The real Power catalog retains both tested sessions and supports meaning, locator
and one same-build restart. Standard discovery JSON/CSV exports work; unobserved
contexts and update survival remain unqualified. Full gate passed: 514 .NET tests,
820 Python passes/two skips. VMware Tools/cached login used; no game input or
network change. Evidence: `artifacts/power-interface-20261025-01/`.

**Power locator — LIVE AND FULL-GAME RESTART PASSED:**
The [exact-build Power reader](reference/native-power-locator.md) follows the
player resource objects and reconstructs the API's regeneration calculation.
One guarded Light's Balm click produced 120/120 complete native reads,
100 -> 83 -> 100, alongside Lua 100 -> 82 -> 88 -> 94 -> 100. Nearest readings
differed by at most 2 points within 0.212 seconds; 12 eligible clock-aligned
cross-checks matched exactly. Health and XYZ were unchanged. The prior float64
candidate is linked to a portrait UI heap and is not the locator. The separate
reader is deployed and hash verified through VMware Tools; cached login reused,
NAT unchanged. One normal full exit/relaunch changed PID 1224 -> 12076 and all
player/resource addresses; the unchanged locator reacquired without a Power
scan. Independent process-absence and old-identity rejection evidence is saved.
The second cast produced another 120/120 native reads and advancing Lua agreement
(maximum near-time residual 2; 14 clock-aligned cross-checks exact). A stale
controller binding blocked final cleanup; its normal reconnect recovered, and
the shared preflight now rejects that stale binding before input. V23 is ready,
disarmed/idle, no held input, queue clear. Evidence export:
`artifacts/exports/power-locator-and-restart-20261025-01/`.
The interface/catalog increment above completes the follow-up. Health-change,
patch recovery and HTTP work stay deferred.

**Guest launcher — DEPLOYED; TRANSFERS MEASURED:** The
[managed launcher and live results](validation/guest-agent-launcher-2026-10-25.md)
cover rejected bad hashes, clean agent replacement and a successful CLI repeat.
V23 and the managed guest agent are active; workflow configuration now points
to V23. RIFT and the VM were not restarted. All 12 VMware test copies verified:
512 KiB median about 1.7 seconds, 8 MiB about 5.7 seconds in either direction.
HTTP connectivity failed, so there is no HTTP speed comparison. NAT, firewall,
adapters and shared folders remain unchanged. Startup is registered, but fresh
Windows logon/reboot is untested. The full gate passed (487 .NET tests, 817
Python passes and two skips). Evidence is exported under
`artifacts/exports/guest-launcher-and-transfers-20261025-01/`.
Practical next field work remains resource
owner/provenance and a durable locator; health-change and patch recovery stay
deferred. Use the [launcher CLI](reference/guest-agent-launcher.md) for agent updates.

**Targeted spell click — DEPLOYED AND LIVE PASSED:** The new
[reviewed button-click helper](validation/targeted-click-2026-10-25.md) moved an
edge cursor into Light's Balm's slot 7, checked its position before pressing,
and delivered/released one click. Lua Power **100 → 81 → 87 → 100**, full health
and unchanged XYZ establish the live response. That test used V22 and the upgraded guest
agent; the managed-launcher checkpoint above supersedes its runtime. Full validation
passed; the 19-file evidence export verified. Final state is disarmed/idle,
no held inputs, clear queue. RIFT was not restarted. The previously responding
native address read zero during this baseline, so it is not reliable current
Power; owner/provenance remains the field-discovery follow-up. Health-change
testing, patch recovery and direct ChatGPT Computer Use remain deferred.

**Clean Power test — RESPONSE DEMONSTRATED:** The coordinated hands-off repeat
recorded one Light's Balm click inside slot 7, Lua **100 → 89 → 95 → 100**, and
a responding `float64` memory candidate **100 → 89 → 96 → 100**. Health stayed
18208/18208 and XYZ did not change. The initial latest-frame-only summary missed
the intermediate Lua values; all validated retained frames recover them. See
[the evidence and limitations](validation/power-test-2026-10-25.md).
Candidate `0x202DBECE9C8` is session-only; owner/provenance (including possible
addon copy), durable locator and restart qualification remain open. The
16-file export verified; final state is disarmed/idle/no held inputs, queue
clear. Input testing is finished. Health-change testing and patch recovery
remain deferred. No input blocker was enabled.

**Earlier Power experiment — interference-qualified observations:** One reviewed
Light's Balm click was followed by a healing effect, UI Power 88 and advancing
Lua Power 100 → 93 → 100; health stayed 18208. Four suspected native current-Power
values remained 100. A later click was recentered away from the hotbar and is
not a cast trial. Joey then reported using the in-game UI during testing; the
interference interval is unspecified, so do not call these exclusively controlled
runs. The clean repeat above supersedes that pending step. Evidence and the
interpretation amendment are at `artifacts/exports/power-live-20261025-01/`.
The subsequent large inline guest command caused a `vmrun` crash dialog;
staging and hashing the script, then using a short bootstrap, completed the
read-only baseline and two six-round captures. Root cause remains unconfirmed.

**Latest user direction:** Defer the health-change test. Identify the class,
resource and a suitable ability from Lua, and use the existing guarded helpers
for the bounded resource test. Health meaning/locator/restart qualification
therefore remains unfinished; do not provoke health loss. Patch recovery and
direct ChatGPT Computer Use remain deferred.

**Class/resource — LIVE IDENTIFIED:** Existing Lua identified Atank as a level
45 Warrior, role `tank`, with Power 100. Two independent captures contained
advancing player sequences; in-game ability tooltips independently name Power.
The earlier guarded preparation inspected tooltips and restored action bar 1
without activating an ability. Joey then placed Light's Balm in slot 7;
`resource-lua-20261025-01/slot7-confirm-01/` retained the placement. The clean
Power test above subsequently verified its tooltip and response. Health
changed-state qualification remains deferred.
See the [Lua/resource checkpoint](validation/xyz-goals-implementation-2026-10-25.md#lua-classresource-identification-and-deferred-health-test).
The 84-file export verified; final state was disarmed/idle/no held inputs and a
clear queue. Cached background guest login worked; interactive VMware launch
was separately rejected because that account is not the logged-in desktop user.

**Future interaction-addon consideration — user observation:** An in-game Lua
addon may help interactions, but this is a substantial separate effort requiring
accumulated RIFT-specific Lua/API documentation, restrictions and live evidence.
Do not assume an addon can cast or automate arbitrary interactions. Reuse the
existing addon knowledge and establish supported capabilities before proposing
implementation; this observation does not authorize a new automation subsystem.

**Goals 1–2 — LIVE DEMONSTRATED:** [Reusable workflow, real catalog and numeric scout](validation/xyz-goals-implementation-2026-10-25.md)
now have retained live proof. Repeatable run 04 reused the cached guest login
without prompting, verified 36 returned phase files, issued and released one
guarded 100 ms W pulse, and produced consistent native/Lua displacement. The
real catalog mechanically supports exact-build meaning, locator and the one
observed same-build full-game restart. Health and resource/power changed-state
discovery remain open; patch survival remains unqualified and deferred.

**Health seed — LIVE CANDIDATES:** The separately deployed numeric scout read
its 1 GiB allowance in about 16 seconds and retained 41 matches, with no read
holes. Three promising health/power-shaped blocks now have a verified **252-byte**
targeted reread, so the next test does not need another broad scan. Evidence:
`artifacts/validation/health-scout-20261025-02/`. These are candidate session
addresses; health/resource changes, meanings, durable locators and their full
game restart checks remain unproved. Health-change testing is now deferred;
class/resource identification is complete, and a safe ability test remains next.

**Paired capture ready; one candidate rejected:** Three fresh Lua/native rounds
showed one block no longer matched unchanged Lua health/power. Two blocks remain
plausible; the next native request is just **168 bytes**. The paired-capture
export, original failed narrow Lua search and negative candidate evidence are
retained under the same health-scout directory. The next step requires an
actual resource change, not more unchanged scans; health changes are deferred.

**Remaining goals:** [Current practical roadmap](planning/implementation-roadmap.md#remaining-practical-goals--refreshed-october-25-2026)
now separates completed XYZ interface/restart/movement, reusable workflow and
real catalog work from the remaining sequence: health, then resource/power.
Another XYZ restart is a confidence follow-up, not a repeated
acceptance blocker. Patch recovery stays deferred; optional Courier deployment
is not required while authenticated CLI transfers meet the need.

**Latest live result — GUARDED MOVEMENT PASSED:** [Helper-driven XYZ displacement](validation/xyz-guarded-displacement-2026-10-25.md)
used one requested 100 ms W pulse through the existing V21 controller, with
recorded key-down/key-up and successful release. Native/Lua distance was
**0.61293 / 0.61388 units**, maximum per-axis displacement residual **0.00415**
(limit 0.04); 9/9 Lua comparisons advanced and 38 returned files verified. Final
status was disarmed/idle/no held inputs, sole controller, clean access queue;
temporary guest credentials were not saved. AGENTS now distinguishes deferred
ChatGPT Computer Use from the separately authorized guarded helpers. Reuse this
working CLI-plus-helper path; patch recovery remains deferred.

**Newest live result — DISPLACEMENT PASSED:** [CLI collection and native/Lua comparison](validation/xyz-cli-displacement-2026-10-25.md)
reused the installed reader through authenticated VMware guest commands and file
copies. User-reported manual movement produced **2.03814 native / 2.03196 Lua game
units**, maximum per-axis displacement residual **0.00635** (gate 0.04), with
native/Lua acquisitions about **0.3 seconds apart** at each endpoint. All six
native samples completed, four cross-phase Lua comparisons advanced, and all 34
returned originals verified. Temporary guest credentials were not saved; the
session closed normally, V21 remained sole owner, and final status was idle with
no held inputs. No new game restart, automated movement or patch recovery occurred.

**Working preference — USER DECISION:** Prioritize practical, reliable results
with small changes and proportional checks. Reuse the existing workflow and move
to actual use; avoid further infrastructure or documentation layers without a
concrete need. Essential identity, freshness and controller protections remain.

**Newest repeatable XYZ result — LIVE PASSED:** [Repeatable workflow](reference/xyz-live-workflow.md)
run 04 returned `candidate-motion-consistent`: **0.665936 native / 0.673551
Lua units**, maximum per-axis displacement residual **0.0078125**, all **6/6**
cross-phase comparisons advancing. Baseline/after transfers verified **19 + 17**
original files. The cached login established in run 02 was reused without a
prompt; no credentials entered project files. Final state was foreground,
disarmed, idle and no inputs held. Verified export: **63 files**, 1,712,950
bytes, SHA-256 `7C68EDED513C16981F49D54B0C6813F1AEE939CF5D35EBED778247AEC5F85FB6`.

**Newest XYZ workflow result — OFFLINE:** [Reusable preparation, archive verification and panel export](validation/xyz-workflow-tools-2026-10-25.md)
prepared the pinned corrected reader locally, recovered both retained guest ZIPs
with their original 260/357 files, and exported audited sessions with the initial
48 findings preserved and the corrected trial clean. No guest deployment,
transfer, VM action or new restart occurred. Media/Courier/live transfer-service
generalization remains separate; patch recovery and direct guest Computer Use
remain deferred. [Commands and scope](reference/xyz-workflow-tools.md).

**XYZ workflow follow-up:** Added a [reusable saved-session audit](workflows/xyz-collection.md).
Both retained panel trials replayed: the initial trial correctly reports its 48
live subnormal leaks; the corrected trial passes with 59 raw startup observations
withheld and zero live leaks. This is offline evidence review, not another live
restart. Local preparation/verification/export commands are now available above; patch
recovery and direct in-guest Computer Use remain deferred.

**Current interaction policy — USER DECISION:** Defer ChatGPT Computer Use for
direct RIFT interaction inside VMware until Joey explicitly resumes it. Do not
prioritize further troubleshooting or retesting of that path. Use the verified
CLI workflow for applicable VM management; existing live-input scope and guards
still apply. This policy update performs no VM or game interaction.

**Newest interface result — PASSED:** [Corrected Start / Read / Stop window survived full game exit/relaunch](validation/position-panel-corrected-restart-2026-10-25.md). Fix `8e94c5b` passed **469 .NET, 669 Python, 108 Lua, 22 Lua/C#** and the full gate. New guest installation, actual buttons and normal RIFT **11712 → 1224** restart passed. All **59** subnormal startup reports were retained but withheld from live presentation; the same panel then produced **181** correct readings without another Start. Independent **3/3 before + 3/3 after**, raw float32 agreement, absence and old-epoch rejection passed. All **356** declared original hashes verified. Original media restored through authenticated CLI; V21 **PID 73252** independently ready/connected, sole console, guest disarmed/idle/no held inputs, queue clean, transfer port closed. Game was not foreground at final status. Refresh identities before further input. Portable results: `artifacts/exports/xyz-interface-restart-20261025-02.zip`. Patch recovery stays deferred.

**Earlier interface checkpoint:** [Actual host Read / Start / Stop buttons passed; guest restart validation in progress](validation/position-panel-live-progress-2026-10-25.md). Computer Use now works; the earlier permission refusal is historical. Production code `8a9f894` passed the full **465 .NET, 669 Python, 108 Lua and 22 Lua/C#** gate. V20 exited normally at **13:15:23 UTC**, V21 is prepared but unstarted, and the queue is quarantined for exclusive maintenance. Guarded guest-console clicks/keys are explicitly authorized. After VMware's settings dialog closed, guest File Explorer still showed the old `RR2_FIELDS` disc; manual Browse selection of the pinned ISO is pending. No new guest install or game restart has been performed. Refresh actual ownership on resume. Patch recovery stays deferred.

**Earlier sampler restart checkpoint:** [October 25 normal RIFT restart, unchanged-profile XYZ reacquisition, stale/absent-process rejection and fresh Lua comparison](validation/native-xyz-restart-2026-10-25.md). The deployed reader is live-proven across this **one same-build game restart**, following the [earlier movement trial](validation/native-xyz-sampler-live-2026-10-25.md). Current priority: durable collection across full game exit and relaunch; patch/update recovery is **deferred until Joey explicitly resumes it**, not the automatic next task. See the [accepted durability policy](decisions/0008-full-game-restart-durability.md). The [earlier handoff](handoff-2026-10-25-native-xyz-sampler.md) preserves the operating workflow; its pending-deployment and old-owner statements are historical.

**Results exported:** [portable October 25 evidence package and report](validation/native-xyz-results-export-2026-10-25.md), with four hash-pinned discovery records (JSON/CSV/JSONL), offline explorer, raw guest archives, exact restart replay evidence and payload checksums. Both original process epochs and candidate-only limitations are preserved. Output: `artifacts/exports/xyz-live-and-restart-20261025-01.zip`.

## October 25: Durable restart policy — USER DECISION

- **Restart means fully exiting RIFT, confirming the old process has ended, then
  launching the game again and reacquiring fresh process/start/owner identity.**
  Addon reload, character relog, or reader restart alone does not satisfy this.
  VM/host restarts are separate validation scopes.
- Preserve reusable build-specific locating recipes and evidence; resolve current
  addresses on each run, reject absent/stale processes, and never substitute old
  coordinates for fresh data. The existing October 25 evidence establishes one
  observed full game exit/relaunch on the same build.
- Patch recovery is deferred until explicitly resumed. Exact executable SHA
  guards remain in force; a changed build fails closed. Semantic qualification
  and the limits of the observed restart case remain explicit.
- Policy is recorded in AGENTS, the brief, roadmap, handoff and
  [ADR 0008](decisions/0008-full-game-restart-durability.md). No new live trial is
  implied by this documentation update.

## October 25: Normal game restart and XYZ reacquisition — LIVE PASSED

- Used normal RIFT **Exit Game**, its countdown, Glyph **Play** and Atank's world-entry **Play**. RIFT PID **6940** / ticks **639284177321390013** exited; new PID **9704** / ticks **639285237698112372** started **11:16:09.8112372 UTC**, with unchanged game executable SHA. VMware was not restarted.
- The exact deployed sampler/profile were unchanged and guest-hash checked. A fresh **3/3** baseline preceded exit; absent-game sampling returned **exit 2**, zero game processes and no report. After world entry, automatic discovery/re-resolution completed **5/5** samples, then **3/3** beside independent evidence. Owner changed **0x211D37C0010 → 0x1D610AC0010**. The old-PID request was separately rejected, **exit 2/no report**.
- Two bounded new-process Lua scan/copy passes retained byte-limit partial coverage and **six complete original snapshots**. All **9/9** strict C# pairings advanced; selected Lua **733 → 1125**, same player. Two independently retained native owner reads agreed with Lua within **0.0025 units per axis**, with **71.106/80.122-second** acquisition lags. Final sampler readings also matched within **0.00224 units**, all under the explicit 180-second/0.02-unit acceptance bounds.
- **Recovered owner at checkpoint:** independent **V20 PID 56804**, session 2, `inJob=false`, authenticated ready/connected, sole console owner, running supervisor, new game PID 9704 foreground, guest disarmed/not busy/no held inputs, canonical queue clean, transfer port 8765 closed. Target epoch changed; VM epoch remained unchanged. Always refresh these dated identities on resume.
- Exact ZIP/receipts, baseline and rejection originals, snapshots, pointer bytes, all comparison diagnostics and replay summary are preserved in ignored `artifacts/update-recovery-20261023-01/xyz-restart-oct25-01/`. See the [restart evidence record](validation/native-xyz-restart-2026-10-25.md). One observed same-build restart is established; patch recovery, loading-state semantics and semantic catalog qualification are separate.
- **Fresh full gate:** PowerShell 7.6.8, **exit 0 at 2026-10-25T11:36:43Z**: **450 .NET, 669 Python, 108 Lua, 22 Lua/C# contracts**, native publish/smoke, replay, formatting and **518 links**. Evidence `artifacts/validation/20261025T113542Z-6f8b2b3c`. Actual selected Lua/native outputs also replayed byte-identically. Only tracked documentation changed in this restart pass.

## October 25: Guest XYZ deployment and bounded movement comparison — LIVE PASSED

- Installed the exact SHA-pinned sampler and profile into new guest `C:\RIFT_TRANSFER\RR2-XYZ-oct25-02\`; both guest size/hash gates passed and the initial smoke completed **3/3**, exit **0**. Prior installation and historical SHA-pinned transfer scripts were preserved.
- An independent finite native feed completed **30/30** reads from **10:49:52–10:50:55 UTC**, spanning exactly one reviewed access-queued **100 ms W** pulse at **10:50:35 UTC**. Key-down/up, successful release and no target loss are recorded. Sample 21 was the first changed sample; native displacement was **0.6473471 units**, with no stale/failed reads and empty stderr.
- The original broad typed scout hit its existing 32,768-region limit, and a saved-string narrow read later contained no frames. Both failures are retained. Explicit **13,697,024-byte** captures of a freshly evidenced readable Lua heap range succeeded without changing code or limits. Strict C# inspection verified independently advancing same-player Lua sequences **206626 → 207242**.
- Native and Lua before/after acquisition differences were **8.318/8.492 seconds**. All endpoint axes agreed within **0.0025 units** and displacement residuals within **0.0035 units**. The unchanged reviewer returned **candidate-motion-consistent**, retaining its **candidate-only** qualification; source/API observations remain distinct from native memory and derived changes.
- **Recovered owner at checkpoint:** independent **V19 PID 67508**, signed-in session 2, `inJob=false`, exclusive console, authenticated ready/connected supervisor, same RIFT PID **6940**/build and VMware PID **38044**/epoch, game foreground, guest disarmed/not busy/no held inputs. One-use transfer port **8765** closed. Refresh ownership rather than reuse these PIDs on resume.
- Full originals, claims/uploads, action timeline, negative evidence and hashes: ignored `artifacts/update-recovery-20261023-01/xyz-live-oct25-02/`. See the [live validation record](validation/native-xyz-sampler-live-2026-10-25.md). No new restart/patch trial, fully synchronized Lua stream or field-catalog promotion is claimed.
- **Fresh full gate:** PowerShell 7.6.8 `scripts/validate.ps1`, **exit 0 at 2026-10-25T11:00:09Z**: **450 .NET, 669 Python, 108 Lua, 22 Lua/C# contracts**, native publish/synthetic smoke, replay, formatting and **510 links**. Evidence `artifacts/validation/20261025T105909Z-de2d4c8b`. Two test-only executor assumptions were repaired (bounded disposable-process startup and supported PowerShell selection); deployed production code/settings were unchanged.

## Earlier October 25 checkpoint: Known-build XYZ direct sampler — host preparation

- **Reuse-first operational path:** The new Windows Live `sample-position` command consumes a small strict `native-position-profile/1` JSON recipe pinned to the October 24 RIFT executable SHA **7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD**, root RVA **0x32E0200**, and owner float32 offsets **+0x320/+0x324/+0x328**. It discovers exactly one fresh `rift_x64` PID, opens a read-only exact-build session, re-resolves the chain per sample without heap/Lua rescanning, and refuses stale/wrong-build identity. Bounds: 1–30 reads, 0–2000 ms post-read interval, at most 60 seconds scheduled delays.
- **Honest, immediate consumption:** Each sample emits one compact JSON line as soon as it completes, including explicit unavailable/nonfinite states; the final line summarizes the run. A separate no-overwrite `native-position-samples/1` report retains native owner session address, terminal-byte SHA, actual timestamps, XYZ when finite, and failure status. The report remains **candidate-only-not-motion-or-update-qualified**; the direct reader neither promotes catalog truth nor proves game behavior or future patch applicability. [Usage and limits](reference/known-position-sampling.md).
- **Read-only candidate change hints:** Consecutive complete samples now include per-axis deltas, Euclidean distance, and monotonic time since the previous read. The report summarizes 0.1-unit significant native candidate change, first/last displacement, maximum excursion and largest step; tiny jitter and return-to-origin are covered. This is not proof of player movement, and a failed read never reuses stale XYZ.
- **Real host verification:** Nine focused .NET 10 tests pass (known build, changing XYZ, profile hashing/schema, wrong build, identity invalidation, failed reads, nonfinite values, live sample callback and motion-hint negative cases), and the Windows Live `--help` smoke lists the command. Latest PowerShell **7.6.8** full gate exited **0 at 2026-10-25T09:36:44Z**: **450 .NET tests** (311 core + 139 Live), **669 Python**, 108 Lua, 22 Lua→C# contracts, published-native synthetic-host smoke, formatting, and **502 documentation links**; evidence `artifacts/validation/20261025T093540Z-12ff745f`.
- **Bounded guest delivery prepared, NOT executed:** New isolated `scripts/serve_guest_position_sampler.py` reuses the original one-use HTTP handler **without modifying its historically SHA-pinned server source** (an initial change was reverted after the full suite correctly rejected it). Exact `executable` 74,349,475-byte validated publish SHA **5CA4A6EA9B8904C4987315AA2AE287B3F32B4BB8ED27F5BA951D4D704682C07B**, and `profile` 395-byte JSON SHA **FFA948C24170070F7A0E7A986273BEF7E0774D953DFEA4ECABB14112FCCF88C8**, have distinct fixed routes, signed-in one-use serving, exact guest IP and ignored receipt destination. Both no-listener CLI preflights and **34/34** focused new+legacy+recovery tests passed; no listener, guest download, process read or VM input was started. The **entire final validation gate passed**.
- **Explicit live boundary:** The new sampler has **not** been installed or run against the RIFT-Lab guest yet. Fresh authenticated **read-only** status at **2026-10-25T08:41:30Z** found unchanged RIFT PID **6940**, start ticks **639284177321390013**, matching executable SHA, game foreground, no held keys, V16 controller exclusive and healthy; no competing console was opened. Next: guarded exact-epoch publish/guest smoke, then near-time motion evidence via the existing [V17 offline reviewer](reference/native-motion-pair-review.md). Automatic cross-patch locator rediscovery remains separate.

## October 24: Evidence-preserving discovery compilation and offline explorer — NO VM INPUT

- **Finalized plan and implementation:** D0 [bounded compilation roadmap](planning/discovery-compilation-roadmap.md) commit `d62cbc3`, D1/D2 compiler/filter/sort/JSON+CSV+JSONL commit `0f31cf6`. Strict explicit SHA/byte-pinned source manifest, honest per-row qualifications, stable filters/sorts, deterministic results, and never-overwrite output. The self-contained `scripts/discovery_explorer.html` previews a user-chosen JSON compilation in a browser with search, header sorting, categorical filters, evidence inspection, pagination, and local filtered downloads. See [usage contract](reference/discovery-compilation.md) and [ADR 0007](decisions/0007-discovery-compilation-views.md).
- **Actual historical RIFT input replay, read-only:** One V15/V16 advancing-typed-source original and one native pointer review original were pinned in an ignored local manifest, compiled to two distinct rows with separate source hashes and epochs. Typed row remains `advanced-in-covered-scope` / source-only; native row remains `candidate-compatible` / **not synchronized or motion-qualified**. This run did not contact VMware, start a host listener, read the game process, or alter V16 console ownership. [Evidence and limitations](validation/discovery-compilation-2026-10-24.md).

- **Actual local Chrome UI proof and final gate:** Independent headless Chrome loaded **6 synthetic** and **2 previously retained real RIFT** rows via the local file picker; status/SHA filter, precise UTC sort, CSV and JSON filtered downloads passed (jobs `rr2-disc-d4-browser-real-01`, `rr2-disc-d4-browser-live-evidence-01`). The full PowerShell 7.6.8 `scripts/validate.ps1` gate then finished **exit 0 at 2026-10-25T01:51:18Z**, **441 .NET**, **660 Python**, 108 Lua, 22 Lua→C# contracts, published-native smoke, formatting, 490 links. Evidence `artifacts/validation/20261025T015017Z-106b7fd1`. [Full proof](validation/discovery-compilation-2026-10-24.md); human visual/accessibility review remains separate.

## October 24: V17 host-only motion comparator and safe successor STAGED — NO VM INPUT

- **Fresh V16 read-only proof:** At **2026-10-25T00:25:38Z**, the authenticated owner remained ready/connected, RIFT foreground PID **6940**/exact build, VMware PID **38044**/same epoch, no held keys, guest disarmed, supervisor running and console exclusively reserved. The no-overwrite **V16→V17 same-epoch handover** prepared plan and launcher at **00:26:31Z** using the existing clean queue; **no V16 STOP marker, VM console access, game input or V17 launch** was performed.
- **New moving-XYZ offline reviewer:** `scripts/review_native_motion_pair.py` consumes strict advancing typed Lua before/after plus two exact-epoch original native pointer reports. It checks SHA pins, root/owner bytes, player identity, independent snapshots, nonoverlapping chronology, **unrounded at-most-180-second pair lag**, 0.02-unit endpoint tolerance and 0.1-unit minimum source displacement. Status is `candidate-motion-consistent`, `candidate-motion-disagrees`, or `insufficient-source-motion`, always **candidate-only** without stimulus/clock-skew proof. **17/17 focused safety tests** pass, including a real V16 original negative control and direct CLI. The full PowerShell 7.6.8 gate then passed exit **0 at 2026-10-25T00:34:39Z**: **660 Python**, **432 .NET**, 108 Lua, 22 Lua→C# cases, native publish/replay/format, **471 links**; evidence `artifacts/validation/20261025T003336Z-def5acac`. No new actual movement claim. [V17 evidence contract and safe multi-owner sequence](reference/native-motion-pair-review.md).

## October 24: FIRST LIVE current-epoch native XYZ — TWO ORIGINALS MATCH, V16 RECOVERED

- **Actual game-memory result:** Normal V15 STOP and quarantined queue preceded 33 bounded exact-PID read-only guest PowerShell commands. Two independently saved pointer reports (113.116609 seconds apart) resolved main-module RVA **0x32E0200**, owner **0x211D37C0010**, and owner offsets **+0x320/+0x324/+0x328** to identical native XYZ **(7461.19921875, 863.8524169921875, 2977.061767578125)**. Guest screenshots showed **EXE_GATE=True**, both native command exit codes **0**, and **PTR_A_GATE=True/PTR_B_GATE=True**. No movement or process writes.
- **Real original-byte proof and independent reviewer:** Separate signed-in session-2, out-of-job one-use claim/upload services cryptographically bound guest **192.168.56.128**, same game/build/bundle epoch, declared SHA and actual transferred **3,135-byte** ZIP (SHA **1BD407E20FC7ACFD2691D30BFFCA2E534870491FE40D9F933275B6CE9257B3E3**). Exact three original members recovered, source-linked native/Lua reviewer returned **candidate-compatible**, each axis delta under **0.0025** versus qualified advancing Lua. **Qualification stays candidate-only-not-synchronized** because the source frame was about 2.4 hours older and no controlled movement was performed. [Full original hashes, times, values, scope and limitations](validation/native-pointer-xyz-first-live-2026-10-24.md).
- **Safe restored owner:** Verified guest-shell close restored RIFT foreground, both one-use services and port 8765 are closed, and independent **V16 PID 28496** (Windows session 2, not in a job) is authenticated ready/connected with supervisor running and exclusive VM console ownership. Exact RIFT PID **6940** / VMware PID **38044** remain unchanged; guest disarmed, no held keys, canonical queue unblocked/unheld with fresh cleanup receipt. V16 is now the live owner. **Do not access its console concurrently.** Next gate: prepare a new guarded handoff for near-time advancing Lua + supervised bounded movement/native before-after comparison.
- **Validated and repeatable:** Strict reviewer was replayed on the actual guest ZIP through its direct CLI; all five output files were byte-identical in separate no-overwrite directories. Windows Python/PowerShell subprocess and authentic-receipt test isolation problems were corrected in test harnesses. The authoritative PowerShell 7.6.8 `scripts/validate.ps1` now discovers all Python tests: **643/643 Python**, **432/432 .NET 10**, 108 Lua lifecycle/encoder, 22 Lua→C# contracts, published-native smoke, deterministic replay, format, **468 links**. Exit 0 at **2026-10-25T00:24:06Z**, evidence `artifacts/validation/20261025T002307Z-755c5bd7`.

## October 24: V16 guarded native XYZ guest trial, dual one-use services and abort path — HISTORICAL HOST PREPARATION

- **Guest operation prepared:** New `scripts/run_guest_pointer_trial.py` assembles 33 exact-epoch, serial read-only PowerShell actions (+bootstrap, success-close or abort). Each transport command is regenerated and matched to its canonical pinned source; the previous action receipt must match the exact command SHA, stage, VM identity and request SHA, with no false guest-completion claim. The actual 33 commands passed Windows PowerShell 5.1 AST syntax parsing, **33/33, no commands executed**. The installed guest executable, 816-byte pointer request and both complete native resolutions are independently gated before ZIP packaging.
- **Independent service ownership:** `scripts/run_guest_pointer_service.py` reuses separate, fixed-IP one-use SHA/size claim and content-matched ZIP upload services on port 8765. The guest POST gates require the actual Windows listener PID and process start identity, not just a startup receipt; claim/upload phases cannot overlap. An incorrect claim-server source SHA pin was detected by the first offline preview and corrected before any listener. New `--abort` requires no live service/port, a verified PowerShell screenshot and canonical guest authority; it records failure without pretending a ZIP was received. **14/14 focused safety tests and 642/642 full Python tests passed**, plus Python compilation, Git diff check and the 33-command PowerShell AST gate.
- **Fresh read-only live preflight at 22:41:02 UTC:** V15 exclusively owns console and remains authenticated ready/connected; guest RIFT PID **6940**, exact start ticks/build, VMware PID **38044**/log epoch unchanged, game foreground, guest disarmed/no keys held. **No V15 STOP, VNC/guest interaction, native pointer reports or V16 startup yet.** [Exact physical sequence, abort/recovery and evidence gates](validation/current-epoch-pointer-v16-preflight-2026-10-24.md).

## October 24: V16 native XYZ pointer ZIP transfer host-proven — NO GUEST ACTION

- **Pointer originals transfer pathway now host-proven:** Extended the existing guest ZIP SHA claim and one-use content-pinned receiver with a distinct native-pointer route, preserving old inline/map defaults. New scripts/verify_pointer_zip_archive.py requires the exact three-file ZIP, verifies both process/guest/bundle/receipt identities and actual archive-member bytes, runs the strict native-vs-Lua reviewer and publishes no-overwrite originals/derivation. **52/52 focused archive/transport tests passed (including legacy compatibility)**. No new listener/guest access yet. [V16 complete staged gateway](validation/current-epoch-pointer-v16-preflight-2026-10-24.md).

## October 24: V16 native XYZ pointer gate staged — HOST PREPARATION ONLY

- **Current read-only owner/status:** V15 PID 27856 remains authenticated ready, guest disarmed/no keys held, RIFT foreground PID 6940/ticks 639284177321390013, VMware epoch unchanged (read-only host status 22:00:47 UTC). Canonical same-epoch V15→V16 successor plan/launcher was prepared safely (22:01:28 UTC), but **V15 STOP not requested and V16 NOT launched**.
- **Two precise native pointer requests staged:** Existing guest PowerShell planner generated two separate 10-step no-overwrite plans with the same SHA-pinned exact-game request C6B90D59DCF472E50DCEEAE6992AED98446754D466AE2AFA1AE9510EFD5BE9EE. Each follows root RVA 0x32E0200 once, reads 816 bytes to include offsets +0x320/+0x324/+0x328, and caps execution at 5 seconds. They have NOT run in the guest.
- **Native comparison reviewer implemented:** New scripts/review_current_pointer_xyz.py verifies both complete pointer reports, exact root/byte-level pointer hops, process/build/epoch, qualified stationary advancing Lua source and SHA, temporal separation and XYZ float32 differences. Synthetic focused 10 tests passed; it also accepted the actual source comparison SHA CF353BD49E6D5D7FFC810C6C8C3AF8C049D26B10F2F9700257DEBBC9486274D5. **Still missing: two real pointer originals, guest SHA-pinned transfer and actual native/Lua agreement.** [Full V16 native XYZ preparation and safe next sequence](validation/current-epoch-pointer-v16-preflight-2026-10-24.md).

## October 24: post-live guest transfer completion hardening — HOST ONLY

- The successful real 74,254,755-byte guest download took approximately 167 seconds, beyond the earlier fixed screenshot delay. The guarded guest stepper now expressly marks every step receipt as a completed console action, not verified guest-command completion. After the download command, step 4 and later require distinct one-use independent service owner/exit receipts and the genuine exact-peer, exact-route, full-byte, correct-SHA delivered sender event. Step 30 and later require the completed guest ZIP claim before upload.
- The new guard passed against the retained actual delivered sender event (read-only, V15 untouched), plus 25/25 focused fail-closed tests covering missing/partial transfers, mismatched PID, VM epoch, SHA and guest IP. The full Python suite passed 598/598, compileall passed. A service test was isolated from now-existing real claim artifacts so it remains repeatable. This was applied after the real capture; it does not retroactively prove guest-command completion in the old receipts. V15 still exclusively owns the VM; no fresh guest input was generated.

## October 24: FIRST LIVE same-scan RIFT captures — advancing Lua producer frames QUALIFIED

- **Live game capture and provenance:** Two exact-PID/build read-only 512 MiB scan-and-immediate-copy runs executed with the SHA-pinned new V2 guest CLI after a normal V14 STOP/exclusive maintenance. Run 01 found **3 prefixes/2 complete copied snapshots**; Run 02 **5 prefixes/4 complete copied snapshots**. Both correctly partial by byte cap, zero holes. Guest returned a **90,878-byte** ZIP, SHA **26D5DF797ADDC263B8A8D0DECEB8A856B8708326F1CD36B7700D5A5BC4CD8D58**; separate exact guest hash/length claim and actual content-addressed upload matched. The strict offline verifier accepted both receipts and preserved **6 original snapshots/272,936 JSON bytes**, proof SHA **C98EE8C8619F315A2F90EDBDCBB1BAA3BCA4ED6A209977993493287443E5568**.
- **Breakthrough C# strict wire result:** Independent **2 × 4 = 8** cross-run comparisons found **6 statuses advanced-in-covered-scope**, two appropriately blocked stale pairs. Freshest same-player unit **u035400012FA2D207** advanced producer sequence **112332→112588** and frame clock **56728.363→56858.117** while Lua XYZ remained **(7461.20, 863.85, 2977.06)**. Native XYZ comparison and movement **not yet qualified**. A stale valid frame at 0xD8ACDB0 was negative control; old binary-followed 0xD3DB230 prefix correctly declined. Source evidence scoped to 512 MiB per run, not whole-process.
- **Restored operational owner:** V14 exited normally, one-use transport listeners shut down, guest PowerShell exited. SHA-pinned **V15 PID 27856**, independent Windows session 2, inJob=false, authenticated ready/disarmed at **21:42:44 UTC**, RIFT foreground, exact unchanged game+VM epoch, clean queue. **V15 now owns the VM; no concurrent console access.** [Complete first live original hashes, advancing pair matrix and guarded V15 recovery](validation/typed-inline-first-live-six-snapshots-2026-10-24.md). Next engineering gate: independently validate live native XYZ for this source-qualified Lua position; guard future console transitions with the new receipt boundary.

## October 24: guarded V14 → V15 typed-inline guest trial prepared, foreground restored — HOST ONLY

- **Fresh owner check:** V14 authenticated and ready, game PID **6940** / exact 64-bit start/build unchanged, VM epoch unchanged, queue unheld/unblocked/0 pending. Joey corrected a VMware dialog stealing focus; a renewed read-only observation at **21:08:34 UTC** confirmed **RIFT foreground=true**. V14 still owns exclusive console, with **no STOP, bundle transfer or new guest memory scan**.
- **Ready for serial maintenance:** New `scripts/run_guest_inline_trial.py` creates 31 bounded, individually receipted guest PowerShell commands guarded by V14 normal exit, blocked/unheld queue, exact V15 VM epoch, screenshot-gated shell and request/bundle SHA. New `scripts/run_guest_inline_service.py` restricts independent one-use download → ZIP hash claim → exact-hash upload to signed-in Windows `pythonw.exe`, exact guest IP and mutually exclusive phase receipts. **20/20** focused host tests passed; real PowerShell ZIP format rechecked byte-identically. Fixed a would-be **64-bit start-tick precision loss** in initial request construction *before use*. [Strict operational handoff](validation/typed-inline-v15-guarded-sequence-host-2026-10-24.md).

## October 24: closed guest ZIP checksum/receipt gap — HOST LOOPBACK VERIFIED

- **One-use receiver reuse:** New bounded guest ZIP declaration receives only fixed-IP, exact-epoch **SHA + byte count**; existing one-use exact-digest ZIP upload receiver is unchanged. The archive verifier now binds *both* original receipts to actual ZIP SHA/length, path, guest peer, game process and bundle before publishing; it refuses mismatches and marks host fixtures separately. No new VM listener opened.
- **Proven host path:** Actual loopback claim → original ZIP upload → exact-receipt crosscheck → eight recovered originals passes. New claim tests 9, added receipt-crosscheck tests 2, combined 24 focused pass; full Python **573/573** pass. Normal no-listener Windows preflight pinned latest-known game/build and reported guestZipReceived=false. [Strict claim and transport proof](validation/typed-inline-zip-claim-host-2026-10-24.md).

## October 24: TWO native self-process captures archived and recovered — full host path proved

- **Actual host execution:** The published single-file V2 capture ran **twice** against a controlled live Windows test-process allocation, each copying seven 4 KiB pages byte-for-byte. A real PowerShell ZIP archived both distinct reports. New bounded host verifier rechecked exact archive/game/bundle/provenance/chunk hashes and restored **8 originals / 92,272 bytes** with a no-overwrite receipt. ZIP **7,575 bytes**, SHA **A5CE12ECD37AADD90CBB6D210C9A719A5B5B263ACD672B5BB9890159CFD71A7A**.
- **Strict independent diagnostic:** C# inspect-typed-wire opened both recovered complete snapshots and correctly returned **blocked: incomplete-typed-fragment-in-covered-scope** for the deliberate test-only prefix. Focused archive tests **13/13**, full Python **562/562**, diff check pass. **This is a test-process proof, not in-game Lua/XYZ.** No VM interaction, V14 STOP or guest file upload. [Two-run archived evidence and live gate](validation/typed-inline-archive-two-run-host-2026-10-24.md).

## October 24: new published typed-capture bundle now allowed by guarded one-use transport — HOST ONLY

- **Reuse-first delivery improvement:** `scripts/serve_guest_native_scout.py` now supports explicit `--bundle typed-inline`, with a distinct exact URL and the SHA-pinned 74,254,755-byte single-file executable, while the existing `scout` default, one-use, exact-peer, expiry and no arbitrary-file serving remain. Both original and new ~74 MB sources passed **real full-file SHA preflights without opening a socket**.
- **Gates:** 14/14 focused new/legacy transfer tests, 26/26 combined sender/receiver tests and **549/549 full Python tests** passed. A preexisting Windows socket-abort flake in header-refusal receiver tests was fixed **in test harness only**, retaining exact refusal-code checks; production receiver unchanged. No guest transfer, V14 STOP or guest capture. [Transport proof and next gate](validation/typed-inline-bundle-transfer-host-2026-10-24.md).

## October 24: V14 live preflight; V15 PREPARED ONLY, foreground not confirmed

- **Read-only host observation at 19:30:35 UTC:** RIFT-Lab-1's V14 supervisor was ready/connected, disarmed and held the exclusive console; exact RIFT PID 6940/start ticks 639284177321390013/SHA and VMware PID 38044/log epoch unchanged. Canonical queue generation 1248, 0 pending, unblocked. **Guest `foreground=false`**, so a future UI operation must not assume focus. **No gameplay input.**
- **19:31:32 UTC:** normal same-epoch **V15 successor plan generated but not executed**. V14 remains owner; STOP not requested; no VM maintenance, bundle transfer or guest capture. [Observed evidence and guarded next steps](validation/typed-inline-capture-v15-preflight-2026-10-24.md).

## October 24: same-scan typed CLI HOST VALIDATED; tested guest bundle ready, not deployed

- **V2 implementation:** New `scout-copy-typed-native --request PATH --output NEW_DIRECTORY` uses an exact PID/start/executable-SHA-bound, **512 MiB/30 s/128-prefix** maximum private-memory scout and **at most eight** in-callback `RRAPIVAL2|{`-plausible **7 × 4 KiB** snapshots. Outputs are source-request/SHA-linked strict `native-memory-snapshot/1` originals with per-candidate status in `native-typed-inline-capture/1` `index.json`, published under a new folder by no-overwrite final directory rename. Post-capture process identity drift invalidates the manifest and suppresses usable snapshot files. The old prefix scout, V1 and gameplay controls are unchanged. [New command contract](reference/typed-inline-capture.md).
- **Real host validation:** The command actually scanned/copied the **Windows test process**, saved two-level content hashes, passed strict snapshot loader, and refused output overwrite/stale target. The **published single-file executable itself** also scanned/copied **28,672 test-process bytes** byte-for-byte and passed a separate published native `MZ` read/replay/stale-epoch smoke. Bundle: ignored `artifacts/validation/rr2-scout-copy-publish-oct24-01/RiftReader2.Live.exe`, **74,254,755 bytes**, SHA-256 **`484FC6A0980BCAC823154229B974B0BD18412A9053903A542BC0313EB5EF1716`**. Published trial manifest SHA **`E70078F55DE1780216E8C4AC7E7E0C4FB1E59724C5ABE1556E4AF5270D850DDF`**.
- **Gates:** full .NET **432/432** (139 Live + 293 core), Python **545/545**, Lua 5.1 **108** and actual Lua→C# **22** cases, targeted format, bundle publish and native self-process smokes passed. Stock all-in-one PowerShell validation **not completed** because PowerShell 7 is unavailable and PS5.1 changes native quoting/BOM; component checks were rerun independently. [Full real host proof and restrictions](validation/typed-inline-capture-cli-host-2026-10-24.md).
- **Live next step, NOT YET PERFORMED:** fresh exact V14/game/VM preflight and safe V14→V15 normal handover, SHA-pinned bundle transfer to guest, two distinct bounded read-only scan-copy acquisitions and original report transfers, strict wire advancement check, independently restored supervisor. Do not enter the V14-owned VM console concurrently. **Current fresh valid typed Lua frames, native XYZ agreement and game-patch resilience remain unproven.**

## October 24: complete pure scout→copy pass; 430/430 .NET tests

- **Integrated host-only discovery primitive:** Added `TypedApiInlineCapturePass.Run` to compose the 64 KiB prefix scanner, immediate plausibility recheck and SHA-bound seven-page copier **in the same callback before the next scan read**. A hard **8-candidate copy cap** and the original scan byte/time/match budgets prevent runaway work. It retains candidate-level false-prefix, moved-header, out-of-range, copy-limited and partial-time statuses, without promoting prefixes or incomplete scan coverage to typed frames. **No public guest CLI or report publication yet**, no game/VM access.
- **Actual verification:** Six new pure orchestration cases, plus the earlier real Windows self-process scanner→copy byte-exact smoke. **Full .NET 430/430 tests passed** (137 Live + 293 core); `dotnet format --verify-no-changes` for the changed source/tests passed. The next engineering gate is a strict exact-target CLI with no-overwrite, hash-linked `native-memory-snapshot/1` files and fail-closed process revalidation. [Pass evidence](validation/typed-inline-capture-pass-host-validation-2026-10-24.md).

## October 24: tested immediate prefix→memory-copy primitive — host only

- **Substantial V2 code milestone, no guest deployment:** New `TypedApiImmediateNeighborhood.Capture` is a bounded synchronous consumer for the previously committed `onMatch` hook. It rechecks exact `RRAPIVAL2|{` in the same process handle, rejects NUL/binary/stale markers without dumping memory, then retains **7 × 4 KiB pages / 28,672 actual bytes** centered on a plausible candidate, with per-chunk SHA-256, partial/unavailable failures, strict time gate and safe `native-memory-snapshot/1` wrapping. This avoids assuming the earlier hour-stale addresses are still valid.
- **Actual Windows host proof:** Added **11 focused tests**, including a real Windows self-process allocation: the true 64 KiB read-only native scanner called the inline hook, which used the true Windows 4 KiB memory reader to copy 28 KiB from the **test process**, byte-for-byte verified with process identity revalidation. Full .NET **424/424 tests pass** (131 Live + 293 core), targeted `dotnet format --verify-no-changes` and `git diff --check` pass. This is not proof of a RIFT typed Lua frame or a new guest command. [Detailed host validation and next gates](validation/typed-inline-neighborhood-host-proof-2026-10-24.md).
- **Next:** wire the collector into a bounded, versioned no-overwrite live CLI with exact target/request proof, capture limits and process invalidation handling; obtain independent samples using newly found positions. **V14 remains exclusive console owner; no new VM action.**

## October 24: immediate post-match capture hook — host-only implementation

- **V2 pure scanner improvement, NOT YET A LIVE FEATURE:** `TypedApiPrefixScout.Scan` now accepts an optional, synchronous `onMatch` observer notified of **retained matches in the current 64 KiB scan block before the next read**. The observer cannot receive cross-hole matches or candidate-overflow entries; existing `scout-typed-native` CLI and scan request/report remain unchanged and do not install an observer. This provides a tested seam for future **same-operation read-only neighborhood capture**, avoiding the roughly hour-long stale-address lag of the first live scout/snapshot follow-up. New focused tests cover prompt notification, overflow and split/hole cases. **No guest bundle deployed, VM console input or game read issued as part of this code change.**
- **Next:** add a bounded, provenance-rich immediate capture consumer and test it without the game before touching V14; there is no current qualified typed wire or XYZ. [Scanner contract](reference/typed-prefix-scout.md).

## October 24: TWO REAL read-only native snapshot reports recovered; V14 healthy

- **Live acquisition complete (17:44–17:45 UTC):** After a normal V13 STOP, exclusive VM console acquired two independent `snapshot-native` reports from the unchanged RIFT PID **6940** / start ticks **639284177321390013**, using the 3 × 28,672-byte exact-session source windows. Every one of **21 chunks per report** was complete and independently SHA-verified, with no holes. Sample A: **126,199 bytes**, SHA `32FE40D65E0F2312378797A50F69E005D754F50693C613777B7F9268841DFA33`; sample B: **128,139 bytes**, SHA `13AF9B26B9DD8A846029AA81BD6589D5A2BCC981F2BD033D418AF14DF35602C2`. Both full originals, transfer receipts and hashes are retained under ignored `artifacts/update-recovery-20261023-01/`.
- **Strict wire inspection is NEGATIVE in covered scope:** `inspect-typed-wire` published a separately hash-verified report with `status=unavailable`, `reason=before:no-complete-usable-frame-in-covered-scope`; both inputs cover **86,016 bytes**, but contain **zero complete candidate frames**. One scout marker at `0xD3DB230` persisted next to binary, not JSON; the other two addresses lost their marker as their heaps changed. **No typed-frame advancement, native XYZ comparison, or whole-process negative claim.** Immediate scan-to-copy is the evidence-driven next approach.
- **V14 safely restored (independent verification 17:52:10 UTC):** Exactly pinned V13→V14 handover closed the PowerShell console and started independent `pythonw.exe` V14 **PID 36776**, session **2**, `inJob=false`. Authenticated **ready/connected**, supervisor **running/cleanup verified**, unchanged RIFT foreground, guest **disarmed/idle**, canonical SQLite **unblocked/no holder/zero pending**, generation **1152**. **V14 now holds the VM console; no concurrent VNC or game input.** See [full real pair, hashes, decoder and recovery evidence](validation/typed-snapshot-first-live-pair-2026-10-24.md). The prep sections below are historical, not current owners or pending gates.

## October 24: V14 exact-epoch successor prepared; V13 still in command

- **Independent live read-only preflight (17:17:53 UTC):** V13 `pythonw.exe` PID **65364** remains authenticated ready/connected with supervisor and exclusive console healthy, guest disarmed/idle, RIFT foreground PID **6940**/start **639284177321390013**/unchanged executable SHA, VMX PID **38044**/exact same start/log epoch. Canonical SQLite queue: **unblocked, no holder or pending, generation 1128**. The guarded same-epoch handover helper then returned `handover-prepared-not-executed` for **V13→V14**; V14 plan/launcher saved no-overwrite. **No STOP or guest activity was issued**.
- **Guest snapshot transport prepared, not used:** The one-use guest stepper validates pinned 84 KiB request, V13 normal STOP evidence, quarantined queue, VM mutex, and foreground PowerShell screenshot before typing. Offline preview reported **24 bounded commands** and the reference screenshot classifier correctly distinguished PowerShell from RIFT. New guest-IP-restricted two-digest receiver (SHA/size declarations only, no memory content) passed **8/8 focused and 545/545 full Python tests**; report originals must still transfer via the existing one-use content-hash receiver. [V14 preflight and pending gates](validation/typed-snapshot-v14-preflight-2026-10-24.md).

## October 24: exact-epoch two-snapshot plan generated offline; live capture pending

- **Host-only follow-up complete (17:10 UTC):** The tested `scripts/plan_typed_scout_snapshots.py` consumed the original **2,902-byte**, SHA-pinned game scout report and created two **identical, no-overwrite `snapshot-native` request files** plus provenance manifest at `artifacts/update-recovery-20261023-01/rr2-typed-snapshot-plan-oct24-01/`. Each future sample selects **3 × 28,672-byte** windows, starting at **`0xD3D9000`, `0xD6BE000`, `0xD761000`**; total **86,016 bytes / 21 chunks**, 10-second limit. Request SHA-256 **`0BF11FCFB280BF4042DC97CA68DE98AA8099B4194F9DD2D241F34C82E7DFF92F`**; independent manifest hash **`C8D508350162FBF5D245F65BBE5E140DD6A5A8BECD3DF67E3810CC2ADDDDE3A7`**. **13/13 focused, 537/537 full Python, and 410/410 unchanged .NET 10 regression tests pass**; this is **not** evidence of actual guest snapshots or advancing Lua data. [Exact plan and gates](validation/typed-scout-snapshot-followup-plan-2026-10-24.md).
- **Pending guest acceptance:** Fresh exact-VM, game process and coordinator status required before using absolute addresses; V13 remains the exclusive owner until a genuine normal V13→V14 handover. Acquire two independent guest `snapshot-native` reports, transfer originals with SHA checks, restore healthy coordination, and run strict `inspect-typed-wire`. No game movement, memory writes, new VNC owner, or guest operation occurred while constructing this offline plan.

## October 24: FIRST LIVE typed-prefix scout; V13 restored and healthy

- **Real guest execution and recovered evidence (16:42–16:54 UTC):** The SHA-pinned 74,209,699-byte `scout-typed-native` executable ran read-only in RIFT-Lab-1 against unchanged RIFT PID **6940** / start ticks **639284177321390013** / executable SHA **`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`**. CLI exit **3** is its documented `partial` / `byte-budget-exceeded` status. Exactly **536,870,912 attempted and examined bytes**, one covered private span and **zero holes** yielded three `RRAPIVAL2|` prefix addresses: **`0xD3DB230`, `0xD6C0550`, `0xD763500`**. The scan covers **5.669%** of eligible private virtual bytes; recorded but untested continuation cursor **`0x7FFDFFF7`**. They are **candidate byte prefixes only**, not complete fresh Lua frames or XYZ.
- **Original report preserved and SHA independently checked:** `artifacts/update-recovery-20261023-01/rr2-scout-oct24-01-host.json` is **2,902 bytes**, SHA-256 **`87A67D74E2EC8E54530944B4C24893F605719D437F74A3F03FD81D367B9771F6`**, matching the guest and one-use transfer receipt; temporary transfer endpoints shut down. Detailed process, transfer, original screenshot hashes and operational receipts: [first live scout validation](validation/typed-prefix-scout-live-2026-10-24.md).
- **V13 normal recovery checked (16:54 UTC):** The previous V12 owner exited via STOP; only then did the exclusive maintenance scan run. Authenticated independent V13 `pythonw.exe` **PID 65364**, Windows session 2, now owns native console: **connected/ready**, supervisor **running**, initial cleanup verified, guest disarmed/idle, RIFT foreground, SQLite **unblocked, no holder or pending requests**, VM and game epoch unchanged. **Do not interact with its VM/VNC while it owns the console.** Next: design narrow, identity-bound `snapshot-native` windows for the three prefix hits; two time-separated snapshots and strict `inspect-typed-wire` require a new guarded V13→V14 handover.

## October 24: pinned native-scout transfer preflight and V13 plan (historical; now completed)

- **Reuse-first host→guest transfer ready, not launched:** New `scripts/serve_guest_native_scout.py` streams the exact **74,209,699-byte** hash-pinned V2 executable in 64 KiB blocks to only the existing VMnet8 guest IP and one route; it expires after one verified transfer or 600 seconds. Wrong peer, method, path, truncated content, and hash drift cannot count as success. **10/10 focused tests, 524/524 full Python suite passed**; actual Windows source-hash/size preflight passed without opening a listener. See [host-only transfer readiness](validation/typed-prefix-scout-transfer-2026-10-24.md).
- **V13 continuity prepared, not executed:** The existing same-epoch handover procedure pinned VMX PID **38044** and its unchanged log epoch, confirmed free canonical authority and V12 PID **15336** alive, and produced ignored V13 plan/launcher. V12 remains the live exclusive console owner; **no shutdown marker, guest input or transfer listener was issued**. Guest download, bounded scout, report return and normal V13 restoration are the next controlled acceptance gates.

## October 24: bounded typed-prefix scout CLI host-validated; guest trial pending

- **V2 implementation committed:** `c6908c8` adds the read-only, 64 KiB streaming `RRAPIVAL2|` scanner with coverage, holes, byte/time/match limits and overlap-safe resume cursor; `2e73b9a` adds `scout-typed-native`, exact process-epoch request validation, versioned hash-bound no-overwrite reports, and identity-invalidated status. Existing 4 KiB `snapshot-native` contract and V1 source were preserved.
- **Host-only validation:** 23/23 focused scanner/matcher, 4/4 focused CLI, **410/410 .NET 10** full solution (117 Live + 293 core), **514/514 Python**, **108 Lua + 22 real Lua-to-C# shared cases**, full .NET formatting and zero-warning Release build passed. The published single-file executable passed its own-process native identity/no-overwrite smoke; size **74,209,699**, SHA-256 `C34D1C9BC5EC134D50AE38FBE6A16D13B0DBAC9EC412D9C4F4714E3DDFD9876C` (ignored `artifacts/validation/rr2-scout-publish-20261024-01/`). **The one-shot PowerShell 7 composite was unavailable**, but its principal component gates ran separately. No RIFT guest memory was scanned. See [command contract](reference/typed-prefix-scout.md) and [host validation](validation/typed-prefix-scout-host-validation-2026-10-24.md).
- **Live state untouched:** most recent read-only coordinator status at **11:29 EDT** remained authenticated connected/ready, RIFT PID **6940** foreground, supervisor running, guest disarmed/idle. **No new guest binary, current Lua candidate, complete advancing typed frame, or native/Lua XYZ match yet.** Next: hash-pin the tested guest binary and execute the first bounded pass only after fresh exact-epoch/queue preflight and legitimate exclusive console release.

## October 24: handoff checkpoint — typed-prefix matcher committed, V12 live

- **New verified implementation (10:47 EDT):** `6db17e1` adds V2 `TypedApiPrefixMatcher` plus 12 passing focused tests. Full .NET 10 solution gate **395/395** (293 core, 102 Live); earlier Python **514/514** remains the last Python full-suite check. This pure code was **not deployed to the guest**. It reports `RRAPIVAL2|` prefix candidates only and does not verify a complete Lua frame.
- **Latest non-mutating live check (10:49 EDT):** V12 is authenticated **connected/ready**, owned supervisor **running** with initial cleanup verified; guest PID **6940** remains foreground, disarmed/idle, no sampled desktop input down. SQLite snapshot: authority **blocked=0**, holder absent, zero pending, fresh cleanup receipt `nav-cleanup:dd28b9be952b422e77ccf17cc7429a15e880545899ac9070163f4d3f083ccad9`. No VM or guest operation was performed in this check.
- **Resume from the handoff:** [October 24 operational handoff](handoff-2026-10-24-typed-prefix-scout.md) records current identity, last ten implementation/evidence commits, exact artifact checksums, tests, safe preflight and next acceptance gates. **Next**: connect the matcher to an explicitly bounded, exact-epoch 64 KiB V2 scanner and versioned report/CLI. No current typed Lua candidate, advancement or native/Lua XYZ qualification has been established.

## October 24: complete guest map on host; native coordinator V12 active

- **Lossless current-epoch report retained (10:21 EDT):** The full **2,831,071-byte** guest `native-memory-map/1` JSON is now at `artifacts/update-recovery-20261023-01/rr2-map-oct24-01-host.json` on the Windows host. Original guest, pre-upload, streaming receiver and independent host SHA-256 all equal `5A5F74EB80F81FBE86F7D04E9F2CCEA35D09709E18CDE959F2321DF9F04D9B3B`. The temporary one-use host-only upload receiver accepted exactly one hash-pinned POST and exited; no listener on 8765 remains. The new scoped receiver passed **12 focused** tests and the **514/514 full Python** suite; implementation checkpoint `183bd71`.
- **Map anatomy verified from actual JSON:** **20,838** committed/readable non-guard regions, totaling **7,846,682,624 readable virtual bytes** (not RAM usage); **19,956** private regions hold **7,648,837,632** bytes. Historical October 16 typed-frame absolute addresses are **not mapped as readable** in today's RIFT PID **6940**, confirming those old absolute locators cannot be reused. No current typed Lua frame or native/Lua XYZ agreement is claimed.
- **Coordinator restored safely (10:23 EDT):** After genuine V11 STOP/release, the exact source/VM-pinned V12 launched independently as `pythonw.exe` PID **15336** (Windows session 2, not in Workbridge's job). Authenticated status: guest connected/idle/disarmed and RIFT foreground, coordination ready, owned supervisor running with `initialCleanupVerified=true`. Read-only SQLite: **blocked=0**, holder absent, zero pending, new cleanup receipt; **no manual queue reset**. The earlier V11 checkpoint below is historical.
- **Next meaningful gate, revised after reuse-first code review:** One 64 MiB snapshot covers less than 0.9% of the private readable space, so build a **bounded V2 marker-only scout** for `RRAPIVAL2|`, reusing the existing 64 KiB streaming scanner and exact-epoch guards. Use positive prefix addresses to select small `snapshot-native` ranges for two advancing `inspect-typed-wire` samples, then compare native XYZ. See [scout design](research/typed-prefix-scout-reuse-2026-10-24.md) and [full-map transfer/V12 evidence](validation/guest-map-report-transfer-2026-10-24.md).

## October 24: current-epoch guest map succeeded; native coordinator V11 restored

- **Read-only guest acquisition succeeded (09:53 EDT):** Under exclusive VNC maintenance after a genuine V10 STOP/release, guest `RiftReader2.Live.exe map-native` returned `MAP_EXIT=0`, `MAP_STATUS=complete`, and **20,838** regions for exact RIFT PID **6940**, start ticks **639284177321390013**, unchanged executable SHA-256. The 276-byte request's guest SHA matched `F1C41A5F...`; guest report SHA-256 is `5A5F74EB80F81FBE86F7D04E9F2CCEA35D09709E18CDE959F2321DF9F04D9B3B`. The full JSON remains **guest-local**, not yet transferred to host; screenshots and one-use receipts are preserved under ignored artifacts. No Lua frame, native XYZ match, game movement or memory write was claimed.
- **Verified safe restoration (09:58 EDT):** Guest PowerShell was closed and Rift foreground verified. Independent V11 `pythonw.exe` PID **60420**, Windows session **2**, outside the Workbridge job, started from the exact VM/config/runtime-hash-pinned plan. Authenticated status: connected, coordination ready, owned supervisor running with `initialCleanupVerified=true`, guest idle/disarmed and foreground. Its normal startup reconciliation returned the canonical SQLite queue to **blocked=0**, no holder, zero pending, with new cleanup receipt. **No manual queue reset.** Earlier V10/V11 preparation statements below are historical snapshots, superseded by this V11 live state.
- **Superseded after the 10:23 EDT transfer:** The complete report was subsequently copied and hash-verified on the host, and V12 now owns the live coordinator. The still-open work is bounded snapshots, typed-wire advancement and same-epoch native/Lua XYZ agreement; see the newer section above and [the original guest map evidence](validation/current-epoch-native-map-2026-10-24.md).

## October 24: typed Lua wire — offline inspector verified; live acquisition pending

- **V2 bounded analyzer now exists:** Added `inspect-typed-wire` for two existing `native-memory-snapshot/1` files. It reuses the strict hash-verified snapshot loader, never bridges unavailable chunks, searches complete `RRAPIVAL2|` v0.6.0 strings, rejects malformed/incomplete/conflicting copies, and requires same game process, source player, advancing sequence and `Inspect.Time.Frame`. It reports XYZ as `advanced-in-covered-scope` only, not globally unique/fresh or native-field qualified. This does not interact with VMware or V1.
- **Validation:** 19/19 focused .NET tests, **383/383 full .NET 10** (293 core + 90 Live), clean scoped `dotnet format --verify-no-changes`, and CLI help smoke. The prior full Python suite was **502/502**; the PowerShell 7 composite runner remains unavailable through Workbridge. See [offline typed-wire validation](validation/typed-wire-offline-inspector-2026-10-24.md) and [usage contract](reference/typed-wire-snapshot.md).
- **Status after the subsequent live map milestone:** This offline checkpoint's `map-native` blocker is now resolved for current RIFT PID 6940; two bounded `snapshot-native` reports, host retention of the full map, fresh typed frames, and Lua/native XYZ agreement are still pending. See the newer section above.

## October 24: verified three-frame visual baseline

- **Three distinct foreground RIFT frames (12:21Z / 12:52Z / 12:53Z):** Existing V10 PID **8168** acquired two more authenticated Track B screenshots with unique queue leases; all requests **succeeded** with independent STOP/release cleanup and no ARM, movement, game keys or manual queue reset. Each verified BMP is **1211×686**/32-bit, 3,323,038 bytes, tied to unchanged RIFT PID **6940**/start/build and VMware PID **38044**. Host capture IDs, instants and hashes are distinct.
- **Temporal QA, not motion qualification:** Deterministic pixel comparisons show **73.5576%** changed in frame 01→02 (~31 min), **39.2586%** in 02→03 (~87s), and **42.1977%** within the central-world ROI in the latter pair (mean RGB delta 0.5093). Scene animation/UI noise remain possible; these numbers do not prove player/camera motion or object recognition. Added reusable offline `scripts/compare_native_frames.py` with **6/6 tests** and no-overwrite reports under ignored artifacts. Both this suite and handover tests are included in `scripts/validate.ps1`. See [three-frame evidence](validation/native-v10-temporal-frames-2026-10-24.md).

## October 24: typed Lua readback blocker — targeted repair research

- **Source-level cause confirmed, live fix still pending:** The V1 observer’s default 4 GiB/10 s broad private-memory scan stops with `scan-byte-budget-exceeded`; its incomplete pass deliberately prevents typed freshness evaluation. No evidence shows a missing Lua frame or changed game binary. The last blocked observation belonged to the older October 23 game epoch, **not yet remeasured** for current PID 6940.
- **Positive reuse evidence found:** An actual October 16 two-sample typed addon capture (same executable SHA-256) reported advancing source sequences **5603→5608** and frame clocks **5302.787→5305.596**, with **5→3** candidate copies. The selected heap address changed within the same process; old absolute locations are invalid for today’s process. Source/parser/producer hashes, exact frame contract and a bounded-scanning acceptance design are captured in [typed API recovery research](research/typed-api-bounded-recovery-2026-10-24.md).
- **Next core milestone:** obtain an exact-current-process bounded map/snapshot in the guest, locate complete typed wire frame(s) without budget expansion, require independent source advancement, and compare same-epoch Lua XYZ with native root RVA `0x32E0200`. No V1 edits, VM settings changes, additional network port or gameplay input were made by this research.

## October 24: guarded same-VM-epoch coordinator preparation

- **Prepared but did not launch V11 (12:33Z):** Added explicit `--same-epoch` to `scripts/prepare_native_host_handover.py`. It demands the exact unchanged VMware identity, a live V10 owner, matching config/runtime hashes, and read-only SQLite proof of `blocked=0`, no holder/pending requests, and a cleanup receipt. The existing restarted-VM mode still requires queue quarantine and a changed VM epoch. Python-only plan creation prevents JavaScript rounding of Windows 64-bit `startTicks`.
- **Verified live without interrupting V10:** V11 plan and launcher exist under ignored `artifacts/update-recovery-20261023-01/`; the V11 plan preserves exact `startTicks=134372941117887852`, all five runtime hashes, full VM identity, and has no shutdown marker. V10 PID **8168** remains alive; queue free/unheld/cleaned, no actions dispatched. **V11 is not running** and is valid only while this VM process epoch remains unchanged.
- **Tests:** 7 focused handover, **496 Python**, **364 .NET** passed, plus `git diff --check`. The full `validate.ps1` runner was not completed: PowerShell 7 executable unavailable via Workbridge; Windows PowerShell 5.1 fallback mispassed Lua inline-code quotes on its first test. See [same-epoch handover evidence](validation/same-epoch-native-host-handover-2026-10-24.md). Next: resume field qualification using the verified V10 capture; no coordinator handover is needed for read-only discovery.

## October 24: receiver and coordinated host restored after VM epoch change

- A fresh host read-only check at 2026-10-24T10:30:44Z confirmed vmware-vmx PID 38044 and its VNC listener on port 5905, with no native listeners on 49712/49715; old V7 coordinator PID 34352 no longer exists. V7 had first refused orderly shutdown (`shutdown-release-unverified`) and was terminated only after exact-process/no-in-flight checks. **This was not a guest STOP/release or cleanup receipt.** The prepared V8 coordinator has not been launched; its plan must be rechecked against the current VM epoch.
- The last documented read-only canonical SQLite snapshot for `vm:rift-lab-1` recorded **blocked=1**, holder absent, no cleanup receipt, and zero pending work. That queue was not queried in this follow-up process/port check. Preserve its database/journal/history; never infer that the emergency host exit unblocked it. RIFT pixels were visible through a separate host screenshot route, but authenticated guest-receiver readiness and unattended startup are still unverified.
- **Live native capture qualified (12:21Z):** V9's first leased capture was correctly rejected because RIFT was background; its request was cancelled and cleaned. After a clean supervisor-backed V9 shutdown, a taskbar click brought RIFT to the foreground without gameplay input. Losslessly generated V10 passed all identity/hash/queue checks, connected as independent PID **8168**, supervisor `initialCleanupVerified=true`. One authenticated leased screenshot succeeded: **1211×686 BMP, 3,323,038 bytes, SHA-256 `28297faf...`**, visually confirmed world/HUD with no window occlusion. Request `rr2-v10-scout-20261024-01` is **succeeded** and queue returned to free/unheld/zero-pending after verified STOP/release. No ARM/movement. V10 is current as of this checkpoint; guest reboot auto-start remains unproved. See [V10 live capture evidence](validation/native-v10-foreground-capture-2026-10-24.md).
- **Recovery completed (12:03Z):** The already installed current-user `RiftReader2 Receiver` Startup shortcut passed the pinned installer’s `already-installed`/exit-0 check. V8 first started without a connected guest, then **gracefully shut down** with no supervisor, verified exit and closed ports. The historical V9 host (PID **50980**, Windows session 2) was **connected/ready** to the correct guest and game PID 6940, supervisor `initialCleanupVerified=true`, guest disarmed/idle, no held keys. Read-only canonical SQLite inspection confirmed **blocked=0**, no holder, fresh cleanup receipt, zero pending work, with **no manual queue reset**. True unattended logon/reboot recovery remains untested. See [live recovery completion](validation/receiver-guest-recovery-2026-10-24.md).
- **Guest ZIP verified, manifest present, receiver not yet connected:** Fresh bounded VM-console interaction found an already downloaded ZIP in `C:\Users\mrkoo\Downloads` whose *guest-computed* SHA-256 exactly matched pinned `ab5242d0317257dc2b2328f0bc1da98cc24088a2140ea4d968a29c86c23f708f`. An additional one-shot HTTP transfer received the exact guest request, but Chrome blocked that newer download as insecure; no security override was made. The previously extracted six-file folder was visible. In guest Windows, `CHECK-STATUS.cmd` validated the installed manifest/launcher/receiver/config and returned **`state=start`, `connectionVerified=false`, exit 0**, meaning receiver launch is possible, **not** that it is running. Those were subsequently verified in the recovery-completion checkpoint above. See [live guest recovery checkpoint](validation/receiver-guest-recovery-2026-10-24.md).
- The intact and SHA-256-verified six-file v2 guest installer ZIP has been placed into a new one-click Windows IMAPI2 ISO (63,488 bytes; SHA-256 507002784F251628E05DA12AEAD4F70391C6F88CFC3D6D3180D8A1C5174F25A1). Independent Joliet extraction confirmed the embedded ZIP byte-for-byte; 4/4 focused tests passed. **This is host media only:** the VM optical image remains unchanged, no guest installer ran, and no guest input was sent.
- **Next after restoration:** continue read-only RIFT field-discovery work through the authenticated, leased native host; review current pixels and keybinding evidence before any new bounded game input. Separately qualify one controlled guest logoff/logon and later VM reboot for **unattended** receiver Startup, preserving the canonical queue and requiring fresh cleanup/identity verification each time. The earlier [ISO/transfer preparation](validation/receiver-iso-host-prep-2026-10-24.md) remains historical host-only evidence, not a needed transfer step now.

## Receiver transfer — existing Pythonw firewall exception reused

**A limited-duration native Windows transfer endpoint was deployed on the host,
not inside guest Windows.** The existing Python 3.14 `pythonw.exe` had an enabled
Windows Firewall inbound TCP Allow rule (Public profile), unlike `python.exe`.
Using Python's standard HTTP server with a thin single-file/IP restriction, a
normal session-1 Pythonw process was launched independently of Workbridge and
verified still listening after the Workbridge job exited.

Observed launch: **2026-10-22T09:39:42.901691Z / 5:39:42 a.m. EDT**, PID 39644,
bind `192.168.56.1:8765`, allowed guest source `192.168.56.128`,
one pinned ZIP, and automatic stop after one download or ten minutes. **Do not
treat the historical PID or listener as permanently current.** Last checked
2026-10-22T09:42:04Z: running, zero downloads, guest installation unverified.
The existing native coordinator remained connected/ready, RIFT was not foreground.

Seven isolated HTTP tests passed, including an actual Pythonw.exe process,
exact file/host limits, HTTP 403/404/501 refusal, checksum, and automatic exit.
The real PowerShell launcher preflight passed; a simultaneous second launch was
correctly refused because port 8765 was already owned. No Windows Firewall,
VMware isolation, administrator rights, game input or guest credentials changed.
A valid package was also copied non-destructively to the existing configured
host media folder `C:\RIFT MODDING\Media\RR2-Guest-Startup-v2-20261022.zip`,
but guest HGFS remains explicitly disabled and guest read access is NOT proved.

If the live listener has expired, the physical-host launcher is
`artifacts/receiver-milestones-20261022-01/START-RECEIVER-TRANSFER-PYTHONW.cmd`.
In signed-in guest Windows, open
`http://192.168.56.1:8765/RR2-Guest-Startup-v2.zip`, verify ZIP SHA-256,
extract, and run `INSTALL-ONCE.cmd`. Host
`CHECK-RECEIVER-TRANSFER.cmd` reports a transfer receipt. No guest download
or startup installation has been established; GuestInfo remained empty.
Next acceptance still requires the one-time guest installation, then a
receiver restart and separate Windows guest login/reboot qualification.
See [the transfer investigation](validation/receiver-transfer-pythonw-2026-10-22.md).
Artifacts: `artifacts/receiver-milestones-20261022-01/`.

## Historical three receiver deployment milestones — host-side work complete

**Scope: host delivery and verification; the guest Startup shortcut is NOT yet installed.**
M1: standard-library Python HTTP transfer bound to private VMware **VMnet8 NAT-side**
address `192.168.56.1` was proven locally, with a
SHA-256-matching download and no VMware isolation/firewall changes. The server
was shut down; no guest-initiated download was claimed.

M2: six-file **v2** guest package adds launcher SHA-256 verification before
installation, status, or removal. Thirteen real Windows CMD/disposable checks
passed, including tamper, missing file and wrong-machine rejection. New ZIP:
`artifacts/receiver-milestones-20261022-01/host-only-download/RR2-Guest-Startup-v2.zip`
SHA-256 `ab5242d0317257dc2b2328f0bc1da98cc24088a2140ea4d968a29c86c23f708f`.
Recommended host launcher: `artifacts/receiver-milestones-20261022-01/START-HOST-ONLY-TRANSFER-v2.cmd`.
The old v1 package and launch script are retained only as prior evidence.

M3: `scripts/verify_guest_recovery.py` provides read-only, exact-VM/host/
receiver/game and durable-queue baseline-and-compare checks. **18 focused tests
passed**. The live baseline succeeded while RIFT was **not foreground**;
an immediate no-restart comparison was correctly refused. A positive future
comparison by itself does NOT establish an actual Windows reboot or unattended
shortcut launch. Full main-repository gate: **364 C# / 462 Python**, 108 Lua and
22 shared Lua/C# checks, zero-warning Release. Totals overlap the focused tests.

The current coordinated native host and canonical authority were left running.
No guest install, receiver restart, VM reboot or movement trial was attempted.
Guest-side package transfer, a one-time normal-user installation and the actual
logon/restart trial remain required. Do not claim autonomous reboot recovery yet.
Read [the three-milestone evidence](validation/receiver-deployment-reuse-first-2026-10-22.md).
Ignored artifact root: `artifacts/receiver-milestones-20261022-01/`.
Previous dirty work/Git history and private config were preserved; no commit/push.

## Historical receiver deployment — original Windows Startup package

**Guest installation still pending.** Reuse-first verification selected Windows'
current-user Startup folder and the already tested RiftReader2 PowerShell launcher
rather than building another service, credential store, execution channel, or
privileged scheduled task. Microsoft documents the Startup folder; VMware's
supported guest-execution commands require separate guest Windows credentials.

Host-side package:
`artifacts/receiver-reuse-20261022-01/RR2-Guest-Startup.zip`
(SHA-256 `b219c79b52e70bf2fbbcfa06f0e0d3793174bf9a0f9f1b40c19a49a37f547712`).
It includes the unchanged launcher, an interactive one-time installer, status
checker, removal shortcut and instructions. Five packaged entries were verified,
and the existing launcher tests passed 3/3 (including its disposable 38-check
PowerShell contract). No guest binary, configuration or credential is included.

Read-only detection first confirmed the exact VM (PID 52872), then a connected
and ready native host; RIFT PID 5076 was disarmed but **not foreground**.
Guest management endpoints WinRM 5985/5986, SMB 445, and RDP 3389 were not
listening. The coordinated console mutex remained held; it was not bypassed.
No VM input, host restart or source/runtime modification occurred.

**Next:** a single installation while logged in to guest Windows: transfer
the package with an existing authorized VMware/USB file-copy method, extract it,
run `INSTALL-ONCE.cmd`, verify `shell:startup` and `CHECK-STATUS.cmd`.
Only after the actual shortcut works should the guest logon/restart test be
declared complete. Until then, autonomous reboot recovery remains **unproved**.
See `artifacts/receiver-reuse-20261022-01/PLAN.md`. Do not rerun the
previous blocked guest-console diagnostics or old single-use maintenance helpers.

## Historical receiver restart recovery — tested launcher; guest installation blocked

**The restart problem is still open. No guest Startup entry was installed.**
The current-user receiver launcher and installer/removal tests are integrated,
not deployed. The final isolated gate passed **364 C# / 444 Python** and existing
Lua contracts; three main focused cases passed, including 38 PowerShell contract
checks in temporary directories. These are not guest reboot/recovery evidence.

Two guest transfer attempts did not return the required acknowledgment and stopped
before installation. Each restored the coordinated host and original queue. A
separate Run-dialog diagnostic confirmed that shortcut visually but typed no
command text. A subsequent visible diagnostic was blocked by the tool safety
check and did not execute; it was not rerouted around the block.

At **2026-10-22T07:33:00.941243Z / 3:33 a.m. EDT**, the restored native host was
**PID 6560** (start ticks 134371277545443317), connected/ready with its watchdog
running. VMware 52872, RIFT 5076 and receiver 8b9468f7712941f487a232b6cf7c5329
retained their identities. Guest state: idle, disarmed, no recovery or sampled
held input. **RIFT was not foreground**; do not claim movement readiness.
The canonical queue had no active, queued or cleanup requests and kept its history.

Current process receipt and wrapper:
`artifacts/receiver-startup-20261022-01/evidence-a03/restored-host-process.json`
and `artifacts/receiver-startup-20261022-01/run_restored_host_a03.py`.
Current absent shutdown marker:
`artifacts/receiver-startup-20261022-01/STOP-NATIVE-HOST-A03`.
The prior host PID 54952 and shutdown markers below are historical. Re-detect the
actual host before maintenance; do not reuse old activation or reset the queue.
No VM, game or guest-receiver restart occurred in this task; three native-host
maintenance restarts used verified orderly shutdown, not forced termination.

Next: resolve the observable/permitted guest setup channel, install the tested
startup helper, prove receiver restoration via the actual shortcut, then qualify
one real guest logon/restart. Do not add more control-framework milestones instead.
See [the partial recovery report](validation/receiver-startup-recovery-2026-10-22.md).
Evidence: `artifacts/receiver-startup-20261022-01/`. Native runtime source, original
config, prior source work, Git index and HEAD were preserved; no commit or push.

## Historical NAV-SCHED-02I: coordinated host active and live-verified

**The production ownership system is now enabled on recovered RIFT-Lab-1.**
Native host PID 54952 replaced the older host after verified
STOP/idle release, without restarting VMware, RIFT or the guest receiver. The
original configuration/ports/credentials are unchanged. Fresh VM detection
preceded access. Activation: 2026-10-22T05:39:31.854007+00:00.

Actual host startup now owns one durable queue, the known console mutex, and a
verified supervisor for every guest connection. Reconnect joins the previous
supervisor and invalidates old grants/queued work using exact-row reconciliation
before fresh cleanup. Existing authority on process restart requires explicit
reconciliation; never delete/reset the queue to make a blocked state disappear.

Live no-movement acceptance passed: unleased capture refused, issued-lease capture
saved and hash-checked, request finished after verified cleanup, completed token
refused, known console contender excluded. After 135 seconds idle, **1
automatic reconnect(s)** returned the same host to ready, with no outstanding
requests. No ARM/action/movement was sent; cleanup STOP was sent and verified.
The capture was not visually reviewed, so it is not a fresh movement review gate.

Both final candidate and main gates passed **364 C# / 441 Python**, **108 Lua /
22 shared cases**, zero-warning Release, synthetic smoke and deterministic replay.
34 new Python cases are included. The failed fixture run and shutdown-journal
regression remain retained; diagnostics cannot unlock a blocked shutdown on write
failure. Code review was by the implementing assistant, not independent review.

Authority: `artifacts/native-coordination-live/queue.sqlite3`, resource
`vm:rift-lab-1`. Process receipt and launch/shutdown details are in
[the activation report](validation/navigation-coordinated-host-2026-10-22.md).
Evidence: `artifacts/navsched02i-20261022-01/evidence/`.
**Do not repeat the single-use activation or reuse old process IDs.** No OS
autostart/service was installed. Preserve queue/history and re-detect on resume.

Next: return to field-discovery/navigation experiments using the live ownership
system, with fresh screenshot/keybinding review before any bounded input. Known
cooperative console exclusion does not cover manual VMware UI or arbitrary bypass
clients. Git staging/HEAD, earlier source work and original config were preserved;
no commits, pushes, dependency or external-repository changes.

## Historical NAV-SCHED-02H: shared console exclusion qualified offline

The coordinated gateway can now reserve the existing per-VM Windows console
mutex for its lifetime, including idle periods and guest reconnects. Known V1/V2
console capture/bootstrap and legacy experiment entry points are blocked while
reserved. Native requests on other threads borrow that ownership but retain VM
identity, lease and supervisor checks. Native STOP/status/release remain usable.

Acquisition requires denied-first supervision and an exact configured VM. A
pending release keeps the lock until an explicit same-thread retry; another
thread cannot close the owned handle. Identity drift blocks native admission
without silently unlocking the console. Local lock release is not proof of guest
input cleanup, and production teardown must stop/join supervisors first.

The full isolated gate passed **364 C# / 407 Python**, **108 Lua checks / 22 shared
cases**, zero-warning Release, synthetic native smoke and deterministic replay.
There are **27 new reservation tests**; focused regression contains 286 cases.
The installed legacy mutex/observe tool and fake-adapter experiment entry paths
were verified against disposable VM paths with external sources unchanged.
Final promoted-checkout and preservation results are saved in
`artifacts/navsched02h-20261021-01/evidence/milestone-complete.json`.

**Not activated on the recovered host.** This adds an internal construction
option, not a new live config or automatic restart. The existing connection was
freshly identified before guest status; no live input, capture, ARM, STOP or
console reservation was sent. Prior source changes, config, Git index and HEAD
are preserved; no external-repository edits, commit or push.

Next: production per-session supervisor startup and explicit existing-resource /
reconnect reconciliation, then reviewed activation and one bounded live trial.
Known lock-participating legacy callers are excluded when ownership is enabled;
manual VMware UI and arbitrary bypass callers are not covered. See
[shared console evidence](validation/navigation-console-exclusion-2026-10-22.md).

## Historical NAV-SCHED-02G: native caller ownership and denied-first reconnects

HTTP, CLI and the browser panel now carry explicit ownership credentials to the
existing send-boundary queue check. Private lease files are bounded to 8 KiB;
only request ID/token are forwarded out-of-band, never to the guest or journal.
Older hosts reject the envelope and callers never silently retry without it.
STOP/release/status remain usable without a lease file. Panel import, replacement
and clearing invalidate prior reviews and prevent an accidental unleased fallback.
The panel no longer labels Q/E as guaranteed strafing bindings.

An explicit `require_supervisor=True` gateway construction option starts every
newly authenticated session suspended before publication. Reconnects cannot
inherit the former policy/lease. This is a composition option, not a new live
configuration switch; the recovered host remains unchanged and uncoordinated.

Focused tests passed **259** (22 new Python cases); the panel harness includes
eight additional ownership scenarios. The full gate passed **364 C# / 380 Python**,
**108 Lua checks / 22 shared cases**, zero-warning Release, native smoke,
formatting and deterministic replay. These counts overlap. Final hashes and
main-checkout acceptance are recorded under `artifacts/navsched02g-20261021-01/evidence/`.

The recovered VM was identified before guest status and was connected, foreground,
idle/disarmed and recovery-free. Re-detect rather than reuse those observations.
No live input, capture, ARM, STOP, host restart, new guest binary or configuration
change occurred. No staging, commit or push. Prior source changes remain preserved.

Next: reconcile VM-console/bootstrap/legacy ownership, wire per-session owned
supervision and explicit reconnect reconciliation into production startup, then
review activation and a bounded live trial. Manual callers can transport issued
grants; grant issuance/heartbeat/finish still belong to the coordinator. Full
live multi-controller exclusion is not claimed. See
[native caller verification](validation/navigation-native-callers-2026-10-21.md).

## Historical NAV-SCHED-02F: owned supervisor lifecycle complete offline

The recovered VM/control connection was freshly verified before guest status:
VM PID 52872, RIFT PID 11748, same receiver instance, foreground, idle/disarmed,
no recovery and no sampled held input. The live host is not restarted or
hot-reloaded by this source increment. Refresh identities and status on resume.

The new `OwnedSupervisor` explicitly owns startup, one joinable watchdog thread,
lease-expiry cleanup and shutdown. Readiness requires saved identity-bound cleanup
and the active runner; delayed start/stop never silently enables actions or claims
finished cleanup. Concurrent stop callers share one shutdown. Failed or stopped
supervision keeps the resource blocked and does not replay work or rebind targets.

A reproduced startup registration race is fixed: `require_absent=True` rejects an
existing resource inside the registration transaction. Session preparation also
excludes competing composition/cleanup without suspending an already running
owner. Six test processes produced exactly one new authority owner.

The expanded focused suite passed **237 tests** (25 new), and the isolated full
gate passed **364 C# / 358 Python**, **108 Lua checks / 22 shared cases**, zero-warning
Release, native synthetic smoke, formatting and deterministic replay. Focused and
repeated counts overlap. Final source hashes, full-gate and main regression results
are retained in `artifacts/navsched02f-20261021-01/evidence/`.

**Not live-enabled.** The ordinary native host still does not construct the
supervisor. Next: route manual panel/CLI and VM-console/legacy controllers through
one ownership contract, publish authenticated sessions only after deny-first
startup, then review activation. No movement, ARM, STOP, new guest binary,
configuration change, live queue creation, service restart, Git staging or commit.
See [owned lifecycle validation](validation/navigation-owned-supervisor-2026-10-21.md).

## Historical native connection recovery — October 21, 2026, evening

**The missing native host/receiver connection is restored and live-tested.**
Exact VMX/log/process-start/listener checks identified recovered RIFT-Lab-1
before any console access. The existing host was restored as a normal user
process that survives its bounded launcher; the existing hash-verified guest
receiver was started without a new binary or configuration change.

Observed identities for this recovery (refresh them on resume): VM PID **52872**,
host PID **49956**, RIFT PID **11748**, guest instance
`ad6bffc45e804a879a00d6f2a4c299df`, machine `DESKTOP-8632QPL`.
Native agent/UI ports **49712/49715** are restored. Fresh authenticated status
reports RIFT foreground, disarmed, idle, no recovery and no sampled held input.
Native screenshot capture and release-only STOP passed. A **135-second idle
reconnect test** recorded actual disconnect/reconnect journal events and returned
the same receiver/VM/game, still idle/disarmed, at **9:33 p.m. EDT**.

Windows bootstrap keyboard input was used to inspect/start the receiver and
restore game foreground. No native ARM or character-movement command was sent.
The first transient host launch and unsuccessful guest command launches are
retained as failed evidence, not successful deployments. No host/VM reboot,
credential, firewall, dependency, Git staging, commit or push was performed.
Implementation source and host configuration matched their baseline hashes.

**Do not repeat recovery merely because older sections say disconnected.**
First use fresh host/VM detection and native status. Normal host/guest processes
are running; no automatic Windows-startup service/task was installed. The
current bounded transport is now running in the restored host. NAV-SCHED
policy/watchdog/manual-path integration remains a separate unfinished rollout;
this restoration does not claim multi-worker exclusion or navigation success.

Report: [native connection recovery](validation/native-control-recovery-2026-10-21.md).
Evidence: `artifacts/native-recovery-20261021-01/evidence/`.
Before further live experiments, verify current game identity, foreground,
text-entry state and fresh visual evidence; do not reuse old review/arm tokens.

## Historical NAV-SCHED-02E: recovered VM verified; guarded bootstrap offline

Read-only detection at 9:01 p.m. EDT found exactly one VMware VM, matching
`C:\\rift modding\\VMs\\RIFT-Lab\\RIFT-Lab.vmx`, and VM process PID 52872
owning port 5905. The configured native control ports had no listener and the
status call returned WinError 10061. **VMware is running, but the RIFT guest
receiver and control host are not verified.** Do not send actions or use old
VM/guest process identities; detect everything again on reconnect.

`nav_supervisor_bootstrap.py` now prepares a new single-resource authority from
a qualified guest session and existing durable queue, initially **blocked**.
It suspends controls before read-only startup qualification, rejects reused
resource records, installs exact-resource admission, and constructs—but does not
start—the watchdog. Failures leave the session blocked. Six fake-guest integration
checks passed. The full repository gate passed **364 C# and 333 Python tests**,
108 Lua checks, 22 shared cases, and 291 relative documentation links; the
Release build had zero warnings. Closing host inspection still found only the
VM port 5905, without native control listeners. It is **not wired into the live host**; manual and legacy control
ownership, supervised runner startup and final release gates remain.

See [recovery and bootstrap report](validation/navigation-recovered-vm-bootstrap-2026-10-21.md).

## Historical NAV-SCHED-02D: startup identity preflight, offline

A new read-only `qualify_startup` helper collects two fresh status responses
from the same authenticated session and verifies durable VM/guest/RIFT identity,
idle/disarmed state, no recovery, and no sampled held inputs. It produces a
proposed resource epoch but **does not register an authority, install a policy,
start a watchdog, or enable gameplay control**. Changing command sequence
numbers are intentionally ignored; missing identity or unsafe state fails closed.

Eleven preflight checks, including real disposable guest framing, passed.
The final full gate passed **364 C# and 327 Python tests**, 108 Lua checks,
22 shared cases, zero-warning Release and 288 relative links. Evidence:
`artifacts/validation/20261021T225624Z-3ed013d8`.
The native endpoint refused the connection (WinError 10061), and read-only
host inspection found no VMware VMX process or matching control-port listener.
Current RIFT-Lab-1 connectivity is **not confirmed**. No restart, arming,
movement, or screenshot replacement was attempted.

Next: trusted startup authority/policy/watchdog composition, and manual/legacy
ownership reconciliation, before any reviewed activation. See the
[startup qualification report](validation/navigation-startup-preflight-2026-10-21.md).

## Historical NAV-SCHED-02C: stalled-send handling qualified offline

Authenticated-session frame writes now use nonblocking I/O with a two-second
whole-frame budget, a bounded send-lock wait, and a bounded-buffer reader.
Partial progress cannot extend the deadline. Failed/partial sends close the
session and fail pending requests without replay or a fabricated STOP/release.
The watchdog integration test confirms the resource stays blocked afterward.

Focused validation passed **195/195** (32 new transport cases). The isolated full
gate passed **364 C# tests, 316 Python tests, 108 Lua checks and 22 shared cases**,
zero-warning Release, locked restore, format, synthetic native smoke and replay.
Three additional runs passed all 96 executions of the same 32 transport tests;
these are repetitions, not extra unique tests. Full job:
`navsched02c-full-gate-20261021-01`. Main regression and preservation are recorded
in `artifacts/navsched02c-20261021-01/evidence/milestone-complete.json`.

**Not activated on the live host.** No game input, ARM, runtime restart, guest
installation, configuration change, Git staging, commit or push occurred.
Prior uncommitted work is preserved. See [transport validation](validation/navigation-bounded-transport-2026-10-21.md).
The two-second budget is for sending, not an end-to-end or hard real-time promise.

Next: fresh trusted startup identity/authority binding and policy/watchdog
lifecycle composition, then manual panel/CLI and competing VM-console/legacy
ownership participation. Activation and a bounded live trial still require fresh
visual review and independent observations. Do not repeat this completed slice.

## Historical NAV-SCHED-02B: expiry watchdog and verified cleanup, offline

The next integration slice adds a pinned-session LeaseWatchdog and a local
cleanup exclusion/drain boundary. Expiry now drives STOP in the fake-guest tests;
cleanup is published only after exact identity checks, successful STOP, drained
requests, fresh idle/disarmed/recovery-free status, no sampled held inputs and a
saved receipt. Uncertainty latches access blocked; an explicit cleanup retry does
not replay the original action. Shutdown stops but does not free the resource.

Focused validation passed **163 tests**, including **41 new cases**. The isolated
full gate passed **364 C# tests, 284 Python tests, 108 Lua checks and 22 shared
Lua/C# cases**, zero-warning Release, locked restore, format, native synthetic
smoke and deterministic replay. Full job: navsched02b-full-gate-20261021-01.
The first focused run exposed delayed waiter settlement on disconnect; close now
fails pending local waiters directly. The failure and diagnostic remain retained.

**Still not live-enabled.** Construction starts no process/thread; the explicit
watchdog loop ran only in disposable tests. The running RIFT-Lab-1 host, guest and
configuration were not restarted or armed, and no game input or screenshot
replacement was sent. The nine prior NAV-SCHED-02A source changes were preserved.

Next: bound stalled transport sends, wire fresh live identity/policy/watchdog
startup, and reconcile manual panel/CLI plus VM-console/bootstrap/legacy access.
Then perform reviewed activation and a bounded live experiment with current
screenshots and independent observation. Do not claim the active VM is already
protected by the new queue/watchdog. See
[watchdog validation](validation/navigation-watchdog-cleanup-2026-10-21.md).
Evidence: artifacts/navsched02b-20261021-01/evidence/. No independent reviewer,
commit, push, global settings or unrelated-project edits are claimed.

## Historical NAV-SCHED-02A: dispatch admission implemented offline

Joey approved starting the next integration after the live RIFT-Lab-1 status
check. The queue now has cooperative cross-process dispatch fencing and the
native gateway/session has an optional startup admission policy. Checks occur
at the actual send point, after queued-action/send-lock waits. STOP/release and
status bypass experiment admission; STOP/release invalidate older queued work.
No SQLite transaction remains open during transport send/reply waiting.

Focused acceptance passed **122 tests**, including **27 new fake-guest/fence
cases**. The isolated full gate passed **364 C# tests, 243 Python tests, 108 Lua
checks and 22 Lua/C# cases**, with a zero-warning Release build, native synthetic
smoke, deterministic replay and 269 relative links. Full-gate job:
`navsched02-full-gate-v2-20261021-01`. Source/test changes are preserved with
hash guards; final documentation additions receive separate link checks.

**Not live-enabled.** The current host/guest/configuration were not restarted,
deployed or armed, and no game input was sent. The native target baseline was
connected, foreground, idle/disarmed, with no recovery or sampled held input.
That is not a screenshot review or a new movement/navigation result.

Next: bind policy to fresh exact live identities; implement watchdog-driven
STOP, in-flight release reconciliation and evidence-backed cleanup; reconcile
manual panel/CLI and VM-console/bootstrap/legacy paths; qualify stalled sends.
Only then enable and validate one bounded live experiment. Do not treat the
admission seam alone as completed live coordination. See the
[dispatch validation and remaining gates](validation/navigation-dispatch-fence-2026-10-21.md).
Evidence: `artifacts/navsched02-20261021-01/evidence/`. No independent workers
or reviewers were launched; no commits, pushes or unrelated-project edits.

## NAV-SCHED-01: offline experiment access queue

Joey requested concurrent A/B/C navigation research with intelligent queuing for
conflicting live-client access. The [access queue roadmap](planning/navigation-access-queue.md)
now has a standard-library Python/SQLite core and CLI, durable requests and audit
records, priority aging, dependencies, atomic multi-resource reservations, bounded
leases, stale-token rejection, and cleanup-required handoff. This is experiment
coordination, not a new gameplay controller or a claim of native pathfinding.

Focused validation passed: 42 queue tests plus 53 existing native host/client/VM
helper tests (95 total). Tests include eight competing threads, six independent
processes, abrupt worker exit, transaction interruption/rollback, restart, stale
epochs, negative cleanup evidence, and heartbeat hard deadlines. These are offline
fixtures, not AI agents or live game trials.

Full repository validation passed: 364 C# tests, 216 Python tests (including the
42 new queue cases), 108 Lua checks, 22 Lua/C# cases, zero-warning Release, locked
restore, native synthetic smoke, formatting, deterministic replay, and 266 relative
links. Log: `artifacts/navsched-20261021/full-gate-01.log`; generated evidence:
`artifacts/validation/20261021T133445Z-4c3b1dd5`. Final documentation-only updates
receive separate link/whitespace checks; source/test bytes match the full gate.

Next: enforce leases in the actual native control gateway and every conflicting
control path, with an immediate STOP/release path and fake-guest acceptance before
any separately approved bounded live experiment. The queue currently cannot stop
or fence a caller bypassing it. No host restart, guest deployment, VM operation,
live game input, RRE edit, or independent worker launch occurred in this increment.

## Camera responsiveness and actual window blur

The [camera/focus pass](validation/camera-tracking-focus-2026-10-20.md)
reduced camera-only pulses to 20 ms, retained 100 ms movement, and limited
pending camera motion to one bounded action. Release/blur discard it immediately.
Nine actions per camera mode visibly changed the view; measured button intervals
were 21.84–38.73 ms. This improves pulse cadence, not a claim of continuous
frame-by-frame tracking or one-to-one camera mapping.

Actual physical Edge Alt-Tab tests now verify window-blur STOP, both while
armed and with a browser drag held. Visible feedback and native logs agree:
disarmed, idle, no recovery, no sampled input down. The native pulse completed
before blur; guest foreground loss mid-pulse remains unqualified live.

Full gate passed: 364 C# tests, 174 Python tests including 18 async panel
scenarios, Lua contracts, zero-warning Release, native smoke and repository
checks. Evidence: `artifacts/validation/20261020T173733Z-c655e828`.
Two gate failures also led to narrow native-capture process-exit hardening and
a disposable-process initialization fix. The deployed control agent is unchanged;
the restarted host (PID 43936) serves the revised panel using
`artifacts/native-usability-20261020/host.json`.

Next useful work: longer human comfort checks if needed, then information
discovery. Do not repeat the basic camera/zoom or real window-blur baselines
without a new reason. Continuous guest-held camera streaming would require a
separate bounded lifecycle design; it is not necessary for the current trials.

## Native control usability and session cleanup

The [usability pass](validation/native-control-usability-2026-10-20.md)
inspected the actual RIFT bindings and camera settings without changing them.
Browser trials demonstrated strafe, both camera drag modes, reversible zoom,
release cleanup, horizontal-wheel suppression, and preserved action feedback.
Computer Use could inspect VMware but did not reliably deliver menu input;
the repository-owned VM-specific console helper completed that inspection.

Fixed pending ARM/STOP races, duplicate arm submission, stale queued input and
responses, late Pointer Lock grants, surface-focus release, shortcut handling,
and status overwriting action evidence. The guest now invalidates old review
authorization on STOP, recovery, and replacement capture. A live page-exit
failure led to keepalive on every STOP; the corrected trial acknowledged STOP
0.481 seconds after ARM and left the guest disarmed with no sampled input down.

Full gate passed: **364 C# tests**, **174 Python tests** including 14 executable
async panel scenarios, 108 Lua assertions, 22 Lua/C# cases, zero-warning Release,
native smoke, locked restore, formatting/module checks, and deterministic
replay. Evidence: `artifacts/validation/20261020T161445Z-98004030`.
The deployed native executable matches that gate. Active configuration:
`artifacts/native-usability-20261020/host.json`; receiver
`d26484f41ed34c9da6911d465530bdf9`. Final status: connected, disarmed, idle,
no recovery or sampled input down. Temporary bootstrap stopped.

Next authorized work can resume information discovery. Longer human usability,
live window-blur qualification outside the in-app tab-switch behavior, smooth
continuous camera tracking, numerical camera calibration, other builds, and
fullscreen remain open. Do not repeat completed basic movement/zoom trials
without a new reason.

## Native wheel zoom fixed and verified

The [zoom validation record](validation/native-zoom-2026-10-20.md) closes the
remaining wheel-control gap in the identified RIFT-Lab-1 windowed session.
Joey confirmed physical-wheel zoom works. The old native insertion path still
produced no visible zoom; targeted `WM_MOUSEWHEEL` dispatch produced reversible
zoom out/in on the final deployed binary. Four static ground patches returned
to their original pixel positions after the opposite notch.

The native agent checks exact process/window/foreground/client geometry,
dispatches once with a 100 ms timeout, and never retries an unknown result.
The panel reports dispatch separately from observed zoom. Existing movement,
camera drag, review/arm, and release behavior remain intact.

Full gate passed: **358 C# tests**, **173 Python tests**, 108 Lua assertions,
22 Lua/C# cases, zero-warning Release build, native smoke, locked restore,
deterministic replay, formatting and module checks. Evidence:
`artifacts/validation/20261020T131932Z-22b4af08`. The deployed executable is the
exact full-gate published binary. Native host/guest remain connected, disarmed,
idle, with no pending release or sampled input down; bootstrap server stopped.

Next useful work is sustained human panel usability and further information
discovery. Numerical camera calibration, other builds/fullscreen, optional
Pointer Lock outside Codex, and hard-crash cleanup remain unqualified. Do not
repeat completed S/A/D or wheel baselines without a new reason.

## Earlier native control follow-up: browser drag and timing

The [follow-up record](validation/native-vm-controls-followup-2026-10-20.md)
documents the latest improvement set. The Codex browser rejected Pointer Lock;
the panel now defaults to bounded click-and-drag camera input, which reached
the guest and visibly changed the view. Pointer release cancelled the final
pulse, released the button, and left its result visible alongside release
feedback. Camera modes, review countdown, expiry feedback, and mode-change
stops are explicit.

The hold budget now includes setup after the first press. Completed 100 ms
trials measured 101.97–113.96 ms button intervals in this small sample.
Cursor preparation avoids unnecessary warps, rejects existing button-down
state or insufficient client space, and never restores the cursor after input.
Status includes read-only Windows input-state diagnostics.

Final full gate: **336 C# tests** (274 portable, 62 Windows), **172 Python
tests**, 108 Lua assertions, 22 Lua/C# cases, zero-warning Release build, native
smoke, locked restore, deterministic replay, formatting and module checks.
Evidence: `artifacts/validation/20261020T125211Z-934ab6e9`; 251 links checked.
The final deployed executable matches the full-gate published binary.
Native host/guest remain connected and disarmed, with no pending release or
sampled input down. Temporary bootstrap service is stopped.

At this earlier checkpoint, wheel zoom was unresolved. The subsequent physical
baseline and native message-path fix are recorded above. The historical
follow-up record preserves the earlier negative observations.

## Initial native supervised movement and camera controls

The [native control roadmap](planning/native-vm-control-roadmap.md) is
implemented with recorded validation limits. The repository now owns its
guest-local input agent, persistent host connection, operator panel, CLI,
bounded executor, and VM bootstrap/capture helper. The recommended control path
does not import or run original RiftReader source. See
[usage](reference/native-vm-controls.md) and the
[live record](validation/native-vm-controls-2026-10-20.md).

On RIFT-Lab-1, reviewed trials demonstrated S/A/D, W+Q, left camera orbit, and
right yaw/pitch; an earlier native trial demonstrated W. Emergency stop
interrupted a 250 ms action, acknowledged in 39.19 ms, and released the key.
Idle host reconnect cleared an armed session. The final host/guest remain
available, disarmed, with no pending release. The panel was opened for review.
V1 receiver/observer and the temporary bootstrap server are stopped.

Wheel zoom remains unverified despite successful insertion in both directions.
One camera-button interval missed the proposed ±20 ms timing target.
Numerical camera calibration, fullscreen capture, sustained human Pointer Lock
usability, and hard-crash cleanup are unqualified. Next priority is a human
panel usability pass and binding-aware wheel diagnosis, then further field
discovery. Do not repeat the completed S/A/D baselines as discovery.

Final full gate passed: **315 C# tests** (271 portable, 44 Windows), **168 Python
tests**, 108 Lua assertions, 22 Lua/C# cases, zero-warning Release build, native
smoke, locked restore, deterministic replay, formatting/module checks, and
246 relative links. Evidence: `artifacts/validation/20261020T121433Z-4e11a754`.
The final published hash matches the guest timeout-fix binary. A 35-second idle
review and brief panel keyboard/release test passed after deployment.

## Earlier supervised movement-control parity work

The [movement-control parity roadmap](planning/movement-control-parity-roadmap.md)
now has separate successful 100 ms S/A/D trials on Joey's selected RIFT-Lab-1,
with fresh receiver/observer identity, reviewed screenshots, release delivery,
and advancing independent API samples. S changed position; A/D produced opposite
visual viewpoint rotations with unchanged XYZ and confirmed turn bindings.
Heading/angle remains unmeasured. The controller is stopped with no pending
release. See the [October 20 record](validation/movement-parity-2026-10-20.md).
Do not repeat these baselines on resumption; reacquire current identity for any
new experiment. Next useful discovery remains changed-state health/resource
capture using the completed targeted-audit tools.

October 20 full gate passed: 273 C# tests, 121 Python tests, 108 Lua assertions,
22 Lua/C# cases, zero-warning Release build, native synthetic smoke, locked
restore, replay, formatting/module checks and 229 links. Evidence:
`artifacts/validation/20261020T105058Z-83f84b40`. Older verification sections
below describe their own earlier milestones.

## Direction and completed scope

RiftReader2 is an independently developed hybrid Lua addon plus modular .NET
application. Keep it a practical personal research tool. V1 remains unchanged
reference material and selected lab infrastructure. See [architecture](architecture.md)
and [roadmap](planning/implementation-roadmap.md).

Steps 0–6 and the additionally requested memory-discovery feature are implemented
within their recorded limits:

- Five production modules, pinned .NET 10, strict configuration, and one validation gate.
- Content-pinned replay, motion analysis with explicit gaps, and durable output.
- First-class Lua producer/C# decoder with shared executable contracts.
- Nonce-bound addon transport with freshness and session/reload invalidation.
- Bounded read-only native capture and a durable field catalog/qualification workflow.
- One supervised movement/turning pulse with reviewed screenshots, exact VM/game
  binding, stop/release recovery, and before/after API evidence. See
  [experiment usage](reference/guarded-experiments.md).
- Read-only memory maps and bounded snapshots, typed value/pattern searches,
  snapshot comparisons, RVA-rooted reverse pointer discovery, and live chain
  resolution. Uses existing modules, no new projects or packages. See
  [memory discovery](reference/memory-discovery.md).

Git author remains repository-local `360madden <360madden@gmail.com>`; branch
`codex/modular-foundation`. Use Git for current commit/worktree state.

## Latest verification

The earlier native-player-field discovery pass was **incomplete at Joey's
handoff request**; a subsequent live restart and field sweep is recorded below. One bounded live capture resolved `[rift_x64+0x32E0200]` and found
float32 XYZ at owner offsets `0x320/0x324/0x328`, within 0.004 of fresh typed Lua
values in one stationary sample. The historical nearby health offsets failed.
A supervised 100 ms forward pulse completed with release and newer API
coordinates, but no post-movement native capture or game restart was performed.
No gameplay field was qualified. See the [resumption record](validation/native-player-fields-2026-10-19.md)
for exact identities, evidence, candidate paths, and the next steps.

This pass changed documentation only; the temporary capture helper and raw
evidence remain under ignored `artifacts/field-discovery/`. The original DVD is
restored and connected; the temporary GuestObserver, host receiver, and watcher
were stopped. RIFT remains logged in. Documentation/link/Git checks apply to
this handoff; the full application gate below belongs to the preceding build.

The final combined gate passed **238 C# tests** (225 portable, 13 Windows),
**21 Python tests**, 108 Lua assertions, 22 actual Lua-to-C# cases, locked restore,
zero-warning Release build, formatting/module checks, deterministic motion and
catalog replay, the published native smoke, and 198 relative links before final
handoff edits. Evidence: `artifacts/validation/20261019T052736Z-c7039e2e` and
`artifacts/memory-validation/full-gate.log`.
All 196 links in the final documentation passed a separate check.

The [memory runtime record](validation/memory-discovery-2026-10-19.md) covers the
same exact published bundle as the full gate, SHA-256
`17A1C90E5EB5864F314DE9B6218DA6FB685A15E910E020B3CCE8029EBF63B9EC`.
In RIFT PID 11620 it mapped 8,281 readable regions, captured/repeated the header,
retained unreadable-memory failures, rejected wrong epoch/build and overwrite,
and followed the PE ImageBase pointer at RVA `0x1B8` back to `MZ`. All four
portable discovery commands processed these exact runtime snapshots. This is a
real RIFT acquisition/pointer check, not a player-object or gameplay-field claim.

The [experiment record](validation/experiments-2026-10-19.md) covers a supervised
100 ms `w` pulse with key-up, matching identity, and newer ReaderBridge API
coordinates, plus identity/duplicate rejection and stop-before-input. The final
adapter also has tested retry handling for transient post-release unavailability;
the successful live trial's retained hashes identify the preceding adapter revision.

Independent review checked native rights, identity/failure provenance, strict IO,
bounds, pointer/work limits, and stop/release behavior. The original DVD is
restored, temporary observer/receiver processes are stopped, and RIFT remains
logged in. No V1 source or global configuration changed.

Earlier records separately cover [addon recovery](validation/restart-recovery-2026-10-18.md),
[native process restart](validation/native-capture-2026-10-19.md),
[fixed wall replay](validation/wall-replay-2026-10-19.md), and
[catalog semantics](validation/field-catalog-2026-10-19.md). They identify their
own inputs/builds and do not requalify this new bundle for every recovery scenario.

## October 19 resumed evidence review

Two later **previously retained** native reports (05:57 and 06:00 UTC) were found
in ignored `artifacts/field-discovery/runs/`, after the earlier 05:45 capture.
Both independently reread the root and show post-movement XYZ within 0.004 of
fresh typed Lua values in the same RIFT process/build as the original capture.
A fresh 08:22 UTC host receipt confirmed the same live game process and Lua
coordinates, but did not include a fresh native capture. No new movement or
RIFT restart was performed in this review. The VMware CD/DVD configuration
currently selected the field-lab ISO; this was observed, not changed.

The new [native position evidence reviewer](reference/native-field-evidence.md)
replays all three reports, pins source bytes/hashes, checks exact game/observer
identities and root-owner bytes, measures XYZ agreement, and distinguishes the
first capture's **unrecorded** root stability reread from the later verified
ones. Its output is `movement-consistent-stability-unverified` with exactly one
process epoch, `candidate-only`, and no restart/update qualification. Local
review: `artifacts/field-discovery/candidate-review-20261019.json` (ignored).
The reviewer has a dedicated regression suite and is included in the full
`validate.ps1` gate. See the [updated live handoff](validation/native-player-fields-2026-10-19.md).

The resumed full repository gate passed on October 19: 238 C# tests,
40 Python tests (including 19 for the new reviewer), 108 Lua assertions,
22 Lua-to-C# cases, zero-warning Release build, locked restore, native
smoke, deterministic replay, formatting checks, and 208 relative links.
Evidence: `artifacts/validation/20261019T083341Z-16701712` (ignored).

## October 19 live restart and health candidate sweep

An additional bounded guest capture at 08:54 UTC used the existing read-only
field-lab executable and fresh typed Lua in game PID `11620`. The report at
`artifacts/field-discovery/runs/d8d0c66fdb954d6590962e529f3858a3/report.json`
(SHA-256 `2D2120DCC8E2986BB284F3401B6EBBB7E49BBC0790E3B4AD1E3A144910B676B9`)
scanned 1,073,741,824 bytes with zero read failures and 126 matches for health
18,208 (119 int32, 7 float64). It hit the byte limit and is not exhaustive.

The guest game then exited via its ordinary in-game Exit Game menu; a fresh
GuestObserver report showed zero game processes and foreground Glyph. Glyph
restarted the same RIFT build without sign-in, and Atank re-entered the world.
The new game PID `8356` started `2026-10-19T09:11:06.5141458Z`
(UTC ticks `639279978665141458`), replacing PID `11620`
(UTC ticks `639279813293755454`). The Lua observer stayed alive and its
typed generation reset from 1 to 2, with fresh advancing values.

A second independently bounded read-only native capture at 09:13 UTC resolved
the same root RVA `0x32E0200` with a successful root reread, now to a
**different** session owner `0x220BF9406A0` instead of `0x216ECFE06A0`.
The resulting XYZ `(7296.40381, 876.31891, 3054.37769)` matched fresh
Lua `(7296.39990, 876.32001, 3054.37988)` within 0.004. The source is
`artifacts/field-discovery/runs/4ebbe9ee91c148c4a05466ebb9049d25/report.json`,
SHA-256 `07DB7E70D98EA102FE0939A9CD89C1153FA8A0D0318B5E431B90D3BC3766415F`.
This is **observed same-build cross-process-epoch locator recovery**, not
semantic qualification or update survival. A separate invalid-old-epoch
request was not run in this session.

The new capture scanned 977,739,776 bytes with zero read failures and stopped
at 128 exact health matches. The tracked
[native field reviewer](reference/native-field-evidence.md) now also validates
recorded health-hit contexts and clusters and distinguishes same-build
cross-epoch candidate evidence from actual qualification. The health review
produced 111 clusters and no authoritative health/resource locator. Health
was 18,208/18,208 and raw power 100 before and after both scans; there was
no changed-health reference to distinguish cached values. Full raw captures,
reviews and screenshots stay under ignored `artifacts/field-discovery/`.
See [the chronological validation record](validation/native-player-fields-2026-10-19.md).

The full repository validation passed again on October 19, including **238 C#
tests, 58 Python tests** (37 native-field reviewer tests), 108 Lua assertions,
22 actual Lua-to-C# contract cases, locked restore, a zero-warning Release
build, published native synthetic-process smoke, deterministic replay,
formatting/module checks, and 210 relative links. Local gate evidence:
`artifacts/validation/20261019T091919Z-2dba17e0` (ignored). No V1 source or
RIFT executable was modified; the RIFT-Lab game was relaunched normally.

## October 19 offline cross-epoch health structure comparison

The new `--compare-health-hits` replay in
[the field evidence guide](reference/native-field-evidence.md) checks the
existing 08:54 and 09:13 raw reports against each other without touching the
live game. Both reports have different PID/start epochs but the same build,
player, and unchanged typed health/max `18208/18208` and power `100`.
Only validated int32 marker layouts are compared; no absolute heap address
is treated as a portable locator.

Of 104 and 111 recorded health-hit groups, **10 and 7** respectively
contained informative multi-marker layouts. Exactly one layout recurred:
**8 instances before restart and 5 after** with repeated health, power and
independently observed level `45` values at the same relative offsets.
That multiplicity argues against assuming any instance is a unique field.
The ignored replay report is
`artifacts/field-discovery/health-cross-epoch-shapes-20261019.json`
(SHA-256 `6C3CD09B59F34F92A78B42D85DEF677A31B5C3A595C443E0EAA37E413C9E81BD`).
It records `candidate-only`, no tested changed-state values, and no
qualified restart or update survival for health. The comparison is bounded,
deterministic, and covered by focused tests. No live game changes occurred.

The full October 19 gate passed with 238 C# tests, **73 Python tests**,
108 Lua assertions, 22 actual Lua-to-C# contract cases, a zero-warning Release
build, native synthetic smoke, locked restore, replay, formatting checks, and
212 relative documentation links. Evidence:
`artifacts/validation/20261019T120612Z-21633586` (ignored).

## Limits and next useful work

No native position, health/resource, combat, cast, cooldown, or ability field is
qualified yet. Memory hits and chains are candidates. Use Lua/API observations
as reference, then record field meaning, units, locator/build applicability,
contrary evidence, and restart/update checks in the [catalog](reference/field-catalog.md).
The next task is to gather controlled **changed-state** health and raw resource
observations, capture only relevant regions, and distinguish true fields from
copied/cached structures. Measure reacquisition over additional restarts and
separately check old-epoch request rejection for the specific field chain.
Always reacquire process/session/build identity; never reuse heap addresses.
Update survival requires a different executable build and independent evidence.
Use the saved replay and catalog rather than repeating completed baselines.

Snapshot reads are sequential, capped at 64 MiB per explicit request, and are
not atomic. Pointer discovery searches selected bytes, 8-byte-aligned x64 slots,
main-module roots, depth up to four, and nonnegative offsets up to 4,096. Results
report truncation. Encoded pointers and other-module roots are not supported.
A process restart requires fresh inspection and explicit requests; build changes
require separate validation. Large scans have not been benchmarked in RIFT.

Experiments retain timing uncertainty: host/guest skew is unmeasured, so their
API samples support coarse before/after comparisons, not precise motion timing.
Mid-hold stop, hard crash, snapshot restore, and update recovery remain unqualified
in RIFT. Sending key-up is not proof of game key state. Dedicated navigation,
combat, and casting automation remain outside this repository.

The foundation implementation is complete; the native position candidate has
same-build restart evidence, but semantic catalog qualification, health/resource
discovery and update recovery remain unfinished. Keep versioned files; there is no
measured reason to add the roadmap's optional SQLite index. Routine fixtures,
field entries, and documentation can use cheaper models with the same gate;
identity, native IO, pointer semantics, and input control still warrant strong review.
