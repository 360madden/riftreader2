# Native combat telemetry: next useful field experiment

Date: 2026-11-14. This is a source audit and experiment recommendation, not a
live result. No process memory was read and no game input was sent. All proposed
work remains pinned to the current exact-build SHA in
`CurrentBuildPlayerLookup.GameSha256`; offsets from older builds are not recipes.

## Ranked result

1. **Qualify self cast state and the matching cooldown transition together.**
   This most directly replaces the addon facts that currently arrive only after
   a 1–3 second cast. `CurrentBuildWorldCastCandidateReader` already resolves the
   unit table, cast component, selected child/key, game clock, begin candidate,
   and a fingerprinted runtime duration input. For the experiment, reuse its
   component decoding on the freshly resolved self entity rather than scanning
   up to 256 units. In the same identity-pinned lease, bracket one reviewed known
   1–3 second cast with `CurrentBuildAbilityMapsCandidateReader` samples. Capture
   idle -> cast start -> active -> stop -> cooldown-active -> cooldown-clear,
   alongside an independently fresh addon/UI reference. The useful success
   condition is a repeatable self child/key transition plus one map entry whose
   clock-relative values change and return consistently for that same ability.
   Do not promote zero children to semantic idle, a raw key to an ability ID, or
   map floats to public cooldown fields until the transition agrees with the
   reference. This single experiment attacks cast gating, action completion and
   cooldown eligibility without introducing another reader family.

2. **Reconcile learned abilities from the existing map and typed registry.**
   Ability maps already completed prior live acquisitions in about 10–17 ms and
   expose bounded player-associated keys. `CurrentBuildAbilityRecordsCandidateReader`
   resolves requested keys to type-verified definitions, full-ID candidates,
   List-filter byte, raw costs, base timing, range and variants. This is enough
   for a fast cached combat catalog, but not yet proof of learned/spellbook
   membership. The smallest qualification is a controlled learn/unlock or level
   transition with before/after map, typed records and independently observed
   ability list. Until that exists, use the addon ability list as the membership
   authority and native records only as definition/timing candidates.

3. **Add current-build Power only after the cast/cooldown experiment.**
   `PowerCandidateReader` is genuinely changed-state and one-restart qualified,
   but it is pinned to SHA `7C356C9D...`; the current player lookup is pinned to
   `1935A05C...`. It must not run against the current build or lend its old
   offsets to a new implementation. `CurrentBuildVitalsCandidateReader` already
   shares the current-build player/component/resource-kind ownership path and
   implements typed Mana/Energy reconstruction, but deliberately leaves other
   resource kinds unavailable. The next Power experiment should statically
   recover and fingerprint the current-build kind-1 record, then compare a
   bounded spend/regeneration series with the addon. This is likely reusable,
   but it is less urgent than cast completion and cooldown gating because the
   runtime can conservatively defer resource-sensitive actions meanwhile.

## Reusable source points

- `src/RiftReader2.Live/CurrentBuildWorldCastCandidateReader.cs`: current cast
  topology, selected child/key and typed primary runtime duration candidate.
- `src/RiftReader2.Live/CurrentBuildAbilityMapsCandidateReader.cs`: player-owned
  maps, game-clock bracket, bounded keys and raw float pairs.
- `src/RiftReader2.Live/CurrentBuildAbilityRecordsCandidateReader.cs`: typed
  definitions, IDs, costs, base timing, ranges and variants for requested keys.
- `src/RiftReader2.Live/CurrentBuildVitalsCandidateReader.cs`: current-build
  self ownership, resource kind and typed resource reconstruction seam.
- `src/RiftReader2.Application/PowerCandidateReader.cs`: older-build Power
  arithmetic and safety pattern only; its SHA and locator are not current.
- `docs/reference/native-cooldown-static-followup-2026-11-06.md` and
  `docs/reference/native-cast-duration-factories-2026-11-07.md`: public-field
  arithmetic, selection gates and the still-missing live semantic evidence.

## Qualification still required

Every accepted field needs exact PID/start/SHA and self-key ownership before and
after acquisition, stable consumed bytes, an independent changed-state reference,
and unavailable-on-race behavior. A successful same-epoch cast is not restart
qualification: repeat the resolved route after a complete game restart before
making it routine authority. Learned membership needs an observed membership
change; cooldown needs active and clear transitions; cast needs positive start,
progress and stop; current-build Power needs spend and regeneration. Patch
recovery remains separate for all four.
