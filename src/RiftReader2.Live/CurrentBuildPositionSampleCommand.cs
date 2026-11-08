using System.Buffers.Binary;
using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

/// <summary>
/// Exact-build, read-only, source-epoch-bound native XYZ candidate sampling.
/// No Lua binding, game actions, saved absolute addresses, or field promotion.
/// </summary>
internal static class CurrentBuildPositionSampleCommand
{
    internal const string GameSha256 = CurrentBuildPlayerLookup.GameSha256;
    private static readonly JsonSerializerOptions LineOptions = new(JsonFormat.Options) { WriteIndented = false };

    internal static async Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options, TextWriter output,
        CancellationToken cancellationToken)
    {
        if (!options.TryGetValue("--pid", out var rawPid) ||
            !int.TryParse(rawPid, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var rawTicks) ||
            !long.TryParse(rawTicks, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 ||
            !options.TryGetValue("--output", out var path))
            throw new ArgumentException("--pid, --start-ticks and --output are required for the current-build candidate sampler.");
        var samples = BoundedInt(options, "--samples", 3, 1, 30);
        var interval = BoundedInt(options, "--interval-ms", 500, 0, 2000);
        if ((long)(samples - 1) * interval > 60_000)
            throw new ArgumentException("Sampling delays exceed 60 seconds.");
        if (File.Exists(path))
            throw new IOException("Native candidate output exists; never overwrite an earlier observation.");

        await using var session = await WindowsNativeMemorySession.OpenAsync(
            pid, ticks, GameSha256, cancellationToken);
        var readings = new List<CurrentBuildPositionObservation>(samples);
        var timer = Stopwatch.StartNew();
        for (var index = 0; index < samples; ++index)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var begin = DateTimeOffset.UtcNow;
            var started = timer.Elapsed.TotalMilliseconds;
            var owned = CurrentBuildPositionCandidateReader.ReadOwned(session);
            var xyz = owned.Position;
            var invalidated = await session.RevalidateAsync(cancellationToken);
            if (invalidated is not null)
                throw new InvalidDataException("Native candidate process identity was invalidated; no completed report was published.");
            var reading = new CurrentBuildPositionObservation(
                index + 1, begin.ToString("O"), DateTimeOffset.UtcNow.ToString("O"),
                started, timer.Elapsed.TotalMilliseconds,
                xyz.X, xyz.Y, xyz.Z)
            {
                UnitKey = owned.UnitKeyText,
                UnitIdCandidate = owned.UnitIdCandidate,
                OwnerIdentityStatus = "player-component-chain-anchored"
            };
            readings.Add(reading);
            await output.WriteLineAsync(JsonSerializer.Serialize(new
            {
                recordType = "native-current-position-candidate/1",
                qualification = "candidate-only-not-passive-fresh-or-player-semantic-qualified",
                observation = reading
            }, LineOptions));
            if (index + 1 < samples)
                await Task.Delay(interval, cancellationToken);
        }

        var report = new
        {
            schemaVersion = 1,
            contractVersion = "native-current-position-candidate-samples/1",
            qualification = "candidate-only-not-passive-fresh-or-player-semantic-qualified",
            sourceBuildSha256 = GameSha256,
            session.Identity,
            requestedSamples = samples,
            completedSamples = readings.Count,
            status = "complete",
            observations = readings,
            limitations = new[]
            {
                "The exact executable and process epoch are pinned; loaded game module bytes are not independently hashed.",
                "Each sample re-resolves the current-build manager/player/component chain; absolute addresses are never persisted.",
                "Within-sample ownership and XYZ reads are bracketed, but sequential reads are not atomic and ABA cannot be excluded.",
                "Per-observation unit identity comes from the same anchored lookup; equal sampled keys do not prove uninterrupted owner continuity.",
                "The cached XYZ component has not been independently proven to be passively refreshed player position.",
                "Separate same-unit API and changed-state evidence is required before navigation or freshness qualification.",
                "Sampling intervals include overhead; they are not a promised polling rate."
            }
        };
        await JsonReportWriter.WriteNewAsync(path, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(new
        {
            recordType = "native-current-position-candidate-summary/1",
            report.status,
            report.qualification,
            report.completedSamples,
            output = Path.GetFullPath(path)
        }, LineOptions));
        return 0;
    }

    private static int BoundedInt(IReadOnlyDictionary<string, string> options, string key,
        int fallback, int minimum, int maximum)
    {
        if (!options.TryGetValue(key, out var value))
            return fallback;
        if (!int.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out var parsed) ||
            parsed < minimum || parsed > maximum)
            throw new ArgumentException($"{key} must be in {minimum}..{maximum}.");
        return parsed;
    }
}

