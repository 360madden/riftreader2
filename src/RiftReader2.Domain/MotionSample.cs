namespace RiftReader2.Domain;

/// <summary>
/// A single observed pose sample from one identified capture session.
/// </summary>
public sealed record MotionSample(
    string SessionId,
    long Sequence,
    double TimestampSeconds,
    double X,
    double Y,
    double Z,
    double YawRadians);
