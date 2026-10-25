# Fast known-build player-position sampling

The existing native pointer resolver can already read player-position-like XYZ bytes. This command provides a small **operational candidate feed** without repeating a heap scan or waiting for a full semantic qualification pipeline. It does not replace the independent evidence reviewer.

## Run only where RIFT is running

On the Windows guest (or another Windows x64 machine with exactly one `rift_x64.exe` process), use the **newly built** `RiftReader2.Live.exe`. Copy the profile with the binary using the existing reviewed guest-transfer workflow; do not assume a host-side executable can read the VM's memory.

```powershell
.\RiftReader2.Live.exe sample-position --profile .\position-candidate-profile.json --samples 3 --interval-ms 500 --output .\position-samples-new.json
```

The tracked source profile is `config/position-candidate-profile.json`. It is explicitly pinned to executable SHA-256 `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`, module root RVA `0x32E0200`, and float32 owner offsets `+0x320/+0x324/+0x328`. Those are current-build **candidate** observations from the October 24 proof, not universal RIFT offsets.

The command:

1. Validates a strict, small `native-position-profile/1` file and refuses existing outputs.
2. Discovers exactly one current `rift_x64` PID and opens the existing read-only memory session with the profile's exact executable SHA. No stale PID or absolute heap address is imported.
3. Re-resolves the known module-rooted chain for each requested sample, validates process identity before and after, and decodes finite float32 XYZ.
4. Prints one compact JSON line immediately for each sample (including failure status), followed by a final summary JSON line; saves a never-overwritten `native-position-samples/1` JSON report. Status is `complete`, `partial`, or `failed`; errors never reuse the last good XYZ.

From the second valid sample onward, each JSON line also includes `observation.changeFromPrevious`: float32-derived `deltaX/deltaY/deltaZ`, three-dimensional distance in game units, and monotonic milliseconds between sample starts. The saved summary includes `motion`: first-to-last displacement, maximum excursion from the first reading, largest consecutive step, complete sample count, and a fixed **0.1 game-unit** threshold. `native-candidate-change-observed` reports changing candidate bytes only; `no-significant-native-change-observed` does not prove the character stood still, and `insufficient-complete-samples` means fewer than two successful reads. This is an *operational motion hint*, not independent proof of the player field, input causation, or addon agreement.

Defaults are three samples separated by a 500 ms *post-read delay*. Allowed bounds are 1–30 samples and 0–2000 ms delay, with at most 60 seconds of requested delays. The actual cadence may be slower because exact process identity checks include executable hashing. Cancellation publishes no completed report. A completed sample is still marked `candidate-only-not-motion-or-update-qualified`; it is useful for testing and observation, **not** qualified navigation truth.

## Recovery and research separation

- **Known exact build, chain works:** use this short direct path. No broad value scan, typed-prefix scout, or addon-frame search is required just to read the candidate bytes.
- **Chain read fails or returns nonfinite values:** preserve the failed report and troubleshoot the target/profile using `inspect-native`, `follow-pointer`, and saved evidence. Do not substitute a different heap address automatically.
- **Executable SHA changes after a patch:** fail closed. Establish and review a new root/profile through [memory discovery](memory-discovery.md) and [native field evidence](native-field-evidence.md); do not silently carry this profile to another build.
- **Semantic verification:** use the separate [near-time motion reviewer](native-motion-pair-review.md), source clock checks, stimulus receipts and field catalog. Operational sampling does not satisfy those gates.

The command performs **no game input, process writes, debugger attachment, VM control, external delivery or field promotion**. Its compact report includes sample timestamps, native owner address, bytes SHA-256, XYZ and error status, but not the original 816-byte owner buffer. Use the existing `follow-pointer` capture to retain independently reviewable raw bytes.
