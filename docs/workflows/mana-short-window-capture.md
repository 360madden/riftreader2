# Coordinated Mana baseline capture

`scripts/capture_mana_short_window.py` is a prepared, read-only coordinator for
one Lab-1 baseline:

```text
bounded typed API capture
        -> exact-owner native kind-3 record probe
        -> bounded typed API capture
        -> offline short-window assessment
```

It reuses the reviewed typed-reference and native-owner tools rather than adding
a new guest reader or input path. The two API phases each retain their original
archives and strict identity receipts. The native phase retains its full owner
review. The coordinator chooses the newest usable before frame and earliest
usable after frame, requires the same exact VM, PID/start/build/module and player,
and then invokes the fail-closed Mana assessor.

The default declared maximum gap is **180 seconds on each side** of the native
observation. This is intentionally a practical acquisition bound, not a claim
that the tools normally take three minutes or that `Inspect.Time.Frame` is
synchronized to host UTC. Actual host snapshot-completion-to-native and
native-to-snapshot-start gaps are retained. The API sequence and frame clock must
also advance independently. Callers may choose a smaller bound after measuring
the first reviewed run; values above 300 seconds are rejected.

The command requires an explicitly hash-pinned published reader and the retained
same-epoch Mana descriptor review with its SHA-256. It pins the coordinator and
all imported acquisition/assessment sources before phase one, rechecks them
between phases and before publication, and fails on drift. No existing evidence
file is overwritten.

The descriptor review is not accepted from its PID/player/RVA fields alone. The
assessor resolves its hash-pinned before/after owner review files and requires
both reviews to match the current native probe's exact VMware identity, game and
player identity, reader SHA, workflow SHA and owner-probe source SHA. The final
summary preserves both API capture directories, capture-summary and archive
hashes, reader hashes, API resource report paths/hashes, native owner evidence
and tool hashes, descriptor path/hash, and assessment path/hash so the result is
self-locating and auditable.

The workflow sends no game input and performs no addon bind, reload, restart,
memory write or native getter call. A successful `stable-baseline-agreement`
result establishes only advancing API/native equality inside the declared host
acquisition gaps. It does not establish a Mana response, passive freshness,
continuity or restart recovery. Changed-state work requires the separately
reviewed one-action experiment and paired before/after observations.

The prepared coordinator has not been executed live. Nineteen focused tests for
resource extraction, assessment and coordination pass, along with Python
compilation and `git diff --check` (apart from unrelated existing line-ending
warnings).
