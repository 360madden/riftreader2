using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Tests;

public sealed class MemoryDiscoveryTests
{
    private static readonly NativeProcessIdentity Identity = new(
        42, 638000000000000000, @"C:\RIFT\rift_x64.exe", new string('A', 64), 0x140000000, 0x4000000);

    [Theory]
    [InlineData(MemoryValueKind.Int32, "-123456", 4)]
    [InlineData(MemoryValueKind.UInt32, "4294967290", 4)]
    [InlineData(MemoryValueKind.Int64, "-9000000000000", 8)]
    [InlineData(MemoryValueKind.UInt64, "18446744073709551610", 8)]
    [InlineData(MemoryValueKind.Float32, "12.5", 4)]
    [InlineData(MemoryValueKind.Float64, "-100.25", 8)]
    public void Search_FindsEveryTypedLittleEndianValue(MemoryValueKind kind, string value, int width)
    {
        var bytes = new byte[32];
        WriteValue(bytes.AsSpan(7, width), kind, value);
        var result = MemoryDiscovery.Search(Snapshot(new MemorySnapshotSegment(0x20000, bytes)), kind, value, null, 10, CancellationToken.None);

        var match = Assert.Single(result.Matches);
        Assert.Equal(0x20007UL, match.Address);
        Assert.Equal(width, result.MatchWidth);
        Assert.False(result.Truncated);
    }

    [Fact]
    public void SearchPattern_CrossesAdjacentChunksButNeverHoles()
    {
        var adjacent = Snapshot(new MemorySnapshotSegment(0x20000, [0x11, 0x22]), new MemorySnapshotSegment(0x20002, [0x33, 0x44]));
        var match = Assert.Single(MemoryDiscovery.SearchPattern(adjacent, "22 ?? 44", 10, CancellationToken.None).Matches);
        Assert.Equal(0x20001UL, match.Address);

        var hole = Snapshot(new MemorySnapshotSegment(0x20000, [0x11, 0x22]), new MemorySnapshotSegment(0x20003, [0x33, 0x44]));
        Assert.Empty(MemoryDiscovery.SearchPattern(hole, "22 33", 10, CancellationToken.None).Matches);
    }

    [Fact]
    public void SearchPattern_BoundsDegenerateWildcardWork()
    {
        var pattern = string.Join(' ', Enumerable.Repeat("??", 1024));
        var result = MemoryDiscovery.SearchPattern(
            Snapshot(new MemorySnapshotSegment(0x20000, new byte[70_000])),
            pattern, 100_000, CancellationToken.None);

        Assert.True(result.Truncated);
        Assert.True(result.SearchedBytes < 70_000);
    }

    [Fact]
    public void Search_FloatingToleranceIsFiniteAndResultLimitIsExplicit()
    {
        var bytes = new byte[12];
        BinaryPrimitives.WriteSingleLittleEndian(bytes.AsSpan(0), 5.01f);
        BinaryPrimitives.WriteSingleLittleEndian(bytes.AsSpan(4), 5.02f);
        BinaryPrimitives.WriteSingleLittleEndian(bytes.AsSpan(8), 6f);

        var result = MemoryDiscovery.Search(Snapshot(new MemorySnapshotSegment(0x20000, bytes)), MemoryValueKind.Float32, "5", .03, 1, CancellationToken.None);

        Assert.Single(result.Matches);
        Assert.True(result.Truncated);
        Assert.Throws<ArgumentOutOfRangeException>(() => MemoryDiscovery.Search(
            Snapshot(new MemorySnapshotSegment(0x20000, bytes)), MemoryValueKind.Float32, "5", double.NaN, 1, CancellationToken.None));
        var hugeFiniteTolerance = MemoryDiscovery.Search(
            Snapshot(new MemorySnapshotSegment(0x20000, bytes)), MemoryValueKind.Float32, "5", 1e300, 10, CancellationToken.None);
        Assert.Contains(hugeFiniteTolerance.Matches, match => match.Address == 0x20000);
        Assert.Contains(hugeFiniteTolerance.Matches, match => match.Address == 0x20004);
        Assert.Contains(hugeFiniteTolerance.Matches, match => match.Address == 0x20008);
    }

    [Fact]
    public void Compare_UsesExactEpochAndSuccessfulByteLayout()
    {
        var beforeBytes = new byte[8];
        var afterBytes = new byte[8];
        BinaryPrimitives.WriteInt32LittleEndian(beforeBytes, 10);
        BinaryPrimitives.WriteInt32LittleEndian(afterBytes, 11);
        BinaryPrimitives.WriteInt32LittleEndian(beforeBytes.AsSpan(4), 20);
        BinaryPrimitives.WriteInt32LittleEndian(afterBytes.AsSpan(4), 20);

        var increased = MemoryDiscovery.Compare(
            Snapshot(new MemorySnapshotSegment(0x20000, beforeBytes)), Snapshot(new MemorySnapshotSegment(0x20000, afterBytes)),
            MemoryValueKind.Int32, MemoryComparison.Increased, 10, CancellationToken.None);
        Assert.Contains(increased.Matches, item => item.Address == 0x20000 && item.Value == "11");

        var otherIdentity = Identity with { ProcessStartUtcTicks = Identity.ProcessStartUtcTicks + 1 };
        Assert.Throws<InvalidDataException>(() => MemoryDiscovery.Compare(
            Snapshot(new MemorySnapshotSegment(0x20000, beforeBytes)), new(otherIdentity, [new(0x20000, afterBytes)]),
            MemoryValueKind.Int32, MemoryComparison.Changed, 10, CancellationToken.None));
        Assert.Throws<InvalidDataException>(() => MemoryDiscovery.Compare(
            Snapshot(new MemorySnapshotSegment(0x20000, beforeBytes)), Snapshot(new MemorySnapshotSegment(0x20001, afterBytes)),
            MemoryValueKind.Int32, MemoryComparison.Changed, 10, CancellationToken.None));
    }

