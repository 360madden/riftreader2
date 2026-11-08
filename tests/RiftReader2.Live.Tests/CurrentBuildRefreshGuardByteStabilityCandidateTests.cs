using System.Buffers.Binary;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildRefreshGuardByteStabilityCandidateTests
{
    private static byte[] Snapshot(ulong handle, byte flag)
    {
        var bytes = new byte[CurrentBuildRefreshGuardByteStabilityCandidate.SnapshotLength];
        BinaryPrimitives.WriteUInt64LittleEndian(bytes.AsSpan(0, 8), handle);
        bytes[8] = flag;
        return bytes;
    }

    [Theory]
    [InlineData(0UL, (byte)0, "guard-ineligible-candidate")]
    [InlineData(0UL, (byte)1, "alternate-flag-guard-candidate")]
    [InlineData(0UL, byte.MaxValue, "alternate-flag-guard-candidate")]
    [InlineData(1UL, (byte)0, "handle-present-guard-candidate")]
    [InlineData(0xFFFFFFFFFFFFFFFFUL, byte.MaxValue, "handle-present-guard-candidate")]
    public void EqualNineBytesClassifyRawGuardWithHandleFirst(
        ulong handle, byte flag, string expectedStatus)
    {
        var result = CurrentBuildRefreshGuardByteStabilityCandidate.Compare(
            Snapshot(handle, flag), Snapshot(handle, flag));
        Assert.True(result.SequentiallyStable);
        Assert.Equal("guard-bytes-stable-sequential-candidate", result.Status);
        Assert.Equal($"0x{handle:X16}", result.RefreshHandleHex);
        Assert.Equal(flag, result.RefreshFlagRaw);
        Assert.Equal(expectedStatus, result.RefreshGuardStatus);
        Assert.Contains("cannot exclude ABA", result.Qualification);
        Assert.Contains("does not prove", result.Qualification);
    }

    [Fact]
    public void ChangedHandleFailsClosedWithoutPublishingRawValues()
    {
        var result = CurrentBuildRefreshGuardByteStabilityCandidate.Compare(
            Snapshot(0x100, 1), Snapshot(0x101, 1));
        AssertUnavailable(result, "guard-bytes-changed");
    }

    [Fact]
    public void ChangedFlagFailsClosedEvenWhenHandleRemainsNonzero()
    {
        var result = CurrentBuildRefreshGuardByteStabilityCandidate.Compare(
            Snapshot(0xFFFFFFFFFFFFFFFF, 0), Snapshot(0xFFFFFFFFFFFFFFFF, 1));
        AssertUnavailable(result, "guard-bytes-changed");
    }

    [Fact]
    public void MissingEitherSnapshotRemainsUnknownNeverZero()
    {
        AssertUnavailable(CurrentBuildRefreshGuardByteStabilityCandidate.Compare(null, Snapshot(0, 0)),
            "first-snapshot-unavailable");
        AssertUnavailable(CurrentBuildRefreshGuardByteStabilityCandidate.Compare(Snapshot(0, 0), null),
            "second-snapshot-unavailable");
        AssertUnavailable(CurrentBuildRefreshGuardByteStabilityCandidate.Compare(null, null),
            "first-snapshot-unavailable");
    }

    [Theory]
    [InlineData(0, 9)]
    [InlineData(8, 9)]
    [InlineData(9, 8)]
    [InlineData(9, 10)]
    [InlineData(10, 9)]
    public void RejectsAnyNonNineByteSnapshot(int firstLength, int secondLength)
    {
        AssertUnavailable(CurrentBuildRefreshGuardByteStabilityCandidate.Compare(
            new byte[firstLength], new byte[secondLength]), "snapshot-length-invalid");
    }

    [Fact]
    public void DoesNotRetainCallerBuffers()
    {
        var first = Snapshot(0x123456789ABCDEF0, 1);
        var second = (byte[])first.Clone();
        var result = CurrentBuildRefreshGuardByteStabilityCandidate.Compare(first, second);
        first.AsSpan().Clear();
        second.AsSpan().Fill(0xff);
        Assert.True(result.SequentiallyStable);
        Assert.Equal("0x123456789ABCDEF0", result.RefreshHandleHex);
        Assert.Equal((byte)1, result.RefreshFlagRaw);
    }

    private static void AssertUnavailable(
        CurrentBuildRefreshGuardByteStabilityCandidate.Result result, string status)
    {
        Assert.Equal(status, result.Status);
        Assert.False(result.SequentiallyStable);
        Assert.Null(result.RefreshHandleHex);
        Assert.Null(result.RefreshFlagRaw);
        Assert.Null(result.RefreshGuardStatus);
    }
}
