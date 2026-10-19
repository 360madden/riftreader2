using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

/// <summary>Owns the verified samples handle until replay is complete.</summary>
public sealed class CaptureReader : IAsyncDisposable
{
    private readonly FileStream stream;
    private bool consumed;

    private CaptureReader(CaptureManifest manifest, string manifestSha256, FileStream stream)
    {
        Manifest = manifest;
        ManifestSha256 = manifestSha256;
        this.stream = stream;
    }

    public CaptureManifest Manifest { get; }
    public string ManifestSha256 { get; }

    public static async Task<CaptureReader> OpenAsync(string manifestPath, long maxCaptureBytes, CancellationToken cancellationToken = default)
    {
        if (maxCaptureBytes <= 0)
            throw new ArgumentOutOfRangeException(nameof(maxCaptureBytes));
        var bytes = await BoundedJson.ReadAsync(manifestPath, cancellationToken);
        var manifest = JsonSerializer.Deserialize<CaptureManifest>(bytes, JsonFormat.Options)
            ?? throw new InvalidDataException("Manifest cannot be null.");
        manifest.Validate();
        var samplesPath = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(manifestPath))!, manifest.SamplesFile);
        if ((File.GetAttributes(samplesPath) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("Samples must be a regular file, not a symbolic link or junction.");
        var stream = new FileStream(samplesPath, FileMode.Open, FileAccess.Read, FileShare.Read, 65536, FileOptions.Asynchronous | FileOptions.SequentialScan);
        try
        {
            if (stream.Length > maxCaptureBytes)
                throw new InvalidDataException($"Capture exceeds configured {maxCaptureBytes} byte limit.");
            var actualHash = Convert.ToHexString(await SHA256.HashDataAsync(stream, cancellationToken));
            if (!actualHash.Equals(manifest.SamplesSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Capture SHA-256 does not match the manifest.");
            stream.Position = 0;
            return new(manifest, Convert.ToHexString(SHA256.HashData(bytes)), stream);
        }
        catch
        {
            await stream.DisposeAsync();
            throw;
        }
    }

    public async IAsyncEnumerable<MotionSample> ReadSamplesAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        if (consumed)
            throw new InvalidOperationException("Open a new capture reader for each replay.");
        consumed = true;
        using var reader = new StreamReader(stream, new UTF8Encoding(false, true), detectEncodingFromByteOrderMarks: false, bufferSize: 4096, leaveOpen: true);
        var buffer = new char[4096];
        var line = new StringBuilder();
        var lineNumber = 1;
        int read;
        while ((read = await reader.ReadAsync(buffer.AsMemory(), cancellationToken)) != 0)
        {
            for (var i = 0; i < read; i++)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (buffer[i] == '\n')
                {
                    yield return ParseLine(line.ToString(), lineNumber++);
                    line.Clear();
                }
                else
                {
                    if (line.Length >= 16384)
                        throw new InvalidDataException($"Sample line {lineNumber} exceeds 16384 characters.");
                    line.Append(buffer[i]);
                }
            }
        }
        if (line.Length > 0)
            yield return ParseLine(line.ToString(), lineNumber);
    }

    private MotionSample ParseLine(string line, int number)
    {
        try
        {
            var sample = JsonSerializer.Deserialize<MotionSample>(line, JsonFormat.Options)
                ?? throw new InvalidDataException($"Sample line {number} is null.");
            if (sample.SessionId != Manifest.SessionId)
                throw new InvalidDataException($"Sample line {number} has a different session from its manifest.");
            return sample;
        }
        catch (JsonException ex)
        {
            throw new InvalidDataException($"Invalid JSON at sample line {number}: {ex.Message}", ex);
        }
    }

    public ValueTask DisposeAsync() => stream.DisposeAsync();
}
