using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Cli;

/// <summary>
/// Offline, scope-limited inspection of the typed Lua wire in identity-bound native snapshots.
/// Reads already retained evidence only. This is not a guest reader or field qualification.
/// </summary>
internal static class TypedWireSnapshotCommand
{
    private static readonly byte[] Prefix = "RRAPIVAL2|"u8.ToArray();
    private static readonly byte[] Suffix = "|RRAPIVALEND"u8.ToArray();
    private static readonly UTF8Encoding Utf8 = new(false, true);
    private const int MaxJsonBytes = 8192;
    private const int MaxCandidates = 128;
    private static readonly string[] TopLevelKeys =
    [
        "schemaVersion", "addon", "addonVersion", "source", "sequence", "clock",
        "player", "target", "nativeTextEntryState", "autonomousInputReady"
    ];
    private static readonly IReadOnlyDictionary<string, string> FieldKinds = new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["coordX"] = "number",
        ["coordY"] = "number",
        ["coordZ"] = "number",
        ["health"] = "number",
        ["healthMax"] = "number",
        ["mana"] = "number",
        ["manaMax"] = "number",
        ["combat"] = "boolean",
        ["dead"] = "boolean",
        ["mounted"] = "boolean",
        ["zone"] = "string",
        ["power"] = "number",
        ["combo"] = "number",
        ["planar"] = "number",
        ["planarMax"] = "number"
    };

    internal static async Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options, TextWriter output, CancellationToken cancellationToken)
    {
        if (!options.TryGetValue("--before", out var beforePath) || !options.TryGetValue("--after", out var afterPath))
            throw new ArgumentException("--before and --after are required.");

        options.TryGetValue("--session-id", out var sessionId);
        var historical = options.TryGetValue("--protocol", out var protocol);
        if (historical && protocol != "historical-rrapival2")
            throw new ArgumentException("--protocol must be historical-rrapival2.");
        if ((sessionId is null) == !historical)
            throw new ArgumentException("Specify exactly one of --session-id or --protocol historical-rrapival2.");
        if (sessionId is not null && (sessionId.Length != 32 || sessionId.Any(c => !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')))))
            throw new ArgumentException("--session-id must be 32 lowercase hexadecimal characters.");
        var before = await NativeMemorySnapshotFile.LoadAsync(beforePath, cancellationToken);
        var after = await NativeMemorySnapshotFile.LoadAsync(afterPath, cancellationToken);
        if (before.File.Status == "identity-invalidated" || after.File.Status == "identity-invalidated")
            throw new InvalidDataException("Identity-invalidated snapshots cannot be inspected for typed wire.");
        if (before.File.Identity != after.File.Identity)
            throw new InvalidDataException("Typed-wire comparison requires the exact same process PID, start ticks, and executable identity.");
        if (before.FileSha256 == after.FileSha256)
            throw new InvalidDataException("Typed-wire comparison requires two distinct retained snapshots.");
        var beforeEnd = DateTimeOffset.Parse(before.File.CompletedAtUtc, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal);
        var afterStart = DateTimeOffset.Parse(after.File.StartedAtUtc, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal);
        if (beforeEnd >= afterStart)
            throw new InvalidDataException("Typed-wire comparison requires nonoverlapping chronological capture windows.");

        var first = Scan(before.Snapshot, cancellationToken, sessionId);
        var second = Scan(after.Snapshot, cancellationToken, sessionId);
        var firstSelected = Select(first, out var firstError);
        var secondSelected = Select(second, out var secondError);
        var status = "blocked";
        string reason;
        if (firstError is not null || secondError is not null)
            reason = firstError is not null ? $"before:{firstError}" : $"after:{secondError}";
        else if (firstSelected is null || secondSelected is null)
        {
            status = "unavailable";
            reason = firstSelected is null ? "before:no-complete-usable-frame-in-covered-scope" : "after:no-complete-usable-frame-in-covered-scope";
        }
        else if (firstSelected.Wire!.Epoch != secondSelected.Wire!.Epoch)
            reason = "source-epoch-changed";
        else if (firstSelected.Wire!.PlayerUnitId != secondSelected.Wire!.PlayerUnitId)
            reason = "player-identity-changed";
        else if (secondSelected.Wire.FrameTime <= firstSelected.Wire.FrameTime ||
                 secondSelected.Wire.Sequence <= firstSelected.Wire.Sequence)
            reason = "source-clock-or-sequence-not-advanced";
        else
        {
            status = "advanced-in-covered-scope";
            reason = "two-distinct-captures-with-advancing-typed-sequence-and-clock";
        }

        var report = new
        {
            schemaVersion = 1,
            evidenceKind = "typed-wire-snapshot-inspection/1",
            operation = "inspect-typed-wire",
            status,
            reason,
            identity = before.File.Identity,
            source = new
            {
                before = Input(before, first),
                after = Input(after, second)
            },
            selected = new { before = Selection(firstSelected), after = Selection(secondSelected) },
            advances = status == "advanced-in-covered-scope"
                ? new
                {
                    sequenceDelta = secondSelected!.Wire!.Sequence - firstSelected!.Wire!.Sequence,
                    frameTimeDelta = secondSelected.Wire.FrameTime - firstSelected.Wire.FrameTime
                }
                : null,
            coverageWarnings = before.CoverageWarnings.Select(w => "before: " + w)
                .Concat(after.CoverageWarnings.Select(w => "after: " + w)).ToArray(),
            limitations = new[]
            {
                "Only complete frames entirely inside successful contiguous snapshot bytes were inspected; no unscanned process memory is implied absent.",
                "A scan with complete scoped snapshots is still scope-limited and cannot prove global candidate uniqueness.",
                "Two advancing producer frames are independent source evidence, not proof of wall-clock freshness or native XYZ semantics.",
                "Saved absolute addresses are valid only for this exact PID/start epoch; heap frames may relocate even without a restart.",
                "The native snapshot loader checks each retained chunk SHA-256 and file SHA-256; request SHA-256 is producer-declared.",
                "Neither guest memory nor game input is accessed by this offline command."
            }
        };
        if (options.TryGetValue("--output", out var destination))
            await JsonReportWriter.WriteNewAsync(destination, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(report, JsonFormat.Options));
        return 0;
    }

    private static object Input(LoadedMemorySnapshot snapshot, ScanResult scan) => new
    {
        snapshotSha256 = snapshot.FileSha256,
        snapshot.File.Status,
        snapshot.File.StartedAtUtc,
        snapshot.File.CompletedAtUtc,
        snapshot.File.Source,
        coveredSegmentCount = snapshot.Snapshot.Segments.Count,
        coveredByteCount = snapshot.Snapshot.Segments.Sum(s => (long)s.Bytes.Length),
        completeCandidateCount = scan.Candidates.Count(c => c.Kind != "incomplete"),
        malformedCompleteCount = scan.Candidates.Count(c => c.Kind == "malformed-complete"),
        incompleteFragmentCount = scan.Candidates.Count(c => c.Kind == "incomplete"),
        candidateLimitExceeded = scan.LimitExceeded,
        candidates = scan.Candidates.Select(c => new
        {
            address = $"0x{c.Address:X}",
            c.Kind,
            c.Reason,
            c.WireSha256,
            sequence = c.Wire?.Sequence,
            frameTime = c.Wire?.FrameTime,
            playerUnitId = c.Wire?.PlayerUnitId
        }).ToArray()
    };

    private static object? Selection(Candidate? candidate) => candidate?.Wire is null ? null : new
    {
        address = $"0x{candidate.Address:X}",
        candidate.WireSha256,
        candidate.Wire.Sequence,
        candidate.Wire.FrameTime,
        candidate.Wire.PlayerUnitId,
        addon = candidate.Wire.Addon,
        addonVersion = candidate.Wire.Protocol == "RR2R1" ? "0.2.0" : "0.6.0",
        protocol = candidate.Wire.Protocol,
        source = "rift-api",
        candidate.Wire.SessionId,
        candidate.Wire.Epoch,
        fields = candidate.Wire.Fields,
        xyz = new { x = candidate.Wire.X, y = candidate.Wire.Y, z = candidate.Wire.Z }
    };

    private static Candidate? Select(ScanResult scan, out string? error)
    {
        error = null;
        if (scan.LimitExceeded)
        {
            error = "candidate-limit-exceeded";
            return null;
        }
        if (scan.Candidates.Any(candidate => candidate.Kind == "malformed-complete"))
        {
            error = "malformed-complete-frame";
            return null;
        }
        if (scan.Candidates.Any(candidate => candidate.Kind == "incomplete"))
        {
            error = "incomplete-typed-fragment-in-covered-scope";
            return null;
        }
        var candidates = scan.Candidates.Where(candidate => candidate.Wire is not null).ToArray();
        if (candidates.Length == 0)
            return null;
        var reference = candidates.Any(c => c.Wire!.Protocol == "RR2R1");
        if (reference && (candidates.Select(c => c.Wire!.Epoch).Distinct().Count() != 1 ||
                          candidates.Select(c => c.Wire!.PlayerUnitId).Distinct().Count() != 1))
        {
            error = "mixed-source-epoch-or-player";
            return null;
        }
        var selected = reference
            ? candidates.OrderByDescending(c => c.Wire!.Sequence).ThenByDescending(c => c.Wire!.FrameTime).First()
            : candidates.OrderByDescending(c => c.Wire!.FrameTime).ThenByDescending(c => c.Wire!.Sequence).First();
        if (reference && candidates.Any(c => c.Wire!.Sequence < selected.Wire!.Sequence && c.Wire.FrameTime > selected.Wire.FrameTime))
        {
            error = "source-clock-regression-within-epoch";
            return null;
        }
        if (candidates.Any(c => (reference || c.Wire!.FrameTime == selected.Wire!.FrameTime) &&
                                c.Wire!.Sequence == selected.Wire!.Sequence &&
                                c.WireSha256 != selected.WireSha256))
        {
            error = "conflicting-latest-frames";
            return null;
        }
        return selected;
    }

    private static ScanResult Scan(MemorySnapshot snapshot, CancellationToken cancellationToken, string? sessionId)

    {
        var prefix = sessionId is null ? Prefix : "RR2R1|"u8.ToArray();
        var suffix = sessionId is null ? Suffix : "|ENDRR2R1"u8.ToArray();
        var candidates = new List<Candidate>();
        foreach (var segment in snapshot.Segments)
        {
            var bytes = segment.Bytes.AsSpan();
            var next = 0;
            while (next <= bytes.Length - prefix.Length)
            {
                cancellationToken.ThrowIfCancellationRequested();
                var offset = bytes[next..].IndexOf(prefix);
                if (offset < 0)
                    break;
                var start = next + offset;
                next = start + prefix.Length;
                if (next >= bytes.Length || bytes[next] != (byte)'{')
                    continue;
                if (candidates.Count == MaxCandidates)
                    return new(candidates, true);
                var address = checked(segment.StartAddress + (ulong)start);
                var end = FindJsonEnd(bytes, next);
                if (end is null || end.Value - next > MaxJsonBytes ||
                    end.Value + suffix.Length > bytes.Length ||
                    !bytes.Slice(end.Value, Math.Min(suffix.Length, bytes.Length - end.Value)).SequenceEqual(suffix))
                {
                    candidates.Add(new(address, "incomplete", "terminator-or-coverage-missing", null, null));
                    continue;
                }

                var total = end.Value + suffix.Length - start;
                var raw = bytes.Slice(start, total).ToArray();
                if (sessionId is not null && total > 8192)
                {
                    candidates.Add(new(address, "malformed-complete", "wire-frame-too-large", null, null));
                    continue;
                }
                var sha = Convert.ToHexString(SHA256.HashData(raw));
                var result = sessionId is null ? Parse(raw.AsSpan(prefix.Length, end.Value - next)) : ParseReference(raw.AsSpan(prefix.Length, end.Value - next), sessionId);
                candidates.Add(result.Value is null
                    ? new(address, "malformed-complete", result.Error, sha, null)
                    : new(address, "valid", null, sha, result.Value));
            }
        }
        return new(candidates, false);
    }

    private static int? FindJsonEnd(ReadOnlySpan<byte> bytes, int start)
    {
        var depth = 0;
        var quoted = false;
        var escaped = false;
        var limit = Math.Min(bytes.Length, start + MaxJsonBytes + 1);
        for (var index = start; index < limit; index++)
        {
            var c = bytes[index];
            if (quoted)
            {
                if (escaped)
                    escaped = false;
                else if (c == (byte)'\\')
                    escaped = true;
                else if (c == (byte)'"')
                    quoted = false;
                continue;
            }
            if (c == (byte)'"') quoted = true;
            else if (c == (byte)'{') depth++;
            else if (c == (byte)'}' && --depth == 0) return index + 1;
        }
        return null;
    }

    private static (Wire? Value, string? Error) Parse(ReadOnlySpan<byte> json)
    {
        if (json.Length > MaxJsonBytes)
            return (null, "wire-json-too-large");
        try
        {
            _ = Utf8.GetString(json);
            using var doc = JsonDocument.Parse(json.ToArray(), new JsonDocumentOptions { MaxDepth = 32 });
            var root = doc.RootElement;
            if (ContainsDuplicate(root))
                return (null, "json-duplicate-key");
            if (!HasKeys(root, TopLevelKeys) ||
                !root.TryGetProperty("schemaVersion", out var schema) || !schema.TryGetInt32(out var schemaVersion) || schemaVersion != 2 ||
                !Exact(root, "addon", "RiftReaderApiProbe") ||
                !Exact(root, "addonVersion", "0.6.0") ||
                !Exact(root, "source", "rift-api") ||
                !Exact(root, "nativeTextEntryState", "unknown") ||
                root.GetProperty("autonomousInputReady").ValueKind != JsonValueKind.False ||
                !root.GetProperty("sequence").TryGetInt64(out var sequence) || sequence <= 0)
                return (null, "snapshot-contract-invalid");
            var clock = root.GetProperty("clock");
            if (!HasKeys(clock, ["status", "domain", "value"]) ||
                !Exact(clock, "status", "ok") || !Exact(clock, "domain", "Inspect.Time.Frame") ||
                !FiniteNumber(clock.GetProperty("value"), out var frameTime) || frameTime < 0)
                return (null, "source-clock-invalid");
            var player = root.GetProperty("player");
            if (!ValidEntity(player, requirePlayer: true, out var playerId, out var xyz))
                return (null, "player-contract-or-xyz-invalid");
            if (!ValidEntity(root.GetProperty("target"), requirePlayer: false, out _, out _))
                return (null, "target-contract-invalid");
            return (new(sequence, frameTime, playerId!, xyz[0], xyz[1], xyz[2], Fields: player.GetProperty("fields").Clone()), null);
        }
        catch (Exception ex) when (ex is JsonException or ArgumentException or InvalidOperationException or DecoderFallbackException or KeyNotFoundException or OverflowException)
        {
            return (null, "json-or-contract-invalid");
        }
    }

    private static (Wire? Value, string? Error) ParseReference(ReadOnlySpan<byte> json, string sessionId)
    {
        try
        {
            foreach (var value in json)
                if (value > 127) return (null, "wire-not-ascii");
            using var doc = JsonDocument.Parse(json.ToArray(), new JsonDocumentOptions { MaxDepth = 8 });
            var root = doc.RootElement;
            if (ContainsDuplicate(root)) return (null, "json-duplicate-key");
            if (!HasKeys(root, ["schemaVersion", "addon", "addonVersion", "source", "sessionId", "sequence", "epoch", "clock", "player", "fields"]) ||
                !root.GetProperty("schemaVersion").TryGetInt32(out var schema) || schema != 1 ||
                !Exact(root, "addon", "RiftReader2") || !Exact(root, "addonVersion", "0.2.0") ||
                !Exact(root, "source", "rift-api") || !Exact(root, "sessionId", sessionId) ||
                !PositiveCounter(root.GetProperty("sequence"), out var sequence) ||
                !PositiveCounter(root.GetProperty("epoch"), out var epoch))
                return (null, "reference-contract-or-session-invalid");
            var clock = root.GetProperty("clock");
            var player = root.GetProperty("player");
            if (!ReferenceField(clock, "number") || !ReferenceField(player, "string"))
                return (null, "reference-clock-or-player-invalid");
            var clockOk = Exact(clock, "status", "ok");
            var playerOk = Exact(player, "status", "ok");
            if (clockOk && clock.GetProperty("value").GetDouble() < 0 ||
                playerOk && player.GetProperty("value").GetString()!.Length == 0 ||
                !clockOk && !Exact(player, "status", "unavailable"))
                return (null, "reference-clock-or-player-invalid");
            var fields = root.GetProperty("fields");
            if (!HasKeys(fields, FieldKinds.Keys)) return (null, "reference-fields-invalid");
            foreach (var (name, kind) in FieldKinds)
            {
                var field = fields.GetProperty(name);
                if (!ReferenceField(field, kind) ||
                    ((!clockOk || !playerOk) && !Exact(field, "status", "unavailable")))
                    return (null, "reference-fields-invalid");
            }
            if (!clockOk || !playerOk || new[] { "coordX", "coordY", "coordZ" }.Any(name => !Exact(fields.GetProperty(name), "status", "ok")))
                return (null, "reference-source-or-xyz-unavailable");
            return (new(sequence, clock.GetProperty("value").GetDouble(), player.GetProperty("value").GetString()!,
                fields.GetProperty("coordX").GetProperty("value").GetDouble(),
                fields.GetProperty("coordY").GetProperty("value").GetDouble(),
                fields.GetProperty("coordZ").GetProperty("value").GetDouble(),
                "RiftReader2", "RR2R1", sessionId, epoch, fields.Clone()), null);
        }
        catch (Exception ex) when (ex is JsonException or ArgumentException or InvalidOperationException or KeyNotFoundException or OverflowException)
        {
            return (null, "json-or-reference-contract-invalid");
        }
    }

    private static bool PositiveCounter(JsonElement item, out long value)
    {
        value = 0;
        return item.ValueKind == JsonValueKind.Number && item.TryGetInt64(out value) && value is > 0 and <= 9007199254740991;
    }

    private static bool ReferenceField(JsonElement field, string kind)
    {
        if (field.ValueKind != JsonValueKind.Object || !field.TryGetProperty("status", out var status) || status.ValueKind != JsonValueKind.String)
            return false;
        var state = status.GetString();
        if (state is not ("ok" or "unavailable" or "invalid") || !HasKeys(field, state == "ok" ? ["status", "value"] : ["status"]))
            return false;
        if (state != "ok") return true;
        var value = field.GetProperty("value");
        return kind switch
        {
            "number" => FiniteNumber(value, out _),
            "boolean" => value.ValueKind is JsonValueKind.True or JsonValueKind.False,
            "string" => value.ValueKind == JsonValueKind.String && value.GetString()!.Length <= 128 && value.GetString()!.All(c => c is >= ' ' and <= '~'),
            _ => false
        };
    }

    private static bool ValidEntity(JsonElement entity, bool requirePlayer, out string? unitId, out double[] xyz)
    {
        unitId = null;
        xyz = [];
        if (entity.ValueKind != JsonValueKind.Object ||
            !entity.TryGetProperty("status", out var statusElement) || statusElement.ValueKind != JsonValueKind.String)
            return false;
        var status = statusElement.GetString();
        if (status is not ("ok" or "absent" or "unavailable" or "error" or "invalid" or "identity-changed"))
            return false;
        var hasId = entity.TryGetProperty("unitId", out var id);
        if (!HasKeys(entity, hasId ? ["status", "fields", "unitId"] : ["status", "fields"]))
            return false;
        if ((status == "ok" && !hasId) ||
            (status is "absent" or "identity-changed" && hasId) ||
            (hasId && (!SafeString(id) || id.GetString()!.Length == 0)))
            return false;
        if (requirePlayer && status != "ok")
            return false;
        if (hasId) unitId = id.GetString();
        var fields = entity.GetProperty("fields");
        if (!HasKeys(fields, FieldKinds.Keys))
            return false;
        var coords = new List<double>();
        foreach (var (fieldName, kind) in FieldKinds)
        {
            var field = fields.GetProperty(fieldName);
            if (field.ValueKind != JsonValueKind.Object ||
                !field.TryGetProperty("status", out var fieldStatus) || fieldStatus.ValueKind != JsonValueKind.String)
                return false;
            var state = fieldStatus.GetString();
            if (state is not ("ok" or "unavailable" or "invalid") ||
                !HasKeys(field, state == "ok" ? ["status", "value"] : ["status"]) ||
                (status != "ok" && state != "unavailable"))
                return false;
            if (state == "ok")
            {
                var value = field.GetProperty("value");
                if (kind == "number" && !FiniteNumber(value, out _) ||
                    kind == "boolean" && value.ValueKind is not (JsonValueKind.True or JsonValueKind.False) ||
                    kind == "string" && !SafeString(value))
                    return false;
                if (requirePlayer && fieldName is "coordX" or "coordY" or "coordZ")
                    coords.Add(value.GetDouble());
            }
            else if (requirePlayer && fieldName is "coordX" or "coordY" or "coordZ")
                return false;
        }
        xyz = coords.ToArray();
        return !requirePlayer || xyz.Length == 3;
    }

    private static bool HasKeys(JsonElement element, IEnumerable<string> expected)
    {
        if (element.ValueKind != JsonValueKind.Object)
            return false;
        return element.EnumerateObject().Select(prop => prop.Name).ToHashSet(StringComparer.Ordinal)
            .SetEquals(expected);
    }

    private static bool Exact(JsonElement root, string name, string expected) =>
        root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String && value.GetString() == expected;

    private static bool SafeString(JsonElement item)
    {
        if (item.ValueKind != JsonValueKind.String)
            return false;
        var value = item.GetString()!;
        return !value.Any(c => c < 32 || c == 127) && Utf8.GetByteCount(value) <= 128;
    }

    private static bool FiniteNumber(JsonElement item, out double value)
    {
        value = default;
        return item.ValueKind == JsonValueKind.Number && item.TryGetDouble(out value) && double.IsFinite(value);
    }

    private static bool ContainsDuplicate(JsonElement item)
    {
        if (item.ValueKind == JsonValueKind.Object)
        {
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in item.EnumerateObject())
                if (!seen.Add(property.Name) || ContainsDuplicate(property.Value))
                    return true;
        }
        else if (item.ValueKind == JsonValueKind.Array)
        {
            foreach (var element in item.EnumerateArray())
                if (ContainsDuplicate(element))
                    return true;
        }
        return false;
    }

    private sealed record Wire(long Sequence, double FrameTime, string PlayerUnitId, double X, double Y, double Z,
        string Addon = "RiftReaderApiProbe", string Protocol = "RRAPIVAL2", string? SessionId = null,
        long? Epoch = null, JsonElement? Fields = null);
    private sealed record Candidate(ulong Address, string Kind, string? Reason, string? WireSha256, Wire? Wire);
    private sealed record ScanResult(IReadOnlyList<Candidate> Candidates, bool LimitExceeded);
}
