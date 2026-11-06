using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

public sealed record NativeValueScoutRequest(
    int SchemaVersion,
    string EvidenceKind,
    NativeCaptureTarget Target,
    string StartAddress,
    IReadOnlyList<NativeValueScoutReferenceRequest> References,
    int ContextBeforeBytes,
    int ContextAfterBytes,
    long MaxScanBytes,
    int MaxDurationMilliseconds,
    int MaxRegionCount,
    int MaxMatchCount);

public sealed record NativeValueScoutReferenceRequest(
    string Name,
    string Type,
    string Value,
    double? Tolerance = null);

public sealed record LoadedNativeValueScoutRequest(
    NativeValueScoutRequest Request,
    NativeValueScoutPlan Plan,
    string RequestSha256,
    string FullPath,
    byte[] RawBytes);

public static class NativeValueScoutRequestFile
{
    private const int MaxRequestBytes = 65_536;
    private const ulong MinUserAddress = 0x10000;
    private const ulong MaxUserEnd = 0x00007FFF_FFFF_FFFF;

    public static async Task<LoadedNativeValueScoutRequest> LoadAsync(
        string path, CancellationToken cancellationToken = default)
    {
        var fullPath = Path.GetFullPath(path);
        byte[] bytes;
        await using (var stream = new FileStream(fullPath, FileMode.Open, FileAccess.Read, FileShare.Read))
        {
            if (stream.Length > MaxRequestBytes)
                throw new InvalidDataException("Native value scout request exceeds 65536 bytes.");
            using var memory = new MemoryStream(checked((int)stream.Length));
            var buffer = new byte[8192];
            while (true)
            {
                var remaining = MaxRequestBytes + 1 - checked((int)memory.Length);
                if (remaining <= 0)
                    throw new InvalidDataException("Native value scout request exceeds 65536 bytes.");
                var count = await stream.ReadAsync(buffer.AsMemory(0, Math.Min(buffer.Length, remaining)), cancellationToken);
                if (count == 0)
                    break;
                memory.Write(buffer, 0, count);
            }
            if (memory.Length > MaxRequestBytes)
                throw new InvalidDataException("Native value scout request exceeds 65536 bytes.");
            bytes = memory.ToArray();
        }

        var request = JsonSerializer.Deserialize<NativeValueScoutRequest>(bytes, JsonFormat.Options)
            ?? throw new InvalidDataException("Native value scout request is empty.");
        var plan = Validate(request);
        return new(request, plan, Convert.ToHexString(SHA256.HashData(bytes)), fullPath, bytes);
    }

    private static NativeValueScoutPlan Validate(NativeValueScoutRequest request)
    {
        if (request.SchemaVersion != 1 || request.EvidenceKind != "native-value-scout-request/1")
            throw new InvalidDataException("Only native-value-scout-request/1 schema version 1 is supported.");
        if (request.Target is null || request.Target.ProcessId <= 0 || request.Target.ProcessStartUtcTicks <= 0 ||
            string.IsNullOrWhiteSpace(request.Target.ExecutableSha256) ||
            request.Target.ExecutableSha256.Length != 64 ||
            request.Target.ExecutableSha256.Any(character => !Uri.IsHexDigit(character)))
            throw new InvalidDataException("target must contain an exact positive PID/start identity and 64-digit executable SHA-256.");
        if (!string.Equals(request.Target.ExecutableSha256,
                request.Target.ExecutableSha256.ToUpperInvariant(), StringComparison.Ordinal))
            throw new InvalidDataException("target executableSha256 must use uppercase hexadecimal.");
        var startAddress = ParseHex(request.StartAddress, "startAddress");
        if (startAddress < MinUserAddress || startAddress >= MaxUserEnd)
            throw new InvalidDataException("startAddress is outside the supported 64-bit user address range.");
        if (request.References is null || request.References.Count is < 1 or > 8 ||
            request.References.Any(reference => reference is null))
            throw new InvalidDataException("references must contain between 1 and 8 entries.");
        if (request.References.Select(reference => reference.Name).Distinct(StringComparer.Ordinal).Count() !=
            request.References.Count)
            throw new InvalidDataException("Reference names must be unique.");
        if (request.ContextBeforeBytes is < 0 or > 2048 || request.ContextAfterBytes is < 0 or > 2048 ||
            request.ContextBeforeBytes + request.ContextAfterBytes + 8 > 4096)
            throw new InvalidDataException("Context bounds must be nonnegative and allow at most one 4096-byte read including the widest value.");
        if (request.MaxScanBytes is < 65_536 or > 1_073_741_824)
            throw new InvalidDataException("maxScanBytes must be between 65536 and 1073741824.");
        if (request.MaxDurationMilliseconds is < 1 or > 30_000)
            throw new InvalidDataException("maxDurationMilliseconds must be between 1 and 30000.");
        if (request.MaxRegionCount is < 1 or > 32_768)
            throw new InvalidDataException("maxRegionCount must be between 1 and 32768.");
        if (request.MaxMatchCount is < 1 or > 128)
            throw new InvalidDataException("maxMatchCount must be between 1 and 128.");

        var references = request.References.Select(ParseReference).ToArray();
        return new(
            request.Target.ProcessId,
            request.Target.ProcessStartUtcTicks,
            request.Target.ExecutableSha256,
            startAddress,
            references,
            request.ContextBeforeBytes,
            request.ContextAfterBytes,
            request.MaxScanBytes,
            request.MaxDurationMilliseconds,
            request.MaxRegionCount,
            request.MaxMatchCount);
    }

