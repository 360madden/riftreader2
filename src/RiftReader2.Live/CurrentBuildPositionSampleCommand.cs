using System.Buffers.Binary;
using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;
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

    internal static Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options, TextWriter output,
        CancellationToken cancellationToken) =>
        RunAsync(options, output, cancellationToken,
            static async (pid, ticks, token) => await NativeReadFileLease.AcquireAsync(
                pid, ticks, GameSha256, TimeSpan.FromSeconds(1), token),
            static async (pid, ticks, token) => await WindowsNativeMemorySession.OpenAsync(
                pid, ticks, GameSha256, token),
            CurrentBuildPositionCandidateReader.ReadOwned);

    // Explicit offline-only seam: production entry always supplies the real lease.
    internal static async Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options, TextWriter output, CancellationToken cancellationToken,
        Func<int, long, CancellationToken, Task<IAsyncDisposable>> acquireLease,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession, CurrentBuildOwnedPosition> read)
    {
        ArgumentNullException.ThrowIfNull(acquireLease);
        ArgumentNullException.ThrowIfNull(open);
        ArgumentNullException.ThrowIfNull(read);
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

        await using var lease = await acquireLease(pid, ticks, cancellationToken);
        cancellationToken.ThrowIfCancellationRequested();
        await using var session = await open(pid, ticks, cancellationToken);
        var readings = new List<CurrentBuildPositionObservation>(samples);
        ulong? burstPlayerKey = null;
        var timer = Stopwatch.StartNew();
        for (var index = 0; index < samples; ++index)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var begin = DateTimeOffset.UtcNow;
            var started = timer.Elapsed.TotalMilliseconds;
            var owned = read(session);
            var xyz = owned.Position;
            var invalidated = await session.RevalidateAsync(cancellationToken);
            if (invalidated is not null)
                throw new InvalidDataException("Native candidate process identity was invalidated; no completed report was published.");
            if (burstPlayerKey is ulong pinnedKey && pinnedKey != owned.UnitKey)
                throw new InvalidDataException("Native position owner changed during sampling; no completed report was published.");
            burstPlayerKey = owned.UnitKey;
            var reading = new CurrentBuildPositionObservation(
                index + 1, begin.ToString("O"), DateTimeOffset.UtcNow.ToString("O"),
                started, timer.Elapsed.TotalMilliseconds,
                xyz.X, xyz.Y, xyz.Z)
            {
                UnitKey = owned.UnitKeyText,
                UnitIdCandidate = owned.UnitIdCandidate,
                OwnerIdentityStatus = "player-component-chain-anchored",
                RefreshHandleHex = owned.RefreshHandleHex,
                RefreshFlagRaw = owned.RefreshFlagRaw,
                RefreshGuardStatus = owned.RefreshGuardStatus
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
                "Within-sample ownership, exact-build position dispatch pointer and XYZ reads are bracketed, but sequential reads are not atomic and ABA cannot be excluded.",
                "Per-observation unit identity comes from the same anchored lookup; equal sampled keys do not prove uninterrupted owner continuity.",
                "The cached XYZ component has not been independently proven to be passively refreshed player position.",
                "Optional +0x100/+0x108 refresh guard bytes come from the same 0x110-byte component read as XYZ; they are not separately reread and do not prove native writer execution.",
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
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? RefreshHandleHex { get; init; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public byte? RefreshFlagRaw { get; init; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? RefreshGuardStatus { get; init; }
}

internal sealed record CurrentBuildXyz(float X, float Y, float Z);

internal sealed record CurrentBuildOwnedPosition(ulong UnitKey, CurrentBuildXyz Position)
{
    public string UnitKeyText => UnitKey.ToString(CultureInfo.InvariantCulture);
    public string UnitIdCandidate => $"u{UnitKey:X16}";
    public string? RefreshHandleHex { get; init; }
    public byte? RefreshFlagRaw { get; init; }
    public string? RefreshGuardStatus { get; init; }
    // The component's cached secondary XYZ at +0x88, not proven current world position.
    public CurrentBuildXyz? SecondaryPositionCandidate { get; init; }
}

internal sealed record CurrentBuildPositionOwnerSnapshot(ulong UnitKey, ulong EntityAddress, ulong ComponentAddress, Action VerifyUnchanged);

/// <summary>
/// Mirrors only the source-verified manager-to-entity-to-position lookup
/// from scripts/probe_native_unit_manager.py. It does not guess unknown roots.
/// </summary>
internal static class CurrentBuildPositionCandidateReader
{
    internal const ulong PositionIndexRva = 0x2F588A0;
    // Historical exact-build position components: 49/49 headers matched this RVA.
    private const ulong PositionComponentVptrRva = 0x26B4FB0;

    internal static CurrentBuildXyz Read(IReadOnlyNativeMemorySession session) =>
        ReadOwned(session).Position;

    internal static CurrentBuildXyz Read(IReadOnlyNativeMemorySession session,
        Func<IReadOnlyNativeMemorySession, CurrentBuildPositionOwnerSnapshot> resolveOwner) =>
        ReadOwned(session, resolveOwner).Position;

    internal static CurrentBuildOwnedPosition ReadOwned(IReadOnlyNativeMemorySession session) =>
        ReadOwned(session, source =>
        {
            var owner = CurrentBuildPlayerLookup.Resolve(source);
            return new(owner.PlayerKey, owner.EntityAddress, owner.ResolveComponent(PositionIndexRva), owner.VerifyUnchanged);
        });

    internal static CurrentBuildOwnedPosition ReadOwned(IReadOnlyNativeMemorySession session,
        Func<IReadOnlyNativeMemorySession, CurrentBuildPositionOwnerSnapshot> resolveOwner,
        PosePayloadCheck? check = null)
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
        var entity = CurrentBuildPlayerLookup.Pointer(owner.EntityAddress);
        var component = CurrentBuildPlayerLookup.Pointer(owner.ComponentAddress, 0x110);
        var valueRaw = CurrentBuildPlayerLookup.Exact(session, component, 0x110);
        var expectedVptr = checked(identity.ModuleBaseAddress + PositionComponentVptrRva);
        if (BinaryPrimitives.ReadUInt64LittleEndian(valueRaw.AsSpan(0, 8)) != expectedVptr)
            throw new InvalidDataException("Position component dispatch pointer differs from exact-build position type.");
        if (BinaryPrimitives.ReadUInt64LittleEndian(valueRaw.AsSpan(0x10, 8)) != entity)
            throw new InvalidDataException("Position component entity backlink differs.");
        var xyzBytes = valueRaw.AsSpan(0x48, 12).ToArray();
        // These guards are co-sampled from the EXISTING full component read;
        // no native getter or additional process read is needed.
        var refreshHandle = BinaryPrimitives.ReadUInt64LittleEndian(valueRaw.AsSpan(0x100, 8));
        var refreshFlag = valueRaw[0x108];

        owner.VerifyUnchanged();
        if (session.Identity != identity) throw new InvalidDataException("Position process identity changed.");
        CurrentBuildPlayerLookup.RequireSame(
            CurrentBuildPlayerLookup.Exact(session, component, 8), valueRaw.AsSpan(0, 8).ToArray());
        PosePayloadCheck.Verify(
            CurrentBuildPlayerLookup.Exact(session, checked(component + 0x48), 12), xyzBytes, "entity XYZ", check);
        CurrentBuildPlayerLookup.RequireSame(
            CurrentBuildPlayerLookup.Exact(session, checked(component + 0x10), 8),
            valueRaw.AsSpan(0x10, 8).ToArray());
        owner.VerifyUnchanged();
        if (session.Identity != identity) throw new InvalidDataException("Position process identity changed.");

        var x = BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32LittleEndian(xyzBytes.AsSpan(0, 4)));
        var y = BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32LittleEndian(xyzBytes.AsSpan(4, 4)));
        var z = BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32LittleEndian(xyzBytes.AsSpan(8, 4)));
        if (!float.IsFinite(x) || !float.IsFinite(y) || !float.IsFinite(z))
            throw new InvalidDataException("Native position component is nonfinite.");
        // +0x88 is already inside the 0x110-byte owner-checked component read.
        // Keep it optional so a bad secondary buffer cannot invalidate primary XYZ.
        var sx = BinaryPrimitives.ReadSingleLittleEndian(valueRaw.AsSpan(0x88, 4));
        var sy = BinaryPrimitives.ReadSingleLittleEndian(valueRaw.AsSpan(0x8C, 4));
        var sz = BinaryPrimitives.ReadSingleLittleEndian(valueRaw.AsSpan(0x90, 4));
        var secondary = float.IsFinite(sx) && float.IsFinite(sy) && float.IsFinite(sz)
            ? new CurrentBuildXyz(sx, sy, sz) : null;
        return new(owner.UnitKey, new(x, y, z))
        {
            SecondaryPositionCandidate = secondary,
            RefreshHandleHex = $"0x{refreshHandle:X16}",
            RefreshFlagRaw = refreshFlag,
            RefreshGuardStatus = refreshHandle != 0 ? "handle-present-guard-candidate"
                : refreshFlag != 0 ? "alternate-flag-guard-candidate" : "guard-ineligible-candidate"
        };
    }

    internal static ulong BucketIndex(ulong key, ulong count) =>
        CurrentBuildPlayerLookup.BucketIndex(key, count);
}