    [Fact]
    public void PointerSearch_FindsDeterministicModuleRvaChainWithNonzeroOffsets()
    {
        var root = U64(0x200000);
        var middle = U64(0x300000);
        var snapshot = Snapshot(
            new MemorySnapshotSegment(Identity.ModuleBaseAddress + 0x100, root),
            new MemorySnapshotSegment(0x200020, middle),
            new MemorySnapshotSegment(0x300030, [0xAB]));

        var result = MemoryDiscovery.FindPointerChains(snapshot, 0x300030,
            new(4, 4096, 100, 1000, 1000), CancellationToken.None);

        var chain = Assert.Single(result.Chains);
        Assert.Equal(0x100UL, chain.RootRva);
        Assert.Equal([0x20U, 0x30U], chain.Offsets);
        Assert.False(result.Truncated);
    }

    [Fact]
    public void PointerSearch_ReportsIndexAndCandidateBoundsAndHonorsCancellation()
    {
        var manyRoots = Enumerable.Range(0, 4)
            .Select(index => new MemorySnapshotSegment(Identity.ModuleBaseAddress + (ulong)(index * 8), U64(0x300000)))
            .ToArray();
        var indexLimited = MemoryDiscovery.FindPointerChains(new(Identity, manyRoots), 0x300000,
            new(1, 0, 10, 1, 10), CancellationToken.None);
        Assert.True(indexLimited.IndexTruncated);
        Assert.True(indexLimited.Truncated);

        var candidateLimited = MemoryDiscovery.FindPointerChains(new(Identity, manyRoots), 0x300000,
            new(1, 0, 1, 10, 10), CancellationToken.None);
        Assert.Single(candidateLimited.Chains);
        Assert.True(candidateLimited.Truncated);

        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        Assert.ThrowsAny<OperationCanceledException>(() => MemoryDiscovery.FindPointerChains(
            new(Identity, manyRoots), 0x300000, new(1, 0, 1, 10, 10), cancellation.Token));
    }

    [Fact]
    public void PointerSearch_BoundsDegenerateEdgeExpansion()
    {
        var firstLevel = new byte[500 * 8];
        for (var offset = 0; offset < firstLevel.Length; offset += 8)
            BinaryPrimitives.WriteUInt64LittleEndian(firstLevel.AsSpan(offset), 0x600000);
        var secondLevel = new byte[5000 * 8];
        for (var offset = 0; offset < secondLevel.Length; offset += 8)
            BinaryPrimitives.WriteUInt64LittleEndian(secondLevel.AsSpan(offset), 0x500000);

        var result = MemoryDiscovery.FindPointerChains(Snapshot(
                new MemorySnapshotSegment(0x500000, firstLevel),
                new MemorySnapshotSegment(0x700000, secondLevel)),
            0x600000, new(2, 4096, 10, 10_000, 1_000_000), CancellationToken.None);

        Assert.True(result.Truncated);
        Assert.Empty(result.Chains);
    }

    [Fact]
    public async Task ResolvePointerChain_RebasesRootAndPreservesRawHopsAndTerminalBytes()
    {
        var rebased = Identity with
        {
            ProcessId = 99,
            ProcessStartUtcTicks = Identity.ProcessStartUtcTicks + 100,
            ModuleBaseAddress = 0x150000000
        };
        var session = new FakeSession(rebased, new Dictionary<ulong, NativeReadResult>
        {
            [rebased.ModuleBaseAddress + 0x100] = Success(U64(0x400000)),
            [0x400020] = Success(U64(0x500000)),
            [0x500030] = Success([1, 2, 3, 4])
        });

        var result = await MemoryDiscovery.ResolvePointerChainAsync(
            new(0x100, [0x20, 0x30]), rebased, session, 4, CancellationToken.None);

        Assert.Equal("complete", result.Status);
        Assert.Equal(2, result.Hops.Count);
        Assert.Equal(rebased.ModuleBaseAddress + 0x100, result.Hops[0].PointerAddress);
        Assert.Equal(0x500030UL, result.TerminalAddress);
        Assert.Equal([1, 2, 3, 4], result.TerminalRead!.Bytes);
        Assert.Equal(2, session.RevalidationCount);
    }

