using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

public sealed record VerifiedDiscoverySource(DiscoverySourceStamp Stamp, string FullPath, byte[] Bytes);

public sealed record LoadedDiscoverySources(string ManifestSha256, IReadOnlyList<VerifiedDiscoverySource> Sources);

/// <summary>Exact-byte bounded input manifest; no implicit repository or artifact scanning.</summary>
public static class DiscoverySourcesFile
{
    private const int MaxManifestBytes = 65_536;
    private const int MaxSourceBytes = 8 * 1024 * 1024;
    private const long MaxTotalBytes = 64L * 1024 * 1024;
    private static readonly HashSet<string> Kinds = new(StringComparer.Ordinal)
    {
        "field-catalog", "typed-wire", "native-position-review", "native-motion-review", "record-set"
    };

    public static async Task<LoadedDiscoverySources> LoadAsync(
        string manifestPath, CancellationToken cancellationToken = default)
    {
        var full = Path.GetFullPath(manifestPath);
        var manifestBytes = await ReadBoundedAsync(full, MaxManifestBytes, cancellationToken);
        ValidateUniqueJson(manifestBytes);
        var manifest = JsonSerializer.Deserialize<DiscoverySourcesDocument>(manifestBytes, JsonFormat.Options)
            ?? throw new InvalidDataException("Discovery source manifest must be a JSON object.");
        if (manifest.SchemaVersion != 1 || manifest.ContractVersion != "discovery-sources/1" ||
            manifest.Sources is null || manifest.Sources.Count is < 1 or > 128 ||
            manifest.Sources.Any(static item => item is null))
            throw new InvalidDataException("Unsupported or empty discovery-sources/1 manifest.");
        var sourceIds = new HashSet<string>(StringComparer.Ordinal);
        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var directory = Path.GetDirectoryName(full)!;
        var sources = new List<VerifiedDiscoverySource>(manifest.Sources.Count);
        long total = 0;
        foreach (var stamp in manifest.Sources)
        {
            cancellationToken.ThrowIfCancellationRequested();
            RequireText(stamp.SourceId, 100, "sourceId");
            if (!sourceIds.Add(stamp.SourceId))
                throw new InvalidDataException($"Duplicate discovery sourceId '{stamp.SourceId}'.");
            if (!Kinds.Contains(stamp.Kind))
                throw new InvalidDataException($"Unsupported discovery source kind '{stamp.Kind}'.");
            if (!paths.Add(stamp.Path))
                throw new InvalidDataException("A discovery source path is repeated.");
            ValidateSha(stamp.Sha256);
            if (stamp.ByteLength is < 1 or > MaxSourceBytes)
                throw new InvalidDataException("Discovery source byte length exceeds limit.");
            total = checked(total + stamp.ByteLength);
            if (total > MaxTotalBytes)
                throw new InvalidDataException("Discovery source byte total exceeds 64 MiB.");
            var child = ResolveChild(directory, stamp.Path);
            var bytes = await ReadBoundedAsync(child, MaxSourceBytes, cancellationToken);
            if (bytes.Length != stamp.ByteLength ||
                !Convert.ToHexString(SHA256.HashData(bytes)).Equals(stamp.Sha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"Discovery source '{stamp.SourceId}' length/SHA-256 mismatch.");
            ValidateUniqueJson(bytes);
            sources.Add(new(new(stamp.SourceId, stamp.Kind, stamp.Path, stamp.ByteLength,
                stamp.Sha256.ToUpperInvariant()), child, bytes));
        }
        return new(Convert.ToHexString(SHA256.HashData(manifestBytes)), sources);
    }

    public static void ValidateSha(string value)
    {
        if (value is null || value.Length != 64 || value.Any(c => !Uri.IsHexDigit(c)))
            throw new InvalidDataException("Expected 64 hex characters for SHA-256.");
    }

    public static void RequireText(string? value, int maxLength, string name)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Length > maxLength || value.Any(char.IsControl))
            throw new InvalidDataException($"Invalid {name}.");
    }

    public static DateTimeOffset Utc(string value)
    {
        if (value is null || !(value.EndsWith("Z", StringComparison.Ordinal) ||
                               value.EndsWith("+00:00", StringComparison.Ordinal)) ||
            !DateTimeOffset.TryParse(value, System.Globalization.CultureInfo.InvariantCulture,
                System.Globalization.DateTimeStyles.None, out var parsed) ||
            parsed.Offset != TimeSpan.Zero)
            throw new InvalidDataException("Discovery observation timestamp requires explicit UTC.");
        return parsed;
    }

    private static string ResolveChild(string directory, string path)
    {
        RequireText(path, 512, "source path");
        if (path.StartsWith("/", StringComparison.Ordinal) || path.Contains('\\') ||
            path.Contains(':') || path.Split('/').Any(segment => segment is "" or "." or ".."))
            throw new InvalidDataException("Discovery source path must be relative without traversal.");
        var current = directory;
        foreach (var part in path.Split('/'))
        {
            current = Path.Combine(current, part);
            if (File.Exists(current) || Directory.Exists(current))
            {
                if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                    throw new InvalidDataException("Discovery source path cannot traverse a link.");
            }
        }
        var result = Path.GetFullPath(current);
        if (!result.StartsWith(Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar) +
                Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Discovery source escapes manifest directory.");
        return result;
    }

    private static async Task<byte[]> ReadBoundedAsync(string path, int maximum, CancellationToken cancellationToken)
    {
        if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("Discovery source link not supported.");
        await using var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read,
            65536, FileOptions.Asynchronous | FileOptions.SequentialScan);
        if (input.Length is < 1 || input.Length > maximum)
            throw new InvalidDataException("Discovery JSON file size outside bound.");
        var bytes = new byte[checked((int)input.Length)];
        await input.ReadExactlyAsync(bytes, cancellationToken);
        if (input.Length != bytes.Length)
            throw new InvalidDataException("Discovery source changed while reading.");
        return bytes;
    }

    private static void ValidateUniqueJson(byte[] bytes)
    {
        using var json = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 16 });
        Visit(json.RootElement);
    }

    private static void Visit(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var member in value.EnumerateObject())
            {
                if (!names.Add(member.Name))
                    throw new InvalidDataException("Duplicate JSON property in discovery evidence.");
                Visit(member.Value);
            }
        }
        else if (value.ValueKind == JsonValueKind.Array)
            foreach (var item in value.EnumerateArray()) Visit(item);
    }

    private sealed record DiscoverySourcesDocument(
        int SchemaVersion, string ContractVersion, IReadOnlyList<DiscoverySourceStamp> Sources);
}
