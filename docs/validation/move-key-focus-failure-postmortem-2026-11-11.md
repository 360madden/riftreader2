# Postmortem: RR2 move-key focus failure and recovery

**Date:** November 11, 2026 (America/New_York)  
**Project:** RiftReader2 (RR2), branch codex/modular-foundation  
**Verified host:** AMD-DESKTOP only  
**Severity:** High development blocker; repeated wasted effort, but no evidence of a stuck key or harmful game input during the failed focus runs  
**Resolution:** Narrow focus fix committed and pushed as 6643a34dca81b2e1a33060ce4118d2ac43890def

> **Direct accountability:** I repeatedly referenced the working legacy RiftReader helper yet failed to test its unchanged executable first or reproduce its critical focus sequence faithfully. I built and revised RR2's own code, committed plausible fallbacks, and relied on offline checks while the real foreground-focus blocker persisted. Joey's suggestion to run the known-good helper side by side finally separated an implementation problem from speculation about RIFT rejecting simulated keys. This failure in engineering approach should not recur.

## Executive finding

The obstacle was **Windows foreground activation before input**, not demonstrated RIFT rejection of W. Early RR2 attempts stopped *before sending W* because RR2 could not establish the physical RIFT window as foreground. Meanwhile, the old RiftReader C# helper already had a historical movement record and a usable compiled binary.

The decisive test ran that old binary **unchanged** against the same AMD-DESKTOP RIFT PID/window. It acquired focus and reported a bounded W key-down/key-up. Comparing actual source then exposed a material implementation difference: the old helper attached the relevant Windows input threads **before** calling SetForegroundWindow; RR2 initially tried SetForegroundWindow directly and only attached threads in a fallback after an optional asynchronous wait. The final RR2 implementation adopted the old sequence and collected focus-result diagnostics.

One physical RR2 test then successfully acquired RIFT foreground focus, inserted and released a 750 ms W request, and measured **4.6516 units of same-owner candidate X/Z displacement**. This is strong changed-state correlation, **not yet independent UI/Lua proof that RIFT consumed the key**. The exact Windows reason the previous ordering failed has not been isolated in a controlled repeated trial.

## A known-good reference existed

- The historical source is C:\rift modding\RiftReader\tools\RiftReader.SendInput\Program.cs, particularly FocusTarget (lines 531–605 at inspection), and the .NET 10 Windows project RiftReader.SendInput.
- The historical receipt is C:\rift modding\RiftReader\docs\recovery\csharp-sendinput-scancode-proof-2026-05-11.json, with commit 06d82cd29bc173d4145829513b8eb521c0d9c6f5. It recorded a 750 ms W scan-code input, two SendInput events, exact foreground HWND, and a 0.946955-unit difference across API coordinate captures. The capture gap was about 29 seconds, so that record alone does **not** exclude intervening movement.
- At the November 11 A/B test, the existing compiled Debug DLL (last modified October 15) had SHA-256 01B5D0A81AB533DF59D63B8EB90A66DA12BA436C18E87895A8FDD5468A96935A. This is not a claim that its bytes were identical to the May 11 build; the relevant source and behavior were inspected.
- RR2 is required to be standalone. That constraint permits **selective technique reuse**; it did not justify postponing a diagnostic run of the old executable or changing working call order without a test.

## Timeline: what failed, and how it was resolved

