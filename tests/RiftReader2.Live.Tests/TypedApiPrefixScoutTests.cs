using System.Runtime.InteropServices;
using System.Text;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class TypedApiPrefixScoutTests
{
    private const ulong Base = 0x10000;
    private const uint Private = 0x20000;
    private const uint Image = 0x1000000;
    private static readonly byte[] Marker = Encoding.ASCII.GetBytes(TypedApiPrefixMatcher.MarkerText);

    [Fact]
    public void Scan_CompleteScopeFindsActualPrefixAddressesWithoutFrameClaims()
    {
        var memory = new byte[128];
        Marker.CopyTo(memory.AsSpan(7));
        Marker.CopyTo(memory.AsSpan(37));

        var result = Scan(memory);

        Assert.Equal("complete", result.Status);
        Assert.Null(result.NextAddress);
        Assert.Equal(new ulong[] { Base + 7, Base + 37 }, result.PrefixAddresses);
        Assert.Equal(memory.Length, result.EligiblePrivateBytes);
        Assert.Equal(memory.Length, result.AttemptedBytes);
        Assert.Equal(memory.Length, result.ExaminedBytes);
        Assert.Equal(new TypedApiScanSpan(Base, memory.Length), Assert.Single(result.CoveredSpans));
        Assert.Empty(result.Holes);
    }

    [Fact]
    public void Scan_AcrossSixtyFourKilobyteBoundaryRetainsMarker()
    {
        var memory = new byte[TypedApiPrefixScout.ChunkBytes + 60];
        const int start = TypedApiPrefixScout.ChunkBytes - 4;
        Marker.CopyTo(memory.AsSpan(start));

        var result = Scan(memory);

        Assert.Equal("complete", result.Status);
        Assert.Equal(Base + start, Assert.Single(result.PrefixAddresses));
        Assert.Equal(memory.Length, Assert.Single(result.CoveredSpans).ByteLength);
    }

    [Fact]
    public void Scan_ByteCapIsPartialAndCursorOverlapRecoversSplitMarkerOnNextPass()
    {
        var memory = new byte[2 * TypedApiPrefixScout.ChunkBytes];
        const int start = TypedApiPrefixScout.ChunkBytes - 4;
        Marker.CopyTo(memory.AsSpan(start));

        var first = Scan(memory, maxScanBytes: TypedApiPrefixScout.ChunkBytes);
        var second = Scan(memory, first.NextAddress!.Value, TypedApiPrefixScout.ChunkBytes);

        Assert.Equal("partial", first.Status);
        Assert.Equal("byte-budget-exceeded", first.Reason);
        Assert.Empty(first.PrefixAddresses);
        Assert.Equal(Base + TypedApiPrefixScout.ChunkBytes - (ulong)(Marker.Length - 1), first.NextAddress);
        Assert.Equal(Base + start, Assert.Single(second.PrefixAddresses));
        Assert.True(second.ExaminedBytes <= TypedApiPrefixScout.ChunkBytes);
    }

    [Fact]
    public void Scan_DoesNotSearchImageOrMappedRegions()
    {
        var imageMemory = new byte[Marker.Length];
        Marker.CopyTo(imageMemory);
        var privateMemory = new byte[100];
        var regions = new[]
        {
            new WindowsMemoryRegion(Base, (ulong)imageMemory.Length, 4, Image),
            new WindowsMemoryRegion(Base + 0x10000, (ulong)privateMemory.Length, 4, Private)
        };
        var readCalls = 0;
        var result = TypedApiPrefixScout.Scan(TypedApiPrefixMatcher.MarkerText, regions, Base, TypedApiPrefixScout.ChunkBytes, 128,
            (address, output, count) =>
            {
                readCalls++;
                Assert.Equal(Base + 0x10000, address);
                privateMemory.AsSpan(0, count).CopyTo(output);
                return new(true, count, null);
            }, () => false);

        Assert.Equal("complete", result.Status);
        Assert.Empty(result.PrefixAddresses);
        Assert.Equal(1, readCalls);
        Assert.Equal(100, result.EligiblePrivateBytes);
        Assert.Equal(1, result.EligiblePrivateRegionCount);
    }

    [Fact]
    public void Scan_FailedReadRetainsHoleAndNeverJoinsFalsePrefix()
    {
        var memory = new byte[3 * TypedApiPrefixScout.ChunkBytes];
        Marker.CopyTo(memory.AsSpan(2 * TypedApiPrefixScout.ChunkBytes - 4));
        var regions = Regions(memory);
        var result = TypedApiPrefixScout.Scan(TypedApiPrefixMatcher.MarkerText, regions, Base, TypedApiPrefixScout.MaxScanBytes, 128,
            (address, output, count) =>
            {
                var offset = checked((int)(address - Base));
                if (offset == TypedApiPrefixScout.ChunkBytes)
                    return new(false, 0, 299);
                memory.AsSpan(offset, count).CopyTo(output);
                return new(true, count, null);
            }, () => false);

        Assert.Equal("partial", result.Status);
        Assert.Equal("read-holes", result.Reason);
        Assert.Empty(result.PrefixAddresses);
        Assert.Equal(Base + TypedApiPrefixScout.ChunkBytes - (ulong)(Marker.Length - 1), result.NextAddress);
        Assert.Equal(2 * TypedApiPrefixScout.ChunkBytes, result.ExaminedBytes);
        Assert.Equal(3 * TypedApiPrefixScout.ChunkBytes, result.AttemptedBytes);
        Assert.Equal(2, result.CoveredSpans.Count);
        var hole = Assert.Single(result.Holes);
        Assert.Equal(Base + TypedApiPrefixScout.ChunkBytes, hole.BaseAddress);
        Assert.Equal(TypedApiPrefixScout.ChunkBytes, hole.ByteLength);
        Assert.Equal(299, hole.Win32Error);
    }

    [Fact]
    public void Scan_PartialReadRetainsOnlyReadBytesAndDisclosesMissingTail()
    {
        var memory = new byte[TypedApiPrefixScout.ChunkBytes];
        Marker.CopyTo(memory);
        var result = TypedApiPrefixScout.Scan(TypedApiPrefixMatcher.MarkerText, Regions(memory), Base, TypedApiPrefixScout.ChunkBytes, 128,
            (address, output, count) =>
            {
                memory.AsSpan(0, 100).CopyTo(output);
                return new(false, 100, 299);
            }, () => false);

        Assert.Equal("partial", result.Status);
        Assert.Equal(Base, Assert.Single(result.PrefixAddresses));
        Assert.Equal(100, result.ExaminedBytes);
        Assert.Equal(TypedApiPrefixScout.ChunkBytes - 100, Assert.Single(result.Holes).ByteLength);
    }

    [Fact]
    public void Scan_MatchBudgetStopsAtFirstUnretainedMarkerWithoutClaimingFullCoverage()
    {
        var memory = new byte[TypedApiPrefixScout.ChunkBytes];
        Marker.CopyTo(memory.AsSpan(0));
        Marker.CopyTo(memory.AsSpan(20));
        Marker.CopyTo(memory.AsSpan(40));

        var result = Scan(memory, maxMatches: 2);

        Assert.Equal("partial", result.Status);
        Assert.Equal("candidate-budget-exceeded", result.Reason);
        Assert.Equal(Base + 40, result.NextAddress);
        Assert.Equal(new ulong[] { Base, Base + 20 }, result.PrefixAddresses);
        Assert.Equal(40 + Marker.Length, result.ExaminedBytes);
        Assert.Equal(memory.Length, result.AttemptedBytes);
    }

    [Fact]
    public void Scan_TimeBudgetCanStopBeforeFirstReadWithoutProducingFalseAbsence()
    {
        var memory = new byte[100];
        var result = TypedApiPrefixScout.Scan(TypedApiPrefixMatcher.MarkerText, Regions(memory), Base, TypedApiPrefixScout.ChunkBytes, 128,
            (_, _, _) => throw new InvalidOperationException("read should not occur"), () => true);

        Assert.Equal("partial", result.Status);
        Assert.Equal("time-budget-exceeded", result.Reason);
        Assert.Equal(Base, result.NextAddress);
        Assert.Equal(0, result.AttemptedBytes);
        Assert.Empty(result.CoveredSpans);
    }

    [Fact]
    public void Scan_FindsPrefixWhenStartAddressIsInsideReadablePrivateRegion()
    {
        var memory = new byte[100];
        Marker.CopyTo(memory.AsSpan(50));

        var result = Scan(memory, startAddress: Base + 30);

        Assert.Equal("complete", result.Status);
        Assert.Equal(Base + 50, Assert.Single(result.PrefixAddresses));
        Assert.Equal(70, result.EligiblePrivateBytes);
        Assert.Equal(70, result.ExaminedBytes);
    }

    [Fact]
    public void Scan_RejectsBadBudgetsOverlapsAndUnexpectedReadCounts()
    {
        var memory = new byte[100];
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            Scan(memory, maxScanBytes: TypedApiPrefixScout.ChunkBytes - 1));
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            Scan(memory, maxScanBytes: TypedApiPrefixScout.MaxScanBytes + 1));
        var overlapping = new[]
        {
            new WindowsMemoryRegion(Base, 100, 4, Private),
            new WindowsMemoryRegion(Base + 50, 100, 4, Private)
        };
        Assert.Throws<InvalidDataException>(() => TypedApiPrefixScout.Scan(TypedApiPrefixMatcher.MarkerText,
            overlapping, Base, TypedApiPrefixScout.ChunkBytes, 128, (_, _, _) => new(true, 100, null),
            () => false));
        Assert.Throws<InvalidDataException>(() => TypedApiPrefixScout.Scan(TypedApiPrefixMatcher.MarkerText,
            Regions(memory), Base, TypedApiPrefixScout.ChunkBytes, 128,
            (_, _, requested) => new(true, requested + 1, null), () => false));
    }

    [Fact]
    public void Scan_InlineObserverCanCaptureFirstMarkerBeforeNextScanChunkIsRead()
    {
        var memory = new byte[2 * TypedApiPrefixScout.ChunkBytes];
        Marker.CopyTo(memory.AsSpan(123));
        var notified = false;
        var reads = 0;
        var result = TypedApiPrefixScout.Scan(TypedApiPrefixMatcher.MarkerText, Regions(memory), Base,
            TypedApiPrefixScout.MaxScanBytes, 128,
            (address, output, count) =>
            {
                if (reads++ == 1)
                {
                    Assert.True(notified);
                    Assert.Equal(Base + TypedApiPrefixScout.ChunkBytes, address);
                }
                memory.AsSpan(checked((int)(address - Base)), count).CopyTo(output);
                return new(true, count, null);
            }, () => false, onMatch: address =>
            {
                Assert.Equal(Base + 123, address);
                Assert.Equal(1, reads);
                notified = true;
            });

        Assert.Equal("complete", result.Status);
        Assert.Equal(2, reads);
        Assert.True(notified);
    }

    [Fact]
    public void Scan_InlineObserverRunsBeforeNextReadAndReceivesOnlyRetainedMatches()
    {
        var memory = new byte[2 * TypedApiPrefixScout.ChunkBytes];
        Marker.CopyTo(memory.AsSpan(2));
        Marker.CopyTo(memory.AsSpan(40));
        Marker.CopyTo(memory.AsSpan(90));
        var nextRead = false;
        var notified = new List<ulong>();
        var result = TypedApiPrefixScout.Scan(TypedApiPrefixMatcher.MarkerText, Regions(memory), Base,
            TypedApiPrefixScout.MaxScanBytes, 2,
            (address, output, count) =>
            {
                if (address == Base + TypedApiPrefixScout.ChunkBytes)
                {
                    nextRead = true;
                    Assert.Equal(new ulong[] { Base + 2, Base + 40 }, notified);
                }
                memory.AsSpan(checked((int)(address - Base)), count).CopyTo(output);
                return new(true, count, null);
            }, () => false, onMatch: address =>
            {
                Assert.False(nextRead);
                notified.Add(address);
            });

        Assert.Equal("partial", result.Status);
        Assert.Equal("candidate-budget-exceeded", result.Reason);
        Assert.Equal(new ulong[] { Base + 2, Base + 40 }, notified);
        // The overflow terminates before the next scan chunk is read.
        Assert.False(nextRead);
    }

    [Fact]
    public void Scan_InlineObserverHandlesSplitMarkerAndNeverNotifiesAcrossReadHole()
    {
        var memory = new byte[2 * TypedApiPrefixScout.ChunkBytes];
        Marker.CopyTo(memory.AsSpan(TypedApiPrefixScout.ChunkBytes - 4));
        var found = new List<ulong>();
        var success = TypedApiPrefixScout.Scan(TypedApiPrefixMatcher.MarkerText, Regions(memory), Base,
            TypedApiPrefixScout.MaxScanBytes, 128,
            (address, output, count) =>
            {
                memory.AsSpan(checked((int)(address - Base)), count).CopyTo(output);
                return new(true, count, null);
            }, () => false, onMatch: found.Add);
        Assert.Equal("complete", success.Status);
        Assert.Equal(new[] { Base + TypedApiPrefixScout.ChunkBytes - 4UL }, found);

        found.Clear();
        var withHole = TypedApiPrefixScout.Scan(TypedApiPrefixMatcher.MarkerText, Regions(memory), Base,
            TypedApiPrefixScout.MaxScanBytes, 128,
            (address, output, count) =>
            {
                if (address == Base)
                    return new(false, 0, 299);
                memory.AsSpan(checked((int)(address - Base)), count).CopyTo(output);
                return new(true, count, null);
            }, () => false, onMatch: found.Add);
        Assert.Equal("partial", withHole.Status);
        Assert.Empty(found);
    }

    [Fact]
    public async Task WindowsSession_BoundedReusableBufferReadsOwnKnownAllocation()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;
        var allocation = Marshal.AllocHGlobal(64);
        try
        {
            Marshal.Copy(Marker, 0, allocation, Marker.Length);
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                Environment.ProcessId, null, null, CancellationToken.None);
            var buffer = new byte[TypedApiPrefixScout.ChunkBytes];
            var address = checked((ulong)allocation.ToInt64());

            var actual = session.ReadScanChunk(address, buffer, Marker.Length);

            Assert.True(actual.Complete);
            Assert.Equal(Marker.Length, actual.BytesRead);
            Assert.True(Marker.SequenceEqual(buffer.AsSpan(0, Marker.Length).ToArray()));
            Assert.Throws<ArgumentOutOfRangeException>(() => session.Read(address, 4097));
            Assert.Throws<ArgumentOutOfRangeException>(() => session.ReadScanChunk(address, buffer, buffer.Length + 1));
        }
        finally
        {
            Marshal.FreeHGlobal(allocation);
        }
    }

    private static TypedApiScoutResult Scan(
        byte[] memory,
        ulong startAddress = Base,
        long maxScanBytes = TypedApiPrefixScout.MaxScanBytes,
        int maxMatches = 128) =>
        TypedApiPrefixScout.Scan(TypedApiPrefixMatcher.MarkerText, Regions(memory), startAddress, maxScanBytes, maxMatches,
            (address, output, count) =>
            {
                memory.AsSpan(checked((int)(address - Base)), count).CopyTo(output);
                return new(true, count, null);
            }, () => false);

    private static WindowsMemoryRegion[] Regions(byte[] memory) =>
        [new(Base, checked((ulong)memory.Length), 4, Private)];
}
