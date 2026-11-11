using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Infrastructure;

namespace RiftReader2.Cli;

/// <summary>Compare retained native candidate stat reports. Never opens a game process.</summary>
internal static class NativeStatsComparisonCommand
{
    private const int MaxReportBytes = 2 * 1024 * 1024;
    private static readonly (string Name, int Selector)[] Expected =
    [
        ("armor", 37), ("powerAttack", 24), ("powerSpell", 32), ("critAttack", 26),
        ("critSpell", 33), ("strength", 5), ("dexterity", 1), ("intelligence", 3),
        ("wisdom", 4), ("endurance", 2), ("resistLife", 35), ("resistDeath", 36),
        ("resistFire", 38), ("resistWater", 39), ("resistEarth", 40), ("resistAir", 41),
        ("hit", 31), ("critPower", 83), ("block", 27), ("dodge", 30)
    ];

    private sealed record Value(string Status, long? Raw);
    private sealed record Row(string Name, int Selector, int Index, Value Ordinary, Value Unbuffed);
    private sealed record Snapshot(string Path, string Sha256, string Build, int Pid, long StartTicks,
        ulong PlayerKey, DateTimeOffset Started, DateTimeOffset Completed, IReadOnlyList<Row> Rows, OwnerPath? OwnerPath);
    private sealed record OwnerPath(ulong Entity, ulong Health, ulong Owner, ulong Record, ulong Mapping);
    private sealed record Difference(string Status, long? Before, long? After, decimal? Delta);
    private sealed record Spread(string Status, decimal? Before, decimal? After, decimal? Delta);

