using RiftReader2.Domain;

namespace RiftReader2.Application;

/// <summary>Pure, deterministic query semantics shared by exports and tests.</summary>
public static class DiscoveryQuery
{
    private static readonly HashSet<string> SortKeys =
        new(StringComparer.OrdinalIgnoreCase)
        {
            "id", "fieldId", "category", "sourceKind", "status",
            "qualification", "buildSha256", "sessionId", "observedAtUtc", "evidenceKind"
        };

    public static IReadOnlyList<DiscoveryRecord> Apply(
        IReadOnlyList<DiscoveryRecord> records, DiscoverySelection selection)
    {
        ArgumentNullException.ThrowIfNull(records);
        ArgumentNullException.ThrowIfNull(selection);
        var keys = ParseSort(selection.Sort);
        var result = records.Where(record =>
            Matches(record.SourceKind, selection.Source) &&
            Matches(record.Category, selection.Category) &&
            Matches(record.Status, selection.Status) &&
            (string.IsNullOrWhiteSpace(selection.Search) || Searchable(record).Contains(
                selection.Search, StringComparison.OrdinalIgnoreCase))).ToList();
        result.Sort((left, right) =>
        {
            foreach (var (key, descending) in keys)
            {
                int compare;
                if (key.Equals("observedAtUtc", StringComparison.OrdinalIgnoreCase))
                {
                    // Missing observation times remain last for both directions.
                    if (!left.ObservedAtUtc.HasValue || !right.ObservedAtUtc.HasValue)
                        compare = left.ObservedAtUtc.HasValue.CompareTo(right.ObservedAtUtc.HasValue) * -1;
                    else
                    {
                        compare = left.ObservedAtUtc.Value.CompareTo(right.ObservedAtUtc.Value);
                        if (descending) compare = -compare;
                    }
                }
                else
                {
                    compare = StringComparer.OrdinalIgnoreCase.Compare(Value(left, key), Value(right, key));
                    if (descending) compare = -compare;
                }
                if (compare != 0) return compare;
            }
            return StringComparer.Ordinal.Compare(left.Id, right.Id);
        });
        return result;
    }

    public static IReadOnlyList<(string Key, bool Descending)> ParseSort(string sort)
    {
        if (string.IsNullOrWhiteSpace(sort))
            throw new ArgumentException("Sort must name at least one key.");
        var result = new List<(string, bool)>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var token in sort.Split(',', StringSplitOptions.TrimEntries))
        {
            var parts = token.Split(':', StringSplitOptions.TrimEntries);
            if (parts.Length is < 1 or > 2 || !SortKeys.Contains(parts[0]) ||
                !seen.Add(parts[0]) ||
                (parts.Length == 2 && parts[1] is not ("asc" or "desc")))
                throw new ArgumentException($"Invalid or duplicate sort key '{token}'.");
            result.Add((parts[0], parts.Length == 2 && parts[1] == "desc"));
            if (result.Count > 5)
                throw new ArgumentException("At most five sort keys are permitted.");
        }
        return result;
    }

    private static bool Matches(string value, string? filters) =>
        string.IsNullOrWhiteSpace(filters) || filters.Split(',', StringSplitOptions.TrimEntries)
            .Any(filter => filter.Length > 0 && value.Equals(filter, StringComparison.OrdinalIgnoreCase));

    private static string Searchable(DiscoveryRecord record) =>
        string.Join(' ', record.Id, record.FieldId, record.Category, record.Meaning,
            record.SourceKind, record.Status, record.Qualification, record.LocatorKind,
            record.Locator, record.BuildSha256, record.SessionId, record.EvidenceKind,
            record.EvidenceSha256, record.SourceId, record.SourcePath, record.Units,
            record.ObservedAtUtc?.ToUniversalTime().ToString("O", System.Globalization.CultureInfo.InvariantCulture),
            string.Join(' ', record.Limitations), record.Value?.Text,
            record.Value?.Components is null ? null :
                string.Join(' ', record.Value.Components.Select(item =>
                    item.Key + "=" + item.Value.ToString("R", System.Globalization.CultureInfo.InvariantCulture))));

    private static string Value(DiscoveryRecord item, string key) => key.ToLowerInvariant() switch
    {
        "id" => item.Id,
        "fieldid" => item.FieldId,
        "category" => item.Category,
        "sourcekind" => item.SourceKind,
        "status" => item.Status,
        "qualification" => item.Qualification,
        "buildsha256" => item.BuildSha256,
        "sessionid" => item.SessionId,
        "evidencekind" => item.EvidenceKind,
        _ => throw new ArgumentException("Unsupported sort key.")
    };
}
