using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Cli;

internal static class FieldCatalogCommand
{
    public static async Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options, TextWriter output, CancellationToken cancellationToken)
    {
        foreach (var required in new[] { "--catalog", "--build-sha256", "--session-id", "--as-of" })
            if (!options.ContainsKey(required))
                throw new ArgumentException($"{required} is required.");
        if (!DateTimeOffset.TryParseExact(options["--as-of"],
                ["yyyy-MM-dd'T'HH:mm:ss'Z'", "yyyy-MM-dd'T'HH:mm:ss.FFFFFFF'Z'"],
                CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal,
                out var asOf))
            throw new ArgumentException("--as-of must be an explicit UTC instant such as 2026-10-19T00:00:00Z.");

        cancellationToken.ThrowIfCancellationRequested();
        var loaded = await FieldCatalogFile.LoadAsync(options["--catalog"], cancellationToken);
        var context = new FieldQualificationContext(options["--build-sha256"], options["--session-id"], asOf);
        var evaluation = new FieldQualificationEvaluator().Evaluate(loaded.Catalog, loaded.Assessments, context);
        var implementation = ToolIdentity.FromAssemblies(
            typeof(CliRunner).Assembly.GetName().Version!.ToString(),
            typeof(CliRunner).Assembly, typeof(FieldQualificationEvaluator).Assembly,
            typeof(FieldQualificationContext).Assembly, typeof(FieldCatalogFile).Assembly);
        var report = new FieldQualificationReport(
            1, "field-qualification/1", "recorded-field-assessment-evaluation", implementation,
            loaded.CatalogSha256, "verified-retained-bytes", "declared-only", evaluation);
        cancellationToken.ThrowIfCancellationRequested();
        if (options.TryGetValue("--output", out var destination))
            await JsonReportWriter.WriteNewAsync(destination, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(report, JsonFormat.Options));
        return 0;
    }
}
