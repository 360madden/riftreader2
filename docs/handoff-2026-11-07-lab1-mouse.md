# Lab 1 mouse setup continuation — November 7, 2026

Checkpoint 18:53 EST. Authoritative checkout C:/work/riftreader2,
branch codex/modular-foundation. Read AGENTS.md. The earlier nine-hour discovery
goal ended at 17:26:48; this is the subsequently requested Lab 1 mouse setup,
not a resumed timed goal. Practical results; focused checks and no framework.

## Findings and ownership

User requested the Lab 2 GitHub-backed mouse capability for Lab 1. Reuse the
already installed host vncdotool 1.4.2, upstream sibson/vncdotool, through a new
RR2-owned scripts/external_lab1_mouse.py. No package/helper installed in guest,
no RRE runtime dependency and no changes to the RRE/REA-Lab1 owned checkouts.
Root alone owns live actions. RRE was notified to remain offline for both labs.

Host launch lock and nonabandoned console mutex are held through disconnect;
queue vm:rift-lab-1 stays BLOCKED/unheld with no pending Lab 1 requests.
Controller UI 49811/agent 49810 must be absent. Do not reset/unblock the queue,
force a lease, or start a controller. The prior controller PID 15636 is absent
and its Scheduler task is inactive, but historical normal cleanup is UNVERIFIED:
its last generation has no exited.json and Scheduler reports nonzero last result.
A new VM epoch plus independently checked present-day absence/ownership is the
new baseline, not fabricated historical STOP evidence.

## Verified setup receipts

artifacts/external-lab1-mouse-20261107/ contains all trials. capture-01/02 safely
blocked before input on a demonstrated Windows TCP-probe false positive. The
adapter now reads the OS IPv4 listener table. capture-03 succeeded and root
reviewed its original 1211x757 full-desktop image: Trio L41, normal RIFT HUD,
Collector 0.4.11 research toolbar. No reload/deployment/cast/rebind is authorized
by this setup. Capture itself sent NO input and confirmed disconnect/mutex release.

Guest session-0 checks cannot attest desktop foreground or neutral keys. VMware
interactive execution initially rejected the cached username spelling. Fresh
session-owner-01 receipt proves the authenticated account, interactive account
and game owner share the SAME Windows SID. interactive-alias-01 succeeded with
that same account's canonical MACHINE\\user spelling, same per-VM cached password,
and a temporary in-memory username buffer: PowerShell session1, RIFT session1,
foreground PID6820. No cache writes or alternate account/password attempts.
The final adapter must perform fresh SID equality checks, never substitute
session-0 held-key readings for interactive evidence, and bound state age.

Current VM epoch23:16:48.672Z, VMX PID31864/start134385670086118542;
RIFT PID6820/start639296903905448486, game SHA1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8.
These values are receipts, not reusable future admission identities.

## Discovery summary provenance

Today's RR2 Lab 1 findings are in handoff-2026-11-07-native-discovery.md and the
native player/buff reference notes: 122 catalog rows/119 names/43 filtered names;
Trio/Mage/41/Mathosian; 40 raw stats; XP144585/245308/rested0; selected dummy HP,
position and numeric level50; zone candidate z487C9102D2EA79BE; 28 buff rows and
sentinel stack paths. These remain candidates, not continuing freshness or restart
qualification. REA-Lab1's latest research is November2–3, not new November7 work.

## Verified live milestone

The same-SID canonical interactive route is implemented. Eleven focused tests
passed, including SID mismatch, stale observation, queue/controller admission,
review refusal, click failure release and unconfirmed disconnect. After review,
the final guest probe plus final admission checks must complete within10 seconds;
executable hashing precedes foreground/neutral sampling. Credentials are unchanged.

Root visually reviewed each fresh full-desktop image and completed:
move-browse-02 (pointer move to899,502), click-browse-01 (opened browser), and
click-close-01 (closed browser at1146,430). Each exited0; both pre-input guest
probes matched and VM identity matched before/after the action. Button release,
connection close and console mutex release
were true. Root inspected every after image. Browser is closed; toolbar moved
upward as a side effect of opening it. No casting, movement keys, reload, Capture,
bind or addon deployment. move-browse-01 safely failed at stdin review (non-PTY
EOF) before input; use an interactive PTY for reviewed move/click operations.

Post-run independent checks confirmed controller listeners absent and Lab1 queue
still blocked/unheld/no pending request. No controller was started. The existing
historical cleanup caveat above remains unchanged. Small UUID-named diagnostic
JSON files were written in the configured guest staging folder; no helper or
guest package was installed. Do not perform a broad guest-folder cleanup.

Invocation: use artifacts/tools/control-python/Scripts/python.exe -B
scripts/external_lab1_mouse.py capture|move|click [x y] --output FRESH_RR2_ARTIFACTS.
For move/click, run with a PTY, inspect the emitted image, then submit the exact
captureId approval with a specific visual note. Coordinates refer to the FULL
guest desktop and must be selected again from the new screenshot.

## Product direction clarified

Joey clarified18:53 EST: this repository is a practical discovery AND retrieval
framework for wide-ranging data, not only a collection of findings. Findings
should feed working on-demand readers/commands with current source resolution,
identity/freshness checks and structured values/unavailable results. Report
discovery, available retrieval and remaining qualification separately. This is
now explicit in AGENTS.md and does not require a new infrastructure framework.

Joey additionally clarified: RRE and RR2 are parallel complementary efforts,
similar but different. RRE's repository is a valuable framework information
source: reuse its findings/readers/artifacts/techniques with provenance, preserve
its owners and coordinate shared lab access. Imported historical/static evidence
does not silently become qualified current RR2 live data. AGENTS.md records this.
