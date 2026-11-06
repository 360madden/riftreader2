namespace RiftReader2.Domain;

public enum NativeAddressKind
{
    ModuleRelative,
    Absolute
}

public sealed record NativeCaptureRange(
    string Id,
    NativeAddressKind AddressKind,
    ulong Address,
    int ByteLength);

public sealed record NativeCapturePlan(
    int ProcessId,
    long ProcessStartUtcTicks,
    string ExecutableSha256,
    IReadOnlyList<NativeCaptureRange> Ranges,
    int SampleCount,
    int IntervalMilliseconds,
    int MaxDurationMilliseconds);

public sealed record NativeProcessIdentity(
    int ProcessId,
    long ProcessStartUtcTicks,
    string ExecutablePath,
    string ExecutableSha256,
    ulong ModuleBaseAddress,
    ulong ModuleSize);

public sealed record NativeRangeCapture(
    string RangeId,
    string AddressKind,
    string RequestedAddress,
    string ResolvedAddress,
    int RequestedByteLength,
    string Status,
    int BytesRead,
    string? BytesBase64,
    string? BytesSha256,
    int? Win32ErrorCode,
    string? Reason);

public sealed record NativeCaptureSample(
    long Sequence,
    string StartedAtUtc,
    string CompletedAtUtc,
    double MonotonicStartMilliseconds,
    double MonotonicEndMilliseconds,
    IReadOnlyList<NativeRangeCapture> Ranges);

public sealed record NativeCaptureSummary(
    Guid CaptureId,
    string Status,
    string? Reason,
    NativeProcessIdentity Identity,
    string StartedAtUtc,
    string CompletedAtUtc,
    double ElapsedMilliseconds,
    int RequestedSampleCount,
    int AttemptedSampleCount,
    int SuccessfulSampleCount,
    IReadOnlyList<NativeCaptureSample> Samples);
