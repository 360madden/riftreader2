# Native and API reference research — 2026-11-07

These are historical addon consumers, archived client-documentation mirrors, and
Microsoft documentation. They are not a current official RIFT contract, live
API observation, or evidence that a native candidate has API parity. Keep raw
native, addon, and derived results distinct; qualify comparisons with the same
player, process epoch, field presence, and independently observed state change.

## Historical addon source

- **Presence and resources.** Sunspots' Archimedes
  [`core.lua`](https://repos.curseforge.com/rift/archimedes/file/9f0cd7ae1c86/core.lua)
  and [`view.lua`](https://repos.curseforge.com/rift/archimedes/file/9f0cd7ae1c86/view.lua),
  changeset `9f0cd7ae1c86`, 2011-11-13, use separate mana, energy, power and
  charge displays, hide absent/false fields, and use a display fallback of 100
  for a missing maximum. Lua numeric zero is truthy: that fallback does not
  establish the game's maximum, and missing does not mean zero. Calling alone
  does not establish which native resource is applicable.
- **Cast state.** The same author's
  [`castbar.lua`](https://repos.curseforge.com/rift/archimedes/file/9f0cd7ae1c86/castbar.lua)
  separately handles active channel remaining time and non-channel progress.
  That is current castbar state, not proof that a definition's casting time
  equals an active cast's duration or that interruption has been classified.
- **Ability IDs.** Naifu's [EnKai cooldown manager](https://repos.curseforge.com/rift/enkai/trunk/cooldown/cooldown.lua)
  at SVN trunk revision 367 (accessed 2026-11-07; preceding r366 release
  2016-12-03) passes the wildcard `New.List` result to `New.Detail` and uses
  IDs as equality keys; its cooldown threshold is an addon filter. This path
  does not prove learned ranks, variant selection, unique names, or an ID
  encoding. Compare exact distinct public IDs and presence, not cache membership
  or highest numeric ID.
- **Buffs.** Wildtide and Lifeismystery's Gadgets
  [buff bars](https://github.com/Lifeismystery/gadgets/blob/2775cf74c07b10860f6b869d5e1f9502ab76cc60/wtBuffBars_Renderer.lua#L58-L88)
  and [icons](https://github.com/Lifeismystery/gadgets/blob/2775cf74c07b10860f6b869d5e1f9502ab76cc60/wtBuffIcons_Renderer.lua#L48-L55),
  commit `2775cf74`, 2018-05-26, distinguish absent duration from numeric zero
  through Lua truthiness. The icon renderer slices characters 10–17 of an ID;
  this is an addon assumption, not a supported encoding or lifetime contract.
- **Experience.** Gadgets' [XP bar](https://github.com/Lifeismystery/gadgets/blob/2775cf74c07b10860f6b869d5e1f9502ab76cc60/wtXPBarGadget.lua#L133-L171),
  same 2018 commit, computes `accumulated / needed` and renders a full bar
  when `needed` is zero. This historical UI denominator and max-level handling
  are consumer assumptions, not proof of current native or API semantics.

## Historical client-documentation reproductions

[Igor's client documentation export](https://github-wiki-see.page/m/chrisbecke/Igor/wiki/RIFT-API-Documents)
separately describes `race` and localized `raceName`, and lists calling strings;
it does not establish race-token literals, native key mappings, or current
behavior. The archived PTS pages for [ability detail](https://www.seebs.net/rift/pts/inspect_ability_new_detail.html)
and [cooldown events](https://www.seebs.net/rift/pts/event_ability_new_cooldown_begin.html)
describe different outputs: event zero indicates a finished cooldown, while an
omitted Detail field is not thereby zero. [Experience documentation](https://www.seebs.net/rift/pts/Experience_index.html)
describes accumulated, needed and rested, but does not settle every denominator
or level-cap interpretation. These archives have unverified exact client builds.

## Windows snapshot limits

Microsoft describes [PSS VA clones](https://learn.microsoft.com/en-us/windows/win32/api/processsnapshot/ne-processsnapshot-pss_capture_flags)
and its [snapshot implementation](https://devblogs.microsoft.com/oldnewthing/20220314-00/?p=106346)
as briefly freezing the source while capturing cloneable memory, with copy-on-write
costs. A clone can help an exceptional diagnostic traversal, but is not a default
replacement for the existing short read-only anchored observations. It captures
possible intermediate state and does not establish API parity. Microsoft's
[ReadProcessMemory documentation](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-readprocessmemory)
does not promise a shared instant across separate reads; matching anchors cannot
exclude ABA or threads that existed only between thread snapshots.

**Player stats consumer.** The original Gadgets [stat text bar](https://github.com/Lifeismystery/gadgets/blob/2775cf74c07b10860f6b869d5e1f9502ab76cc60/wtStatTextBar.lua#L483-L504), same 2018 commit, calls `Inspect.Stat()` and individual stat names, then subscribes to `Event.Stat`. Its [update code](https://github.com/Lifeismystery/gadgets/blob/2775cf74c07b10860f6b869d5e1f9502ab76cc60/wtStatTextBar.lua#L602-L623) mistakenly assigns `resistLife` to the displayed fire resistance; this is a concrete reminder that addon presentation is not a ground truth. The historical [API reproduction](https://github-wiki-see.page/m/chrisbecke/Igor/wiki/RIFT-API-Documents) describes `Inspect.Stat` as player stats, including separately named unbuffed values; it does not qualify a native offset or atomicity. Preserve the exact requested stat and independently compare changed state.

## Historical official Souls archive comparison

The [vendor Souls archive](https://webcdn.triongames.com/addons/assets/Rift_souls_EN_2018_10_12.zip)
was retained at `artifacts/rre-peer-reference-20261107/Rift_souls_EN_2018_10_12.zip`:
419,274 bytes, SHA-256 `C680A6C5E8171E31DC0D918C94D0C141F71FF23B1D6C00E9287BA1890C3688EF`.
Exact full IDs match 23 of 134 Lab 2 native catalog rows and 9 of 54
separately captured API rows. Three compatible examples are Concussive Blast
(XML cooldown `10.000000`, energy `11`; native base `10000` ms, raw energy
`11`; API cooldown `10`, energy `11`), Repelling Shot (`20.000000`/`10`,
`20000` ms/`10`, `20`/`10`), and Piercing Shot (`10.000000`/`24`,
`10000` ms/`24`, `10`/`24`). The 2018 XML cooldown strings have no explicit
unit attribute; these numerical comparisons do not establish current units,
adjustment, selected variants, or freshness across the different captures.
Full source hashes, all matches and limitations are in
`artifacts/rre-peer-reference-20261107/official-souls-comparison.json` and
`artifacts/rre-peer-reference-20261107/official-souls-comparison.md`.

## Historical vendor item Range examples

The vendor's [2018-10-16 Discoveries archive](https://webcdn.triongames.com/addons/assets/Rift_Discoveries_2018-10-16.zip)
contains `Items.xml`. A bounded HTTP range and in-memory deflate of its initial
prefix observed Dread Axe of Dancing Blades (`2h_axe`) with `Range` `3.000000`.
A separate bounded prefix observed Thunderous Blunderbuss of Accursed Dreamers
(`2h_ranged_gun`) with `Range` `30.000000`. The archive was 157,876,206 bytes;
these were partial reads, not full-archive or member checksum verification.
Details, byte ranges, ETag and item identifiers are retained in
`artifacts/sammie315-coordination-20261107/discoveries-item-schema.md` and
`artifacts/sammie315-coordination-20261107/discoveries-ranged-item-sample.md`.
These historical raw fields establish no units, current equipped-item value,
runtime identifier mapping, or ability-range formula.
