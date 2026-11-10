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
                    analyze-turn-probe --before PATH --after PATH --receipt PATH --matrix primary|secondary --uncontaminated true|false [--target-degrees NUMBER] [--output PATH]
                    analyze --manifest PATH [--config PATH] [--output PATH]
                    validate-capture --manifest PATH [--config PATH]
                    decode-addon --frame PATH [--output PATH]
                    decode-live-addon --frame PATH --session-id HEX [--output PATH]
                    guide-addon (--snapshot PATH | --frame PATH) --lab lab1|lab2 --session-id HEX --result-sequence INTEGER --destination-x NUMBER --destination-y NUMBER --destination-z NUMBER [--output PATH]
                    replay-wall-motion --manifest PATH [--output PATH]
                    qualify-fields --catalog PATH --build-sha256 HEX --session-id ID --as-of UTC [--output PATH]
                    export-discoveries --manifest PATH --build-sha256 HEX --session-id ID --as-of UTC --format json|csv|jsonl --output PATH [--source LIST] [--category LIST] [--status LIST] [--search TEXT] [--sort KEYS] [--columns CSV]
                    search-memory --snapshot PATH --type TYPE --value VALUE [--tolerance NUMBER] [--output PATH]
                    find-pattern --snapshot PATH --pattern PATTERN [--output PATH]
                    compare-memory --before PATH --after PATH --type TYPE --mode MODE [--output PATH]
                    audit-targeted-health --request PATH --manifest PATH --receipt PATH --snapshot PATH [--output PATH]
                     compare-targeted-health --before PATH --after PATH [--output PATH]
                     find-pointers --snapshot PATH --target 0xADDRESS --max-depth 1..4 --max-offset 0..4096 [--output PATH]

                    Paths are relative to the current directory. Capture samples are beside their manifest;
                    wall replay uses the exact source path pinned in its evidence manifest.
                    Without --config, built-in schema-1 defaults apply. No environment overrides.
                    Analysis emits derived motion with provenance. An existing output is never replaced.
                    Addon decoding verifies the contract only; source binding and freshness remain unverified.
                    Field qualification evaluates recorded assessments at an explicit build/session/time.
                    Exit 0 for qualification means a valid report; inspect its claim statuses before use.
                    Exit codes: 0 success, 2 invalid input/IO failure, 130 canceled.
                    """);
                await output.WriteLineAsync("inspect-typed-wire --before PATH --after PATH (--session-id HEX | --protocol historical-rrapival2) [--output PATH]");
                return 0;
            }

            var command = args[0];
            if (command == "analyze-turn-probe")
                return await TurnProbeCliCommand.RunAsync(
                    ParseOptions(args[1..], "--before", "--after", "--receipt", "--matrix",
                        "--uncontaminated", "--target-degrees", "--output"), output, cancellationToken);
            if (command == "guide-addon")
                return await AddonGuidanceCommand.RunAsync(
                    ParseOptions(args[1..], "--frame", "--snapshot", "--lab", "--session-id", "--result-sequence",
                        "--destination-x", "--destination-y", "--destination-z", "--output"), output, cancellationToken);
            if (command is "search-memory" or "find-pattern" or "compare-memory" or "find-pointers")
            {
                var memoryOptions = command switch
                {
                    "search-memory" => ParseOptions(args[1..], "--snapshot", "--type", "--value", "--tolerance", "--output"),
                    "find-pattern" => ParseOptions(args[1..], "--snapshot", "--pattern", "--output"),
                    "compare-memory" => ParseOptions(args[1..], "--before", "--after", "--type", "--mode", "--output"),
                    _ => ParseOptions(args[1..], "--snapshot", "--target", "--max-depth", "--max-offset", "--output")
                };
                return await MemoryDiscoveryCommand.RunAsync(command, memoryOptions, output, cancellationToken);
            }
            if (command == "inspect-typed-wire")
                return await TypedWireSnapshotCommand.RunAsync(
                    ParseOptions(args[1..], "--before", "--after", "--session-id", "--protocol", "--output"), output, cancellationToken);
            if (command == "compare-targeted-health")
                return await TargetedHealthAuditCommand.CompareAsync(
                    ParseOptions(args[1..], "--before", "--after", "--output"), output, cancellationToken);
            if (command == "audit-targeted-health")
                return await TargetedHealthAuditCommand.RunAsync(
                    ParseOptions(args[1..], "--request", "--manifest", "--receipt", "--snapshot", "--output"),
                    output, cancellationToken);
            if (command == "qualify-fields")
                return await FieldCatalogCommand.RunAsync(
                    ParseOptions(args[1..], "--catalog", "--build-sha256", "--session-id", "--as-of", "--output"),
                    output, cancellationToken);
            if (command == "export-discoveries")
                return await DiscoveryExportCommand.RunAsync(
                    ParseOptions(args[1..], "--manifest", "--build-sha256", "--session-id", "--as-of",
                        "--format", "--output", "--source", "--category", "--status", "--search",
                        "--sort", "--columns"), output, cancellationToken);
            if (command == "replay-wall-motion")
            {
                var replayOptions = ParseOptions(args[1..], "--manifest", "--output");
                if (!replayOptions.TryGetValue("--manifest", out var replayManifestPath))
                    throw new ArgumentException("--manifest is required.");
                await using var replay = await WallMotionEvidenceReader.OpenAsync(replayManifestPath, cancellationToken);
                var wallMotionOptions = new WallMotionReplayOptions(
                    replay.Manifest.MaxBoundaryGapMilliseconds,
                    replay.Manifest.MaxProjectionGapMilliseconds);
                var replaySummary = await new WallMotionReplayAnalyzer().AnalyzeAsync(
                    replay.ReadSamplesAsync(cancellationToken),
                    replay.Trials,
                    wallMotionOptions,
                    cancellationToken);
                var replayImplementation = ToolIdentity.FromAssemblies(
                    typeof(CliRunner).Assembly.GetName().Version!.ToString(),
                    typeof(CliRunner).Assembly, typeof(WallMotionReplayAnalyzer).Assembly,
                    typeof(WallMotionSample).Assembly, typeof(WallMotionEvidenceReader).Assembly);
                var replayReport = new WallMotionReplayReport(
                    1,
                    "v1-wall-motion-replay/1",
                    "derived-negative-field-classification",
                    replayImplementation,
                    new(
                        replay.ManifestSha256,
                        replay.Manifest.SourcePath,
                        replay.Manifest.SourceByteLength,
                        replay.Manifest.SourceSha256.ToUpperInvariant(),
                        "verified-on-replay-handle",
                        replay.Manifest.ExpectedSampleCount,
                        replay.Manifest.Identity,
                        replay.Manifest.Trials,
                        "verified-on-replay-handles"),
                    wallMotionOptions,
                    replaySummary,
                    [
                        "Applies only to the identified saved V1 build and process epoch.",
                        "Trial timestamps and guest samples inherit the capture's host/guest UTC-alignment assumption.",
                        "Each trial retains its gameResponseVerified flag; the selected saved V1 runs rely on passed input/release records plus observed coordinate evidence.",
                        "Bracket displacement per key-hold second uses the key interval, not the elapsed interval between bracketing samples.",
                        "The disagreement rejects this projection as realized velocity; it does not identify a native actual-velocity field or prove a positive projection semantic."
                    ]);
                if (replayOptions.TryGetValue("--output", out var replayReportPath))
                    await JsonReportWriter.WriteNewAsync(replayReportPath, replayReport, cancellationToken);
                await output.WriteLineAsync(JsonSerializer.Serialize(replayReport, JsonFormat.Options));
                return 0;
            }
            if (command == "decode-live-addon")
            {
                var liveOptions = ParseOptions(args[1..], "--frame", "--session-id", "--output");
                if (!liveOptions.TryGetValue("--frame", out var livePath) || !liveOptions.TryGetValue("--session-id", out var sessionId))
                    throw new ArgumentException("--frame and --session-id are required.");
                var liveReport = await LiveAddonFrameFile.ReadAsync(livePath, sessionId, cancellationToken);
                if (liveOptions.TryGetValue("--output", out var liveReportPath))
                    await JsonReportWriter.WriteNewAsync(liveReportPath, liveReport, cancellationToken);
                await output.WriteLineAsync(JsonSerializer.Serialize(liveReport, JsonFormat.Options));
                return 0;
            }
            if (command == "decode-addon")
            {
                var addonOptions = ParseOptions(args[1..], "--frame", "--output");
                if (!addonOptions.TryGetValue("--frame", out var framePath))
                    throw new ArgumentException("--frame is required.");
                var addonReport = await AddonFrameFile.ReadAsync(framePath, cancellationToken);
                if (addonOptions.TryGetValue("--output", out var addonReportPath))
                    await JsonReportWriter.WriteNewAsync(addonReportPath, addonReport, cancellationToken);
                await output.WriteLineAsync(JsonSerializer.Serialize(addonReport, JsonFormat.Options));
                return 0;
            }
            if (command is not ("analyze" or "validate-capture"))
                throw new ArgumentException($"Unknown command '{command}'. Use --help.");
            var options = command == "analyze"
                ? ParseOptions(args[1..], "--manifest", "--config", "--output")
                : ParseOptions(args[1..], "--manifest", "--config");
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
        catch (Exception ex) when (ex is ArgumentException or IOException or InvalidDataException or JsonException or
            UnauthorizedAccessException or DecoderFallbackException or NotSupportedException or FormatException or OverflowException)
        {
            await error.WriteLineAsync(JsonSerializer.Serialize(new { error = ex.Message }, JsonFormat.Options));
            return 2;
        }
    }

    private static Dictionary<string, string> ParseOptions(string[] args, params string[] allowed)
    {
        var options = new Dictionary<string, string>(StringComparer.Ordinal);
        for (var i = 0; i < args.Length; i += 2)
        {
            var name = args[i];
            if (!allowed.Contains(name, StringComparer.Ordinal))
                throw new ArgumentException($"Unknown option '{name}'.");
            if (i + 1 >= args.Length || string.IsNullOrWhiteSpace(args[i + 1]) || args[i + 1].StartsWith("--", StringComparison.Ordinal))
                throw new ArgumentException($"Missing value for '{name}'.");
            if (!options.TryAdd(name, args[i + 1]))
                throw new ArgumentException($"Duplicate option '{name}'.");
        }
        return options;
    }
}
