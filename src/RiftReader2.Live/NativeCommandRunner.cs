using System.Diagnostics;
using System.ComponentModel;
using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using RiftReader2.Live.Control;

namespace RiftReader2.Live;

public static class NativeCommandRunner
{
    private const int MaxReportBytes = 8 * 1024 * 1024;

    public static async Task<int> RunAsync(
        string[] args,
        TextWriter output,
        TextWriter error,
        CancellationToken cancellationToken = default)
    {
        try
        {
            if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
                throw new NotSupportedException("Native commands require 64-bit Windows.");
            if (args.Length == 0 || args[0] is "help" or "--help" or "-h")
            {
                await output.WriteLineAsync("RiftReader2.Live native tools\ninspect-native --output PATH [--pid N --start-ticks N]\ncapture-native --request PATH --output PATH\nmap-native --request PATH --output PATH\nscout-typed-native --request PATH --output PATH\nscout-copy-typed-native --request PATH --output NEW_DIRECTORY\nscout-copy-casting-reference-native --request PATH --output NEW_DIRECTORY\nscout-values-native --request PATH --output NEW_DIRECTORY\nsnapshot-native --request PATH --output PATH\nfollow-pointer --request PATH --output PATH\nsample-position --profile PATH --output PATH [--samples N] [--interval-ms N]\nsample-current-position --pid N --start-ticks N --output PATH [--samples N] [--interval-ms N] (exact build only)\nsample-current-position-refresh-branch --pid N --start-ticks N --output PATH (cached XYZ refresh guards; candidate only)\nsample-current-orientation --pid N --start-ticks N --output PATH (raw matrix candidate only)\nsample-current-actor-pose --pid N --start-ticks N --output PATH [--samples N] [--interval-ms N] (actor/model/render candidates only)\nsample-current-location-context --pid N --start-ticks N --output PATH (position and optional zone candidates)\nsample-current-paired-position --pid N --start-ticks N --output PATH [--max-pair-span-ms N] (self/selected target candidates)\nsample-current-paired-zone-key --pid N --start-ticks N --output PATH [--max-acquisition-ms N] (raw per-unit key candidates; world unavailable)\nsample-current-vitals --pid N --start-ticks N --output PATH [--samples N] [--interval-ms N] (candidate only)\nsample-current-ability-maps --pid N --start-ticks N --output PATH (candidate only)\nsample-current-ability-records --pid N --start-ticks N --keys CSV --output PATH [--include-costs true] [--include-timing true] [--include-range true] [--include-variants true] (candidate only)\nsample-current-world-casts --pid N --start-ticks N --output PATH [--samples N] [--interval-ms N] (candidate only)\nsample-current-localization-dictionary --pid N --start-ticks N --keys CSV --output PATH (candidate only)\nsample-current-localization --pid N --start-ticks N --keys CSV --output PATH (candidate only)\nsample-current-player-context --pid N --start-ticks N --output PATH (candidate only)\nsample-current-selected-target --pid N --start-ticks N --output PATH [--include-name-seed true] [--include-position true] [--include-context true] (candidate only)\nsample-current-target-template-name --pid N --start-ticks N --output PATH (candidate only)\nsample-current-variant-guards --pid N --start-ticks N --output PATH (candidate only)\nsample-current-experience-values --pid N --start-ticks N --output PATH (candidate only)\nsample-current-experience-seed --pid N --start-ticks N --output PATH (raw candidate only)\nsample-current-cooldown-modifiers --pid N --start-ticks N --output PATH (candidate only)\nsample-current-buff-seeds --pid N --start-ticks N --output PATH [--include-timing true] (candidate only)\nsample-current-buff-visibility --pid N --start-ticks N --output PATH (candidate only)\nsample-current-buff-details --pid N --start-ticks N --output PATH (candidate only)\nsample-current-zone-seed --pid N --start-ticks N --output PATH (candidate only)\nsample-current-player-name --pid N --start-ticks N --output PATH (candidate only)\nsample-current-player-race --pid N --start-ticks N --output PATH (candidate only)\nsample-current-player-decoration --pid N --start-ticks N --output PATH (candidate only)\nsample-current-shard --pid N --start-ticks N --output PATH (candidate only)\nsample-current-stats --pid N --start-ticks N --output PATH (candidate only)\nsample-power --pid N --start-ticks N --output PATH [--samples N] [--interval-ms N]\nExisting outputs are never replaced.");
                await output.WriteLineAsync("position-panel [--profile PATH] [--output-directory NEW_DIRECTORY]\nStart / Read / Stop window; defaults to the profile beside this executable and a new local evidence session.");
                return 0;
            }

            if (args[0] == "inspect-native")
                return await InspectAsync(ParseOptions(args[1..], "--output", "--pid", "--start-ticks"), output, cancellationToken);
            if (args[0] == "capture-native")
                return await CaptureAsync(ParseOptions(args[1..], "--request", "--output"), output, cancellationToken);
            if (args[0] == "map-native")
                return await MemoryDiscoveryCommand.MapAsync(
                    ParseOptions(args[1..], "--request", "--output"), output, cancellationToken);
            if (args[0] == "scout-typed-native")
                return await MemoryDiscoveryCommand.ScoutTypedAsync(
                    ParseOptions(args[1..], "--request", "--output"), output, cancellationToken);
            if (args[0] == "scout-copy-typed-native")
                return await MemoryDiscoveryCommand.ScoutCopyTypedAsync(
                    ParseOptions(args[1..], "--request", "--output"), output, cancellationToken);
            if (args[0] == "scout-copy-casting-reference-native")
                return await CastingReferenceInlineCaptureCommand.RunAsync(
                    ParseOptions(args[1..], "--request", "--output"), output, cancellationToken);
            if (args[0] == "scout-values-native")
                return await NativeValueScoutCommand.RunAsync(
                    ParseOptions(args[1..], "--request", "--output"), output, cancellationToken);
            if (args[0] == "snapshot-native")
                return await MemoryDiscoveryCommand.SnapshotAsync(
                    ParseOptions(args[1..], "--request", "--output"), output, cancellationToken);
            if (args[0] == "follow-pointer")
                return await MemoryDiscoveryCommand.FollowPointerAsync(
                    ParseOptions(args[1..], "--request", "--output"), output, cancellationToken);
            if (args[0] == "sample-position")
                return await PositionSampleCommand.RunAsync(ParseOptions(args[1..], "--profile", "--output", "--samples", "--interval-ms"), output, cancellationToken);
            if (args[0] == "sample-current-position")
                return await CurrentBuildPositionSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output", "--samples", "--interval-ms"), output, cancellationToken);
            if (args[0] == "sample-current-position-refresh-branch")
                return await CurrentBuildPositionRefreshBranchSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-orientation")
                return await CurrentBuildOrientationSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-actor-pose")
                return await CurrentBuildActorPoseSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output", "--samples", "--interval-ms"), output, cancellationToken);
            if (args[0] == "sample-current-location-context")
                return await CurrentBuildLocationContextSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-paired-position")
                return await CurrentBuildPairedPositionSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output", "--max-pair-span-ms"), output, cancellationToken);
            if (args[0] == "sample-current-paired-zone-key")
                return await CurrentBuildPairedZoneKeySampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output", "--max-acquisition-ms"), output, cancellationToken);
            if (args[0] == "sample-current-vitals")
                return await CurrentBuildVitalsSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output", "--samples", "--interval-ms"), output, cancellationToken);
            if (args[0] == "sample-current-ability-maps")
                return await CurrentBuildAbilityMapsSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-localization-dictionary")
                return await CurrentBuildLocalizationDictionarySampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--keys", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-ability-records")
                return await CurrentBuildAbilityRecordsSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--keys", "--output", "--include-costs", "--include-timing", "--include-range", "--include-variants"), output, cancellationToken);
            if (args[0] == "sample-current-world-casts")
                return await CurrentBuildWorldCastSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output", "--samples", "--interval-ms"), output, cancellationToken);
            if (args[0] == "sample-current-localization")
                return await CurrentBuildLocalizationSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--keys", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-player-context")
                return await CurrentBuildPlayerContextSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-selected-target")
                return await CurrentBuildSelectedTargetSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output", "--include-name-seed", "--include-position", "--include-context"), output, cancellationToken);
            if (args[0] == "sample-current-target-template-name")
                return await CurrentBuildTargetTemplateNameSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-variant-guards")
                return await CurrentBuildVariantGuardSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-experience-values")
                return await CurrentBuildExperienceValuesSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-experience-seed")
                return await CurrentBuildExperienceSeedSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-buff-seeds")
                return await CurrentBuildBuffSeedSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output", "--include-timing"), output, cancellationToken);
            if (args[0] == "sample-current-buff-visibility")
                return await CurrentBuildBuffVisibilitySampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-zone-seed")
                return await CurrentBuildZoneSeedSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-player-name")
                return await CurrentBuildPlayerNameSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-player-race")
                return await CurrentBuildPlayerRaceSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-player-decoration")
                return await CurrentBuildPlayerDecorationSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-shard")
                return await CurrentBuildCurrentShardSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-cooldown-modifiers")
                return await CurrentBuildCooldownModifierSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-buff-details")
                return await CurrentBuildBuffDetailsSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-current-stats")
                return await CurrentBuildStatsSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output"), output, cancellationToken);
            if (args[0] == "sample-power")
                return await PowerSampleCommand.RunAsync(ParseOptions(args[1..], "--pid", "--start-ticks", "--output", "--samples", "--interval-ms"), output, cancellationToken);
            throw new ArgumentException($"Unknown command '{args[0]}'.");
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            await error.WriteLineAsync("{\"error\":\"Canceled; no completed report was published.\"}");
            return 130;
        }
        catch (Exception exception) when (exception is ArgumentException or IOException or InvalidDataException or
            JsonException or UnauthorizedAccessException or NotSupportedException or OverflowException or Win32Exception or
            TimeoutException)
        {
            await error.WriteLineAsync(JsonSerializer.Serialize(new { error = exception.Message }, JsonFormat.Options));
            return 2;
        }
    }

    private static async Task<int> InspectAsync(
        IReadOnlyDictionary<string, string> options,
        TextWriter output,
        CancellationToken cancellationToken)
    {
        if (!options.TryGetValue("--output", out var outputPath))
            throw new ArgumentException("--output is required.");
        var binding = ParseInspectProcessBinding(options);
        var processes = Process.GetProcessesByName("rift_x64");
        try
        {
            int selected;
            try
            {
                selected = WindowsControlDesktop.SelectProcessIndex(
                    processes.Select(process => process.Id).ToArray(), binding.ProcessId, "rift_x64");
            }
            catch (InvalidOperationException error)
            {
                throw new InvalidDataException(error.Message, error);
            }
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                processes[selected].Id, binding.StartTicks, null, cancellationToken);
            var identity = session.Identity;
            var identityFailure = await session.RevalidateAsync(cancellationToken);
            if (identityFailure is not null)
                throw new InvalidDataException(identityFailure);
            var request = new NativeCaptureRequest(
                1,
                "native-memory-read-request/1",
                new(identity.ProcessId, identity.ProcessStartUtcTicks, identity.ExecutableSha256),
                new(1, 0, 5_000),
                [new("module-header", "module-relative-rva", "0x0", 64)]);
            var limitations = new[]
            {
                "The SHA-256 identifies the on-disk executable opened by path; it does not hash loaded module bytes.",
                "Module base and size are Toolhelp mapping metadata bracketed by same-handle process identity checks.",
                "The suggested module-header range is semantically unqualified and does not promote a game field."
            };
            var capturedAtUtc = DateTimeOffset.UtcNow.ToString("O");
            var target = new NativeInspectionTarget(
                identity.ProcessId,
                identity.ProcessStartUtcTicks,
                identity.ExecutablePath,
                identity.ExecutableSha256,
                Hex(identity.ModuleBaseAddress),
                identity.ModuleSize);
            var inspectionContent = JsonSerializer.SerializeToUtf8Bytes(new
            {
                capturedAtUtc,
                Target = target,
                SuggestedRequest = request,
                Limitations = limitations
            }, JsonFormat.Options);
            var implementation = CreateImplementationIdentity();
            var report = new NativeInspectionReport(
                1,
                "native-target-inspection/1",
                implementation,
                capturedAtUtc,
                target,
                request,
                Convert.ToHexString(SHA256.HashData(inspectionContent)),
                limitations);
            EnsureSize(report);
            await JsonReportWriter.WriteNewAsync(outputPath, report, cancellationToken);
            await output.WriteLineAsync(JsonSerializer.Serialize(report, JsonFormat.Options));
            return 0;
        }
        finally
        {
            foreach (var process in processes)
                process.Dispose();
        }
    }

    private static async Task<int> CaptureAsync(
        IReadOnlyDictionary<string, string> options,
        TextWriter output,
        CancellationToken cancellationToken)
    {
        if (!options.TryGetValue("--request", out var requestPath) || !options.TryGetValue("--output", out var outputPath))
            throw new ArgumentException("--request and --output are required.");
        var loaded = await NativeCaptureRequest.LoadAsync(requestPath, cancellationToken);
        NativeCaptureRunner.Validate(loaded.Plan);
        await using var session = await WindowsNativeMemorySession.OpenAsync(
            loaded.Plan.ProcessId,
            loaded.Plan.ProcessStartUtcTicks,
            loaded.Plan.ExecutableSha256,
            cancellationToken);
        var capture = await new NativeCaptureRunner().CaptureAsync(loaded.Plan, session, cancellationToken);
        var contentBytes = JsonSerializer.SerializeToUtf8Bytes(new
        {
            loaded.RequestSha256,
            loaded.Request,
            Capture = capture
        }, JsonFormat.Options);
        var implementation = CreateImplementationIdentity();
        var report = new NativeCaptureReport(
            1,
            "native-memory-capture/1",
            "native-memory-semantic-unqualified",
            implementation,
            loaded.RequestSha256,
            loaded.Request,
            capture,
            Convert.ToHexString(SHA256.HashData(contentBytes)),
            [
                "CaptureContentSha256 binds canonical JSON bytes containing requestSha256, request, and capture under the repository JSON settings.",
                "ExecutableSha256 identifies on-disk file bytes; loaded module bytes were not hashed.",
                "Module base and size are Toolhelp mapping metadata bracketed by same-handle process identity checks.",
                "Absolute addresses are valid only for this exact process epoch; no field meaning is inferred.",
                "Partial bytes are retained only with explicit partial status and actual byte count.",
                "CaptureId and timestamps intentionally make separate live runs byte-distinct; the content hash binds this run's logical request and capture, not the surrounding implementation or limitation fields."
            ]);
        EnsureSize(report);
        await JsonReportWriter.WriteNewAsync(outputPath, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(report, JsonFormat.Options));
        return capture.Status == "complete" ? 0 : 3;
    }

    internal static (int? ProcessId, long? StartTicks) ParseInspectProcessBinding(
        IReadOnlyDictionary<string, string> options)
    {
        var hasPid = options.TryGetValue("--pid", out var pidText);
        var hasTicks = options.TryGetValue("--start-ticks", out var ticksText);
        if (hasPid != hasTicks)
            throw new ArgumentException("inspect-native requires --pid and --start-ticks together.");
        if (!hasPid)
            return (null, null);
        if (!int.TryParse(pidText, NumberStyles.None, CultureInfo.InvariantCulture, out var pid)
            || pid <= 0 || !long.TryParse(ticksText, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks)
            || ticks <= 0)
            throw new ArgumentException("inspect-native requires positive decimal PID and start ticks.");
        return (pid, ticks);
    }

    internal static Dictionary<string, string> ParseOptions(string[] args, params string[] allowed)
    {
        var result = new Dictionary<string, string>(StringComparer.Ordinal);
        for (var index = 0; index < args.Length; index += 2)
        {
            var name = args[index];
            if (!allowed.Contains(name, StringComparer.Ordinal))
                throw new ArgumentException($"Unknown option '{name}'.");
            if (index + 1 >= args.Length || string.IsNullOrWhiteSpace(args[index + 1]) ||
                args[index + 1].StartsWith("--", StringComparison.Ordinal))
                throw new ArgumentException($"Missing value for '{name}'.");
            if (!result.TryAdd(name, args[index + 1]))
                throw new ArgumentException($"Duplicate option '{name}'.");
        }
        return result;
    }

    private static void EnsureSize<T>(T value)
    {
        var size = JsonSerializer.SerializeToUtf8Bytes(value, JsonFormat.Options).Length;
        if (size > MaxReportBytes)
            throw new InvalidDataException($"Native report exceeds the {MaxReportBytes}-byte output limit.");
    }

    private static string Hex(ulong value) => $"0x{value:X}";

    internal static NativeImplementationIdentity CreateImplementationIdentity()
    {
        var assemblies = new[]
        {
            typeof(NativeCommandRunner).Assembly,
            typeof(NativeCaptureRunner).Assembly,
            typeof(NativeCaptureSummary).Assembly,
            typeof(NativeCaptureRequest).Assembly
        };
        var toolVersion = typeof(NativeCommandRunner).Assembly.GetName().Version!.ToString();
#pragma warning disable IL3000 // Empty locations intentionally select explicit single-file bundle identity.
        if (assemblies.All(assembly => !string.IsNullOrWhiteSpace(assembly.Location)))
#pragma warning restore IL3000
        {
            var fileIdentity = ToolIdentity.FromAssemblies(toolVersion, assemblies);
            return new(toolVersion, "assembly-files", fileIdentity.AssemblySha256, null, null);
        }

        var processPath = Environment.ProcessPath;
        if (string.IsNullOrWhiteSpace(processPath) || !File.Exists(processPath))
            throw new InvalidDataException("This single-file deployment cannot identify its bundle executable.");
        using var stream = new FileStream(processPath, FileMode.Open, FileAccess.Read, FileShare.Read);
        var bundleSha256 = Convert.ToHexString(SHA256.HashData(stream));
        return new(toolVersion, "single-file-bundle", null, Path.GetFileName(processPath), bundleSha256);
    }
}

public sealed record NativeInspectionTarget(
    int ProcessId,
    long ProcessStartUtcTicks,
    string ExecutablePath,
    string ExecutableSha256,
    string ModuleBaseAddress,
    ulong ModuleSize);

public sealed record NativeInspectionReport(
    int SchemaVersion,
    string ContractVersion,
    NativeImplementationIdentity Implementation,
    string CapturedAtUtc,
    NativeInspectionTarget Target,
    NativeCaptureRequest SuggestedRequest,
    string InspectionContentSha256,
    IReadOnlyList<string> Limitations);
