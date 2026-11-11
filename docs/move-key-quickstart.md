# RR2 movement CLI (disposable C# helper)

This manual, one-shot helper sends a bounded Windows scan-code hold through RR2's C# input engine. No VMware, addon chat-focus synchronization, PowerShell input, or legacy RiftReader runtime.

Run **on the PC actually hosting physical RIFT** from `C:\work\riftreader2`. Initial build and checks were verified on **AMD-DESKTOP only**.

```powershell
# Find the physical game PID. Never copy a stale PID.
Get-Process rift_x64 | Select-Object Id, ProcessName, StartTime

# Preview; does not focus RIFT or send game input.
dotnet run --project .\src\RiftReader2.Live\RiftReader2.Live.csproj --no-restore -- move-key --pid 12345 --key w --hold-ms 1000 --json

# Supervised one-second W pulse: replace 12345 with the actual PID.
dotnet run --project .\src\RiftReader2.Live\RiftReader2.Live.csproj --no-restore -- move-key --pid 12345 --key w --hold-ms 1000 --execute --json

# One pulse with native C# before/after XYZ (exact known RIFT build only):
dotnet run --project .\src\RiftReader2.Live\RiftReader2.Live.csproj --no-restore -- move-key --pid 12345 --key w --hold-ms 1000 --execute --measure-xyz --json

# Any single key a/s/d/q/e; also combines compatible keys:
dotnet run --project .\src\RiftReader2.Live\RiftReader2.Live.csproj --no-restore -- move-key --pid 12345 --key w,e --hold-ms 1200 --execute --json
```

- `--execute` is mandatory to emit input. Without it, only preview output.
- Default hold **1000 ms**; accepted **20–3000 ms**.
- Supports `w,a,s,d,q,e`, including compatible simultaneous combinations. Conflicting `w,s`, `a,d`, `q,e` are refused.
- Exact `--pid` is mandatory. Optional `--expect-start-ticks` and `--expect-sha256` lock it to previously observed identity.
- With `--execute`, the helper **focuses the selected RIFT game window by default**. It tries normal Windows activation, then RiftReader's proven C# `AttachThreadInput` foreground assist if needed; it verifies the exact window again before input. The assist restores only a minimized window (never unmaximizes a visible game). If Windows still denies focus, **no input is sent**; foreground RIFT manually and retry. Use `--no-focus` to manage focus yourself; `--focus` remains accepted. This is game-window focus, **not** addon chat focus. Preview without `--execute` never changes focus.
- The helper uses the same RR2 control-agent semaphore, checks the target epoch/build/window, monitors foreground while holding, and always attempts key-up on normal completion or cancellation.
- This **direct operator CLI** does not use the screenshot approval journal of `scripts/physical_one_pulse_runner.py`. That existing runner remains the supervised capture-bound/recovery option.
- `--measure-xyz` optionally reads the exact-build native player XYZ before and after this single pulse. The first read must succeed or **no input is sent**; a failed second read is reported without repeating input. It reuses the existing C# native memory reader and lease; no addon, PowerShell movement, extra report file, or additional service.
- `xyzFeedback.planarDisplacementCandidate` is distance in X/Z; `movementCandidate` is true at 0.03+ units with the same owner and a valid capture gap. Cached native XYZ may be stale; the reading is **not independent proof the game consumed input**.
- "Input inserted" is **not proof the character moved**. Use candidate XYZ alongside observed gameplay movement, especially when the cached position does not refresh.

Offline checks (never send game input):

```powershell
dotnet test .\tests\RiftReader2.Live.Tests\RiftReader2.Live.Tests.csproj --no-restore --filter FullyQualifiedName~MoveKeyCommandTests
C:\Python314\python.exe -m unittest discover -s tests -p test_physical_one_pulse_runner.py
```
