namespace RiftReader2.Infrastructure;

internal static class BoundedJson
{
    public static async Task<byte[]> ReadAsync(string path, CancellationToken cancellationToken)
    {
        await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (stream.Length > 65536)
            throw new InvalidDataException("JSON metadata exceeds 65536 bytes.");
        using var buffer = new MemoryStream();
        await stream.CopyToAsync(buffer, cancellationToken);
        return buffer.ToArray();
    }
}
