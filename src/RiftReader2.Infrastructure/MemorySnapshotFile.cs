using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

public sealed record NativeMemorySnapshotFile(
    int SchemaVersion,
    string EvidenceKind,
    NativeMemorySnapshotSource Source,
    NativeProcessIdentity Identity,
    string StartedAtUtc,
    string CompletedAtUtc,
    string Status,
    string? Reason,
    IReadOnlyList<NativeMemorySnapshotChunk> Chunks,
    IReadOnlyList<string> Limitations)
{
    private const long MaxFileBytes = 96L * 1024 * 1024;
    private const long MaxRequestedBytes = 64L * 1024 * 1024;
    private const int MaxChunkBytes = 4096;
    private const int MaxChunks = 16384;
    private const ulong MinUserAddress = 0x10000;
    private const ulong MaxUserAddress = 0x00007FFF_FFFF_FFFF;

    public static async Task<LoadedMemorySnapshot> LoadAsync(string path, CancellationToken cancellationToken = default)
    {
        var fullPath = Path.GetFullPath(path);
        byte[] fileBytes;
        await using (var stream = new FileStream(fullPath, FileMode.Open, FileAccess.Read, FileShare.Read))
        {
            if (stream.Length > MaxFileBytes)
                throw new InvalidDataException("Memory snapshot JSON exceeds 96 MiB.");
            using var memory = new MemoryStream(checked((int)stream.Length));
            var buffer = new byte[81920];
            while (true)
            {
                var remaining = MaxFileBytes + 1 - memory.Length;
                if (remaining <= 0)
                    throw new InvalidDataException("Memory snapshot JSON exceeds 96 MiB.");
                var read = await stream.ReadAsync(buffer.AsMemory(0, (int)Math.Min(buffer.Length, remaining)), cancellationToken);
                if (read == 0)
                    break;
                memory.Write(buffer, 0, read);
            }
            if (memory.Length > MaxFileBytes)
                throw new InvalidDataException("Memory snapshot JSON exceeds 96 MiB.");
            fileBytes = memory.ToArray();
        }

        var file = JsonSerializer.Deserialize<NativeMemorySnapshotFile>(fileBytes, JsonFormat.Options)
            ?? throw new InvalidDataException("Memory snapshot is empty.");
        var warnings = file.ValidateAndNormalize(out var segments);
        var fileSha256 = Convert.ToHexString(SHA256.HashData(fileBytes));
        return new(file, new MemorySnapshot(file.Identity, segments), fileSha256, fullPath, warnings);
    }

    private IReadOnlyList<string> ValidateAndNormalize(out IReadOnlyList<MemorySnapshotSegment> segments)
    {
        if (SchemaVersion != 1 || EvidenceKind != "native-memory-snapshot/1")
            throw new InvalidDataException("Only native-memory-snapshot/1 schema version 1 is supported.");
        if (Source is null || Identity is null || Chunks is null || Limitations is null ||
            Chunks.Any(chunk => chunk is null) || Limitations.Any(value => value is null))
            throw new InvalidDataException("Memory snapshot contains a null required object or collection entry.");
        ValidateSource(Source);
        ValidateIdentity(Identity);
        var started = ParseUtc(StartedAtUtc, "startedAtUtc");
        var completed = ParseUtc(CompletedAtUtc, "completedAtUtc");
        if (completed < started)
            throw new InvalidDataException("Memory snapshot completedAtUtc precedes startedAtUtc.");
        if (Chunks.Count > MaxChunks)
            throw new InvalidDataException($"Memory snapshot cannot contain more than {MaxChunks} chunks.");
        if (Limitations.Count > 64 || Limitations.Any(value => string.IsNullOrWhiteSpace(value) || value.Length > 1024))
            throw new InvalidDataException("Memory snapshot limitations are invalid or exceed bounds.");

        var decoded = new List<(ulong Address, int RequestedLength, byte[] Bytes, string Status, string? Reason)>();
        long totalRequested = 0;
        ulong previousEnd = 0;
        for (var index = 0; index < Chunks.Count; index++)
        {
            var chunk = Chunks[index];
            var address = ParseAddress(chunk.Address, index);
            if (chunk.RequestedByteLength is < 1 or > MaxChunkBytes)
                throw new InvalidDataException($"Chunk {index} requestedByteLength must be 1..{MaxChunkBytes}.");
            if (address > ulong.MaxValue - (ulong)chunk.RequestedByteLength)
                throw new InvalidDataException($"Chunk {index} address range overflows.");
            var end = address + (ulong)chunk.RequestedByteLength;
            if (address < MinUserAddress || end - 1 > MaxUserAddress)
                throw new InvalidDataException($"Chunk {index} is outside the supported 64-bit user address range.");
            if (index > 0 && address < previousEnd)
                throw new InvalidDataException($"Chunk {index} overlaps or is out of address order.");
            previousEnd = end;
            totalRequested = checked(totalRequested + chunk.RequestedByteLength);
            if (totalRequested > MaxRequestedBytes)
                throw new InvalidDataException("Memory snapshot requested coverage exceeds 64 MiB.");
            var bytes = ValidateChunk(chunk, index);
            decoded.Add((address, chunk.RequestedByteLength, bytes, chunk.Status, chunk.Reason));
        }

        var successful = decoded.Count(chunk => chunk.Status == "success");
        ValidateOverallStatus(successful);
        var warnings = new List<string>();
        if (Status != "complete")
            warnings.Add($"Snapshot acquisition did not complete normally: overall status is '{Status}'.");
        foreach (var (address, requestedLength, _, chunkStatus, reason) in decoded.Where(chunk => chunk.Status != "success"))
            warnings.Add($"Range 0x{address:X}+{requestedLength} is {chunkStatus}{(string.IsNullOrWhiteSpace(reason) ? "." : $": {reason}")}");
        if (Status == "identity-invalidated")
        {
            warnings.Add("No bytes are analyzable because process identity changed during acquisition.");
            segments = [];
            return warnings;
        }

        var merged = new List<MemorySnapshotSegment>();
        MemoryStream? run = null;
        ulong runStart = 0;
        ulong runEnd = 0;
        foreach (var chunk in decoded)
        {
            if (chunk.Status != "success")
            {
                if (run is not null)
                {
                    merged.Add(new(runStart, run.ToArray()));
                    run.Dispose();
                    run = null;
                }
                continue;
            }
            if (run is null || runEnd != chunk.Address)
            {
                if (run is not null)
                {
                    merged.Add(new(runStart, run.ToArray()));
                    run.Dispose();
                }
                run = new MemoryStream(chunk.Bytes.Length);
                runStart = chunk.Address;
            }
            run.Write(chunk.Bytes, 0, chunk.Bytes.Length);
            runEnd = chunk.Address + (ulong)chunk.Bytes.Length;
        }
        if (run is not null)
        {
            merged.Add(new(runStart, run.ToArray()));
            run.Dispose();
        }
        segments = merged;
        return warnings;
    }

    private static byte[] ValidateChunk(NativeMemorySnapshotChunk chunk, int index)
    {
        if (chunk.Status is not ("success" or "partial" or "unavailable"))
            throw new InvalidDataException($"Chunk {index} has unsupported status '{chunk.Status}'.");
        if (chunk.BytesRead < 0 || chunk.BytesRead > chunk.RequestedByteLength)
            throw new InvalidDataException($"Chunk {index} bytesRead is outside its requested range.");
        if (chunk.Status == "success" && chunk.BytesRead != chunk.RequestedByteLength)
            throw new InvalidDataException($"Successful chunk {index} must contain every requested byte.");
        if (chunk.Status == "partial" && chunk.BytesRead is <= 0 ||
            chunk.Status == "partial" && chunk.BytesRead >= chunk.RequestedByteLength)
            throw new InvalidDataException($"Partial chunk {index} must contain some but not all requested bytes.");
        if (chunk.Status == "unavailable" && chunk.BytesRead != 0)
            throw new InvalidDataException($"Unavailable chunk {index} cannot contain bytes.");
        if (chunk.Status == "success" && (chunk.Win32ErrorCode is not null || chunk.Reason is not null))
            throw new InvalidDataException($"Successful chunk {index} cannot contain an error or reason.");
        if (chunk.Status is "partial" or "unavailable" && string.IsNullOrWhiteSpace(chunk.Reason))
            throw new InvalidDataException($"{chunk.Status} chunk {index} requires a reason.");
        if (chunk.Reason is { Length: > 1024 })
            throw new InvalidDataException($"Chunk {index} reason exceeds 1024 characters.");

        if (chunk.BytesRead == 0)
        {
            if (chunk.BytesBase64 is not null || chunk.BytesSha256 is not null)
                throw new InvalidDataException($"Chunk {index} declares bytes metadata without bytes.");
            return [];
        }
        if (chunk.BytesBase64 is null || chunk.BytesSha256 is null)
            throw new InvalidDataException($"Chunk {index} is missing bytes or their SHA-256.");
        byte[] bytes;
        try
        {
            bytes = Convert.FromBase64String(chunk.BytesBase64);
        }
        catch (FormatException ex)
        {
            throw new InvalidDataException($"Chunk {index} bytesBase64 is invalid.", ex);
        }
        if (bytes.Length != chunk.BytesRead)
            throw new InvalidDataException($"Chunk {index} decoded byte length does not match bytesRead.");
        ValidateSha256(chunk.BytesSha256, $"Chunk {index} bytesSha256");
        var actual = Convert.ToHexString(SHA256.HashData(bytes));
        if (!string.Equals(actual, chunk.BytesSha256, StringComparison.Ordinal))
            throw new InvalidDataException($"Chunk {index} bytes SHA-256 does not match retained bytes.");
        return bytes;
    }

    private void ValidateOverallStatus(int successful)
    {
        if (Status is not ("complete" or "partial" or "failed" or "identity-invalidated" or "time-budget-exceeded"))
            throw new InvalidDataException($"Memory snapshot has unsupported overall status '{Status}'.");
        if (Status == "complete" && (Chunks.Count == 0 || successful != Chunks.Count))
            throw new InvalidDataException("A complete memory snapshot requires every chunk to succeed.");
        if (Status == "partial" && (successful == 0 || successful == Chunks.Count))
            throw new InvalidDataException("A partial memory snapshot requires both successful and unsuccessful chunks.");
        if (Status == "failed" && successful != 0)
            throw new InvalidDataException("A failed memory snapshot cannot contain successful chunks.");
        if (Status == "complete" && Reason is not null)
            throw new InvalidDataException("A complete memory snapshot cannot contain a failure reason.");
        if (Status != "complete" && string.IsNullOrWhiteSpace(Reason))
            throw new InvalidDataException($"A {Status} memory snapshot requires a reason.");
        if (Reason is { Length: > 1024 })
            throw new InvalidDataException("Memory snapshot reason exceeds 1024 characters.");
    }

    private static void ValidateSource(NativeMemorySnapshotSource source)
    {
        if (source.RequestEvidenceKind != "native-memory-snapshot-request/1")
            throw new InvalidDataException("Snapshot source requestEvidenceKind must be native-memory-snapshot-request/1.");
        ValidateSha256(source.RequestSha256, "Snapshot source requestSha256");
        if (source.RequestSha256Verification != "producer-declared")
            throw new InvalidDataException("Snapshot source requestSha256Verification must be 'producer-declared'.");
        if (source.Implementation is null || string.IsNullOrWhiteSpace(source.Implementation.ToolVersion) ||
            source.Implementation.ToolVersion.Length > 128)
            throw new InvalidDataException("Snapshot source implementation identity is required.");
        var implementation = source.Implementation;
        if (implementation.DeploymentKind == "assembly-files")
        {
            if (implementation.AssemblySha256 is null || implementation.AssemblySha256.Count is < 1 or > 64 ||
                implementation.BundleFileName is not null || implementation.BundleSha256 is not null)
                throw new InvalidDataException("Assembly-file implementation identity has an invalid shape.");
            foreach (var (name, hash) in implementation.AssemblySha256)
            {
                if (string.IsNullOrWhiteSpace(name) || name.Length > 260)
                    throw new InvalidDataException("Implementation assembly name is invalid.");
                ValidateSha256(hash, $"Implementation assembly '{name}' SHA-256");
            }
        }
        else if (implementation.DeploymentKind == "single-file-bundle")
        {
            if (implementation.AssemblySha256 is not null || string.IsNullOrWhiteSpace(implementation.BundleFileName) ||
                implementation.BundleFileName.Length > 260 || Path.GetFileName(implementation.BundleFileName) != implementation.BundleFileName ||
                implementation.BundleSha256 is null)
                throw new InvalidDataException("Single-file implementation identity has an invalid shape.");
            ValidateSha256(implementation.BundleSha256, "Implementation bundle SHA-256");
        }
        else
        {
            throw new InvalidDataException("Snapshot source deploymentKind must be assembly-files or single-file-bundle.");
        }
    }

    private static void ValidateIdentity(NativeProcessIdentity identity)
    {
        if (identity.ProcessId <= 0 || identity.ProcessStartUtcTicks <= 0 || string.IsNullOrWhiteSpace(identity.ExecutablePath) ||
            identity.ExecutablePath.Length > 32768 || identity.ModuleBaseAddress < MinUserAddress ||
            identity.ModuleBaseAddress > MaxUserAddress || identity.ModuleSize == 0 ||
            identity.ModuleSize > MaxUserAddress - identity.ModuleBaseAddress + 1)
            throw new InvalidDataException("Memory snapshot process identity is invalid.");
        ValidateSha256(identity.ExecutableSha256, "Memory snapshot executableSha256");
    }

    private static DateTimeOffset ParseUtc(string value, string property)
    {
        if (!DateTimeOffset.TryParseExact(value,
                ["yyyy-MM-dd'T'HH:mm:ss'Z'", "yyyy-MM-dd'T'HH:mm:ss.FFFFFFF'Z'"],
                CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal,
                out var parsed))
            throw new InvalidDataException($"Memory snapshot {property} must be an explicit UTC instant.");
        return parsed;
    }

    private static ulong ParseAddress(string value, int index)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Length is < 3 or > 18 || !value.StartsWith("0x", StringComparison.Ordinal) ||
            !value.AsSpan(2).ToString().All(Uri.IsHexDigit) ||
            !ulong.TryParse(value.AsSpan(2), NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out var address) ||
            value != $"0x{address:X}")
            throw new InvalidDataException($"Chunk {index} address must be canonical hexadecimal such as 0x1000.");
        return address;
    }

    private static void ValidateSha256(string value, string property)
    {
        if (value is null || value.Length != 64 || value.Any(character => character is not (>= '0' and <= '9') and not (>= 'A' and <= 'F')))
            throw new InvalidDataException($"{property} must be 64 uppercase hexadecimal characters.");
    }
}

public sealed record NativeMemorySnapshotSource(
    string RequestEvidenceKind,
    string RequestSha256,
    string RequestSha256Verification,
    NativeImplementationIdentity Implementation);

public sealed record NativeMemorySnapshotChunk(
    string Address,
    int RequestedByteLength,
    string Status,
    int BytesRead,
    string? BytesBase64,
    string? BytesSha256,
    int? Win32ErrorCode,
    string? Reason);

public sealed record LoadedMemorySnapshot(
    NativeMemorySnapshotFile File,
    MemorySnapshot Snapshot,
    string FileSha256,
    string FullPath,
    IReadOnlyList<string> CoverageWarnings);
