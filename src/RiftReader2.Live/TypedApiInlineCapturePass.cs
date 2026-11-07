using RiftReader2.Application;

namespace RiftReader2.Live;

/// <summary>One exact-process scout pass and immediately attempted neighborhood copies.</summary>
public sealed record TypedApiInlineCandidate(
    string MarkerAddress,
    string Status,
    string? Reason,
    TypedApiImmediateNeighborhoodResult? Neighborhood);

public sealed record TypedApiInlineCapturePassResult(
    TypedApiScoutResult Scout,
    int MaxCopiedCandidates,
    int CopiedCandidates,
    IReadOnlyList<TypedApiInlineCandidate> Candidates)
{
    public bool CopyLimited => Candidates.Any(candidate => candidate.Status == "copy-budget-exceeded");
}

/// <summary>
/// Pure orchestration over read-only delegates: scans up to the caller's fixed
/// byte/time/match limits and, during the scanner callback, copies any candidate
/// still immediately followed by an opening JSON brace. Does not write outputs.
/// </summary>
public static class TypedApiInlineCapturePass
{
    public const int MaxCopies = 8;

    public static TypedApiInlineCapturePassResult Run(
        string marker,
        IReadOnlyList<WindowsMemoryRegion> regions,
        ulong startAddress,
        long maxScanBytes,
        int maxMatchCount,
        int maxCopiedCandidates,
        Func<ulong, byte[], int, TypedApiScanReadResult> scanRead,
        Func<ulong, int, NativeReadResult> neighborhoodRead,
        Func<bool> timeBudgetExceeded,
        Func<string>? utcNow = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(neighborhoodRead);
        ArgumentNullException.ThrowIfNull(timeBudgetExceeded);
        if (maxCopiedCandidates is < 1 or > MaxCopies)
            throw new ArgumentOutOfRangeException(nameof(maxCopiedCandidates));

        var candidates = new List<TypedApiInlineCandidate>();
        var copied = 0;
        var scout = TypedApiPrefixScout.Scan(marker,
            regions, startAddress, maxScanBytes, maxMatchCount,
            scanRead, timeBudgetExceeded, cancellationToken,
            onMatch: address =>
            {
                var markerAddress = $"0x{address:X}";
                if (copied >= maxCopiedCandidates)
                {
                    candidates.Add(new(markerAddress, "copy-budget-exceeded",
                        "The declared maximum number of candidate neighborhood copies was reached.", null));
                    return;
                }

                TypedApiImmediateNeighborhoodResult probe;
                try
                {
                    probe = TypedApiImmediateNeighborhood.Capture(marker,
                        address, neighborhoodRead, timeBudgetExceeded, utcNow, cancellationToken);
                }
                catch (ArgumentOutOfRangeException)
                {
                    // An address at the user-range edge cannot fit the fixed
                    // before/after window. Retain an explicit declined result.
                    candidates.Add(new(markerAddress, "window-out-of-range",
                        "The marker is too near a user address boundary for this window.", null));
                    return;
                }

                if (probe.Chunks.Count > 0)
                    copied++;
                candidates.Add(new(markerAddress, probe.Status, probe.Reason,
                    probe.Chunks.Count == 0 ? null : probe));
            });

        return new(scout, maxCopiedCandidates, copied, candidates);
    }
}
