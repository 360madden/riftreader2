using System.Text;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Cli;

public static class CliRunner
{
    public static async Task<int> RunAsync(string[] args, TextWriter output, TextWriter error, CancellationToken cancellationToken = default)
    {
        try
        {
            if (args.Length == 0 || (args.Length == 1 && args[0] is "help" or "--help" or "-h"))
            {
                await output.WriteLineAsync("""
                    RiftReader2 0.1 — offline evidence tools
                    analyze --manifest PATH [--config PATH] [--output PATH]
                    validate-capture --manifest PATH [--config PATH]

                    Paths are relative to the current directory. Samples are beside their manifest.
                    Without --config, built-in schema-1 defaults apply. No environment overrides.
                    Analysis emits derived motion with provenance. An existing output is never replaced.
                    Exit codes: 0 success, 2 invalid input/IO failure, 130 canceled.
                    """);
                return 0;
            }

            var command = args[0];
            if (command is not ("analyze" or "validate-capture"))
                throw new ArgumentException($"Unknown command '{command}'. Use --help.");
            var options = ParseOptions(args[1..], command == "analyze");
            if (!options.TryGetValue("--manifest", out var manifestPath))
                throw new ArgumentException("--manifest is required.");
            var configuration = options.TryGetValue("--config", out var configurationPath)
                ? await ReaderConfiguration.LoadAsync(configurationPath, cancellationToken)
                : ReaderConfiguration.Default;
            configuration.Validate();

            await using var capture = await CaptureReader.OpenAsync(manifestPath, configuration.MaxCaptureBytes, cancellationToken);
            var summary = await new MotionAnalyzer().AnalyzeAsync(capture.ReadSamplesAsync(cancellationToken), configuration.Analysis, cancellationToken);
            if (command == "validate-capture")
            {
                await output.WriteLineAsync(JsonSerializer.Serialize(new
                {
                    schemaVersion = 1,
                    valid = true,
                    summary.SampleCount,
                    capture.ManifestSha256,
                    capture.Manifest.SamplesSha256
                }, JsonFormat.Options));
                return 0;
            }

            var implementation = ToolIdentity.FromAssemblies(
                typeof(CliRunner).Assembly.GetName().Version!.ToString(),
                typeof(CliRunner).Assembly, typeof(MotionAnalyzer).Assembly,
                typeof(MotionSample).Assembly, typeof(CaptureReader).Assembly);
            var report = AnalysisReport.Create(capture, configuration, summary, implementation);
            if (options.TryGetValue("--output", out var reportPath))
                await JsonReportWriter.WriteNewAsync(reportPath, report, cancellationToken);
            await output.WriteLineAsync(JsonSerializer.Serialize(report, JsonFormat.Options));
            return 0;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            await error.WriteLineAsync("{\"error\":\"Canceled; no completed report was published.\"}");
            return 130;
        }
        catch (Exception ex) when (ex is ArgumentException or IOException or JsonException or UnauthorizedAccessException or DecoderFallbackException or NotSupportedException)
        {
            await error.WriteLineAsync(JsonSerializer.Serialize(new { error = ex.Message }, JsonFormat.Options));
            return 2;
        }
    }

    private static Dictionary<string, string> ParseOptions(string[] args, bool allowOutput)
    {
        var options = new Dictionary<string, string>(StringComparer.Ordinal);
        for (var i = 0; i < args.Length; i += 2)
        {
            var name = args[i];
            if (name is not ("--manifest" or "--config") && !(allowOutput && name == "--output"))
                throw new ArgumentException($"Unknown option '{name}'.");
            if (i + 1 >= args.Length || string.IsNullOrWhiteSpace(args[i + 1]) || args[i + 1].StartsWith("--", StringComparison.Ordinal))
                throw new ArgumentException($"Missing value for '{name}'.");
            if (!options.TryAdd(name, args[i + 1]))
                throw new ArgumentException($"Duplicate option '{name}'.");
        }
        return options;
    }
}
