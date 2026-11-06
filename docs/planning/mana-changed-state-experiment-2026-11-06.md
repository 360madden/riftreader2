# Mana changed-state experiment — November 6, 2026

Status: **bounded experiment design; no live input, guest login, scan, reload or
deployment was performed for this note.**

## Existing evidence and authority

Lab 1's current-build native kind-3 record has passed the exact `0x072A` Mana
descriptor fingerprint. Its `3980/3980` value is still a semantic candidate.
The independent `RRAPIVAL2` v0.6 contract contains a typed `player.mana` field;
the retained Lab-2 Warrior frame reported that field unavailable, which does not
predict availability for the Lab-1 kind-3 player.

The repository has historical evidence for one-at-a-time, screenshot-reviewed
protected Cast clicks against a designated training dummy, including resource
change and exact ability/target event matching. That evidence establishes the
guarded method, not current readiness or blanket casting authority. Repository
policy requires a new casting/combat action to be an expressly authorized,
narrow experiment. The current request authorizes Mana changed-state research;
the coordinator must still review and pin the concrete ability, effective target,
scene and single action before delivering input. No rotation, retry loop,
autoattack, arbitrary spell, hostile-world target or health-loss test follows.

## Phase A: no-input short-window comparison

Use Lab 1. Reacquire the exact VM, game PID/start/SHA/module, player ID and tool
identities. First acquire fresh advancing `RRAPIVAL2` frames and require a finite
typed `player.mana` for the same canonical player ID as the native self key. If
Mana is unavailable, stop: neither a UI bar nor the native candidate can replace
the independent numeric reference.

Bracket one type-checked native Mana read with advancing API frames. Retain exact
source/snapshot times and declare the comparison window before assessment. Require:

- one VM and game epoch, exact current build and one canonical player ID;
- live native type `0x072A`, stable owner/record/revision inputs and calculated
  current/maximum;
- finite API `player.mana`, advancing source sequence and frame clock;
- no target/player change and no input during the baseline;
- native/API equality for the compared value, with maximum treated separately.

This can establish a synchronized same-player baseline. It does not establish
change response, passive continuity or restart durability.

## Phase B: one reviewed Mana stimulus

Before input, obtain a current ability inventory from the existing RIFT API and
select exactly one named ability with finite `costMana > 0`. Prefer a harmless
self-target utility or buff if the current API proves its effective target is the
player. Otherwise use only a designated training dummy and a previously reviewed
single protected-cast method. Reject passive, positioned, autoattack, unusable,
out-of-range, mismatched-target, unknown-resource, active-cooldown or active-cast
abilities. Record the ability ID/name, `costMana`, effective target, cooldown and
pre-action player Mana.

The coordinator must hold the exact lab console and queue lease, verify current
foreground identity and a fresh screenshot, arm one reviewed click, and guarantee
STOP/key release and disarm cleanup. Start synchronized API/native observation
before the click. Deliver at most one Cast click; do not retry on a miss, delayed
event or absent Mana change. Stop attack afterward only if the reviewed ability
or observed state starts it and the existing protected Stop action is current.

Accept changed-state evidence only when:

1. API player ID, native self key, process/build and target remain pinned.
2. An authoritative ability/cooldown or exact ability event places the stimulus
   inside the observation window; a click receipt alone is not a successful cast.
3. Independently observed API Mana changes from baseline and the type-checked
   native Mana candidate changes in the same direction and compatible amount.
4. At least one later observation shows a second change or stable recovery trend,
   distinguishing a responsive field from a single coincidental value.
5. All input is released and controller/queue cleanup is independently verified.

Mana cost need not equal the first observed delta exactly because regeneration,
latency and other game effects can overlap. Preserve timestamps and raw values;
do not force equality by selecting convenient samples. A cast with no authoritative
event or no independent API Mana change is an inconclusive stimulus, not negative
proof about the native locator.

## Authorization boundary and next decision

Read-only Phase A fits the existing native/API acquisition authority. Phase B is
within the user's requested changed-state research only after the coordinator has
a concrete reviewed ability, target and one-click plan. A required addon reload,
game/VM restart, new deployment, arbitrary console input, memory write, debugger,
or non-training combat remains outside this experiment and needs its applicable
separate authority. The coordinator alone owns live input; research workers do not.
