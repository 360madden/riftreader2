namespace RiftReader2.Domain;

/// <summary>A named numeric value supplied by an independent observation source.</summary>
public sealed record NativeValueReference(
    string Name,
    MemoryValueKind Kind,
    string Value,
    double Tolerance);

/// <summary>One exact-process, bounded pass over private readable memory.</summary>
public sealed record NativeValueScoutPlan(
    int ProcessId,
    long ProcessStartUtcTicks,
    string ExecutableSha256,
    ulong StartAddress,
    IReadOnlyList<NativeValueReference> References,
    int ContextBeforeBytes,
    int ContextAfterBytes,
    long MaxScanBytes,
    int MaxDurationMilliseconds,
    int MaxRegionCount,
    int MaxMatchCount);

public readonly record struct NativeValueScanReadResult(bool Complete, int BytesRead, int? Win32Error);

public sealed record NativeValueScanRegion(ulong BaseAddress, ulong RegionSize, uint Type);

public sealed record NativeValueScanSpan(ulong BaseAddress, long ByteLength);

public sealed record NativeValueScanHole(ulong BaseAddress, int ByteLength, string Reason, int? Win32Error);

public sealed record NativeValueScanMatch(
    ulong Address,
    int Width,
    IReadOnlyList<string> ReferenceNames);

public sealed record NativeValueScanResult(
    string Status,
    string? Reason,
    ulong StartAddress,
    ulong? NextAddress,
    long EligiblePrivateBytes,
    long AttemptedBytes,
    long ExaminedBytes,
    int EligiblePrivateRegionCount,
    int TouchedPrivateRegionCount,
    IReadOnlyList<NativeValueScanMatch> Matches,
    IReadOnlyList<NativeValueScanSpan> CoveredSpans,
    IReadOnlyList<NativeValueScanHole> Holes);
