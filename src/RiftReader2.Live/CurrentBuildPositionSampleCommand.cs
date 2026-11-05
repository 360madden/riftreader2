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
    internal const string GameSha256 =
        "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8";
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
            var xyz = CurrentBuildPositionCandidateReader.Read(session);
            var invalidated = await session.RevalidateAsync(cancellationToken);
            if (invalidated is not null)
                throw new InvalidDataException("Native candidate process identity was invalidated; no completed report was published.");
            var reading = new CurrentBuildPositionObservation(
                index + 1, begin.ToString("O"), DateTimeOffset.UtcNow.ToString("O"),
                started, timer.Elapsed.TotalMilliseconds,
                xyz.X, xyz.Y, xyz.Z);
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
                "The cached XYZ component has not been independently proven to be passively refreshed player position.",
                "Separate same-unit API and changed-state evidence is required before navigation or freshness qualification.",
                "Sampling intervals include overhead; they are not a promised polling rate."
            }
        };
        await JsonReportWriter.WriteNewAsync(path, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(new
        {
            recordType = "native-current-position-candidate-summary/1",
            report.status, report.qualification, report.completedSamples,
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
    float Z);

internal sealed record CurrentBuildXyz(float X, float Y, float Z);

/// <summary>
/// Mirrors only the source-verified manager-to-entity-to-position lookup
/// from scripts/probe_native_unit_manager.py. It does not guess unknown roots.
/// </summary>
internal static class CurrentBuildPositionCandidateReader
{
    private const ulong ManagerRva = 0x33624A8;
    private const ulong PlayerSystemRva = 0x33623E0;
    private const ulong PositionIndexRva = 0x2F588A0;
    private const ulong MinimumUserAddress = 0x10000;
    private const ulong MaximumUserAddress = 0x7FFF_FFFF_FFFF;

    internal static CurrentBuildXyz Read(IReadOnlyNativeMemorySession session)
    {
        ArgumentNullException.ThrowIfNull(session);
        var identity = session.Identity;
        if (!string.Equals(identity.ExecutableSha256,
                CurrentBuildPositionSampleCommand.GameSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Current-build XYZ candidate requires exact matching executable SHA256.");
        if (identity.ProcessId <= 0 || identity.ProcessStartUtcTicks <= 0 ||
            identity.ModuleBaseAddress < MinimumUserAddress ||
            identity.ModuleSize < ManagerRva + 8)
            throw new InvalidDataException("Invalid current RIFT process/module identity.");

        var module = identity.ModuleBaseAddress;
        var managerRaw = Exact(session, checked(module + ManagerRva), 8);
        var systemRaw = Exact(session, checked(module + PlayerSystemRva), 8);
        var indexRaw = Exact(session, checked(module + PositionIndexRva), 4);
        var manager = Pointer(ReadU64(managerRaw));
        var system = Pointer(ReadU64(systemRaw));
        var positionIndex = BinaryPrimitives.ReadInt32LittleEndian(indexRaw);
        if (positionIndex is < 0 or >= 0x60)
            throw new InvalidDataException("Invalid native position-component selector.");

        var tableRaw = Exact(session, checked(manager + 0x50), 8);
        var keyRaw = Exact(session, checked(system + 0x360), 8);
        var table = Pointer(ReadU64(tableRaw));
        var key = ReadU64(keyRaw);
        if (key == 0)
            throw new InvalidDataException("Player unit key missing.");
        var header = Exact(session, table, 24);
        var buckets = Pointer(ReadU64(header.AsSpan(0, 8)));
        var stride = ReadU64(header.AsSpan(8, 8));
        var count = ReadU64(header.AsSpan(16, 8));
        if (stride is < 24 or > 4096 || stride % 8 != 0 || count is < 1 or > (1 << 24))
            throw new InvalidDataException("Invalid native unit-table layout.");

        var bucket = Pointer(checked(buckets + BucketIndex(key, count) * stride), 24);
        var visited = new HashSet<ulong>();
        var links = new List<(ulong Address, byte[] Bytes)>();
        ulong entity = 0, current = bucket;
        for (var index = 0; index < 8; ++index)
        {
            if (!visited.Add(current))
                throw new InvalidDataException("Native entity bucket chain is cyclic.");
            var bytes = Exact(session, current, 24);
            links.Add((current, bytes));
            var taggedNext = ReadU64(bytes.AsSpan(0, 8));
            var candidateKey = ReadU64(bytes.AsSpan(8, 8));
            if ((index > 0 || (taggedNext & 1) == 0) && candidateKey == key)
            {
                entity = Pointer(ReadU64(bytes.AsSpan(16, 8)), 128);
                break;
            }
            var next = taggedNext & ~1UL;
            if (next == 0)
                throw new InvalidDataException("Player key is absent from the exact native table.");
            current = Pointer(next, 24);
        }
        if (entity == 0)
            throw new InvalidDataException("Native lookup exceeded its eight-node bound.");

        var entityBytes = Exact(session, entity, 128);
        var componentTable = Pointer(ReadU64(entityBytes.AsSpan(0x78, 8)));
        var slot = entityBytes[0x18 + positionIndex];
        if (slot == 0xFF)
            throw new InvalidDataException("Player has no native position component.");
        var componentSlot = Pointer(checked(componentTable + (ulong)slot * 8));
        var componentRaw = Exact(session, componentSlot, 8);
        var component = Pointer(ReadU64(componentRaw), 0x110);
        var valueRaw = Exact(session, component, 0x110);
        var xyzBytes = valueRaw.AsSpan(0x48, 12).ToArray();

        // Read ownership anchors again before accepting this sample. The payload
        // may still be a cached candidate and the reads are not atomic.
        RequireSame(Exact(session, checked(module + ManagerRva), 8), managerRaw);
        RequireSame(Exact(session, checked(module + PlayerSystemRva), 8), systemRaw);
        RequireSame(Exact(session, checked(module + PositionIndexRva), 4), indexRaw);
        RequireSame(Exact(session, checked(manager + 0x50), 8), tableRaw);
        RequireSame(Exact(session, checked(system + 0x360), 8), keyRaw);
        RequireSame(Exact(session, table, 24), header);
        foreach (var link in links)
            RequireSame(Exact(session, link.Address, 24), link.Bytes);
        RequireSame(Exact(session, entity, 128), entityBytes);
        RequireSame(Exact(session, componentSlot, 8), componentRaw);
        RequireSame(Exact(session, checked(component + 0x48), 12), xyzBytes);

        var x = BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32LittleEndian(xyzBytes.AsSpan(0, 4)));
        var y = BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32LittleEndian(xyzBytes.AsSpan(4, 4)));
        var z = BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32LittleEndian(xyzBytes.AsSpan(8, 4)));
        if (!float.IsFinite(x) || !float.IsFinite(y) || !float.IsFinite(z))
            throw new InvalidDataException("Native position component is nonfinite.");
        return new(x, y, z);
    }

    internal static ulong BucketIndex(ulong key, ulong count)
    {
        if (count is < 1 or > (1 << 24))
            throw new ArgumentOutOfRangeException(nameof(count));
        // Signed low32(key), truncating divide, and native 32-bit wrap.
        var low = unchecked((int)(uint)key);
        var quotient = low / 127773;
        var remainder = low - quotient * 127773;
        var signed = unchecked((int)((long)remainder * 16807 - (long)quotient * 2836));
        var adjusted = signed >= 0 ? signed : (long)signed + 2147483647;
        return unchecked((uint)adjusted) % count;
    }

    private static byte[] Exact(IReadOnlyNativeMemorySession source, ulong address, int size)
    {
        if (address < MinimumUserAddress || size is < 1 or > 4096 ||
            address > MaximumUserAddress - (ulong)size)
            throw new InvalidDataException("Native candidate range is outside bounded user memory.");
        var result = source.Read(address, size);
        if (result.Status != "success" || result.Bytes.Length != size)
            throw new InvalidDataException("Native candidate read was incomplete or unavailable.");
        return result.Bytes;
    }

    private static ulong Pointer(ulong value, int length = 8)
    {
        if (value < MinimumUserAddress || value % 8 != 0 ||
            value > MaximumUserAddress - (ulong)length)
            throw new InvalidDataException("Native candidate pointer is invalid.");
        return value;
    }

    private static ulong ReadU64(ReadOnlySpan<byte> bytes) =>
        BinaryPrimitives.ReadUInt64LittleEndian(bytes);

    private static void RequireSame(byte[] now, byte[] earlier)
    {
        if (!now.AsSpan().SequenceEqual(earlier))
            throw new InvalidDataException("Native current-build player ownership or cached XYZ changed during capture.");
    }
}
