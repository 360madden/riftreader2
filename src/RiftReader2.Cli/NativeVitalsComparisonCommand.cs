using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Infrastructure;

namespace RiftReader2.Cli;

/// <summary>Offline comparison of two retained native current-vitals candidate samples.</summary>
internal static class NativeVitalsComparisonCommand
{
    private const int MaxBytes = 2 * 1024 * 1024;
    private const string Contract = "native-current-vitals-candidate-sample/2";
    private const string Qualification = "candidate-only; semantics/passive-freshness/restart-unverified";
    private const string Source = "native-process-memory";

    private sealed record Resource(string Status, long? Current, long? Maximum, string? UnavailableReason);
    private sealed record Snapshot(string Path, string Sha256, string Build, int Pid, long StartTicks,
        ulong PlayerKey, int? ResourceKindCandidate, DateTimeOffset Started, DateTimeOffset Completed,
        Resource Health, Resource Mana, Resource Energy);
    private sealed record Change(string Status, long? BeforeCurrent, long? AfterCurrent,
        long? BeforeMaximum, long? AfterMaximum, long? NetChange,
        decimal? NetChangePerSecondCandidate, string? BeforeUnavailableReason, string? AfterUnavailableReason);

    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct)
    {
        if (!options.TryGetValue("--before", out var beforePath) ||
            !options.TryGetValue("--after", out var afterPath))
            throw new ArgumentException("--before and --after are required.");
        if (Path.GetFullPath(beforePath).Equals(Path.GetFullPath(afterPath), StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Vitals snapshots must be different files.");

        var before = await LoadAsync(beforePath, ct);
        var after = await LoadAsync(afterPath, ct);
        if (before.Build != after.Build || before.PlayerKey != after.PlayerKey)
            throw new InvalidDataException("Native vitals build or player key changed.");
        if (after.Started < before.Completed)
            throw new InvalidDataException("Native vitals observation times overlap or run backward.");
        var span = after.Completed - before.Completed;
        if (span.Ticks <= 0)
            throw new InvalidDataException("Native vitals interval must be positive.");
        var seconds = (decimal)span.Ticks / TimeSpan.TicksPerSecond;
        var health = Compare(before.Health, after.Health, seconds);
        var mana = Compare(before.Mana, after.Mana, seconds);
        var energy = Compare(before.Energy, after.Energy, seconds);
        var sameEpoch = before.Pid == after.Pid && before.StartTicks == after.StartTicks;
        var results = new[] { health, mana, energy };
        var report = new
        {
            schemaVersion = 1,
            contractVersion = "native-vitals-snapshot-comparison/1",
            status = "candidate-only",
            identity = new { executableSha256 = before.Build, unitKey = before.PlayerKey, sameProcessEpoch = sameEpoch },
            resourceKindCandidates = new
            {
                before = before.ResourceKindCandidate, after = after.ResourceKindCandidate,
                same = before.ResourceKindCandidate.HasValue && after.ResourceKindCandidate.HasValue
                    ? before.ResourceKindCandidate == after.ResourceKindCandidate : (bool?)null
            },
            source = new
            {
                before = new { path = before.Path, sha256 = before.Sha256, processId = before.Pid,
                    processStartUtcTicks = before.StartTicks, startedAtUtc = before.Started,
                    completedAtUtc = before.Completed },
                after = new { path = after.Path, sha256 = after.Sha256, processId = after.Pid,
                    processStartUtcTicks = after.StartTicks, startedAtUtc = after.Started,
                    completedAtUtc = after.Completed }
            },
            intervalSeconds = seconds,
            summary = new
            {
                comparedResources = results.Count(r => r.Status != "unavailable"),
                changedResources = results.Count(r => r.Status == "changed"),
                unavailableResources = results.Count(r => r.Status == "unavailable")
            },
            resources = new { health, mana, energy },
            limitations = new[]
            {
                "Average net change between saved observations is not a regeneration rate or cause of change.",
                "Raw native calculations remain candidates; no live freshness or restart qualification.",
                "Unavailable resource values remain null, never zero. No process or game access occurs."
            }
        };
        if (options.TryGetValue("--output", out var destination))
            await JsonReportWriter.WriteNewAsync(destination, report, ct);
        await output.WriteLineAsync(JsonSerializer.Serialize(report, JsonFormat.Options));
        return 0;
    }

    private static Change Compare(Resource before, Resource after, decimal seconds)
    {
        if (before.Status != "calculated-candidate" || after.Status != "calculated-candidate")
            return new("unavailable", before.Current, after.Current, before.Maximum, after.Maximum,
                null, null, before.UnavailableReason, after.UnavailableReason);
        var net = after.Current!.Value - before.Current!.Value;
        return new(net == 0 ? "unchanged" : "changed", before.Current, after.Current,
            before.Maximum, after.Maximum, net, (decimal)net / seconds, null, null);
    }

    private static async Task<Snapshot> LoadAsync(string path, CancellationToken ct)
    {
        var full = Path.GetFullPath(path);
        if (new FileInfo(full).Length is <= 0 or > MaxBytes)
            throw new InvalidDataException("Native vitals report is empty or too large.");
        var bytes = await File.ReadAllBytesAsync(full, ct);
        if (bytes.Length is <= 0 or > MaxBytes)
            throw new InvalidDataException("Native vitals report is empty or too large.");
        using var json = JsonDocument.Parse(bytes);
        var root = json.RootElement;
        if (Int(root, "schemaVersion") != 1 || Text(root, "contractVersion") != Contract ||
            Text(root, "status") != "complete" || Text(root, "source") != Source ||
            Text(root, "qualification") != Qualification)
            throw new InvalidDataException("Unsupported native vitals report contract.");
        var observation = Property(root, "observation");
        if (Text(observation, "source") != Source || Text(observation, "qualification") != Qualification)
            throw new InvalidDataException("Native vitals observation source differs.");
        var id = Property(observation, "identity");
        var pid = Int(id, "processId");
        var ticks = Long(id, "processStartUtcTicks");
        var build = Text(id, "executableSha256").ToUpperInvariant();
        if (pid <= 0 || ticks <= 0 || build.Length != 64 ||
            build.Any(c => !Uri.IsHexDigit(c)) ||
            Text(root, "sourceBuildSha256").ToUpperInvariant() != build)
            throw new InvalidDataException("Invalid game identity for native vitals.");
        var key = ULong(observation, "unitKey");
        if (key == 0) throw new InvalidDataException("Invalid native vitals player key.");
        int? resourceKind = null;
        if (observation.TryGetProperty("resourceKindCandidate", out var kindValue) &&
            kindValue.ValueKind != JsonValueKind.Null)
        {
            if (kindValue.ValueKind != JsonValueKind.Number || !kindValue.TryGetInt32(out var kind))
                throw new InvalidDataException("Invalid native resource-kind candidate.");
            resourceKind = kind;
        }
        var started = Utc(observation, "startedAtUtc");
        var completed = Utc(observation, "completedAtUtc");
        if (completed < started) throw new InvalidDataException("Native vitals sample interval reversed.");
        var health = ReadResource(observation, "health");
        var mana = ReadResource(observation, "mana");
        var energy = ReadResource(observation, "energy");
        if (mana.Status == "calculated-candidate" && energy.Status == "calculated-candidate")
            throw new InvalidDataException("Contradictory simultaneous Mana and Energy kinds.");
        if (resourceKind is int kindCandidate &&
            ((mana.Status == "calculated-candidate" && kindCandidate != 3) ||
             (energy.Status == "calculated-candidate" && kindCandidate != 4)))
            throw new InvalidDataException("Native vitals resource kind contradicts typed Mana/Energy data.");
        return new(full, Convert.ToHexString(SHA256.HashData(bytes)), build, pid, ticks,
            key, resourceKind, started, completed, health, mana, energy);
    }

    private static Resource ReadResource(JsonElement observation, string name)
    {
        var field = Property(observation, name);
        var status = Text(field, "status");
        var current = Property(field, "current");
        var maximum = Property(field, "maximum");
        var unavailableReason = Property(field, "unavailableReason");
        var inputs = Property(field, "inputs");
        if (status == "unavailable" && current.ValueKind == JsonValueKind.Null &&
            maximum.ValueKind == JsonValueKind.Null &&
            (inputs.ValueKind is JsonValueKind.Null or JsonValueKind.Object) &&
            unavailableReason.ValueKind == JsonValueKind.String &&
            !string.IsNullOrWhiteSpace(unavailableReason.GetString()))
            return new(status, null, null, unavailableReason.GetString());
        if (status != "calculated-candidate" || unavailableReason.ValueKind != JsonValueKind.Null ||
            inputs.ValueKind != JsonValueKind.Object ||
            current.ValueKind != JsonValueKind.Number || !current.TryGetInt64(out var value) ||
            maximum.ValueKind != JsonValueKind.Number || !maximum.TryGetInt64(out var max) ||
            max <= 0 || value < 0 || value > max)
            throw new InvalidDataException($"Invalid native {name} candidate.");
        if (name is "mana" or "energy")
        {
            var type = Text(inputs, "verifiedTypeCode");
            if (type != (name == "mana" ? "0x072A" : "0x072B"))
                throw new InvalidDataException($"Native {name} type fingerprint differs.");
        }
        return new(status, value, max, null);
    }

    private static JsonElement Property(JsonElement item, string name) =>
        item.ValueKind == JsonValueKind.Object && item.TryGetProperty(name, out var value)
            ? value : throw new InvalidDataException($"Missing native vitals field: {name}.");
    private static string Text(JsonElement item, string name)
    {
        var value = Property(item, name);
        return value.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(value.GetString())
            ? value.GetString()! : throw new InvalidDataException($"Invalid text field: {name}.");
    }
    private static int Int(JsonElement item, string name)
    {
        var value = Property(item, name);
        return value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out var number)
            ? number : throw new InvalidDataException($"Invalid integer field: {name}.");
    }
    private static long Long(JsonElement item, string name)
    {
        var value = Property(item, name);
        return value.ValueKind == JsonValueKind.Number && value.TryGetInt64(out var number)
            ? number : throw new InvalidDataException($"Invalid long field: {name}.");
    }
    private static ulong ULong(JsonElement item, string name)
    {
        var value = Property(item, name);
        return value.ValueKind == JsonValueKind.Number && value.TryGetUInt64(out var number)
            ? number : throw new InvalidDataException($"Invalid unit key: {name}.");
    }
    private static DateTimeOffset Utc(JsonElement item, string name)
    {
        if (!DateTimeOffset.TryParse(Text(item, name), CultureInfo.InvariantCulture,
                DateTimeStyles.None, out var time) || time.Offset != TimeSpan.Zero)
            throw new InvalidDataException($"Invalid UTC sample field: {name}.");
        return time;
    }
}