    [Fact]
    public async Task ResolvePointerChain_FailsClosedForIdentityDriftMissingBytesAndInvalidPointer()
    {
        var mismatchSession = new FakeSession(Identity with { ProcessId = 43 }, new Dictionary<ulong, NativeReadResult>());
        var mismatch = await MemoryDiscovery.ResolvePointerChainAsync(
            new(0x100, [0]), Identity, mismatchSession, 4, CancellationToken.None);
        Assert.Equal("identity-mismatch", mismatch.Status);
        Assert.Empty(mismatchSession.Addresses);

        var missingSession = new FakeSession(Identity, new Dictionary<ulong, NativeReadResult>
        {
            [Identity.ModuleBaseAddress + 0x100] = new("unavailable", [], 299, "Unreadable page.")
        });
        var missing = await MemoryDiscovery.ResolvePointerChainAsync(
            new(0x100, [0]), Identity, missingSession, 4, CancellationToken.None);
        Assert.Equal("read-failed", missing.Status);
        Assert.Null(missing.TerminalRead);
        Assert.Equal(Identity.ModuleBaseAddress + 0x100, missing.FailedReadAddress);
        Assert.Equal(299, missing.FailedRead!.Win32ErrorCode);
        Assert.Equal(2, missingSession.RevalidationCount);

        var invalidSession = new FakeSession(Identity, new Dictionary<ulong, NativeReadResult>
        {
            [Identity.ModuleBaseAddress + 0x100] = Success(U64(0))
        });
        var invalid = await MemoryDiscovery.ResolvePointerChainAsync(
            new(0x100, [0]), Identity, invalidSession, 4, CancellationToken.None);
        Assert.Equal("invalid-pointer", invalid.Status);
        Assert.Equal(2, invalidSession.RevalidationCount);

        var invalidatedSession = new FakeSession(Identity, new Dictionary<ulong, NativeReadResult>
        {
            [Identity.ModuleBaseAddress + 0x100] = new("unavailable", [], 299, "Process disappeared.")
        })
        { FailRevalidationAt = 2 };
        var invalidated = await MemoryDiscovery.ResolvePointerChainAsync(
            new(0x100, [0]), Identity, invalidatedSession, 4, CancellationToken.None);
        Assert.Equal("identity-invalidated", invalidated.Status);
        Assert.Equal("Process identity changed.", invalidated.Reason);
        Assert.NotNull(invalidated.FailedRead);
    }

    [Fact]
    public void SnapshotValidation_RejectsOverlapOverflowAndMoreThan64MiB()
    {
        Assert.Throws<InvalidDataException>(() => MemoryDiscovery.SearchPattern(
            Snapshot(new MemorySnapshotSegment(0x20000, [1, 2]), new MemorySnapshotSegment(0x20001, [3])), "01", 1, CancellationToken.None));
        Assert.Throws<InvalidDataException>(() => MemoryDiscovery.SearchPattern(
            Snapshot(new MemorySnapshotSegment(0x20000, new byte[(32 * 1024 * 1024) + 1]), new MemorySnapshotSegment(0x3000000, new byte[32 * 1024 * 1024])),
            "01", 1, CancellationToken.None));
    }

    private static MemorySnapshot Snapshot(params MemorySnapshotSegment[] segments) => new(Identity, segments);
    private static byte[] U64(ulong value) { var bytes = new byte[8]; BinaryPrimitives.WriteUInt64LittleEndian(bytes, value); return bytes; }
    private static NativeReadResult Success(byte[] bytes) => new("success", bytes, null, null);

    private static void WriteValue(Span<byte> bytes, MemoryValueKind kind, string value)
    {
        switch (kind)
        {
            case MemoryValueKind.Int32: BinaryPrimitives.WriteInt32LittleEndian(bytes, int.Parse(value)); break;
            case MemoryValueKind.UInt32: BinaryPrimitives.WriteUInt32LittleEndian(bytes, uint.Parse(value)); break;
            case MemoryValueKind.Int64: BinaryPrimitives.WriteInt64LittleEndian(bytes, long.Parse(value)); break;
            case MemoryValueKind.UInt64: BinaryPrimitives.WriteUInt64LittleEndian(bytes, ulong.Parse(value)); break;
            case MemoryValueKind.Float32: BinaryPrimitives.WriteSingleLittleEndian(bytes, float.Parse(value)); break;
            case MemoryValueKind.Float64: BinaryPrimitives.WriteDoubleLittleEndian(bytes, double.Parse(value)); break;
        }
    }

    private sealed class FakeSession(NativeProcessIdentity identity, IReadOnlyDictionary<ulong, NativeReadResult> reads) : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; } = identity;
        public string? RevalidationFailure { get; init; }
        public int? FailRevalidationAt { get; init; }
        public int RevalidationCount { get; private set; }
        public List<ulong> Addresses { get; } = [];
        public NativeReadResult Read(ulong address, int byteLength)
        {
            Addresses.Add(address);
            return reads.TryGetValue(address, out var result)
                ? result
                : new("unavailable", [], null, "Address was not present in the fixture.");
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            RevalidationCount++;
            return ValueTask.FromResult(FailRevalidationAt == RevalidationCount
                ? "Process identity changed."
                : RevalidationFailure);
        }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
