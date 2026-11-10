# RIFT-specific secure UI and hardware-event API evidence — 2026-11-10

## Evidence sources and scope

This report makes **no cross-MMO implementation assumptions**. The main source is the
data-only, strictly parsed in-game `Inspect.Documentation` snapshot captured by
`ApiAtlas` and retained as
`C:\Users\mrkoo\OneDrive\Documents\RIFT\Interface\Saved\SavedVariables\ApiAtlas-RIFT-LAB-1.lua`.
The API Atlas companion `api_atlas.core.load_snapshot` validated this capture
without executing saved Lua.

- Game capture UTC: **2026-10-28 15:18:37**, not November 10.
- Captured client build: **Oct 23 2026 11:32:27 RIFT-BUILD-12**,
  internal **STABLE-1-1178-A-1256632**.
- Coverage: **1,940 / 1,940 entries, zero errors, complete**.
- SavedVariables file's later modification time is a **persistence time**,
  not a new capture time.
- The `RiftReader2Casting` addon also calls `Inspect.Documentation`
  directly in `addon/RiftReader2Casting/main.lua` (around lines 357–379)
  and persists selected descriptions under its character SavedVariables.
  Those captures are narrower than a fresh Atlas collection.

## Direct RIFT API findings

| API fact from captured in-game index | Exact interpretation |
| --- | --- |
| `Inspect.System.Secure()` | Reports current secure-mode Boolean. |
| `Event.System.Secure.Enter/Leave` | Indicates transition into/out of secure state, usually associated with combat. |
| `Frame:SetSecureMode("normal" / "restricted")` | Configures UI restriction state and protected child-parent relationships. |
| `Frame:EventMacroSet` | Metadata `requireSecureFrameAndInsecureEnvironment=true`: assigning a macro to a frame event is restricted to eligible frames in a nonsecure addon environment. |
| `hardwareevent=true` | Documented as metadata on **nine** API commands in the captured catalog. This flag alone does not define the OS-level physical-vs-injected keyboard event classifier. |

The nine captured `hardwareevent=true` commands:

- `Command.Auction.Scan`
- `Command.Item.Standard.Drop`
- `Command.Item.Standard.Left`
- `Command.Item.Standard.Right`
- `Command.Mail.Send`
- `Command.Minion.Claim`
- `Command.Minion.Send`
- `Command.Minion.Unlock`
- `Command.Quest.Share`

The complete captured index has **no `Command.Input` entry** and no
documented `Command.Player.Move`/turn-key equivalent. This is an absence
from *that specific documented catalog*, not proof that the executable
cannot consume physical or synthetic Windows input.

The snapshot also contains 165 entries exposing
`noSecureFrameAndEnvironment` metadata and 26 entries exposing
`requireSecureFrameAndInsecureEnvironment`; counts are metadata
occurrences, not necessarily all true values.

## Distinguish three mechanisms

1. **Addon API secure/combat restrictions**: verified in RIFT's own descriptions
   for secure mode and protected macro assignment.
2. **Hardware-event requirements for specific Lua command calls**: nine
   `hardwareevent=true` metadata entries as above; whether/how an input
   is classified remains a separate question.
3. **Windows-generated `SendInput` movement acceptance by the game**:
   not established by the two addon API findings.

In the Nov 10 Lab2 trial, a requested 100 ms `A` pulse recorded key-down
at 139.6767 ms and key-up at 143.5499 ms, a ~3.87 ms interval.
The guest controller returned `deliverySucceeded=false` and
`releaseSucceeded=true`, with no keys held in subsequent checks.
That test **cannot qualify a 100 ms turn** and **does not establish game
rejection of synthetic events**. The earlier Nov 9 Lab2 `A` pulse recorded
117.6375 ms and succeeded at the delivery/release layer; neither trial
qualified actual body-heading change. Evidence:
`artifacts/wall-turn-left-a100-run-20261110-02/action-1.json`;
`docs/validation/lab2-100ms-turn-live-2026-11-09.md`.

## Freshness and next useful checks

- A new snapshot should be collected in the *current* live RIFT client via
  the installed **API Atlas** addon (`/atlas collect`), then exported
  using its supported clipboard or normal SavedVariables persistence.
  `ApiAtlas` does not auto-collect when opened; do not conflate addon
  file modification with captured client build.
- Compare fresh `Inspect.System.Version`, the `hardwareevent` fields and
  secure-mode/macro entries against this dated baseline.
- Keep visual position/facing observations, successful key injection,
  actual key-held duration, addon secure state, and any confirmed player
  heading as separate facts. A zero-XYZ turn is not proof that the game
  ignored the key; a delivered SendInput is not proof it consumed it.
- The first Nov 10 guest SavedVariables check incorrectly reported no matching
  files. A corrected VM-identity-pinned, read-only inventory verified that **both
  labs** have their existing `RIFT\\Interface\\Saved` and installed `ApiAtlas`
  and `RiftReader2Casting` addons. Each lab's SavedVariables tree contained
  multiple `RiftReader2Casting.lua` files; `ApiAtlas.lua` was only 46 bytes,
  not a new full API snapshot. Inventory receipts are under
  `artifacts/api-inventory-20261110/{lab1,lab2}/` (ignored).
- A RIFT client SavedVariables copy last persisted **2026-11-10 05:52 UTC**
  contains eight selected addon `Inspect.Documentation` strings exactly
  equal, byte-for-byte, to the complete October 28 API Atlas reference:
  `Inspect.System.Secure`, `Frame:EventMacroSet`,
  `Layout:EventMacroSet`, `Command.Event.Attach`, `Inspect.Unit.Detail`,
  `Inspect.Unit.Castbar`, `Inspect.Ability.New.List`, and
  `Event.Combat.Damage`. These were parsed as literal Lua strings without
  executing SavedVariables code. Their **file save time is not a proved
  capture time** and eight identical entries do not establish that the other
  1,932 entries are unchanged.
- Both Lab1 and Lab2 controllers were checked on Nov 10: connected/disarmed
  but RIFT was *not foreground*. Accordingly no `/atlas collect`, `/reloadui`,
  or game input was sent. A fresh full catalog from today's live game
  remains pending verified foreground and collection/export.
- Do not use Codex, OpenCode or Ollama for this work without renewed
  authorization. Workbridge parallel *commands* are not independent
  reasoning agents.

No game input, UI reload or addon installation was performed for this
research.