| Time (EST) | Event and evidence | Result |
|---|---|---|
| May 11, 2026 | Original RiftReader saved its C# SendInput ScanCode proof and API-coordinate comparison. | Historical known-good candidate; not a current RR2 acceptance test. |
| Nov 11, 06:06 | RR2 commit 1eebc929 introduced a disposable physical C# move-key helper. | Useful scaffold, but focus not live-qualified. |
| 07:17 | Commit 5cfb5b32 made RR2 focus the selected RIFT window by default, initially using direct SetForegroundWindow. | Windows denied or did not establish foreground in the subsequent test. |
| 07:36 | Commit fc9aa86f added an AttachThreadInput fallback and described it as reused RiftReader assistance. | RR2 still failed foreground; output explicitly said no input sent. |
| About 07:46 | A physical test of RR2 returned: "Windows denied RIFT foreground after direct and attached-thread activation; no input sent." | **W was not sent.** RIFT's input acceptance was not tested. |
| 08:31 | Following Joey's suggestion, the unchanged legacy compiled DLL targeted physical RIFT PID 44888, HWND 0x911EC. | Focus changed from Edge PID 59072 to RIFT PID 44888; exact HWND foreground true; two W input events sent for 750 ms. Movement not measured in this A/B run. |
| 08:51 | RR2 was changed to attach-first focus on its initial CLI thread, followed by SetForegroundWindow and 250 ms settling; fresh PID/window guards retained. | 34/34 focused .NET 10 MoveKeyCommandTests passed. |
| 08:52 | First RR2 live command used a guessed DLL path without the win-x64 subfolder. | Launch failed before any game input. Actual build path was located instead of retrying blindly. |
| 08:53 | Corrected RR2 binary ran a single 750 ms W pulse with native XYZ before and 250 ms settled after. | Focus acquired, insertion and release reported, same-owner X/Z displacement candidate 4.6516 units. |
| 08:55 | Commit 6643a34 recorded the fix and concise evidence; push to origin/codex/modular-foundation succeeded. | Durable RR2 code, quickstart, and status milestone. |

The timestamps above combine retained Git history, saved source/receipt files, and the exact November 11 Workbridge command results. They do not imply a continuous instrumented trace of every earlier attempt.

## Engineering errors I made

### 1. I did not establish known-good parity first

The highest-value first experiment was to run the original compiled helper, unchanged, on the verified host and exact RIFT window. Instead I wrote a new helper and changed its focus logic across commits. Merely opening or mentioning RiftReader is **not** equivalent to validating its actual behavior. This was the principal avoidable mistake.

### 2. I claimed code reuse without matching behavior

The pre-fix RR2 logic was effectively:

~~~csharp
if (!SetForegroundWindow(hwnd) || !await WaitForForegroundAsync(...))
{
    RequestForegroundWithAttachedThreads(hwnd, pid);
    await WaitForForegroundAsync(...);
}
~~~

The historical working helper instead did the important operations in this order:

~~~text
Identify exact HWND/PID
Attach current input thread to foreground and RIFT GUI threads
Restore only if minimized (show only if hidden)
SetForegroundWindow(target HWND)
Wait while attachment is active
Detach both threads in finally
Inspect actual foreground HWND/PID
Only then consider sending input
~~~

The fallback was **inspired by** the old code, but not the same call sequence. It also conditionally skipped the target-thread attachment in one extra case and delayed 500 ms rather than the legacy test's 250 ms. Those differences warranted verification; I should not have called the fallback proven merely because its API names matched.

### 3. I inserted an asynchronous boundary before the critical fallback

In one execution path, RR2 awaited WaitForForegroundAsync before attaching threads. A .NET async continuation can resume on a different thread; Windows input-thread association is thread-specific. This is a **plausible contributing mechanism**, not a proven root cause: the earlier failure did not log whether SetForegroundWindow initially returned true, which thread performed the fallback, or whether each attachment succeeded.

The correction calls the legacy-style focus routine synchronously **before the first await in this path**, then asynchronously verifies exact foreground. That matches the successful legacy sequence more closely.

### 4. I overvalued offline tests and under-instrumented live failure

Parser, identity, bound-duration, and release tests were useful but could never prove Windows would transfer foreground ownership from Edge to RIFT. The failed RR2 message collapsed multiple possibilities into "Windows denied foreground" without recording the actual foreground HWND/PID, individual attachment results, or SetForegroundWindow result. Repeating unit tests was not progress toward the missing live fact.

The fix reports focusAttempt fields: previous/after foreground HWND and PID, attachedForegroundThread, attachedTargetThread, and foregroundRequestAccepted. It still separately checks pinned process, executable hash, window, pressed inputs, key insertion, release, and before/after candidate position.

### 5. I spent time on hypotheses before doing the discriminating A/B test

Because no W was sent during the failed RR2 focus attempts, explanations about RIFT's anti-automation or game-key handling were premature. The concrete decision tree was simple: if legacy succeeds from the same foreground context and RR2 fails, compare implementation paths first. Joey proposed exactly that experiment; I should have proposed it earlier.

