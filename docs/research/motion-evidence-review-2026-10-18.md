# Motion evidence review — 2026-10-18

Status: read-only review of existing V1 evidence. No V2 experiment or numerical
reproduction was run. Technical choices below remain proposals.

## Why this evidence matters

V1 already contains a useful example of a plausible field interpretation being
rejected by a better experiment. A projected motion vector closely matched free
travel, but pointed partly into a wall while the character actually slid along
it. Reusing this case could test whether a future local analyzer preserves
important negative findings. [S1, S2]

| Existing finding | Evidence and scope |
|---|---|
| Body yaw is distinct from camera/aim direction. | The V1 yaw report qualifies `owner + 0x304` as a float32 angle in radians; camera-only rotation and body turning distinguished it from the older `0x30C/0x310/0x314` triplet. Two game restarts passed on the recorded guest build. [S3] |
| A projected vector is not actual velocity. | Free-travel displacement error was about 0.79%; two wall-slide trials then had wrong Z direction and direction errors of 62.605067 and 62.493413 degrees. The player slid; no stationary blocked interval was established. [S2] |
| Actual native velocity, speed, and instantaneous turn rate remain unresolved. | The latest motion report explicitly retains those questions. Component/configuration chain restart qualification does not qualify them as motion fields. [S1] |
| Requested rate differs from recorded rate. | Batch 6 records 9,598 passed samples, median interval 47.1009 ms (21.231 Hz), and p95 53.4093 ms against a 40 ms request. This is one recorded dataset, not a V2 benchmark. [S2] |
| Collection completeness needs separate examination. | Current source retains eight recent samples, sends observations on a 200 ms timer when motion is enabled, and trims oldest motion samples when delivery exceeds 131,072 UTF-8 bytes. These mechanisms do not by themselves establish that every produced sample was retained. [S4–S6] |

Do not promote a saved field merely because it is readable or survives a restart.
The field's meaning must also survive the discriminating cases relevant to its
claimed use.

## Retained evidence and reproducibility

The existing capture is present at:

`C:\rift modding\RiftReader\.riftreader-local\motion-recovery\20261018\batch-6-samples.jsonl`

Fresh file metadata confirmed **100,187,956 bytes**. Its source SHA-256 recorded
by the existing wall report is
`F1B63D83B1DB09B9D06A5A7C051F5FC56235562C748554A17BFB9C68FA8A7D54`.
This review did not read or recompute the hash of the full capture.

The small wall report preserves the source identity, formulas, sample counts,
build/observer identity, and trial artifacts. Its fresh file SHA-256 was
`6520b2caeb0d96540f5dca8ab39076be30541a25e87d6168d92a78e6da6b9716`.

A bounded search of the motion-recovery folder's four saved scripts did not
identify a wall-classification replay command. That is a retrieval gap, not proof
that no implementation exists elsewhere. Retained evidence and a reproducible
analysis entry point are separate accomplishments.

The local recorder `collect.py` is also a research prototype: its deduplication
set lives in memory, and its exception handling suppresses several file/parse/key
errors. It is a reference for provenance, not proof of restart-safe recording.
See the [reuse inventory](../reference/reuse-inventory.md).

## Implications for the next discussion

A useful initial objective would preserve the known rejection, identify the
analysis procedure, and make it reproducible against fixed inputs with compact
results. Then timing and AI interaction cost can be measured honestly.

Use actual sample timestamps and explicit process/session boundaries in any
later calculation. Values derived from position or yaw differences should be
labelled derived; they do not establish discovery of a stored native rate field.

## Sources inspected

- S1: `C:\rift modding\RiftReader\docs\workflow\native-motion-recovery-result-2026-10-18.md`,
  especially lines 37–46, 58–95, and 97–111. Reviewed report SHA-256:
  `03b9a800cda42e6c8031f87e5c40d9bf613dae947936abdf3bc99037f9ad80ea`.
- S2: `C:\rift modding\RiftReader\.riftreader-local\motion-recovery\20261018\analysis-wall-motion.json`,
  source/cadence/formulas and free/wall trial sections.
- S3: `C:\rift modding\RiftReader\docs\workflow\player-yaw-recovery-result-2026-10-18.md`,
  lines 3–39 and 66.
- S4: `C:\rift modding\RiftReader\tools\RiftReader.GuestObserver\NativeMotionWorker.cs`,
  lines 89–108.
- S5: `C:\rift modding\RiftReader\tools\RiftReader.GuestObserver\MainForm.cs`,
  lines 38 and 145–202.
- S6: `C:\rift modding\RiftReader\tools\RiftReader.GuestObserver\ObserverDelivery.cs`,
  lines 58–80.

V1 HEAD observed during the continuation:
`099ddf8bf62d3076e3f9712fd243d86cf79e86c9`, with a clean working tree.
Ignored evidence remains outside that commit. These observations describe the
reviewed state; external files can change independently.
