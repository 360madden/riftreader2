using System.Net;
using System.Text.Json;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

public sealed record LiveConfiguration(
    int SchemaVersion,
    string ProcessName,
    int DurationSeconds,
    int PollIntervalMilliseconds,
    long MaxScanBytes,
    int MaxScanSeconds,
    string? OutputPath,
    int FreshnessTimeoutSeconds,
    LiveDeliveryConfiguration? Delivery)
{
    public const string FileName = "riftreader2-live.json";
    // Optional experimental tuning. Existing files and default sessions stay at 64 KiB.
    public int FullScanChunkKiB { get; init; } = 64;

    public static LiveConfiguration LoadBesideExecutable()
    {
        var path = Path.Combine(AppContext.BaseDirectory, FileName);
        if (!File.Exists(path))
            return Defaults;
        byte[] bytes;
        using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
        using (var buffer = new MemoryStream(65_537))
        {
            var chunk = new byte[8192];
            while (buffer.Length <= 65_536)
            {
                var read = stream.Read(chunk, 0, (int)Math.Min(chunk.Length, 65_537 - buffer.Length));
                if (read == 0)
                    break;
                buffer.Write(chunk, 0, read);
            }
            if (buffer.Length > 65_536 || stream.ReadByte() != -1)
                throw new InvalidDataException($"{FileName} exceeds 65536 bytes.");
            bytes = buffer.ToArray();
        }
        var configuration = JsonSerializer.Deserialize<LiveConfiguration>(bytes, JsonFormat.Options)
            ?? throw new InvalidDataException($"{FileName} cannot be null.");
        configuration.Validate();
        return configuration;
    }

    public static LiveConfiguration Defaults { get; } = new(
        1,
        "rift_x64",
        300,
        500,
        4L * 1024 * 1024 * 1024,
        10,
        null,
        5,
        null);

    public void Validate()
    {
        if (SchemaVersion != 1)
            throw new InvalidDataException("Live configuration schemaVersion must be 1.");
        if (!string.Equals(ProcessName, "rift_x64", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("processName must be rift_x64.");
        if (DurationSeconds is < 1 or > 3600)
            throw new InvalidDataException("durationSeconds must be from 1 through 3600.");
        if (PollIntervalMilliseconds is < 250 or > 60_000)
            throw new InvalidDataException("pollIntervalMilliseconds must be from 250 through 60000.");
        if (MaxScanBytes is < 1 or > 8L * 1024 * 1024 * 1024)
            throw new InvalidDataException("maxScanBytes must be from 1 through 8589934592.");
        if (MaxScanSeconds is < 1 or > 60)
            throw new InvalidDataException("maxScanSeconds must be from 1 through 60.");
        if (FullScanChunkKiB is not (64 or 256))
            throw new InvalidDataException("fullScanChunkKiB must be 64 or 256.");
        if (FreshnessTimeoutSeconds is < 1 or > 60)
            throw new InvalidDataException("freshnessTimeoutSeconds must be from 1 through 60.");
        if (OutputPath is { Length: > 1024 })
            throw new InvalidDataException("outputPath exceeds 1024 characters.");
        Delivery?.Validate();
    }

    public string ResolveOutputPath() => string.IsNullOrWhiteSpace(OutputPath)
        ? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "RiftReader2",
            "Live",
            "latest.json")
        : Path.GetFullPath(OutputPath, AppContext.BaseDirectory);
}

public sealed record LiveDeliveryConfiguration(string Endpoint, string Token)
{
    public void Validate()
    {
        if (!TryValidateEndpoint(Endpoint, out _, out var error))
            throw new InvalidDataException(error);
        if (string.IsNullOrWhiteSpace(Token) || Token.Length < 32 || Token.Length > 512)
            throw new InvalidDataException("delivery.token must contain 32 through 512 characters.");
    }

    public Uri GetValidatedEndpoint()
    {
        if (!TryValidateEndpoint(Endpoint, out var endpoint, out var error))
            throw new InvalidDataException(error);
        return endpoint!;
    }

    private static bool TryValidateEndpoint(string raw, out Uri? endpoint, out string error)
    {
        endpoint = null;
        error = string.Empty;
        if (!Uri.TryCreate(raw, UriKind.Absolute, out var uri) || uri.Scheme != Uri.UriSchemeHttp)
        {
            error = "delivery.endpoint must be an absolute HTTP URL.";
            return false;
        }
        if (!IPAddress.TryParse(uri.Host, out var address) ||
            address.AddressFamily != System.Net.Sockets.AddressFamily.InterNetwork)
        {
            error = "delivery.endpoint host must be a literal private IPv4 address.";
            return false;
        }
        var bytes = address.GetAddressBytes();
        var privateAddress = bytes[0] == 10 ||
            (bytes[0] == 172 && bytes[1] is >= 16 and <= 31) ||
            (bytes[0] == 192 && bytes[1] == 168);
        if (!privateAddress || uri.AbsolutePath != "/observation" ||
            !string.IsNullOrEmpty(uri.Query) || !string.IsNullOrEmpty(uri.Fragment) ||
            !string.IsNullOrEmpty(uri.UserInfo))
        {
            error = "delivery.endpoint must be a private IPv4 /observation URL without credentials, query, or fragment.";
            return false;
        }
        endpoint = uri;
        return true;
    }
}