### 6. I guessed a .NET build-output path even during recovery

The first updated RR2 launch omitted the RuntimeIdentifier directory from the built path. The executable was actually under:

~~~text
C:\work\riftreader2\src\RiftReader2.Live\bin\Debug\net10.0-windows\win-x64\RiftReader2.Live.dll
~~~

The incorrect path returned "Could not execute" with exit code 1 and sent **no input**. Locating the actual built DLL resolved this incidental error. Future runs should discover the artifact or invoke a verified project command, never assume the output layout.

## Decisive A/B evidence on the same physical RIFT instance

**Target identity, Nov 11:** host AMD-DESKTOP; process rift_x64 PID 44888; process-start UTC ticks 639299470183328173; exact RIFT HWND 0x911EC; executable SHA-256 1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8. These are historical *run pins*, **never future defaults**.

| Check | Pre-fix RR2 | Unchanged legacy DLL | RR2 after correction |
|---|---|---|---|
| Focus from Edge to exact RIFT window | Failed | Passed | Passed |
| Foreground before/after PID | Diagnostic unavailable | 59072 → 44888 | 59072 → 44888 |
| Attached foreground/target threads | No per-attachment result | Source sequence inspected; actual attachment booleans not exposed in successful report | true / true |
| SetForegroundWindow result | Not recorded | Focus outcome true; direct call return not exposed | true |
| W input | Not sent | 750 ms, two input events | 750 ms requested, key-down inserted |
| W key release | Not applicable | Reported two input events, release path inspected | releaseSucceeded=true |
| Native position correlation | Not collected | Not collected in this Nov 11 run | 4.651589 units same-owner candidate displacement |
| Independent RIFT UI/Lua proof | Not collected | Not collected | Not collected |

**Final RR2 result, one run:** focusAttempt reported before HWND 0xC12E2 / PID59072; after HWND 0x911EC / PID44888; both thread attachments and SetForegroundWindow accepted. Windows input insertion succeeded, input was bounded, releaseSucceeded=true, targetLost=false, cancelled=false, observed duration **770.2 ms**.

Native before: X 7439.9897, Y 863.58545, Z 2967.548.  
Native after: X 7435.413, Y 863.58545, Z 2968.3796.  
Same unit key: 239816685251645959.  
Delta X = -4.57666015625, delta Z = +0.83154296875, planar displacement = **4.651589179483055**. Capture gap = 1.0876566 seconds. The helper explicitly returned gameResponseVerified=false because the native positions are candidate data rather than independent gameplay confirmation.

**Output distinctions that must never be collapsed:**

1. **Foreground acquired:** Windows shows the exact pinned game window in front.
2. **Input inserted:** SendInput reported the requested keyboard event; bounded key release completed.
3. **Movement candidate:** native position changed with the same unit identity over the test interval.
4. **Game consumption independently confirmed:** requires separate contemporary RIFT UI/Lua or comparably independent evidence; **still pending**.

Do not turn stage 2 or 3 into an unqualified stage-4 claim.

## Root-cause assessment

**Confirmed root of the development failure:** I failed to prioritize a direct known-good executable A/B test and failed to preserve the working helper's call sequence during selective reuse. That caused avoidable iterations and weak diagnosis.

**Confirmed operational blocker in earlier RR2 attempts:** game window foreground was not established; the helper correctly stopped before key input.

**Confirmed working correction in one current live run:** attach-first synchronous focus, exact target revalidation, SendInput with key release, and changed-state candidate XYZ.

**Not established:** which precise Win32 condition made direct-first/fallback RR2 fail; whether asynchronous thread hopping was the determining factor; whether the solution succeeds under every foreground permission state, game restart, multibox layout, or Windows update. Do not claim a universal Windows focus bypass.

## Durable rules for this and future engineering work

