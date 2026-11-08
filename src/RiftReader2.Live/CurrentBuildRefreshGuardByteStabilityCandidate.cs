using System.Buffers.Binary;

namespace RiftReader2.Live;

/// <summary>
/// Pure comparison of two separately supplied 9-byte snapshots of a position
/// component's +0x100 handle (uint64 LE) and +0x108 flag (byte).
/// No process reads, owner lookup, writer call, or game input occur here.
/// </summary>
internal static class CurrentBuildRefreshGuardByteStabilityCandidate
{
    internal const int SnapshotLength = 9;

    internal sealed record Result(
        string Status,
        bool SequentiallyStable,
        string? RefreshHandleHex,
        byte? RefreshFlagRaw,
        string? RefreshGuardStatus)
    {
        public string Qualification =>
            "candidate-only; byte equality across two supplied snapshots is non-atomic, " +
            "cannot exclude ABA, and does not prove same owner/process epoch, " +
            "writer execution, API independence, passive freshness, motion or facing";
    }

    internal static Result Compare(byte[]? first, byte[]? second)
    {
        if (first is null)
            return Unavailable("first-snapshot-unavailable");
        if (second is null)
            return Unavailable("second-snapshot-unavailable");
        if (first.Length != SnapshotLength || second.Length != SnapshotLength)
            return Unavailable("snapshot-length-invalid");
        if (!first.AsSpan().SequenceEqual(second))
            return Unavailable("guard-bytes-changed");

        var handle = BinaryPrimitives.ReadUInt64LittleEndian(second.AsSpan(0, 8));
        var flag = second[8];
        var guard = handle != 0
            ? "handle-present-guard-candidate"
            : flag != 0 ? "alternate-flag-guard-candidate" : "guard-ineligible-candidate";
        return new("guard-bytes-stable-sequential-candidate", true,
            $"0x{handle:X16}", flag, guard);
    }

    private static Result Unavailable(string status) => new(status, false, null, null, null);
}
