using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildOpaqueInternBucketCandidateTests
{
    [Theory]
    [InlineData(new byte[] { 0 }, 0, 0)]
    [InlineData(new byte[] { 97, 0 }, 1, 97)]
    [InlineData(new byte[] { 97, 98, 99, 0 }, 3, 210)]
    [InlineData(new byte[] { 128, 0 }, 1, 353)]
    [InlineData(new byte[] { 255, 128, 1, 0 }, 3, 299)]
    [InlineData(new byte[] { 255, 255, 255, 255, 255, 255, 255, 255, 0 }, 8, 361)]
    public void ReturnsNativeSignedByteHashBucket(byte[] bytes, int maximum, int expected)
    {
        Assert.True(CurrentBuildOpaqueInternBucketCandidate.TryGetBucket(bytes, maximum, out var bucket));
        Assert.Equal(expected, bucket);
        Assert.InRange(bucket, 0, 512);
    }

    [Fact]
    public void MaximumPayloadRequiresTerminatorAtBoundary()
    {
        var bytes = Enumerable.Repeat((byte)97, 4098).ToArray();
        bytes[4096] = 0;
        Assert.True(CurrentBuildOpaqueInternBucketCandidate.TryGetBucket(bytes, 4096, out _));
        bytes[4096] = 97;
        bytes[4097] = 0;
        Assert.False(CurrentBuildOpaqueInternBucketCandidate.TryGetBucket(bytes, 4096, out _));
    }

    [Fact]
    public void ZeroMaximumRejectsNonemptyPayload()
    {
        Assert.False(CurrentBuildOpaqueInternBucketCandidate.TryGetBucket([97, 0], 0, out _));
    }

    [Fact]
    public void StopsAtFirstTerminator()
    {
        Assert.True(CurrentBuildOpaqueInternBucketCandidate.TryGetBucket([97, 0, 255], 2, out var bucket));
        Assert.Equal(97, bucket);
    }

    [Theory]
    [InlineData(new byte[] { }, 0)]
    [InlineData(new byte[] { 97 }, 1)]
    [InlineData(new byte[] { 97, 98, 0 }, 1)]
    [InlineData(new byte[] { 0 }, -1)]
    [InlineData(new byte[] { 0 }, 4097)]
    public void RejectsMissingTerminatorOrInvalidBound(byte[] bytes, int maximum)
    {
        Assert.False(CurrentBuildOpaqueInternBucketCandidate.TryGetBucket(bytes, maximum, out var bucket));
        Assert.Equal(0, bucket);
    }

    [Fact]
    public void ExposesExactBucketLayoutConstants()
    {
        Assert.Equal(513, CurrentBuildOpaqueInternBucketCandidate.BucketCount);
        Assert.Equal(24, CurrentBuildOpaqueInternBucketCandidate.BucketStride);
    }
}
