using System.Buffers.Binary;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

public sealed class WallMotionEvidenceReader : IAsyncDisposable
{
    private readonly FileStream sourceStream;
    private bool consumed;

    private WallMotionEvidenceReader(
        WallMotionEvidenceManifest manifest,
        string manifestSha256,
        FileStream sourceStream,
        IReadOnlyList<WallMotionTrial> trials)
    {
        Manifest = manifest;
        ManifestSha256 = manifestSha256;
        this.sourceStream = sourceStream;
        Trials = trials;
    }

    public WallMotionEvidenceManifest Manifest { get; }
    public string ManifestSha256 { get; }
    public IReadOnlyList<WallMotionTrial> Trials { get; }

    public static async Task<WallMotionEvidenceReader> OpenAsync(string manifestPath, CancellationToken cancellationToken = default)
    {
        var manifestBytes = await BoundedJson.ReadAsync(manifestPath, cancellationToken);
        var manifest = JsonSerializer.Deserialize<WallMotionEvidenceManifest>(manifestBytes, JsonFormat.Options)
            ?? throw new InvalidDataException("Wall-motion manifest cannot be null.");
        manifest.Validate();
        var sourcePath = Path.GetFullPath(manifest.SourcePath);
        RejectReparsePoint(sourcePath, "source");
        var stream = new FileStream(sourcePath, FileMode.Open, FileAccess.Read, FileShare.Read, 65536,
            FileOptions.Asynchronous | FileOptions.SequentialScan);
        try
        {
            await VerifyHandleAsync(stream, manifest.SourceByteLength, manifest.SourceSha256, "source", cancellationToken);
            var sourceDirectory = Path.GetDirectoryName(sourcePath)!;
            var trials = new List<WallMotionTrial>(manifest.Trials.Count);
            foreach (var artifact in manifest.Trials)
                trials.Add(await ReadTrialAsync(sourceDirectory, artifact, manifest.Identity, cancellationToken));
            return new(manifest, Convert.ToHexString(SHA256.HashData(manifestBytes)), stream, trials);
        }
        catch
        {
            await stream.DisposeAsync();
            throw;
        }
    }

