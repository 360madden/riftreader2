# Browser Workbridge guest probe — 2026-10-29

A fresh normal ChatGPT conversation in Chrome showed `This response couldn't
load` after the response completed, even for a simple display-only prompt.
Reopening the earlier conversation did not recover readable responses. This
does not establish the underlying cause. An independent fresh normal ChatGPT
conversation in the in-app browser displayed a complete simple response and,
after the test below, its complete Workbridge report. This is a working
alternative, not a demonstrated repair of Chrome. The in-app browser also
rendered the previously blank Chrome control response and the earlier
Workbridge report, confirming that those answers were saved. The earlier
report's arithmetic was correct. Its claim that doctor did not execute inside
the guest conflicts with the actual implementation, which does execute a
temporary guest diagnostic; the script and job outputs are the evidence.

In the in-app browser, ChatGPT selected Workbridge and submitted two commands
from the main PC: `python scripts/lab_guest_probe.py --lab lab1` and the same
for `lab2`. The coordinator reviewed a scoped terminal approval. Retained
Workbridge command outputs independently confirmed both complete and exit 0:

| Workbridge job | UTC interval | Lab | Guest process count | RIFT executable detected |
| --- | --- | --- | ---: | --- |
| `wb-codexfree-lab1-20261029-01` | 17:33:57–17:34:04 | lab1 | 164 | No |
| `wb-codexfree-lab2-20261029-01` | 17:33:58–17:34:05 | lab2 | 160 | No |

Both jobs report their distinct pinned VMX paths and VM process identities.
The browser's final report matched the retained results and was readable. The
probe uses the existing VM-specific cached credentials, identity guards and
VMware `listProcessesInGuest`; it imports existing lab configuration/session
code but invokes no Codex executable or agent in the guests. It emits only the
process count and whether `rift.exe` or `rift_x64.exe` appears. It does not
start RIFT or modify game state. The main PC coordinator in this trial was
Codex; the browser-to-guest probe itself was Codex-free. This proves a small
read-only process-inventory path, not arbitrary guest commands, game control,
two independent browser workers, or sustained reliability.

The new probe also passed independent local direct runs before browser dispatch.
Its process-list parser rejects an unexpected list format or count rather than
reporting a false successful inventory. Results reflect only the instant sampled.

Browser chat: https://chatgpt.com/c/6ae38321-f0dc-83ea-bc65-6eee8c0723ce
