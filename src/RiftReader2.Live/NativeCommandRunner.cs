using System.Diagnostics;
using System.ComponentModel;
using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

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
                await output.WriteLineAsync("RiftReader2.Live native tools\ninspect-native --output PATH\ncapture-native --request PATH --output PATH\nmap-native --request PATH --output PATH\nscout-typed-native --request PATH --output PATH\nscout-copy-typed-native --request PATH --output NEW_DIRECTORY\nsnapshot-native --request PATH --output PATH\nfollow-pointer --request PATH --output PATH\nExisting outputs are never replaced.");
                return 0;
            }

            if (args[0] == "inspect-native")
                return await InspectAsync(ParseOptions(args[1..], "--output"), output, cancellationToken);
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
            if (args[0] == "snapshot-native")
                return await MemoryDiscoveryCommand.SnapshotAsync(
                    ParseOptions(args[1..], "--request", "--output"), output, cancellationToken);
            if (args[0] == "follow-pointer")
                return await MemoryDiscoveryCommand.FollowPointerAsync(
                    ParseOptions(args[1..], "--request", "--output"), output, cancellationToken);
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
        var processes = Process.GetProcessesByName("rift_x64");
        try
        {
            if (processes.Length != 1)
                throw new InvalidDataException($"Expected exactly one rift_x64 process; found {processes.Length}.");
            await using var session = await WindowsNativeMemorySession.OpenAsync(processes[0].Id, null, null, cancellationToken);
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

    private static Dictionary<string, string> ParseOptions(string[] args, params string[] allowed)
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
