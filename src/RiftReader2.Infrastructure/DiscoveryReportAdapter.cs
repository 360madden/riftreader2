using System.Globalization;
using System.Text.Json;
using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

/// <summary>Offline adapters for already-produced reports. Import is not independent semantic attestation.</summary>
public static class DiscoveryReportAdapter
{
    public static IReadOnlyList<DiscoveryRecord> Parse(VerifiedDiscoverySource source)
    {
        try
        {
            using var json = JsonDocument.Parse(source.Bytes, new JsonDocumentOptions { MaxDepth = 16 });
            var root = json.RootElement;
            Require(root.ValueKind == JsonValueKind.Object, "Report is not an object.");
            return source.Stamp.Kind switch
            {
                "typed-wire" => [Typed(root, source.Stamp)],
                "native-position-review" => [Native(root, source.Stamp, motion: false)],
                "native-motion-review" => [Native(root, source.Stamp, motion: true)],
                "record-set" => Recorded(source),
                _ => throw new InvalidDataException("No adapter for this discovery source kind.")
            };
        }
        catch (Exception ex) when (ex is InvalidOperationException or KeyNotFoundException)
        {
            throw new InvalidDataException("Discovery source has malformed required fields.", ex);
        }
    }

    private static DiscoveryRecord Typed(JsonElement report, DiscoverySourceStamp source)
    {
        Header(report, "typed-wire-snapshot-inspection/1");
        var status = String(report, "status");
        Require(status is "advanced-in-covered-scope" or "blocked" or "unavailable",
            "Unsupported typed-wire status.");
        var identity = Identity(report.GetProperty("identity"));
        DiscoveryValue? value = null;
        DateTimeOffset? observed = null;
        var details = new List<string> { "Scoped typed producer evidence; not native field qualification." };
        var reason = String(report, "reason");
        details.Add(reason);
        if (status == "advanced-in-covered-scope")
        {
            var selection = report.GetProperty("selected");
            var before = selection.GetProperty("before");
            var after = selection.GetProperty("after");
            Require(before.ValueKind == JsonValueKind.Object && after.ValueKind == JsonValueKind.Object &&
                String(before, "playerUnitId") == String(after, "playerUnitId") &&
                after.GetProperty("sequence").GetInt64() > before.GetProperty("sequence").GetInt64() &&
                after.GetProperty("frameTime").GetDouble() > before.GetProperty("frameTime").GetDouble(),
                "Typed-wire source does not show same-player advancement.");
            value = Xyz(after.GetProperty("xyz"));
            observed = DiscoverySourcesFile.Utc(String(report.GetProperty("source").GetProperty("after"), "completedAtUtc"));
        }
        details.AddRange(Limitations(report));
        return Row(source, "player.position.xyz", "movement", "addon", status,
            "source-advancement-only-not-native-qualified", "Typed Lua player position in saved native snapshot scope.",
            "game-units", "addon-api", "Inspect.Unit.Detail typed producer",
            identity.Build, identity.Session, observed, value, details);
    }

    private static DiscoveryRecord Native(JsonElement report, DiscoverySourceStamp source, bool motion)
    {
        Header(report, motion ? "native-motion-pair-review/1" : "native-pointer-versus-typed-wire-review/1");
        var status = String(report, "status");
        var qualification = String(report, "qualification");
        if (motion)
            Require(status is "candidate-motion-consistent" or "candidate-motion-disagrees" or
                "insufficient-source-motion" && qualification == "candidate-only-no-stimulus-or-clock-skew-proof",
                "Invalid native motion qualification.");
        else
            Require(status is "candidate-compatible" or "candidate-disagrees" &&
                qualification == "candidate-only-not-synchronized", "Invalid native pointer qualification.");
        Require(String(report, "rootRva") == "0x32E0200", "Unsupported native locator root.");
        var identity = Identity(report.GetProperty("target"));
        var samples = report.GetProperty("nativeSamples");
        var after = motion ? samples.GetProperty("after") : samples.EnumerateArray().Last();
        var value = Xyz(after.GetProperty("xyz"));
        var observed = DiscoverySourcesFile.Utc(String(after, "completedAtUtc"));
        var limitations = Limitations(report);
        limitations.Insert(0, "Candidate comparison only; this export cannot qualify a native field.");
        return Row(source, "player.position.xyz", "movement", "native", status, qualification,
            "Read-only native XYZ candidate compared with advancing typed Lua source.",
            "game-units", "module-relative-rva", "RVA 0x32E0200, owner +0x320/+0x324/+0x328",
            identity.Build, identity.Session, observed, value, limitations);
    }

