using System.Security.Cryptography;

namespace RiftReader2.Infrastructure;

public sealed record LiveAddonDecodedReport(
    int SchemaVersion,
    string SessionId,
    string BindingStatus,
    string FreshnessStatus,
    string EnvelopeSha256,
    AddonDecodedReport Addon);

/// <summary>Decodes a saved envelope without asserting live process binding or freshness.</summary>
public static class LiveAddonFrameFile
{
    public static async Task<LiveAddonDecodedReport> ReadAsync(string path, string sessionId, CancellationToken cancellationToken = default)
    {
        var bytes = await AddonFrameFile.ReadBoundedAsync(path, LiveAddonEnvelopeDecoder.MaxEnvelopeBytes, cancellationToken);
        LiveAddonEnvelopeDecoder.Decode(bytes, sessionId);
        LiveAddonEnvelopeDecoder.ReadChallenge(bytes, out var addonFrame);
        var addon = AddonDecodedReport.FromFrame(addonFrame);
        return new(1, sessionId, "unbound", "unverified", Convert.ToHexString(SHA256.HashData(bytes)), addon);
    }
}
