using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

/// <summary>
/// A bounded, read-only copy made while the prefix scout still holds the target
/// process handle. A plausible marker is not a parsed, fresh typed Lua frame.
/// </summary>
public sealed record TypedApiImmediateNeighborhoodResult(
    string Status,
    string? Reason,
    string MarkerAddress,
    string WindowStart,
    string StartedAtUtc,
    string CompletedAtUtc,
    IReadOnlyList<NativeMemorySnapshotChunk> Chunks)
{
    /// <summary>Wrap a real capture in the existing strict snapshot contract.</summary>
    public NativeMemorySnapshotFile ToSnapshotFile(
        NativeMemorySnapshotSource source,
        NativeProcessIdentity identity)
    {
        if (Status is not ("complete" or "partial" or "failed" or "time-budget-exceeded") ||
            Chunks.Count == 0)
            throw new InvalidOperationException("No captured memory chunks can be published as a native snapshot.");
        return new NativeMemorySnapshotFile(
            1, "native-memory-snapshot/1", source, identity,
            StartedAtUtc, CompletedAtUtc, Status, Reason, Chunks,
            [
                "The memory was copied via read-only 4096-byte ReadProcessMemory calls immediately after its scout prefix was noticed.",
                "The prefixed JSON opening brace is a cheap plausibility gate, not a parsed, current or advancing typed Lua frame.",
                "All addresses are valid only for the exact RIFT process epoch; missing chunks are never zero-filled."
            ]);
    }
}

/// <summary>
/// Stateless capture primitive for an in-scout match callback. It performs at
/// most one 11-byte plausibility read and seven 4096-byte neighborhood reads.
/// It never sleeps, scans additional memory or publishes an output by itself.
/// </summary>
public static class TypedApiImmediateNeighborhood
{
    public const int PageBytes = 4096;
    public const int PagesBefore = 2;
    public const int PagesAfter = 4;
    public const int WindowBytes = (PagesBefore + 1 + PagesAfter) * PageBytes;

    private const ulong MinUserAddress = 0x10000;
    private const ulong MaxUserEnd = 0x00007FFF_FFFF_FFFF;

    public static TypedApiImmediateNeighborhoodResult Capture(
        ulong prefixAddress,
        Func<ulong, int, NativeReadResult> read,
        Func<bool> timeBudgetExceeded,
        Func<string>? utcNow = null,
        CancellationToken cancellationToken = default,
        string marker = TypedApiPrefixMatcher.MarkerText)
    {
        var plausibleStart = Encoding.ASCII.GetBytes(TypedApiPrefixMatcher.ValidateMarker(marker) + "{");
        ArgumentNullException.ThrowIfNull(read);
        ArgumentNullException.ThrowIfNull(timeBudgetExceeded);
        utcNow ??= () => DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture);

        if (prefixAddress < MinUserAddress + PagesBefore * PageBytes ||
            prefixAddress > MaxUserEnd - (PagesAfter + 1UL) * PageBytes)
            throw new ArgumentOutOfRangeException(nameof(prefixAddress),
                "Prefix is too near a supported user-address boundary for the 28 KiB window.");

        var windowStart = (prefixAddress & ~(ulong)(PageBytes - 1)) - PagesBefore * PageBytes;
        if (windowStart < MinUserAddress ||
            checked(windowStart + (ulong)WindowBytes) > MaxUserEnd)
            throw new ArgumentOutOfRangeException(nameof(prefixAddress));

        var started = utcNow();
        TypedApiImmediateNeighborhoodResult Finish(
            string status, string? reason, IReadOnlyList<NativeMemorySnapshotChunk> chunks) =>
            new(status, reason, $"0x{prefixAddress:X}", $"0x{windowStart:X}",
                started, utcNow(), chunks);

        cancellationToken.ThrowIfCancellationRequested();
        if (timeBudgetExceeded())
            return Finish("time-budget-exceeded", "Capture budget expired before prefix recheck.", []);

        // A stale, static or binary-laden marker is not worth an expensive
        // 28 KiB copy. Reject it without claiming anything about other heaps.
        var header = read(prefixAddress, plausibleStart.Length);
        if (header.Status != "success" || header.Bytes.Length != plausibleStart.Length)
            return Finish("header-unavailable", "The marker plus JSON opening brace could not be re-read completely.", []);
        if (!plausibleStart.AsSpan().SequenceEqual(header.Bytes))
            return Finish("prefix-not-plausible", "The observed marker is not immediately followed by '{' at recheck.", []);

        var chunks = new List<NativeMemorySnapshotChunk>(PagesBefore + 1 + PagesAfter);
        var budgetExceeded = false;
        for (var page = 0; page < PagesBefore + 1 + PagesAfter; page++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (timeBudgetExceeded())
            {
                budgetExceeded = true;
                break;
            }

            var address = checked(windowStart + (ulong)(page * PageBytes));
            var result = read(address, PageBytes);
            if (result.Status is not ("success" or "partial" or "unavailable") ||
                result.Bytes is null || result.Bytes.Length > PageBytes ||
                (result.Status == "success" && result.Bytes.Length != PageBytes) ||
                (result.Status == "unavailable" && result.Bytes.Length != 0) ||
                (result.Status == "partial" && result.Bytes.Length is 0 or PageBytes))
                throw new InvalidDataException("Read-only native memory reader returned an inconsistent capture chunk.");
            chunks.Add(new NativeMemorySnapshotChunk(
                $"0x{address:X}",
                PageBytes,
                result.Status,
                result.Bytes.Length,
                result.Bytes.Length == 0 ? null : Convert.ToBase64String(result.Bytes),
                result.Bytes.Length == 0 ? null : Convert.ToHexString(SHA256.HashData(result.Bytes)),
                result.Win32ErrorCode,
                result.Reason));
        }

        budgetExceeded |= timeBudgetExceeded();
        var successes = chunks.Count(chunk => chunk.Status == "success");
        var status = budgetExceeded ? "time-budget-exceeded" :
            successes == PagesBefore + 1 + PagesAfter ? "complete" :
            successes > 0 ? "partial" : "failed";
        var reason = status switch
        {
            "complete" => null,
            "time-budget-exceeded" => "Capture stopped at the declared read-only time budget.",
            "partial" => "At least one neighborhood page was inaccessible or partial.",
            _ => "No neighborhood page was read completely."
        };
        return Finish(status, reason, chunks);
    }
}
