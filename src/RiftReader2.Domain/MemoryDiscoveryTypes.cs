namespace RiftReader2.Domain;

public sealed record MemorySnapshotSegment(ulong StartAddress, byte[] Bytes);

public sealed record MemorySnapshot(
    NativeProcessIdentity Identity,
    IReadOnlyList<MemorySnapshotSegment> Segments);

public enum MemoryValueKind
{
    Int32,
    UInt32,
    Int64,
    UInt64,
    Float32,
    Float64
}

public enum MemoryComparison
{
    Changed,
    Unchanged,
    Increased,
    Decreased
}

public sealed record MemorySearchMatch(ulong Address, string Value);

public sealed record MemorySearchResult(
    long SearchedBytes,
    int MatchWidth,
    IReadOnlyList<MemorySearchMatch> Matches,
    bool Truncated);

public sealed record MemoryPointerSearchOptions(
    int MaxDepth,
    uint MaxOffset,
    int MaxCandidates,
    int MaxIndexEntries,
    int MaxFrontier);

public sealed record MemoryPointerChain(
    ulong RootRva,
    IReadOnlyList<uint> Offsets);

public sealed record MemoryPointerSearchResult(
    IReadOnlyList<MemoryPointerChain> Chains,
    bool Truncated,
    bool IndexTruncated);

public sealed record MemoryReadEvidence(
    string Status,
    byte[] Bytes,
    int? Win32ErrorCode,
    string? Reason);

public sealed record PointerResolutionHop(
    int Level,
    ulong PointerAddress,
    byte[] PointerBytes,
    ulong PointerValue,
    uint Offset,
    ulong ResolvedAddress);

public sealed record PointerResolutionResult(
    string Status,
    string? Reason,
    NativeProcessIdentity ExpectedIdentity,
    NativeProcessIdentity ObservedIdentity,
    IReadOnlyList<PointerResolutionHop> Hops,
    ulong? TerminalAddress,
    MemoryReadEvidence? TerminalRead,
    ulong? FailedReadAddress,
    MemoryReadEvidence? FailedRead);
