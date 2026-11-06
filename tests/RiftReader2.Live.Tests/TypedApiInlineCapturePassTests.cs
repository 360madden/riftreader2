using System.Text;
using RiftReader2.Application;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class TypedApiInlineCapturePassTests
{
    private const ulong Base = 0x100000;
    private const int ScanBytes = TypedApiPrefixScout.ChunkBytes;
    private const ulong FirstMarker = Base + 2 * TypedApiImmediateNeighborhood.PageBytes + 100;
    private static readonly byte[] Plausible = Encoding.ASCII.GetBytes("RRAPIVAL2|{");
    private static readonly byte[] StaticMarker = Encoding.ASCII.GetBytes("RRAPIVAL2|");

    [Fact]
    public void Run_ReferenceMarkerPropagatesThroughScoutAndPlausibilityGate()
    {
        var data = Memory();
        Encoding.ASCII.GetBytes("RR2R1|{").CopyTo(data.AsSpan((int)(FirstMarker - Base)));
        Plausible.CopyTo(data.AsSpan(40_000));
        var result = TypedApiInlineCapturePass.Run(
            Regions(), Base, ScanBytes, 128, 2,
            (address, buffer, length) =>
            {
                data.AsSpan((int)(address - Base), length).CopyTo(buffer);
                return new(true, length, null);
            },
            (address, length) => Read(data, address, length), () => false, marker: "RR2R1|");
        Assert.Equal(FirstMarker, Assert.Single(result.Scout.PrefixAddresses));
        Assert.Equal("complete", Assert.Single(result.Candidates).Status);
        Assert.Equal(1, result.CopiedCandidates);
    }

    [Theory]
    [InlineData("")]
    [InlineData("RR2A1|")]
    [InlineData("RR2R1")]
    public void MatcherRejectsUnsupportedMarkers(string marker) =>
        Assert.Throws<ArgumentException>(() => new TypedApiPrefixMatcher(marker: marker));

    [Fact]
    public void Run_PlausibleMarkerCopiedInlineWhileBinaryMarkerIsRejected()
    {
        var data = Memory();
        Plausible.CopyTo(data.AsSpan((int)(FirstMarker - Base)));
        StaticMarker.CopyTo(data.AsSpan(40_000));
        var readCalls = new List<int>();
        var result = Run(data, maxCopies: 2, readCalls);

        Assert.Equal("complete", result.Scout.Status);
        Assert.Equal(new[] { FirstMarker, Base + 40_000 }, result.Scout.PrefixAddresses);
        Assert.Equal(2, result.Candidates.Count);
        Assert.Equal("complete", result.Candidates[0].Status);
        Assert.Equal(7, result.Candidates[0].Neighborhood!.Chunks.Count);
        Assert.Equal("prefix-not-plausible", result.Candidates[1].Status);
        Assert.Null(result.Candidates[1].Neighborhood);
        Assert.Equal(1, result.CopiedCandidates);
        Assert.False(result.CopyLimited);
        Assert.Equal(9, readCalls.Count); // two header rechecks and seven 4 KiB pages
    }

    [Fact]
    public void Run_EnforcesCopyCountEvenWhenMorePrefixesArePlausible()
    {
        var data = Memory();
        Plausible.CopyTo(data.AsSpan((int)(FirstMarker - Base)));
        Plausible.CopyTo(data.AsSpan(45_000));
        var result = Run(data, maxCopies: 1);

        Assert.Equal("complete", result.Scout.Status);
        Assert.Equal("complete", result.Candidates[0].Status);
        Assert.Equal("copy-budget-exceeded", result.Candidates[1].Status);
        Assert.Null(result.Candidates[1].Neighborhood);
        Assert.Equal(1, result.CopiedCandidates);
        Assert.True(result.CopyLimited);
    }

    [Fact]
    public void Run_DetectsPrefixThatMovedAfterScannerReadBeforeNeighborhoodRecheck()
    {
        var data = Memory();
        Plausible.CopyTo(data.AsSpan((int)(FirstMarker - Base)));
        var result = TypedApiInlineCapturePass.Run(
            Regions(), Base, ScanBytes, 128, 2,
            (address, buffer, length) =>
            {
                data.AsSpan((int)(address - Base), length).CopyTo(buffer);
                data[(int)(FirstMarker - Base)] = 0;
                return new(true, length, null);
            },
            (address, length) => Read(data, address, length),
            () => false);

        Assert.Equal("complete", result.Scout.Status);
        Assert.Equal(FirstMarker, Assert.Single(result.Scout.PrefixAddresses));
        Assert.Equal("prefix-not-plausible", Assert.Single(result.Candidates).Status);
        Assert.Equal(0, result.CopiedCandidates);
    }

    [Fact]
    public void Run_NearUserMemoryBoundaryCannotCopyAndDoesNotAbortScout()
    {
        var data = Memory();
        Plausible.CopyTo(data.AsSpan());
        var result = TypedApiInlineCapturePass.Run(
            [new WindowsMemoryRegion(0x10000, (ulong)data.Length, 4, 0x20000)],
            0x10000, ScanBytes, 128, 2,
            (address, buffer, length) =>
            {
                data.AsSpan((int)(address - 0x10000), length).CopyTo(buffer);
                return new(true, length, null);
            },
            (_, _) => throw new Exception("out-of-range candidate must not be read"),
            () => false);

        Assert.Equal("complete", result.Scout.Status);
        Assert.Equal("window-out-of-range", Assert.Single(result.Candidates).Status);
        Assert.Equal(0, result.CopiedCandidates);
    }

    [Fact]
    public void Run_RejectsInvalidCopyBudgetsBeforeAttemptingNativeScan()
    {
        var data = Memory();
        Assert.Throws<ArgumentOutOfRangeException>(() => Run(data, maxCopies: 0));
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            Run(data, maxCopies: TypedApiInlineCapturePass.MaxCopies + 1));
    }

    [Fact]
    public void Run_PropagatesTimeCapAndDoesNotClaimCompleteCoverage()
    {
        var data = Memory();
        Plausible.CopyTo(data.AsSpan((int)(FirstMarker - Base)));
        var reads = 0;
        var result = TypedApiInlineCapturePass.Run(
            Regions(), Base, ScanBytes, 128, 2,
            (address, buffer, length) =>
            {
                data.AsSpan((int)(address - Base), length).CopyTo(buffer);
                return new(true, length, null);
            },
            (address, length) =>
            {
                reads++;
                return Read(data, address, length);
            },
            () => reads >= 3);

        Assert.Equal("partial", result.Scout.Status);
        Assert.Equal("time-budget-exceeded", result.Scout.Reason);
        var first = Assert.Single(result.Candidates);
        Assert.Equal("time-budget-exceeded", first.Status);
        Assert.Equal(2, first.Neighborhood!.Chunks.Count);
    }

    private static byte[] Memory()
    {
        var bytes = new byte[ScanBytes];
        Array.Fill(bytes, (byte)0x33);
        return bytes;
    }

    private static WindowsMemoryRegion[] Regions() =>
        [new(Base, ScanBytes, 4, 0x20000)];

    private static NativeReadResult Read(byte[] memory, ulong address, int length) =>
        new("success", memory.AsSpan(checked((int)(address - Base)), length).ToArray(), null, null);

    private static TypedApiInlineCapturePassResult Run(
        byte[] memory, int maxCopies, List<int>? readCalls = null) =>
        TypedApiInlineCapturePass.Run(
            Regions(), Base, ScanBytes, 128, maxCopies,
            (address, buffer, length) =>
            {
                memory.AsSpan(checked((int)(address - Base)), length).CopyTo(buffer);
                return new(true, length, null);
            },
            (address, length) =>
            {
                readCalls?.Add(length);
                return Read(memory, address, length);
            },
            () => false);
}