    internal static async Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options, TextWriter output, CancellationToken cancellationToken)
    {
        if (!options.TryGetValue("--before", out var beforePath) ||
            !options.TryGetValue("--after", out var afterPath))
            throw new ArgumentException("--before and --after are required.");
        if (Path.GetFullPath(beforePath).Equals(Path.GetFullPath(afterPath), StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Before and after must be distinct saved reports.");

        var before = await LoadAsync(beforePath, cancellationToken);
        var after = await LoadAsync(afterPath, cancellationToken);
        if (before.Build != after.Build || before.PlayerKey != after.PlayerKey)
            throw new InvalidDataException("Saved stats must have matching game build and player key.");
        if (before.Rows.Count != after.Rows.Count || after.Started <= before.Started ||
            after.Started < before.Completed)
            throw new InvalidDataException("Saved stats need matching selectors in nonoverlapping chronological order.");

        var sameEpoch = before.Pid == after.Pid && before.StartTicks == after.StartTicks;
        var stats = before.Rows.Select((oldRow, i) =>
        {
            var newRow = after.Rows[i];
            if (oldRow.Name != newRow.Name || oldRow.Selector != newRow.Selector)
                throw new InvalidDataException("Native stat selectors differ.");
            return new
            {
                name = oldRow.Name,
                selector = oldRow.Selector,
                beforeMappedIndex = oldRow.Index,
                afterMappedIndex = newRow.Index,
                mappedIndexChanged = oldRow.Index != newRow.Index,
                ordinary = Compare(oldRow.Ordinary, newRow.Ordinary),
                unbuffed = Compare(oldRow.Unbuffed, newRow.Unbuffed),
                ordinaryMinusUnbuffed = CompareSpread(oldRow, newRow)
            };
        }).ToArray();

        var beforeOwnerPath = before.OwnerPath;
        var afterOwnerPath = after.OwnerPath;
        var comparableOwnerPath = sameEpoch && beforeOwnerPath is not null && afterOwnerPath is not null;
        var matchingAnchors = comparableOwnerPath ? new
        {
            entity = beforeOwnerPath!.Entity == afterOwnerPath!.Entity,
            health = beforeOwnerPath.Health == afterOwnerPath.Health,
            owner = beforeOwnerPath.Owner == afterOwnerPath.Owner,
            record = beforeOwnerPath.Record == afterOwnerPath.Record,
            mapping = beforeOwnerPath.Mapping == afterOwnerPath.Mapping
        } : null;

        var report = new
        {
            schemaVersion = 1,
            contractVersion = "native-stats-snapshot-comparison/1",
            status = "candidate-only",
            identity = new { executableSha256 = before.Build, unitKey = before.PlayerKey, sameProcessEpoch = sameEpoch },
            source = new
            {
                before = new { path = before.Path, sha256 = before.Sha256, processId = before.Pid,
                    processStartUtcTicks = before.StartTicks, startedAtUtc = before.Started, completedAtUtc = before.Completed },
                after = new { path = after.Path, sha256 = after.Sha256, processId = after.Pid,
                    processStartUtcTicks = after.StartTicks, startedAtUtc = after.Started, completedAtUtc = after.Completed }
            },
            ownerPathComparison = new
            {
                status = beforeOwnerPath is null || afterOwnerPath is null ? "unavailable" :
                    sameEpoch ? "same-process-epoch" : "cross-epoch-unqualified",
                before = beforeOwnerPath, after = afterOwnerPath,
                sameAddresses = comparableOwnerPath ? beforeOwnerPath == afterOwnerPath : (bool?)null,
                matchingAnchors
            },
            summary = new
            {
                comparedSelectors = stats.Length,
                changedMappings = stats.Count(s => s.mappedIndexChanged),
                changedSelectors = stats.Count(s => s.ordinary.Status == "changed" || s.unbuffed.Status == "changed"),
                changedValues = stats.Sum(s => (s.ordinary.Status == "changed" ? 1 : 0) +
                                                (s.unbuffed.Status == "changed" ? 1 : 0)),
                changedSpreads = stats.Count(s => s.ordinaryMinusUnbuffed.Status == "changed"),
                unavailablePairs = stats.Sum(s => (s.ordinary.Status == "unavailable" ? 1 : 0) +
                                                   (s.unbuffed.Status == "unavailable" ? 1 : 0))
            },
            stats,
            limitations = new[]
            {
                "Saved raw numeric candidates; a delta does not prove stat semantics, cause, or live freshness.",
                "Selector-index remapping is reported independently of raw-value changes.",
                "Same-epoch owner pointer equality is address stability, not semantic or freshness qualification.",
                "Cross-epoch comparisons are historical and do not establish restart recovery.",
                "Unavailable values remain null, never zero. No process access or game input occurs."
            }
        };
        if (options.TryGetValue("--output", out var path))
            await JsonReportWriter.WriteNewAsync(path, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(report, JsonFormat.Options));
        return 0;
    }

    private static Difference Compare(Value before, Value after)
    {
        if (before.Status != "raw-candidate" || after.Status != "raw-candidate")
            return new("unavailable", before.Raw, after.Raw, null);
        return new(before.Raw == after.Raw ? "unchanged" : "changed", before.Raw, after.Raw,
            (decimal)after.Raw!.Value - before.Raw!.Value);
    }

    private static Spread CompareSpread(Row before, Row after)
    {
        if (before.Ordinary.Raw is null || before.Unbuffed.Raw is null ||
            after.Ordinary.Raw is null || after.Unbuffed.Raw is null)
            return new("unavailable", null, null, null);
        var oldSpread = (decimal)before.Ordinary.Raw.Value - before.Unbuffed.Raw.Value;
        var newSpread = (decimal)after.Ordinary.Raw.Value - after.Unbuffed.Raw.Value;
        return new(oldSpread == newSpread ? "unchanged" : "changed", oldSpread,
            newSpread, newSpread - oldSpread);
    }

    private static async Task<Snapshot> LoadAsync(string path, CancellationToken ct)
    {
        var full = Path.GetFullPath(path);
        if (new FileInfo(full).Length > MaxReportBytes)
            throw new InvalidDataException("Stats report exceeds 2 MiB.");
        var bytes = await File.ReadAllBytesAsync(full, ct);
        if (bytes.Length > MaxReportBytes)
            throw new InvalidDataException("Stats report exceeds 2 MiB.");
        using var document = JsonDocument.Parse(bytes);
        var root = document.RootElement;
        if (Int(root, "schemaVersion") != 1 ||
            Text(root, "contractVersion") != "native-current-stats-candidate/1" ||
            Text(root, "status") != "complete")
            throw new InvalidDataException("Unsupported or incomplete native stats report.");

        var observation = Property(root, "observation");
        var identity = Property(observation, "identity");
        var pid = Int(identity, "processId");
        var ticks = Long(identity, "processStartUtcTicks");
        var build = Text(identity, "executableSha256").ToUpperInvariant();
        if (pid <= 0 || ticks <= 0 || build.Length != 64 || build.Any(c => !Uri.IsHexDigit(c)))
            throw new InvalidDataException("Invalid saved native stats identity.");
        var playerKey = ULong(observation, "unitKey");
        if (playerKey == 0)
            throw new InvalidDataException("Missing self player key.");
        var started = Utc(observation, "startedAtUtc");
        var completed = Utc(observation, "completedAtUtc");
        if (completed < started)
            throw new InvalidDataException("Reversed sample interval.");

        var elements = Property(observation, "stats");
        if (elements.ValueKind != JsonValueKind.Array || elements.GetArrayLength() is not (5 or 20))
            throw new InvalidDataException("Stats report must contain 5 or 20 ordered selectors.");
        var rows = new List<Row>();
        var index = 0;
        foreach (var element in elements.EnumerateArray())
        {
            var expected = Expected[index++];
            var name = Text(element, "name");
            var selector = Int(element, "selector");
            var mappedIndex = Int(element, "mappedIndex");
            if (name != expected.Name || selector != expected.Selector)
                throw new InvalidDataException("Unexpected native stat selector.");
            rows.Add(new(name, selector, mappedIndex,
                ReadValue(element, "ordinary", mappedIndex),
                ReadValue(element, "unbuffed", mappedIndex)));
        }
        return new(full, Convert.ToHexString(SHA256.HashData(bytes)), build, pid, ticks,
            playerKey, started, completed, rows, ReadOwnerPath(observation));
    }

    private static OwnerPath? ReadOwnerPath(JsonElement observation)
    {
        string[] fields = ["entity", "health", "owner", "record", "mapping"];
        var present = fields.Count(name =>
            observation.TryGetProperty(name, out var field) && field.ValueKind != JsonValueKind.Null);
        if (present == 0) return null; // Retained minimal reports have no pointer fields.
        if (present != fields.Length)
            throw new InvalidDataException("Incomplete native owner-chain evidence.");
        var chain = new OwnerPath(ULong(observation, "entity"), ULong(observation, "health"),
            ULong(observation, "owner"), ULong(observation, "record"), ULong(observation, "mapping"));
        if (new[] { chain.Entity, chain.Health, chain.Owner, chain.Record, chain.Mapping }
            .Any(address => address < 0x10000 || address % 8 != 0))
            throw new InvalidDataException("Invalid native owner-chain pointer.");
        return chain;
    }

    private static Value ReadValue(JsonElement row, string kind, int mappedIndex)
    {
        var value = Property(row, kind);
        var status = Text(value, "status");
        var raw = Property(value, "rawSigned64");
        if (status == "index-unavailable" && raw.ValueKind == JsonValueKind.Null)
            return new(status, null);
        if (status == "raw-candidate" && mappedIndex >= 0 &&
            raw.ValueKind == JsonValueKind.Number && raw.TryGetInt64(out var number))
            return new(status, number);
        throw new InvalidDataException("Invalid raw native stat candidate.");
    }

    private static JsonElement Property(JsonElement item, string name) =>
        item.ValueKind == JsonValueKind.Object && item.TryGetProperty(name, out var value)
            ? value : throw new InvalidDataException($"Missing native stats field: {name}.");
    private static string Text(JsonElement item, string name)
    {
        var value = Property(item, name);
        return value.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(value.GetString())
            ? value.GetString()! : throw new InvalidDataException($"Invalid text field: {name}.");
    }
    private static int Int(JsonElement item, string name)
    {
        var value = Property(item, name);
        return value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out var result)
            ? result : throw new InvalidDataException($"Invalid integer field: {name}.");
    }
    private static long Long(JsonElement item, string name)
    {
        var value = Property(item, name);
        return value.ValueKind == JsonValueKind.Number && value.TryGetInt64(out var result)
            ? result : throw new InvalidDataException($"Invalid integer field: {name}.");
    }
    private static ulong ULong(JsonElement item, string name)
    {
        var value = Property(item, name);
        return value.ValueKind == JsonValueKind.Number && value.TryGetUInt64(out var result)
            ? result : throw new InvalidDataException($"Invalid unsigned field: {name}.");
    }
    private static DateTimeOffset Utc(JsonElement item, string name)
    {
        var value = Text(item, name);
        if (!DateTimeOffset.TryParse(value, CultureInfo.InvariantCulture, DateTimeStyles.None, out var parsed) ||
            parsed.Offset != TimeSpan.Zero)
            throw new InvalidDataException($"Invalid UTC field: {name}.");
        return parsed;
    }
}
