# Synthetic capture

These five observations are authored test data, not RIFT measurements. The build
hash identifies the text `riftreader2-synthetic-demo-v1`, not a game executable.
Its declared source kind is `synthetic`, position units are `synthetic-units`,
the horizontal plane is XZ, and timing uncertainty is unknown (null).
The two contiguous 0.1-second intervals yield horizontal speed 5 units/second
and absolute yaw rate 1 radian/second. Sequence 3 is missing; the last interval
is 0.4 seconds. Both gap intervals must be counted and excluded from derivatives
with the default 0.25-second limit. Expected: 5 samples, 1 missing sequence,
1 sequence gap, 1 timing gap, 2 derived intervals and 2 skipped intervals.

`capture.json` binds the exact bytes of `samples.jsonl`. Keep LF line endings
when editing this fixture and regenerate its SHA-256 deliberately. A fixture
change must update tests/expected results when semantics change.
