using System.Text;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class TypedApiPrefixMatcherTests
{
    private static readonly byte[] Marker = Encoding.ASCII.GetBytes(TypedApiPrefixMatcher.MarkerText);

    [Fact]
    public void Feed_FindsMarkerAtExactStartAboveFourGigabytes()
    {
        var matcher = new TypedApiPrefixMatcher();
        const ulong address = 0x0000_0002_4321_1000;

        matcher.Feed(address, Marker);

        Assert.Equal(address, Assert.Single(matcher.Addresses));
        Assert.False(matcher.MatchBudgetExceeded);
    }

    [Fact]
    public void Feed_FindsMarkerAcrossEveryPossibleSplit()
    {
        for (var split = 1; split < Marker.Length; split++)
        {
            var matcher = new TypedApiPrefixMatcher();
            matcher.Feed(0x4000, Marker.AsSpan(0, split));
            matcher.Feed(0x4000 + (ulong)split, Marker.AsSpan(split));

            Assert.Equal(0x4000UL, Assert.Single(matcher.Addresses));
        }
    }

    [Fact]
    public void Feed_FindsMarkerStraddlingSixtyFourKilobyteReads()
    {
        var bytes = new byte[64 * 1024 + 64];
        const int markerStart = 64 * 1024 - 4;
        Marker.CopyTo(bytes.AsSpan(markerStart));
        var matcher = new TypedApiPrefixMatcher();

        matcher.Feed(0x10000, bytes.AsSpan(0, 64 * 1024));
        matcher.Feed(0x20000, bytes.AsSpan(64 * 1024));

        Assert.Equal(0x10000UL + markerStart, Assert.Single(matcher.Addresses));
    }

    [Fact]
    public void Feed_FindsBackToBackMarkersWithoutClaimingValidFrames()
    {
        var bytes = Encoding.ASCII.GetBytes(TypedApiPrefixMatcher.MarkerText + TypedApiPrefixMatcher.MarkerText + "not-a-frame");
        var matcher = new TypedApiPrefixMatcher();

        matcher.Feed(0x3000, bytes);

        Assert.Equal(new ulong[] { 0x3000, 0x3000 + (ulong)Marker.Length }, matcher.Addresses);
        Assert.False(matcher.MatchBudgetExceeded);
    }

    [Fact]
    public void Feed_RecoversFromOverlappingPartialPrefix()
    {
        var bytes = Encoding.ASCII.GetBytes("RRA" + TypedApiPrefixMatcher.MarkerText);
        var matcher = new TypedApiPrefixMatcher();

        matcher.Feed(0x3000, bytes);

        Assert.Equal(0x3003UL, Assert.Single(matcher.Addresses));
    }

    [Fact]
    public void Feed_DoesNotCountIncompleteOrSimilarMarkers()
    {
        var bytes = Encoding.ASCII.GetBytes("RRAPIVAL1| RRAPIVAL2? RRAPIVAL2");
        var matcher = new TypedApiPrefixMatcher();

        matcher.Feed(0x3000, bytes);

        Assert.Empty(matcher.Addresses);
    }

    [Fact]
    public void Feed_CanJoinAdjacentReadableRegions()
    {
        var matcher = new TypedApiPrefixMatcher();
        matcher.Feed(0x7000, Marker.AsSpan(0, 5));
        matcher.Feed(0x7005, Marker.AsSpan(5));

        Assert.Equal(0x7000UL, Assert.Single(matcher.Addresses));
    }

    [Fact]
    public void Feed_DoesNotJoinNoncontiguousRegionsOrFailedReads()
    {
        var matcher = new TypedApiPrefixMatcher();
        matcher.Feed(0x7000, Marker.AsSpan(0, 5));
        matcher.Feed(0x7006, Marker.AsSpan(5));
        matcher.Feed(0x8000, Marker.AsSpan(0, 5));
        matcher.ResetMemoryBoundary();
        matcher.Feed(0x8005, Marker.AsSpan(5));

        Assert.Empty(matcher.Addresses);
    }

    [Fact]
    public void Feed_EnforcesExplicitCandidateLimitWithoutSilentTruncation()
    {
        var matcher = new TypedApiPrefixMatcher(maxMatches: 2);
        var bytes = Encoding.ASCII.GetBytes(string.Concat(Enumerable.Repeat(TypedApiPrefixMatcher.MarkerText, 4)));

        matcher.Feed(0x1000, bytes);
        matcher.Feed(0x2000, Marker);

        Assert.True(matcher.MatchBudgetExceeded);
        Assert.Equal(0x1000UL + 2 * (ulong)Marker.Length, matcher.FirstUnretainedAddress);
        Assert.Equal(new ulong[] { 0x1000, 0x1000 + (ulong)Marker.Length }, matcher.Addresses);
    }

    [Fact]
    public void Constructor_RejectsMissingOrExcessiveCandidateBudgets()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => new TypedApiPrefixMatcher(0));
        Assert.Throws<ArgumentOutOfRangeException>(() => new TypedApiPrefixMatcher(TypedApiPrefixMatcher.MaxSupportedMatches + 1));
    }

    [Fact]
    public void Feed_RejectsAddressOverflowWithoutCorruptingPriorMatches()
    {
        var matcher = new TypedApiPrefixMatcher();
        matcher.Feed(0x5000, Marker);

        Assert.Throws<OverflowException>(() => matcher.Feed(ulong.MaxValue, new byte[] { 42, 43 }));

        Assert.Equal(0x5000UL, Assert.Single(matcher.Addresses));
    }

    [Fact]
    public void Feed_IgnoresEmptyInputWithoutBreakingContiguity()
    {
        var matcher = new TypedApiPrefixMatcher();
        matcher.Feed(0x1000, Marker.AsSpan(0, 3));
        matcher.Feed(0xDEAD, ReadOnlySpan<byte>.Empty);
        matcher.Feed(0x1003, Marker.AsSpan(3));

        Assert.Equal(0x1000UL, Assert.Single(matcher.Addresses));
    }
}
