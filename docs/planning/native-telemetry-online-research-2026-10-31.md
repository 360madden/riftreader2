# Native-first RIFT telemetry — online research leads (October 31, 2026)

Four supporting online research lanes, followed by a second targeted wave,
were completed while both labs were investigated read-only. These are source
leads, not proof of current RIFT build offsets or permission for gameplay input.
Prefer original game/vendor documentation and actual open-source parsers;
distinguish historical behavior, available current files and hypotheses.

| Lead | Public evidence | Practical decision |
|---|---|---|
| Historical read-only client memory | [Magelo Sync FAQ](https://rift.magelo.com/fr/faq/view_entry.jspa?faqEntry=12120) documents memory reads without packet sniffing/writes; its proprietary offsets and current compatibility are unavailable. | Supports native feasibility, **not** a current-build implementation. Do not install Magelo on the labs. |
| Self unit identity and HP semantics | [RIFT API reference](https://github-wiki-see.page/m/chrisbecke/Igor/wiki/RIFT-API-Documents); [RiftMeter source](https://gist.github.com/Bamux/6bc1062bf3ad49887c9bec642e471271) compares unit ID with `Inspect.Unit.Lookup("player")`. | Use the existing addon reference as an independent oracle only. `health`, `healthMax`, `healthCap` are distinct; three equal integers do not establish ordering or ownership. The textual `u...` form is not proven native-endian binary. |
| Native combat events | [Gamigo slash commands](https://support.gamigo.com/en/support/solutions/articles/201000105480-rift-slash-commands) documents `/combatlog`; [PrancingTurtle parser](https://github.com/hewisaurus/PrancingTurtle/blob/master/PrancingTurtle/AutoParser/Methods.cs) preserves event types, participant IDs, ability IDs/names; [expanded format notes](https://www.thegharstation.com/2016/12/01/rift-4-0-hotfix-4-1212016/). | Passive file tail when an existing log is enabled: casts, heals, damage, buffs and resource gains; **not** live HP/max, complete ability ownership or actual cooldown remaining. |
| Game ability catalog | [Ghar Station telara.db](https://thegharstation.com/gharwiki/index.php/Telara.db) identifies ability dataset 83, effects 84, icon names 6009. | Potential static metadata only. Database is packaged/encrypted; no loose file at 11 checked lab paths. Extraction requires separate review of format/permissions, and no unlicensed code copying. |
| Read-only 64-bit root discovery | [Microsoft VirtualQueryEx](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualqueryex), [PE format](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format), [Cheat Engine pointer scan algorithm](https://github.com/cheat-engine/cheat-engine/blob/master/Cheat%20Engine/pointerscanworker.pas). | Current int32 value scout only covers `MEM_PRIVATE`, but existing `MemoryDiscovery.FindPointerChains` / CLI `find-pointers` **already handle retained 8-byte pointers and module-rooted candidate chains**. Reuse those with scoped `MEM_IMAGE` section snapshots; avoid a redundant matcher. A pointer to UI cache is still **not** an owner proof. |
| Fresh native coordinate anchor | Original game UI can expose player XYZ, but prior values are now stale; a distinct multi-field float32/float64 XYZ search may discriminate engine objects better than HP equality. | Require fresh independent reference, bounded scans and change correlation. Existing screenshot and lease workflow governs any approved input. |

## Exact live read-only constraints and findings

- Lab 1: RIFT PID 8164, start 639290507142219120; 2/37 HP-shaped
  reread regions persisted initially, then 2/2 retained the layout in enlarged
  context. Lab 2: PID 7012, start 639290507554340644; 14/24 initially
  retained layout, then 10/14 in enlarged context.
- Enlarged context did not contain known self unit IDs in tested LE/BE
  64-bit, ASCII or UTF-16 forms. Adjacent UI markup and addon/library strings
  make the structures **UI/cache-suspect**. This is a reason to seek a
  different native anchor, not a definitive heap-object classification.
- `scripts/inventory_passive_rift_sources.py` checked both exact game
  identities, normal and configured document paths. Both
  `C:\\Users\\mrkoo\\AppData\\Roaming\\RIFT\\Rift.cfg` files say
  `LogCombatConsole=False`, flush interval `0.500000` and
  `DocumentsDirectory=C:/Users/mrkoo/OneDrive/Documents/RIFT`.
  No `CombatLog.txt` or standalone `telara.db` appeared at the checked
  paths. It did not search packaged assets, read combat contents, alter
  config or issue a slash command.

## Native resource and ability interpretation

- Original API exposes multiple class-dependent resource families: mana,
  energy, charge, spirit, focus, combo and planar; absent is not zero.
- Combat-log participant decimal IDs can exceed JavaScript safe integer
  precision. Preserve them as decimal strings or BigInt; the inferred
  hex-to-`u...` mapping must be verified against actual current logs.
- Historical parser schemas contain 10 or 11 structured fields and can
  include punctuation in ability names. Use a bounded append-only reader
  with raw-line provenance, rotation handling and parser warnings if
  logging is later explicitly enabled. Do **not** run old log-import
  executables; some delete source files after ingest.
- No live health, resources, cast, cooldown or learned-ability fields have
  been promoted from these leads. Do not silently expand the Lua addon.

