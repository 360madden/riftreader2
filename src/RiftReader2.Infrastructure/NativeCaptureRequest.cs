using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

public sealed record NativeCaptureRequest(
    int SchemaVersion,
    string EvidenceKind,
    NativeCaptureTarget Target,
    NativeCaptureSampling Sampling,
    IReadOnlyList<NativeCaptureRangeRequest> Ranges)
{
    public static async Task<LoadedNativeCaptureRequest> LoadAsync(string path, CancellationToken cancellationToken)
    {
        var fullPath = Path.GetFullPath(path);
        await using var stream = new FileStream(fullPath, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (stream.Length > 65_536)
            throw new InvalidDataException("Native capture request exceeds 65536 bytes.");
        using var memory = new MemoryStream(checked((int)stream.Length));
        var buffer = new byte[8192];
        while (true)
        {
            var remaining = 65_537 - checked((int)memory.Length);
            if (remaining <= 0)
                throw new InvalidDataException("Native capture request exceeds 65536 bytes.");
            var count = await stream.ReadAsync(buffer.AsMemory(0, Math.Min(buffer.Length, remaining)), cancellationToken);
            if (count == 0)
                break;
            memory.Write(buffer, 0, count);
        }
        if (memory.Length > 65_536)
            throw new InvalidDataException("Native capture request exceeds 65536 bytes.");
        var bytes = memory.ToArray();
        var request = JsonSerializer.Deserialize<NativeCaptureRequest>(bytes, JsonFormat.Options)
            ?? throw new InvalidDataException("Native capture request is empty.");
        if (request.SchemaVersion != 1 || request.EvidenceKind != "native-memory-read-request/1")
            throw new InvalidDataException("Only native-memory-read-request/1 schema version 1 is supported.");
        var plan = request.ToPlan();
        return new(request, plan, Convert.ToHexString(SHA256.HashData(bytes)), fullPath);
    }

    private NativeCapturePlan ToPlan()
    {
        if (Target is null || Sampling is null || Ranges is null || Ranges.Any(range => range is null))
            throw new InvalidDataException("Native capture request contains a null object or range entry.");
        return new(
            Target.ProcessId,
            Target.ProcessStartUtcTicks,
            Target.ExecutableSha256,
            Ranges.Select(range => new NativeCaptureRange(
                range.Id,
                range.AddressKind switch
                {
                    "module-relative-rva" => NativeAddressKind.ModuleRelative,
                    "absolute-session-address" => NativeAddressKind.Absolute,
                    _ => throw new InvalidDataException($"Range '{range.Id}' has an unsupported addressKind.")
                },
                ParseAddress(range.Address, range.Id),
                range.ByteLength)).ToArray(),
            Sampling.SampleCount,
            Sampling.IntervalMilliseconds,
            Sampling.MaxDurationMilliseconds);
    }

    private static ulong ParseAddress(string value, string id)
    {
        if (string.IsNullOrWhiteSpace(value) || !value.StartsWith("0x", StringComparison.Ordinal) ||
            value.Length is < 3 or > 18 || !value.AsSpan(2).ToString().All(Uri.IsHexDigit) ||
            !ulong.TryParse(value.AsSpan(2), System.Globalization.NumberStyles.AllowHexSpecifier,
                System.Globalization.CultureInfo.InvariantCulture, out var address))
            throw new InvalidDataException($"Range '{id}' address must be a canonical hexadecimal string such as 0x1000.");
        if (!string.Equals(value, $"0x{address:X}", StringComparison.Ordinal))
            throw new InvalidDataException($"Range '{id}' address must use canonical uppercase hexadecimal without leading zeroes.");
        return address;
    }
}

public sealed record NativeCaptureTarget(
    int ProcessId,
    long ProcessStartUtcTicks,
    string ExecutableSha256);

public sealed record NativeCaptureSampling(
    int SampleCount,
    int IntervalMilliseconds,
    int MaxDurationMilliseconds);

public sealed record NativeCaptureRangeRequest(
    string Id,
    string AddressKind,
    string Address,
    int ByteLength);

public sealed record LoadedNativeCaptureRequest(
    NativeCaptureRequest Request,
    NativeCapturePlan Plan,
    string RequestSha256,
    string FullPath);

public sealed record NativeCaptureReport(
    int SchemaVersion,
    string ContractVersion,
    string EvidenceKind,
    NativeImplementationIdentity Implementation,
    string RequestSha256,
    NativeCaptureRequest Request,
    NativeCaptureSummary Capture,
    string CaptureContentSha256,
    IReadOnlyList<string> Limitations);

public sealed record NativeImplementationIdentity(
    string ToolVersion,
    string DeploymentKind,
    IReadOnlyDictionary<string, string>? AssemblySha256,
    string? BundleFileName,
    string? BundleSha256);
