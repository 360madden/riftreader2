namespace RiftReader2.Infrastructure;

/// <summary>Reads one bounded offline frame. This does not acquire a live addon observation.</summary>
public static class AddonFrameFile
{
    public static async Task<AddonDecodedReport> ReadAsync(string path, CancellationToken cancellationToken = default)
    {
        await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read,
            bufferSize: 4096, FileOptions.Asynchronous | FileOptions.SequentialScan);
        var bytes = new byte[AddonFrameDecoder.MaxFrameBytes + 1];
        var length = 0;
        while (length < bytes.Length)
        {
            var read = await stream.ReadAsync(bytes.AsMemory(length), cancellationToken);
            if (read == 0)
                break;
            length += read;
        }
        cancellationToken.ThrowIfCancellationRequested();
        return AddonDecodedReport.FromFrame(bytes.AsSpan(0, length));
    }
}