1. **Known-good-first:** Before replacing a failed subsystem, locate the last verified working source *and executable*, its hash, exact invocation, host, and evidence. Test unchanged behavior if authorized, rather than treating a source reference as sufficient.
2. **Same-context A/B:** Compare old and new on the same verified physical host, process epoch, executable hash, HWND, input mode, and bounded action. Record foreground before/after. Do not switch to LEGION or VMware during an AMD-DESKTOP test.
3. **Preserve causally important ordering:** In stateful native/UI APIs, call order, thread identity, attachment lifetime, and timing are behavior. Copy the narrow mechanism faithfully before "improving" it.
4. **One decisive experiment beats repeated conjecture:** After a focus failure, stop before input, capture exact failure diagnostics, and run the known-good baseline when permitted. Do not keep layering generic fallbacks before that comparison.
5. **Prove the actual layer:** Test window focus, Windows input insertion/release, game state response, and independent game confirmation separately. Offline tests are necessary but never proof of an interactive desktop outcome.
6. **Keep RR2 standalone:** Selectively port behavior and tests into RR2-owned C#; the old executable is a **diagnostic comparator**, not a runtime dependency.
7. **Fail closed and release:** Pin process PID/start/exe SHA/HWND, enforce single-controller ownership, refuse ambiguous targets or held inputs, bound key duration, and attempt key-up unconditionally. No retries after uncertain insertion or release.
8. **Do not guess executable paths:** Discover RID-specific .NET outputs (for example win-x64) and run the exact freshly built artifact.
9. **Document limits along with wins:** Store exact output fields, commit IDs, timestamp, and candidate-vs-verified labels. Keep future-run PIDs/HWNDs dynamic.
10. **Escalate to evidence, not workflow overhead:** If a fix fails twice in the same failure layer, stop writing speculative variants; perform a discriminating baseline/diff experiment or state a specific blocker.

## What a future agent should do on recurrence

1. Read this postmortem, the move-key quickstart, and the current RR2 code.
2. Verify the local computer with a machine-local command. Work **only** on that verified computer.
3. Resolve a **fresh** RIFT PID/start/build/HWND; never reuse PID44888 or HWND0x911EC.
4. Run preview/read-only checks first; use a bounded live pulse only when specifically authorized.
5. If RR2 cannot focus: preserve its exact focusAttempt/failure output, compare to the unchanged known-good legacy helper under the same controlled conditions, then inspect thread attachment, foreground window, and timing—not game movement logic.
6. If focus and insertion work but XYZ does not advance: shift the investigation to game input mode, stale/native owner semantics, and independent RIFT evidence. Do **not** re-open the solved foreground code without contrary evidence.
7. Commit the smallest proven code correction and concise evidence, preserving unrelated work.

## Source and trace index

- RR2 source: src/RiftReader2.Live/Control/MoveKeyCommand.cs and src/RiftReader2.Live/Control/WindowsControlDesktop.cs.
- RR2 operator guide: docs/move-key-quickstart.md.
- RR2 status entry: docs/status.md, 08:53 EST November 11.
- Legacy source: C:\rift modding\RiftReader\tools\RiftReader.SendInput\Program.cs.
- Legacy May 11 historical proof: C:\rift modding\RiftReader\docs\recovery\csharp-sendinput-scancode-proof-2026-05-11.json (SHA-256 7BE6337DB20F35B2FD18153CBC313B8BC2AF33C31F79CB6F3744456345C03F28).
- RR2 relevant commits: 1eebc929 (new helper), 5cfb5b32 (direct focus default), fc9aa86f (fallback that did not clear the blocker), 6643a34d (attach-first correction and live milestone).
- Retained command IDs from November 11: legacy A/B rr2-legacy-ab-live-csharp-w750-20261111a; first RR2 path failure rr2-legacy-first-focus-live-w750-xyz-20261111b; successful RR2 rr2-legacy-first-focus-live-w750-xyz-20261111c; focused tests rr2-legacy-focus-tests-20261111b. Job retention is not guaranteed; the essential fields are embedded above.
- Final commit was pushed successfully to https://github.com/360madden/riftreader2.git, branch codex/modular-foundation.

**Final lesson:** Reading a known-good implementation and claiming to reuse it is not enough. **Run the known-good thing, preserve the working behavior, and verify the result on the real target.** This was an avoidable assistant engineering failure; Joey's proposed A/B test supplied the missing evidence.
