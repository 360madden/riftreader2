namespace RiftReader2.Live.Control;

internal sealed record ControlCaptureResponse(
    string CaptureId, DesktopTarget Target, string ImageFormat, string ImageBase64,
    string Sha256, DateTimeOffset CapturedAtUtc, int ReviewExpiresInSeconds, string CaptureBackend)
{
    // Construct the journal's metadata before serialization: the large image must
    // never enter its JSON tree. The authenticated wire response retains it.
    internal object RetainedMetadata() => new
    {
        CaptureId,
        Target,
        ImageFormat,
        Sha256,
        CapturedAtUtc,
        ReviewExpiresInSeconds,
        CaptureBackend
    };
}
