# Browser ChatGPT and Workbridge two-lab diagnostic

On 2026-10-29 Joey authorized an easy autonomous comparison with native
Codex. One normal browser ChatGPT chat selected Workbridge and requested the
existing `python scripts/lab_codex.py doctor --lab lab1` and `--lab lab2`
commands through Workbridge on the main PC. The exact Lab-2 command was reviewed
and allowed once at the browser prompt. Both jobs overlapped and their retained
Workbridge outputs were independently read by the coordinator.

| Job ID | UTC interval | Result | Guest diagnostic |
| --- | --- | --- | --- |
| `rr2-two-lab-doctor-20261029-lab1-01` | 17:24:02–17:24:13 | passed, exit 0 | lab1 ready, Codex CLI 0.165.0, login available |
| `rr2-two-lab-doctor-20261029-lab2-01` | 17:24:01–17:24:14 | passed, exit 0 | lab2 ready, Codex CLI 0.165.0, login available |

The outputs identified the distinct configured VMX processes and VNC ports.
The doctor implementation uses VMware GuestOps to stage a temporary diagnostic
script, execute it in the guest, retrieve the result, and remove temporary
files; it queries the guest's installed Codex CLI. It is not a no-Codex guest
workflow, a browser-driven guest AI task, or proof of game readiness. The prompt
said not to change files; the doctor does create and remove temporary guest
files as described, so the prompt's strict wording was not met. No game input,
game start, or project source edit was requested as part of the diagnostic.

The browser displayed `This response couldn't load` for both the initial final
answer and a no-tool summary follow-up. Therefore the requested browser-side
calculation and final report were not verified. Durable Workbridge job records,
not the submitted-call UI or the missing answer, establish the command results.
Chat: https://chatgpt.com/c/6ae380ed-0c54-83ea-8add-d86ec6bde003

Follow-up: the original response was readable in the in-app browser and its
arithmetic was correct. Its statement that doctor did not execute inside the
guest is inaccurate: the implementation stages and runs a guest diagnostic as
described above. See [follow-up test](browser-workbridge-codex-free-2026-10-29.md).

In contrast, the [native Codex teamwork test](native-codex-teamwork-2026-10-29.md)
sent prompts to existing Codex chats inside each lab and received readable
answers plus a coordinator-relayed review. It did not use VMware-dispatched
doctor commands. The tests cover different simple workloads and do not prove a
speed or cost advantage, sustained reliability, automatic artifact transfer,
or browser-based independent guest workers. One browser worker issued both
diagnostics; two independent browser workers were not tested in this trial.
