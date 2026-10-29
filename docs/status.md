# Current status

Updated: 2026-10-29 (America/New_York).

**Automated two-lab movement trial — IN PROGRESS:** The reviewed session runner
now calibrates actual key responses and makes bounded waypoint decisions from
independently advancing addon XYZ. Code checkpoints `0e2af08` and `d382173`
passed offline validation. Initial live calibration attempts exposed transient
partial-memory reads, feedback cadence limits and a zero-displacement lateral
response; no waypoint arrival is accepted yet. Each failed attempt released
inputs and cleaned up its queue lease. Fresh readers with one complete-scan retry
and 250 ms polling are being rebound. See the
[movement trial report](validation/automated-movement-two-lab-2026-10-29.md)
for current evidence and limitations. The authorized window ends at 22:04:30Z.

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