    private static NativeValueReference ParseReference(NativeValueScoutReferenceRequest reference)
    {
        if (string.IsNullOrWhiteSpace(reference.Name) || reference.Name.Length > 32 ||
            !char.IsLetter(reference.Name[0]) ||
            reference.Name.Any(character => !char.IsLetterOrDigit(character) && character is not '-' and not '_'))
            throw new InvalidDataException("Reference names must begin with a letter and contain only letters, digits, '-' or '_'.");
        if (string.IsNullOrWhiteSpace(reference.Value) || reference.Value.Length > 64)
            throw new InvalidDataException($"Reference '{reference.Name}' value is missing or too long.");
        var kind = reference.Type switch
        {
            "int32" => MemoryValueKind.Int32,
            "float32" => MemoryValueKind.Float32,
            "float64" => MemoryValueKind.Float64,
            _ => throw new InvalidDataException($"Reference '{reference.Name}' type must be int32, float32 or float64.")
        };
        var tolerance = reference.Tolerance ?? 0;
        if (!double.IsFinite(tolerance) || tolerance < 0 || (kind == MemoryValueKind.Int32 && tolerance != 0))
            throw new InvalidDataException($"Reference '{reference.Name}' has an invalid tolerance.");
        try
        {
            switch (kind)
            {
                case MemoryValueKind.Int32:
                    _ = int.Parse(reference.Value, NumberStyles.Integer, CultureInfo.InvariantCulture);
                    break;
                case MemoryValueKind.Float32:
                    if (!float.IsFinite(float.Parse(reference.Value, NumberStyles.Float, CultureInfo.InvariantCulture)))
                        throw new FormatException();
                    break;
                case MemoryValueKind.Float64:
                    if (!double.IsFinite(double.Parse(reference.Value, NumberStyles.Float, CultureInfo.InvariantCulture)))
                        throw new FormatException();
                    break;
            }
        }
        catch (Exception exception) when (exception is FormatException or OverflowException)
        {
            throw new InvalidDataException($"Reference '{reference.Name}' value is invalid for {reference.Type}.", exception);
        }
        return new(reference.Name, kind, reference.Value, tolerance);
    }

    private static ulong ParseHex(string value, string name)
    {
        if (string.IsNullOrWhiteSpace(value) || !value.StartsWith("0x", StringComparison.Ordinal) ||
            value.Length is < 3 or > 18 ||
            !ulong.TryParse(value.AsSpan(2), NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out var parsed) ||
            !string.Equals(value, $"0x{parsed:X}", StringComparison.Ordinal))
            throw new InvalidDataException($"{name} must be canonical uppercase hexadecimal such as 0x10000.");
        return parsed;
    }
}
