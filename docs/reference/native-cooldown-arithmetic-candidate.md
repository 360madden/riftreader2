# Cooldown arithmetic candidate — November 6, 2026

`scripts/native_cooldown_candidate.py` is an offline, exact-build calculator for
the subset of current-cooldown field construction already established by static
instructions. It does not open RIFT, locate an ability or cooldown owner, read
memory, invoke a native getter, or send game input.

For executable SHA-256
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`,
the helper accepts four externally acquired float inputs: producer return `T`,
optional duration `D`, game clock, and the still-unqualified remaining threshold.
It applies float32 rounding and returns the instruction-derived candidates:

- `currentCooldownBegin = T - D`
- `currentCooldownDuration = D`
- `currentCooldownRemaining = max(T - gameClock, threshold)`
- `currentCooldownExpired = -(T - gameClock)` only on the verified negative branch

The positive expired branch and paused predicate remain null. The helper labels
its result `static-arithmetic-candidate`; it does not name `T` a deadline or claim
the input owner, units, time base, ability ID, live cooldown meaning, freshness,
or restart durability. Non-finite/out-of-range inputs and another build fail
explicitly without returning partial fields.

Seven focused tests cover active and expired arithmetic, a nonzero threshold,
float32 rounding and overflow, build rejection, and malformed inputs. These synthetic checks
validate reconstruction behavior only. They are not live cooldown evidence.

The attempted REA/Ghidra follow-up against the same retained PE verified its
identity but timed out during whole-binary default analysis before returning a
function dossier for `0x1290458`. That timeout is a tooling/performance limit,
not negative evidence about the conditional owner lookup. The next useful native
step remains a smaller or cached disassembly route for that lookup, then an
identity-pinned passive acquisition of its actual inputs. A changed cooldown
comparison still requires independent ability evidence and the coordinator's
narrow controlled-action gates.

## Lab 2 Soul Recall cross-phase candidate

On 2026-11-07, a 21:30:47 UTC modifier census found one mode-4 row with a
direct match for Soul Recall key `1012591716`, no exclusion or tag entries,
operation 0, float inputs -300000 and 0, and an observed direct scale candidate
of 2. A separate 21:31:06 UTC typed-definition capture found base cooldown
3600000 milliseconds for the same key and game process identity. Using the
traced float32 multiply/add operations gives -600000, then 3000000 milliseconds;
int32 truncation and float32 multiplication by 0.001 give
`3000.000244140625` seconds. The historical SC628 API record for the same full
ability ID also contains that value.

The raw sources and their hashes, calculation, and limits are in
`artifacts/discovery-20261107-cast/soul-recall-reconciliation.json`; the
single-case offline reproducer is beside it. These are cross-phase candidate
observations, not an atomic capture. The historical API record was captured
around 50 minutes earlier and does not establish a shared process epoch.
Sequential stable bytes cannot exclude release/reuse (ABA), and this agreement
does not establish changed-state response, passive freshness, API parity at the
native capture, or restart qualification.