internal sealed record CurrentBuildPositionObservation(
    int Index,
    string StartedAtUtc,
    string CompletedAtUtc,
    double MonotonicStartMilliseconds,
    double MonotonicEndMilliseconds,
    float X,
    float Y,
    float Z)
{
    public string? UnitKey { get; init; }
    public string? UnitIdCandidate { get; init; }
    public string OwnerIdentityStatus { get; init; } = "unavailable";
}

internal sealed record CurrentBuildXyz(float X, float Y, float Z);

internal sealed record CurrentBuildOwnedPosition(ulong UnitKey, CurrentBuildXyz Position)
{
    public string UnitKeyText => UnitKey.ToString(CultureInfo.InvariantCulture);
    public string UnitIdCandidate => $"u{UnitKey:X16}";
}

internal sealed record CurrentBuildPositionOwnerSnapshot(ulong UnitKey, ulong ComponentAddress, Action VerifyUnchanged);

/// <summary>
/// Mirrors only the source-verified manager-to-entity-to-position lookup
/// from scripts/probe_native_unit_manager.py. It does not guess unknown roots.
/// </summary>
internal static class CurrentBuildPositionCandidateReader
{
    private const ulong PositionIndexRva = 0x2F588A0;

    internal static CurrentBuildXyz Read(IReadOnlyNativeMemorySession session) =>
        ReadOwned(session).Position;

    internal static CurrentBuildXyz Read(IReadOnlyNativeMemorySession session,
        Func<IReadOnlyNativeMemorySession, CurrentBuildPositionOwnerSnapshot> resolveOwner) =>
        ReadOwned(session, resolveOwner).Position;

    internal static CurrentBuildOwnedPosition ReadOwned(IReadOnlyNativeMemorySession session) =>
        ReadOwned(session, source =>
        {
            var owner = CurrentBuildPlayerLookup.Resolve(source);
            return new(owner.PlayerKey, owner.ResolveComponent(PositionIndexRva), owner.VerifyUnchanged);
        });

    internal static CurrentBuildOwnedPosition ReadOwned(IReadOnlyNativeMemorySession session,
        Func<IReadOnlyNativeMemorySession, CurrentBuildPositionOwnerSnapshot> resolveOwner)
    {
        ArgumentNullException.ThrowIfNull(session);
        ArgumentNullException.ThrowIfNull(resolveOwner);
        var identity = session.Identity;
        if (!string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase)
            || identity.ProcessId <= 0 || identity.ProcessStartUtcTicks <= 0 || identity.ModuleSize < PositionIndexRva + 4)
            throw new InvalidDataException("Current-build position requires exact build and process epoch.");
        var owner = resolveOwner(session);
        ArgumentNullException.ThrowIfNull(owner.VerifyUnchanged);
        if (owner.UnitKey == 0) throw new InvalidDataException("Missing position owner.");
        var component = CurrentBuildPlayerLookup.Pointer(owner.ComponentAddress, 0x110);
        var valueRaw = CurrentBuildPlayerLookup.Exact(session, component, 0x110);
        var xyzBytes = valueRaw.AsSpan(0x48, 12).ToArray();

        owner.VerifyUnchanged();
        if (session.Identity != identity) throw new InvalidDataException("Position process identity changed.");
        CurrentBuildPlayerLookup.RequireSame(
            CurrentBuildPlayerLookup.Exact(session, checked(component + 0x48), 12), xyzBytes);
        if (session.Identity != identity) throw new InvalidDataException("Position process identity changed.");

        var x = BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32LittleEndian(xyzBytes.AsSpan(0, 4)));
        var y = BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32LittleEndian(xyzBytes.AsSpan(4, 4)));
        var z = BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32LittleEndian(xyzBytes.AsSpan(8, 4)));
        if (!float.IsFinite(x) || !float.IsFinite(y) || !float.IsFinite(z))
            throw new InvalidDataException("Native position component is nonfinite.");
        return new(owner.UnitKey, new(x, y, z));
    }

    internal static ulong BucketIndex(ulong key, ulong count) =>
        CurrentBuildPlayerLookup.BucketIndex(key, count);
}