    private static IReadOnlyList<DiscoveryRecord> Recorded(VerifiedDiscoverySource source)
    {
        var document = JsonSerializer.Deserialize<RecordedSet>(source.Bytes, JsonFormat.Options)
            ?? throw new InvalidDataException("Recorded discoveries must be a JSON object.");
        if (document.SchemaVersion != 1 || document.ContractVersion != "discovery-record-set/1" ||
            document.Records is null || document.Records.Count is < 1 or > 4096 ||
            document.Records.Any(static x => x is null))
            throw new InvalidDataException("Unsupported or empty discovery-record-set/1.");
        var ids = new HashSet<string>(StringComparer.Ordinal);
        var result = new List<DiscoveryRecord>(document.Records.Count);
        foreach (var entry in document.Records)
        {
            DiscoverySourcesFile.RequireText(entry.RecordId, 128, "recordId");
            DiscoverySourcesFile.RequireText(entry.FieldId, 128, "fieldId");
            DiscoverySourcesFile.RequireText(entry.Category, 64, "category");
            DiscoverySourcesFile.RequireText(entry.Meaning, 512, "meaning");
            DiscoverySourcesFile.RequireText(entry.Units, 64, "units");
            DiscoverySourcesFile.RequireText(entry.SessionId, 256, "sessionId");
            DiscoverySourcesFile.ValidateSha(entry.BuildSha256);
            if (!ids.Add(entry.RecordId))
                throw new InvalidDataException("Duplicate discovery recordId.");
            Require(entry.SourceKind is "addon" or "native" or "derived" or "synthetic" &&
                entry.Status is "hypothesis" or "observed" or "rejected" or "unqualified",
                "Recorded discovery uses an unsupported source or status.");
            if (entry.Locator is not null)
                DiscoverySourcesFile.RequireText(entry.Locator, 1024, "locator");
            if (entry.LocatorKind is not null)
                DiscoverySourcesFile.RequireText(entry.LocatorKind, 128, "locatorKind");
            Require(entry.Limitations is not null && entry.Limitations.Count is >= 1 and <= 32,
                "Recorded discovery requires explicit limitations.");
            foreach (var limitation in entry.Limitations!)
                DiscoverySourcesFile.RequireText(limitation, 512, "limitation");
            if (entry.ObservedAtUtc.HasValue && entry.ObservedAtUtc.Value.Offset != TimeSpan.Zero)
                throw new InvalidDataException("Recorded discovery time must be UTC.");
            if (entry.Value is not null)
            {
                Require(entry.Value.Kind is "text" or "xyz" or "number" or "boolean",
                    "Unsupported recorded value kind.");
                if (entry.Value.Text is not null)
                    DiscoverySourcesFile.RequireText(entry.Value.Text, 1024, "value text");
                if (entry.Value.Components is not null)
                {
                    Require(entry.Value.Components.Count is >= 1 and <= 8, "Invalid numeric component count.");
                    foreach (var component in entry.Value.Components)
                        Require(component.Key.Length is >= 1 and <= 32 && double.IsFinite(component.Value),
                            "Nonfinite or invalid numeric discovery component.");
                }
            }
            result.Add(Row(source.Stamp, entry.FieldId, entry.Category, entry.SourceKind,
                entry.Status, "recorded-only", entry.Meaning, entry.Units,
                entry.LocatorKind, entry.Locator, entry.BuildSha256.ToUpperInvariant(),
                entry.SessionId, entry.ObservedAtUtc, entry.Value, entry.Limitations,
                entry.RecordId));
        }
        return result;
    }

    private static DiscoveryRecord Row(DiscoverySourceStamp stamp, string fieldId, string category,
        string sourceKind, string status, string qualification, string meaning, string units,
        string? locatorKind, string? locator, string build, string session, DateTimeOffset? observed,
        DiscoveryValue? value, IReadOnlyList<string> limitations, string? recordId = null) =>
        new(stamp.SourceId + ":" + (recordId ?? fieldId), fieldId, category, sourceKind,
            status, qualification, meaning, units, locatorKind, locator,
            build, session, observed, value, stamp.Kind, stamp.Sha256, stamp.SourceId,
            stamp.Path, limitations);

    private static DiscoveryValue Xyz(JsonElement node)
    {
        Require(node.ValueKind == JsonValueKind.Object, "XYZ requires an object.");
        var components = new Dictionary<string, double>(StringComparer.Ordinal);
        foreach (var axis in new[] { "x", "y", "z" })
        {
            var value = node.GetProperty(axis).GetDouble();
            Require(double.IsFinite(value), "XYZ must be finite.");
            components.Add(axis, value);
        }
        return new("xyz", null, components);
    }

    private static (string Build, string Session) Identity(JsonElement node)
    {
        var build = String(node, "executableSha256");
        DiscoverySourcesFile.ValidateSha(build);
        var pid = node.GetProperty("processId").GetInt32();
        var ticks = node.GetProperty("processStartUtcTicks").GetInt64();
        Require(pid > 0 && ticks > 0, "Invalid process epoch.");
        return (build.ToUpperInvariant(),
            "pid:" + pid.ToString(CultureInfo.InvariantCulture) +
            "/ticks:" + ticks.ToString(CultureInfo.InvariantCulture));
    }

    private static void Header(JsonElement report, string expectedKind)
    {
        Require(report.GetProperty("schemaVersion").GetInt32() == 1 &&
            String(report, "evidenceKind") == expectedKind, "Discovery report contract differs.");
    }

    private static List<string> Limitations(JsonElement report)
    {
        var value = report.GetProperty("limitations");
        Require(value.ValueKind == JsonValueKind.Array && value.GetArrayLength() <= 32,
            "Discovery report lacks bounded limitations.");
        var result = value.EnumerateArray().Select(x => x.GetString() ??
            throw new InvalidDataException("Null limitation.")).ToList();
        foreach (var item in result) DiscoverySourcesFile.RequireText(item, 1024, "limitation");
        return result;
    }

    private static string String(JsonElement parent, string name) =>
        parent.GetProperty(name).GetString() ?? throw new InvalidDataException($"Missing {name}.");

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidDataException(message);
    }

    private sealed record RecordedSet(
        int SchemaVersion, string ContractVersion, IReadOnlyList<RecordedEntry> Records);

    private sealed record RecordedEntry(
        string RecordId, string FieldId, string Category, string SourceKind, string Status,
        string Meaning, string Units, string? LocatorKind, string? Locator, string BuildSha256,
        string SessionId, DateTimeOffset? ObservedAtUtc, DiscoveryValue? Value,
        IReadOnlyList<string> Limitations);
}
