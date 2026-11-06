using System.Globalization;
using System.Text;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Cli;

/// <summary>Offline evidence compilation; no game, network or control interfaces.</summary>
internal static class DiscoveryExportCommand
{
    private static readonly string[] CsvDefaultColumns =
    [
        "id", "fieldId", "category", "sourceKind", "status", "qualification", "meaning",
        "units", "value", "locatorKind", "locator", "buildSha256", "sessionId",
        "observedAtUtc", "evidenceKind", "evidenceSha256", "sourceId", "sourcePath", "limitations"
    ];

    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken cancellationToken)
    {
        foreach (var required in new[] { "--manifest", "--build-sha256", "--session-id", "--as-of",
                     "--format", "--output" })
            if (!options.ContainsKey(required))
                throw new ArgumentException($"{required} is required.");
        DiscoverySourcesFile.ValidateSha(options["--build-sha256"]);
        DiscoverySourcesFile.RequireText(options["--session-id"], 256, "sessionId");
        if (!DateTimeOffset.TryParseExact(options["--as-of"],
                ["yyyy-MM-dd'T'HH:mm:ss'Z'", "yyyy-MM-dd'T'HH:mm:ss.FFFFFFF'Z'"],
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var asOf))
            throw new ArgumentException("--as-of requires an explicit UTC timestamp ending Z.");
        var format = options["--format"];
        if (format is not ("json" or "csv" or "jsonl"))
            throw new ArgumentException("--format must be json, csv or jsonl.");
        if (format != "csv" && options.ContainsKey("--columns"))
            throw new ArgumentException("--columns applies only to CSV.");
        var selection = new DiscoverySelection(
            Get("--source"), Get("--category"), Get("--status"), Get("--search"),
            Get("--sort") ?? "fieldId:asc,observedAtUtc:desc");
        DiscoveryQuery.ParseSort(selection.Sort);
        foreach (var filter in new[] { selection.Source, selection.Category, selection.Status })
            if (filter is not null && (filter.Length > 512 ||
                filter.Split(',').Any(string.IsNullOrWhiteSpace)))
                throw new ArgumentException("A discovery filter contains an empty or excessive value.");
        if (selection.Search is { Length: > 256 })
            throw new ArgumentException("Search text is too long.");
        string? Get(string key) => options.TryGetValue(key, out var value) ? value : null;

        var columns = format == "csv" ? Columns(Get("--columns")) : CsvDefaultColumns;
        var context = new FieldQualificationContext(
            options["--build-sha256"].ToUpperInvariant(), options["--session-id"], asOf);
        var loaded = await DiscoverySourcesFile.LoadAsync(options["--manifest"], cancellationToken);
        var records = new List<DiscoveryRecord>();
        var fieldEvaluator = new FieldQualificationEvaluator();
        foreach (var source in loaded.Sources)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (source.Stamp.Kind == "field-catalog")
            {
                var catalog = await FieldCatalogFile.LoadAsync(source.FullPath, cancellationToken);
                if (!catalog.CatalogSha256.Equals(source.Stamp.Sha256, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("Field catalog changed between verified reads.");
                var evaluation = fieldEvaluator.Evaluate(catalog.Catalog, catalog.Assessments, context);
                var byId = evaluation.Fields.ToDictionary(item => item.FieldId, StringComparer.Ordinal);
                foreach (var field in catalog.Catalog.Fields)
                {
                    var qualification = byId[field.FieldId];
                    var scopedTimes = catalog.Assessments.Where(a => a.FieldId == field.FieldId &&
                        a.Applicability.BuildSha256.Equals(context.BuildSha256, StringComparison.OrdinalIgnoreCase) &&
                        a.Applicability.SessionId == context.SessionId)
                        .Select(static a => (DateTimeOffset?)a.AssessedAtUtc);
                    var details = new List<string>
                    {
                        "Catalog qualification is recorded assertions, not independent game semantics.",
                        "Build/session identity is declared-only, not live-attested."
                    };
                    details.AddRange(qualification.Reasons);
                    details.AddRange(qualification.Claims.Select(claim =>
                        claim.Claim + ": " + claim.Status +
                        " supporting=[" + string.Join(',', claim.SupportingAssessmentIds) +
                        "] contradicting=[" + string.Join(',', claim.ContradictingAssessmentIds) + "]"));
                    records.Add(new(
                        source.Stamp.SourceId + ":" + field.FieldId, field.FieldId,
                        field.FieldId.Split('.')[0], field.SourceKind, qualification.Status,
                        "recorded-assertions-only", field.Meaning, field.Units,
                        field.Locator.Kind, field.Locator.Method, context.BuildSha256,
                        context.SessionId, scopedTimes.DefaultIfEmpty().Max(), null,
                        "field-catalog/1", source.Stamp.Sha256,
                        source.Stamp.SourceId, source.Stamp.Path, details));
                }
            }
            else
                records.AddRange(DiscoveryReportAdapter.Parse(source));
            if (records.Count > 8192)
                throw new InvalidDataException("Discovery compilation exceeds 8192 records.");
        }
        if (records.Select(static r => r.Id).Distinct(StringComparer.Ordinal).Count() != records.Count)
            throw new InvalidDataException("Duplicate combined discovery record ID.");
        var selected = DiscoveryQuery.Apply(records, selection);
        var result = new DiscoveryCompilation(1, "discovery-compilation/1",
            loaded.ManifestSha256,
            "manifest-and-source-sha256-verified; field-catalog-artifacts-verified-if-present",
            "reported-source-statuses-not-independent-semantic-attestation",
            context, selection, records.Count, selected.Count,
            loaded.Sources.Select(static item => item.Stamp).ToArray(), selected);
        var destination = options["--output"];
        cancellationToken.ThrowIfCancellationRequested();
        if (format == "json")
            await JsonReportWriter.WriteNewAsync(destination, result, cancellationToken);
        else
            await WriteNewTextAsync(destination, format == "csv" ? Csv(selected, columns) :
                JsonLines(selected), cancellationToken);

        await output.WriteLineAsync(JsonSerializer.Serialize(new
        {
            status = "exported",
            format,
            output = destination,
            result.ManifestSha256,
            result.TotalRecords,
            result.SelectedRecords,
            contractVersion = result.ContractVersion
        }, JsonFormat.Options));
        return 0;
    }

    private static string[] Columns(string? columns)
    {
        if (columns is null) return CsvDefaultColumns;
        var list = columns.Split(',', StringSplitOptions.TrimEntries);
        if (list.Length is < 1 or > 19 || list.Any(x => !CsvDefaultColumns.Contains(x, StringComparer.Ordinal)) ||
            list.Distinct(StringComparer.Ordinal).Count() != list.Length)
            throw new ArgumentException("--columns contains an unknown or duplicate column.");
        return list;
    }

    private static string Csv(IReadOnlyList<DiscoveryRecord> records, string[] columns)
    {
        var builder = new StringBuilder();
        builder.AppendLine(string.Join(',', columns.Select(QuoteCsv)));
        foreach (var record in records)
            builder.AppendLine(string.Join(',', columns.Select(key => QuoteCsv(Column(record, key)))));
        return builder.ToString().Replace("\r\n", "\n", StringComparison.Ordinal);
    }

    private static string JsonLines(IReadOnlyList<DiscoveryRecord> records)
    {
        var compact = new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false };
        var builder = new StringBuilder();
        foreach (var record in records)
            builder.AppendLine(JsonSerializer.Serialize(record, compact));
        return builder.ToString().Replace("\r\n", "\n", StringComparison.Ordinal);
    }

    private static string Column(DiscoveryRecord row, string key) => key switch
    {
        "id" => row.Id,
        "fieldId" => row.FieldId,
        "category" => row.Category,
        "sourceKind" => row.SourceKind,
        "status" => row.Status,
        "qualification" => row.Qualification,
        "meaning" => row.Meaning,
        "units" => row.Units,
        "locatorKind" => row.LocatorKind ?? "",
        "locator" => row.Locator ?? "",
        "buildSha256" => row.BuildSha256,
        "sessionId" => row.SessionId,
        "observedAtUtc" => row.ObservedAtUtc?.ToUniversalTime().ToString("O", CultureInfo.InvariantCulture) ?? "",
        "value" => row.Value is null ? "" : row.Value.Text ??
            (row.Value.Components is null ? "" :
                string.Join("; ", row.Value.Components.OrderBy(static item => item.Key, StringComparer.Ordinal)
                    .Select(item => item.Key + "=" + item.Value.ToString("R", CultureInfo.InvariantCulture)))),
        "evidenceKind" => row.EvidenceKind,
        "evidenceSha256" => row.EvidenceSha256,
        "sourceId" => row.SourceId,
        "sourcePath" => row.SourcePath,
        "limitations" => string.Join(" | ", row.Limitations),
        _ => throw new ArgumentException("Unsupported export column.")
    };

    private static string QuoteCsv(string text)
    {
        // Excel-compatible inert data: never let an evidence field execute as a formula.
        if (text.AsSpan().TrimStart() is { Length: > 0 } trimmed &&
            trimmed[0] is '=' or '+' or '-' or '@')
            text = "'" + text;
        return "\"" + text.Replace("\"", "\"\"", StringComparison.Ordinal) + "\"";
    }

    private static async Task WriteNewTextAsync(string path, string text, CancellationToken cancellationToken)
    {
        var full = Path.GetFullPath(path);
        var directory = Path.GetDirectoryName(full)!;
        Directory.CreateDirectory(directory);
        var temp = Path.Combine(directory, "." + Path.GetFileName(full) + "." + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            await using (var file = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                var bytes = new UTF8Encoding(false, true).GetBytes(text);
                await file.WriteAsync(bytes, cancellationToken);
                await file.FlushAsync(cancellationToken);
                file.Flush(flushToDisk: true);
            }
            cancellationToken.ThrowIfCancellationRequested();
            File.Move(temp, full, overwrite: false);
        }
        finally
        {
            if (File.Exists(temp)) File.Delete(temp);
        }
    }
}
