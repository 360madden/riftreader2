using System.Text;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class CastingReferenceInlineCaptureCoreTests
{
    private const ulong Base = 0x100000;
    private const int Bytes = CastingReferenceInlineCaptureCore.ChunkBytes;
    private const ulong MarkerAddress = Base + 2 * 4096 + 100;

    [Fact]
    public void FixedMarkerCapturesSevenPagesAndIgnoresTypedApiMarker()
    {
        var memory = Memory();
        Encoding.ASCII.GetBytes("RR2CASTREF1|{").CopyTo(memory.AsSpan((int)(MarkerAddress - Base)));
        Encoding.ASCII.GetBytes("RRAPIVAL2|{").CopyTo(memory.AsSpan(40000));
        var result = Run(memory);

        Assert.Equal("complete", result.Status);
        Assert.Equal(CastingReferenceInlineCaptureCore.EvidenceKind, result.EvidenceKind);
        var candidate = Assert.Single(result.Candidates);
        Assert.Equal($"0x{MarkerAddress:X}", candidate.MarkerAddress);
        Assert.Equal(7, candidate.Neighborhood!.Chunks.Count);
        Assert.Equal(1, result.CopiedCandidates);
        Assert.DoesNotContain(result.Scout.PrefixAddresses, item => item == Base + 40000);
    }

    [Fact]
    public void MarkerCanSpanSixtyFourKilobyteReadBoundary()
    {
        var memory = new byte[Bytes * 2];
        Array.Fill(memory, (byte)0x33);
        var offset = Bytes - 5;
        Encoding.ASCII.GetBytes("RR2CASTREF1|{").CopyTo(memory.AsSpan(offset));
        var result = Run(memory, maxScanBytes: memory.Length);
        Assert.Equal(Base + (ulong)offset, Assert.Single(result.Scout.PrefixAddresses));
    }

    [Fact]
    public void ExactCurrentBuildAndProcessEpochAreMandatory()
    {
        var memory = Memory();
        var request = Request() with
        {
            Target = new(77, 88, "A" + CastingReferenceInlineCaptureCore.CurrentBuildSha256[1..])
        };
        Assert.Throws<InvalidDataException>(() => Run(memory, request: request));
        Assert.Throws<InvalidDataException>(() => Run(memory, identity: Identity() with
        {
            ProcessStartUtcTicks = 89
        }));
    }

    [Fact]
    public void PostflightIdentityFailureSuppressesCapturedBytes()
    {
        var memory = Memory();
        Encoding.ASCII.GetBytes("RR2CASTREF1|{").CopyTo(memory.AsSpan((int)(MarkerAddress - Base)));
        var result = Run(memory, revalidate: () => "process epoch changed");
        Assert.Equal("identity-invalidated", result.Status);
        Assert.Null(Assert.Single(result.Candidates).Neighborhood);
        Assert.Contains("process epoch changed", result.Reason);
    }

    [Fact]
    public void StaticOrMovedMarkerIsDeclinedWithoutPageCopy()
    {
        var memory = Memory();
        Encoding.ASCII.GetBytes(CastingReferenceInlineCaptureCore.MarkerText)
            .CopyTo(memory.AsSpan((int)(MarkerAddress - Base)));
        var result = Run(memory);
        var candidate = Assert.Single(result.Candidates);
        Assert.Equal("prefix-not-plausible", candidate.Status);
        Assert.Null(candidate.Neighborhood);
        Assert.Equal(0, result.CopiedCandidates);
    }

    [Fact]
    public void BoundsAndCopyCapFailClosed()
    {
        var memory = Memory();
        foreach (var request in new[]
        {
            Request() with { MaxScanBytes = CastingReferenceInlineCaptureCore.MaxScanBytes + 1 },
            Request() with { MaxDurationMilliseconds = 30_001 },
            Request() with { MaxMatchCount = 129 },
            Request() with { MaxCopiedCandidates = 9 },
            Request() with { StartAddress = "0x010000" },
        })
            Assert.Throws<InvalidDataException>(() => Run(memory, request: request));
        Assert.Throws<InvalidDataException>(() => Run(
            memory, request: Request() with { MaxRegionCount = 1 },
            regions:
            [
                new(Base, (ulong)(Bytes / 2), 4, 0x20000),
                new(Base + (ulong)(Bytes / 2), (ulong)(Bytes / 2), 4, 0x20000)
            ]));
    }

    [Theory]
    [InlineData(0x01)]
    [InlineData(0x06)]
    [InlineData(0x100)]
    [InlineData(0x104)]
    [InlineData(0x10)]
    public void PrivateRegionsMustBeReadableAndNonguard(uint protection)
    {
        var memory = Memory();
        Assert.Throws<InvalidDataException>(() => Run(
            memory, regions: [new(Base, (ulong)memory.Length, protection, 0x20000)]));
    }

    [Fact]
    public void CoreOwnsRequestDeadlineAndRejectsBackwardMonotonicClock()
    {
        var memory = Memory();
        var expired = new Queue<long>(new long[] { 1000, 1000, 31_001, 31_001 });
        var result = Run(memory, monotonic: expired.Dequeue);
        Assert.Equal("partial", result.Status);
        Assert.Equal("time-budget-exceeded", result.Reason);

        var postflightExpired = new Queue<long>(new long[] { 1000, 1000, 1000, 31_001 });
        var postflight = Run(memory, monotonic: postflightExpired.Dequeue);
        Assert.Equal("partial", postflight.Status);
        Assert.Equal("time-budget-exceeded-during-capture-or-revalidation", postflight.Reason);

        var backward = new Queue<long>(new long[] { 1000, 999 });
        Assert.Throws<InvalidDataException>(() => Run(memory, monotonic: backward.Dequeue));
    }

    [Fact]
    public void PublishNewDirectoryNeverOverwrites()
    {
        var root = Path.Combine(Path.GetTempPath(), "rr2-cast-ref-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var staging = Path.Combine(root, "staging");
            var output = Path.Combine(root, "output");
            Directory.CreateDirectory(staging);
            File.WriteAllText(Path.Combine(staging, "proof.txt"), "one");
            CastingReferenceInlineCaptureCore.PublishNewDirectory(staging, output);
            Assert.Equal("one", File.ReadAllText(Path.Combine(output, "proof.txt")));
            var second = Path.Combine(root, "second");
            Directory.CreateDirectory(second);
            File.WriteAllText(Path.Combine(second, "proof.txt"), "two");
            Assert.Throws<IOException>(() =>
                CastingReferenceInlineCaptureCore.PublishNewDirectory(second, output));
            Assert.Equal("one", File.ReadAllText(Path.Combine(output, "proof.txt")));
        }
        finally
        {
            if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
        }
    }

    private static byte[] Memory(int length = Bytes)
    {
        var memory = new byte[length];
        Array.Fill(memory, (byte)0x33);
        return memory;
    }

    private static CastingReferenceInlineCaptureRequest Request() => new(
        1, CastingReferenceInlineCaptureCore.RequestKind,
        new(77, 88, CastingReferenceInlineCaptureCore.CurrentBuildSha256),
        $"0x{Base:X}", Bytes, 30_000, 32_768, 128, 8);

    private static NativeProcessIdentity Identity() => new(
        77, 88, @"C:\RIFT\rift_x64.exe",
        CastingReferenceInlineCaptureCore.CurrentBuildSha256, 0x140000000, 0x4000000);

    private static CastingReferenceInlineCaptureResult Run(
        byte[] memory,
        CastingReferenceInlineCaptureRequest? request = null,
        NativeProcessIdentity? identity = null,
        long? maxScanBytes = null,
        Func<string?>? revalidate = null,
        IReadOnlyList<WindowsMemoryRegion>? regions = null,
        Func<long>? monotonic = null)
    {
        request ??= Request() with { MaxScanBytes = maxScanBytes ?? Bytes };
        identity ??= Identity();
        return CastingReferenceInlineCaptureCore.Run(
            request, identity,
            regions ?? [new(Base, (ulong)memory.Length, 4, 0x20000)],
            (address, buffer, length) =>
            {
                memory.AsSpan(checked((int)(address - Base)), length).CopyTo(buffer);
                return new(true, length, null);
            },
            (address, length) => new NativeReadResult(
                "success", memory.AsSpan(checked((int)(address - Base)), length).ToArray(), null, null),
            revalidate ?? (() => null), monotonic ?? (() => 0),
            utcNow: new Queue<string>(new[]
            {
                "2026-11-06T00:00:00Z", "2026-11-06T00:00:01Z",
                "2026-11-06T00:00:02Z", "2026-11-06T00:00:03Z"
            }).Dequeue);
    }
}
