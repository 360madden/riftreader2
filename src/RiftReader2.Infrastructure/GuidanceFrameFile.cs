using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

/// <summary>Reads one saved RR2L1 envelope for offline guidance calculation.</summary>
public static class GuidanceFrameFile
{
    public static async Task<LiveAddonFrame> ReadAsync(
        string path,
        string sessionId,
        CancellationToken cancellationToken = default)
    {
        var bytes = await AddonFrameFile.ReadBoundedAsync(
            path, LiveAddonEnvelopeDecoder.MaxEnvelopeBytes, cancellationToken);
        return LiveAddonEnvelopeDecoder.Decode(bytes, sessionId);
    }
}