    public async IAsyncEnumerable<WallMotionSample> ReadSamplesAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        if (consumed)
            throw new InvalidOperationException("Open a new wall-motion reader for each replay.");
        consumed = true;
        using var reader = new StreamReader(sourceStream, new UTF8Encoding(false, true), false, 65536, true);
        var buffer = new char[65536];
        var line = new StringBuilder();
        var lineNumber = 1;
        long previousSequence = 0;
        DateTimeOffset? previousTimestamp = null;
        double? previousMonotonic = null;
        int read;
        while ((read = await reader.ReadAsync(buffer.AsMemory(), cancellationToken)) != 0)
        {
            for (var i = 0; i < read; i++)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (buffer[i] == '\n')
                {
                    if (line.Length == 0)
                        throw new InvalidDataException($"Wall-motion sample line {lineNumber} is empty.");
                    var sample = ParseSample(line.ToString(), lineNumber);
                    ValidateOrder(sample, lineNumber, previousSequence, previousTimestamp, previousMonotonic);
                    previousSequence = sample.Sequence;
                    previousTimestamp = sample.CapturedAtUtc;
                    previousMonotonic = sample.MonotonicMilliseconds;
                    yield return sample;
                    line.Clear();
                    lineNumber++;
                    if (lineNumber > Manifest.ExpectedSampleCount + 1)
                        throw new InvalidDataException("Wall-motion source contains more samples than declared.");
                }
                else
                {
                    if (line.Length >= Manifest.MaxLineBytes)
                        throw new InvalidDataException($"Wall-motion sample line {lineNumber} exceeds the declared limit.");
                    line.Append(buffer[i]);
                }
            }
        }
        if (line.Length > 0)
        {
            var sample = ParseSample(line.ToString(), lineNumber);
            ValidateOrder(sample, lineNumber, previousSequence, previousTimestamp, previousMonotonic);
            yield return sample;
            lineNumber++;
        }
        var count = lineNumber - 1;
        if (count != Manifest.ExpectedSampleCount)
            throw new InvalidDataException($"Wall-motion source contains {count} samples; expected {Manifest.ExpectedSampleCount}.");
    }

    private WallMotionSample ParseSample(string line, int lineNumber)
    {
        try
        {
            if (Encoding.UTF8.GetByteCount(line) > Manifest.MaxLineBytes)
                throw new InvalidDataException($"Wall-motion sample line {lineNumber} exceeds the declared byte limit.");
            using var document = JsonDocument.Parse(line, new JsonDocumentOptions { AllowDuplicateProperties = false, MaxDepth = 16 });
            var root = document.RootElement;
            RequireString(root, "instanceId", Manifest.Identity.ObserverInstanceId, lineNumber);
            RequireString(root, "rootRva", Manifest.Identity.RootRva, lineNumber);
            var target = root.GetProperty("target");
            RequireInt32(target, "processId", Manifest.Identity.ProcessId, lineNumber);
            RequireTimestamp(target, "processStartUtc", Manifest.Identity.ProcessStartUtc, lineNumber);
            RequireString(target, "executableSha256", Manifest.Identity.ExecutableSha256, lineNumber, ignoreCase: true);
            RequireString(root.GetProperty("buildIdentity"), "executableSha256", Manifest.Identity.ExecutableSha256, lineNumber, ignoreCase: true);

            var sample = root.GetProperty("sample");
            RequireInt32(sample, "schemaVersion", 1, lineNumber);
            RequireString(sample, "status", "passed", lineNumber);
            if (sample.GetProperty("blockers").GetArrayLength() != 0)
                throw new InvalidDataException($"Wall-motion sample line {lineNumber} has blockers.");
            var sequence = sample.GetProperty("sequence").GetInt64();
            var timestamp = sample.GetProperty("capturedAtUtc").GetDateTimeOffset();
            var monotonic = RequireFinite(sample.GetProperty("monotonicMilliseconds").GetDouble(), "monotonic time", lineNumber);
            if (monotonic < 0)
                throw new InvalidDataException($"Wall-motion monotonic time is negative at line {lineNumber}.");
            var coordinate = sample.GetProperty("coordinate");
            var x = RequireFinite(coordinate.GetProperty("x").GetDouble(), "X coordinate", lineNumber);
            var z = RequireFinite(coordinate.GetProperty("z").GetDouble(), "Z coordinate", lineNumber);
            var projectionWindow = sample.GetProperty("windows").EnumerateArray()
                .SingleOrDefault(static window => window.GetProperty("pointerOffset").GetString() == "0x3F8/0x78/0x30");
            if (projectionWindow.ValueKind == JsonValueKind.Undefined)
                throw new InvalidDataException($"Wall-motion sample line {lineNumber} lacks the projection window.");
            var data = Convert.FromBase64String(projectionWindow.GetProperty("dataBase64").GetString()
                ?? throw new InvalidDataException($"Wall-motion sample line {lineNumber} has no projection bytes."));
            if (projectionWindow.GetProperty("offset").GetString() != "0x0"
                || projectionWindow.GetProperty("byteLength").GetInt32() != data.Length)
                throw new InvalidDataException($"Wall-motion sample line {lineNumber} has inconsistent projection-window metadata.");
            if (data.Length < 0xE4)
                throw new InvalidDataException($"Wall-motion sample line {lineNumber} has a short projection window.");
            var projectionX = ReadSingle(data, 0xD8) - ReadSingle(data, 0x48);
            var projectionZ = ReadSingle(data, 0xE0) - ReadSingle(data, 0x50);
            return new(sequence, timestamp, monotonic, x, z,
                RequireFinite(projectionX, "projection X", lineNumber),
                RequireFinite(projectionZ, "projection Z", lineNumber));
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException)
        {
            throw new InvalidDataException($"Invalid wall-motion JSON at line {lineNumber}: {ex.Message}", ex);
        }
    }

    private static async Task<WallMotionTrial> ReadTrialAsync(
        string sourceDirectory,
        WallMotionRunArtifact artifact,
        WallMotionExpectedIdentity identity,
        CancellationToken cancellationToken)
    {
        var path = Path.Combine(sourceDirectory, artifact.File);
        RejectReparsePoint(path, $"trial '{artifact.Phase}'");
        await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 4096,
            FileOptions.Asynchronous | FileOptions.SequentialScan);
        await VerifyHandleAsync(stream, artifact.ByteLength, artifact.Sha256, $"trial '{artifact.Phase}'", cancellationToken);
        var bytes = new byte[artifact.ByteLength];
        await stream.ReadExactlyAsync(bytes, cancellationToken);
        try
        {
            using var document = JsonDocument.Parse(bytes, new JsonDocumentOptions { AllowDuplicateProperties = false, MaxDepth = 32 });
            var root = document.RootElement;
            RequireInt32(root, "schemaVersion", 1, 0);
            RequireString(root, "status", "passed", 0);
            RequireString(root, "key", "w", 0);
            foreach (var property in new[] { "inputSent", "releaseSent" })
                if (!root.GetProperty(property).GetBoolean())
                    throw new InvalidDataException($"Trial '{artifact.Phase}' did not complete verified input and release.");
            var binding = root.GetProperty("guestBinding");
            RequireString(binding, "observerInstanceId", identity.ObserverInstanceId, 0);
            RequireInt32(binding, "gameProcessId", identity.ProcessId, 0);
            RequireTimestamp(binding, "gameProcessStartUtc", identity.ProcessStartUtc, 0, allowMicrosecondTruncation: true);
            RequireString(binding, "gameSha256", identity.ExecutableSha256, 0, ignoreCase: true);
            var down = root.GetProperty("keyDownSentAtUtc").GetDateTimeOffset();
            var up = root.GetProperty("keyUpSentAtUtc").GetDateTimeOffset();
            var observedHold = RequireFinite(root.GetProperty("observedHoldMs").GetDouble(), "observed hold", 0);
            var gameResponseVerified = root.GetProperty("gameResponseVerified").GetBoolean();
            return new(artifact.Phase, artifact.Role, down, up, observedHold, gameResponseVerified, artifact.Sha256.ToUpperInvariant());
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException)
        {
            throw new InvalidDataException($"Invalid wall-motion trial '{artifact.Phase}': {ex.Message}", ex);
        }
    }

    private static async Task VerifyHandleAsync(
        FileStream stream,
        long expectedLength,
        string expectedSha256,
        string label,
        CancellationToken cancellationToken)
    {
        if (stream.Length != expectedLength)
            throw new InvalidDataException($"Wall-motion {label} byte length does not match the manifest.");
        var actual = Convert.ToHexString(await SHA256.HashDataAsync(stream, cancellationToken));
        if (!actual.Equals(expectedSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException($"Wall-motion {label} SHA-256 does not match the manifest.");
        stream.Position = 0;
    }

    private static void RejectReparsePoint(string path, string label)
    {
        if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException($"Wall-motion {label} must be a regular file.");
    }

    private static void ValidateOrder(
        WallMotionSample sample,
        int lineNumber,
        long previousSequence,
        DateTimeOffset? previousTimestamp,
        double? previousMonotonic)
    {
        if (sample.Sequence <= 0 || (previousSequence != 0 && sample.Sequence <= previousSequence))
            throw new InvalidDataException($"Wall-motion sequence is invalid at line {lineNumber}.");
        if (previousTimestamp is not null && sample.CapturedAtUtc <= previousTimestamp)
            throw new InvalidDataException($"Wall-motion UTC time does not advance at line {lineNumber}.");
        if (previousMonotonic is not null && sample.MonotonicMilliseconds <= previousMonotonic)
            throw new InvalidDataException($"Wall-motion monotonic time does not advance at line {lineNumber}.");
    }

    private static float ReadSingle(byte[] data, int offset) =>
        BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32LittleEndian(data.AsSpan(offset, sizeof(float))));

    private static double RequireFinite(double value, string label, int lineNumber)
    {
        if (!double.IsFinite(value))
            throw new InvalidDataException($"Wall-motion {label} is not finite at line {lineNumber}.");
        return value;
    }

    private static void RequireString(JsonElement element, string name, string expected, int lineNumber, bool ignoreCase = false)
    {
        var actual = element.GetProperty(name).GetString();
        if (!string.Equals(actual, expected, ignoreCase ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
            throw new InvalidDataException($"Wall-motion identity mismatch for '{name}' at line {lineNumber}.");
    }

    private static void RequireInt32(JsonElement element, string name, int expected, int lineNumber)
    {
        if (element.GetProperty(name).GetInt32() != expected)
            throw new InvalidDataException($"Wall-motion identity mismatch for '{name}' at line {lineNumber}.");
    }

    private static void RequireTimestamp(
        JsonElement element,
        string name,
        DateTimeOffset expected,
        int lineNumber,
        bool allowMicrosecondTruncation = false)
    {
        var actual = element.GetProperty(name).GetDateTimeOffset();
        var matches = actual == expected || (allowMicrosecondTruncation
            && actual.UtcTicks == expected.UtcTicks - (expected.UtcTicks % 10));
        if (!matches)
            throw new InvalidDataException($"Wall-motion identity mismatch for '{name}' at line {lineNumber}.");
    }

    public ValueTask DisposeAsync() => sourceStream.DisposeAsync();
}
