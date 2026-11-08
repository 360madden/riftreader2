using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

/// <summary>
/// One source-qualified read of the cached-position refresh branch guards.
/// This does not call a getter or prove the candidate XYZ cache is fresh.
/// </summary>
internal static class CurrentBuildPositionRefreshBranchSampleCommand
{
    internal static Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct) =>
        RunAsync(options, output, ct,
            static async (pid, ticks, token) => await WindowsNativeMemorySession.OpenAsync(
                pid, ticks, CurrentBuildPlayerLookup.GameSha256, token),
            CurrentBuildPositionRefreshBranchCandidateReader.Read,
            static async (pid, ticks, sha, timeout, token) =>
                await NativeReadFileLease.AcquireAsync(pid, ticks, sha, timeout, token));

    // Dependencies are injected for offline lifecycle/publication tests only.
    internal static async Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options, TextWriter output, CancellationToken ct,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession, PositionRefreshBranchCandidate> read,
        Func<int, long, string, TimeSpan, CancellationToken, Task<IAsyncDisposable>> acquireLease)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(output);
        ArgumentNullException.ThrowIfNull(open);
        ArgumentNullException.ThrowIfNull(read);
        ArgumentNullException.ThrowIfNull(acquireLease);
        if (options.Keys.Any(key => key is not ("--pid" or "--start-ticks" or "--output")))
            throw new ArgumentException("Unsupported position-refresh-branch option.");
        if (!options.TryGetValue("--pid", out var rawPid) ||
            !int.TryParse(rawPid, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var rawTicks) ||
            !long.TryParse(rawTicks, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 ||
            !options.TryGetValue("--output", out var requestedPath) || string.IsNullOrWhiteSpace(requestedPath))
            throw new ArgumentException("--pid, --start-ticks and --output are required.");
        var path = Path.GetFullPath(requestedPath);
        if (File.Exists(path) || Directory.Exists(path))
            throw new IOException("Output exists; never overwrite earlier branch evidence.");

        ct.ThrowIfCancellationRequested();
        // The session is disposed before the per-game-epoch native-read lease.
        await using var lease = await acquireLease(pid, ticks, CurrentBuildPlayerLookup.GameSha256,
            TimeSpan.FromSeconds(5), ct) ?? throw new InvalidDataException("Native read lease was unavailable.");
        ct.ThrowIfCancellationRequested();
        await using var session = await open(pid, ticks, ct);
        ct.ThrowIfCancellationRequested();
        var identity = session.Identity;
        if (identity.ProcessId != pid || identity.ProcessStartUtcTicks != ticks ||
            !string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase) ||
            identity.ModuleBaseAddress < 0x10000 || identity.ModuleBaseAddress > 0x7FFFFFFFFFFFUL ||
            identity.ModuleSize < CurrentBuildPositionRefreshBranchCandidateReader.SourceSelectorRva + 4 ||
            identity.ModuleSize > 0x7FFFFFFFFFFFUL - identity.ModuleBaseAddress)
            throw new InvalidDataException("Opened branch diagnostic process/module identity mismatch.");

        var observation = read(session);
        ct.ThrowIfCancellationRequested();
        if (session.Identity != identity || observation.Identity != identity ||
            observation.PlayerKey == 0 || observation.PlayerEntity == 0 || observation.PositionComponent == 0 ||
            observation.StartedAtUtc > observation.CompletedAtUtc)
            throw new InvalidDataException("Refresh-branch diagnostic identity or owner changed.");

        if (await session.RevalidateAsync(ct) is not null || session.Identity != identity)
            throw new InvalidDataException("Process identity invalidated; no branch report published.");
        ct.ThrowIfCancellationRequested();
        static string Hex(ulong raw) => $"0x{raw:X16}";
        var report = new
        {
            schemaVersion = 1,
            contractVersion = "native-current-position-refresh-branch-candidate/1",
            status = "complete",
            qualification = "branch-guards-only; no writer execution, independently fresh XYZ, world position or facing proven",
            processRevalidationStatus = "passed-before-publication",
            sourceBuildSha256 = CurrentBuildPlayerLookup.GameSha256,
            processIdentity = new
            {
                identity.ProcessId,
                processStartUtcTicks = identity.ProcessStartUtcTicks.ToString(CultureInfo.InvariantCulture),
                executableSha256 = identity.ExecutableSha256,
                moduleBaseAddressHex = Hex(identity.ModuleBaseAddress),
                identity.ModuleSize
            },
            observation = new
            {
                observation.StartedAtUtc,
                observation.CompletedAtUtc,
                observation.PlayerKeyDecimal,
                observation.PlayerUnitIdCandidate,
                playerEntityHex = Hex(observation.PlayerEntity),
                positionComponentHex = Hex(observation.PositionComponent),
                referencedHandleHex = observation.ReferencedHandle is ulong handle ? Hex(handle) : null,
                observation.ReferencedHandleDecimal,
                observation.ReferencedEntityHex,
                observation.Flag,
                observation.SourceSelector,
                observation.Status,
                sourceComponentHex = observation.SourceComponent is ulong component ? Hex(component) : null
            },
            limitations = new[]
            {
                "Branch guard eligibility is not proof that native 0x6996C0 executes or writes XYZ.",
                "A missing guard is unavailable, not zero; observed zeros mean guard-ineligible for this observation only.",
                "Self and referenced source slots are candidates, not qualified world-position providers.",
                "The position component holds a cache, not independently qualified passive-fresh player coordinates.",
                "Process, unit key and raw address identities are re-resolved; sequential reads cannot exclude ABA.",
                "Large process ticks, player identity and raw pointer values are encoded as decimal/hex strings without JS precision loss.",
                "The executable SHA pins on-disk bytes; loaded module bytes are not independently hashed.",
                "No RIFT getter, input, reload, injection or memory write occurs."
            }
        };
        await JsonReportWriter.WriteNewAsync(path, report, ct);
        await output.WriteLineAsync(JsonSerializer.Serialize(new
        {
            recordType = "native-current-position-refresh-branch-candidate-summary/1",
            report.status,
            report.qualification,
            branchStatus = observation.Status,
            unitIdCandidate = observation.PlayerUnitIdCandidate,
            output = path
        }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }
}
