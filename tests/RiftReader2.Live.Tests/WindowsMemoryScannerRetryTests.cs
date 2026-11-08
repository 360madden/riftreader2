namespace RiftReader2.Live.Tests;

public sealed class WindowsMemoryScannerRetryTests
{
    [Fact]
    public void StableExactRegion_RetriesOnlyTheFailedChunk()
    {
        var reads = new Queue<WindowsMemoryScanner.ChunkReadResult>([
            Chunk(false, 0, 299), Chunk(true, 65536, null)]);
        var revalidations = 0;

        var result = WindowsMemoryScanner.ReadChunkWithStableRegionRetry(
            reads.Dequeue, () => { revalidations++; return true; }, 65536);

        Assert.True(result.Succeeded);
        Assert.Equal((nuint)65536, result.BytesRead);
        Assert.Null(result.ErrorCode);
        Assert.Empty(reads);
        Assert.Equal(1, revalidations);
    }

    [Fact]
    public void ChangedRegion_DoesNotRetryOrAcceptPartialBytes()
    {
        var reads = 0;
        var result = WindowsMemoryScanner.ReadChunkWithStableRegionRetry(
            () => { reads++; return Chunk(false, 4096, 299); },
            () => false,
            65536);

        Assert.False(result.Succeeded);
        Assert.Equal((nuint)4096, result.BytesRead);
        Assert.Equal(299, result.ErrorCode);
        Assert.Equal(1, reads);
    }

    [Fact]
    public void RepeatedPartialCopy_HasABoundedExactChunkRetryCount()
    {
        var reads = 0;
        var revalidations = 0;
        var result = WindowsMemoryScanner.ReadChunkWithStableRegionRetry(
            () => { reads++; return Chunk(false, 0, 299); },
            () => { revalidations++; return true; },
            65536);

        Assert.False(result.Succeeded);
        Assert.Equal(3, reads);
        Assert.Equal(2, revalidations);
    }

    [Fact]
    public void NonPartialCopyAndShortSuccess_DoNotRetry()
    {
        foreach (var first in new[] { Chunk(false, 0, 5), Chunk(true, 4096, null) })
        {
            var reads = 0;
            var revalidations = 0;
            var result = WindowsMemoryScanner.ReadChunkWithStableRegionRetry(
                () => { reads++; return first; },
                () => { revalidations++; return true; },
                65536);

            Assert.Equal(first, result);
            Assert.Equal(1, reads);
            Assert.Equal(0, revalidations);
        }
    }

    [Fact]
    public void PartialCopy_RetriesOnceAndReturnsOnlyTheSecondAttempt()
    {
        var first = Attempt(false, "read-failed", 1, 299);
        var second = Attempt(true, "complete", 2, null);
        var attempts = new Queue<WindowsMemoryScanner.ScanAttemptResult>([first, second]);
        var starts = 0;

        var result = WindowsMemoryScanner.RunWithPartialCopyRetry(
            attempts.Dequeue,
            () => TimeSpan.FromSeconds(2),
            TimeSpan.FromSeconds(10),
            () => starts++);

        Assert.Same(second.Result, result);
        Assert.Equal(2, Assert.Single(result.Candidates).Span[0]);
        Assert.Empty(attempts);
        Assert.Equal(2, starts);
    }

    [Fact]
    public void RepeatedPartialCopy_RemainsIncompleteAndDoesNotMergeAttempts()
    {
        var first = Attempt(false, "read-failed", 1, 299);
        var second = Attempt(false, "read-failed", 2, 299);
        var attempts = new Queue<WindowsMemoryScanner.ScanAttemptResult>([first, second]);

        var result = WindowsMemoryScanner.RunWithPartialCopyRetry(
            attempts.Dequeue,
            () => TimeSpan.FromSeconds(2),
            TimeSpan.FromSeconds(10));

        Assert.Same(second.Result, result);
        Assert.False(result.Completed);
        Assert.Equal(2, Assert.Single(result.Candidates).Span[0]);
        Assert.Empty(attempts);
    }

    [Fact]
    public void OtherReadError_DoesNotRetry()
    {
        var first = Attempt(false, "read-failed", 1, 5);
        var calls = 0;
        var starts = 0;

        var result = WindowsMemoryScanner.RunWithPartialCopyRetry(
            () =>
            {
                calls++;
                return first;
            },
            () => TimeSpan.FromSeconds(2),
            TimeSpan.FromSeconds(10),
            () => starts++);

        Assert.Same(first.Result, result);
        Assert.Equal(1, calls);
        Assert.Equal(1, starts);
    }

    [Fact]
    public void ExhaustedOriginalBudget_DoesNotRetry()
    {
        var first = Attempt(false, "read-failed", 1, 299);
        var calls = 0;

        var result = WindowsMemoryScanner.RunWithPartialCopyRetry(
            () =>
            {
                calls++;
                return first;
            },
            () => TimeSpan.FromSeconds(10),
            TimeSpan.FromSeconds(10));

        Assert.Same(first.Result, result);
        Assert.Equal(1, calls);
    }

    [Fact]
    public void CancellationFromRetry_IsNotConvertedIntoAResult()
    {
        var calls = 0;

        Assert.Throws<OperationCanceledException>(() =>
            WindowsMemoryScanner.RunWithPartialCopyRetry(
                () => ++calls == 1
                    ? Attempt(false, "read-failed", 1, 299)
                    : throw new OperationCanceledException(),
                () => TimeSpan.FromSeconds(2),
                TimeSpan.FromSeconds(10)));
        Assert.Equal(2, calls);
    }

    [Fact]
    public void Experimental256KiB_FallsBackToFourExact64KiBSubreadsAfterPartialCopy()
    {
        var segments = new List<(int Offset, int Length)>();
        var primaryCalls = 0;
        var cancellationChecks = 0;
        var result = WindowsMemoryScanner.ReadChunkWithStableRegionFallback(
            (offset, length) =>
            {
                segments.Add((offset, length));
                if (length == 256 * 1024)
                {
                    primaryCalls++;
                    return Chunk(false, 4096, 299);
                }
                return Chunk(true, (nuint)length, null);
            },
            (_, _) => true,
            256 * 1024,
            256 * 1024,
            () => cancellationChecks++);

        Assert.True(result.Succeeded);
        Assert.Equal((nuint)(256 * 1024), result.BytesRead);
        Assert.Null(result.ErrorCode);
        Assert.Equal(3, primaryCalls);
        Assert.Equal(4, cancellationChecks);
        Assert.Equal(new[]
        {
            (0, 64 * 1024), (64 * 1024, 64 * 1024),
            (128 * 1024, 64 * 1024), (192 * 1024, 64 * 1024)
        }, segments.Skip(3).ToArray());
        Assert.Equal(7, segments.Count);
    }

    [Fact]
    public void Experimental256KiB_AnyFailedSubreadFailsEntireChunk()
    {
        var segments = new List<(int Offset, int Length)>();
        var result = WindowsMemoryScanner.ReadChunkWithStableRegionFallback(
            (offset, length) =>
            {
                segments.Add((offset, length));
                return length == 256 * 1024 || offset == 64 * 1024
                    ? Chunk(false, 1024, 299)
                    : Chunk(true, (nuint)length, null);
            },
            (_, _) => true,
            256 * 1024,
            256 * 1024);

        Assert.False(result.Succeeded);
        Assert.Equal(299, result.ErrorCode);
        Assert.Equal(3, segments.Count(x => x.Length == 256 * 1024));
        Assert.Equal(1, segments.Count(x => x.Offset == 0 && x.Length == 64 * 1024));
        Assert.Equal(3, segments.Count(x => x.Offset == 64 * 1024 && x.Length == 64 * 1024));
        Assert.DoesNotContain(segments, x => x.Offset >= 128 * 1024 && x.Length == 64 * 1024);
    }

    [Fact]
    public void Experimental256KiB_ChangedRegionBlocksStitching()
    {
        var calls = 0;
        var result = WindowsMemoryScanner.ReadChunkWithStableRegionFallback(
            (_, _) => { calls++; return Chunk(false, 1024, 299); },
            (_, _) => false,
            256 * 1024,
            256 * 1024);

        Assert.False(result.Succeeded);
        Assert.Equal(1, calls);
        Assert.Equal((nuint)0, result.BytesRead);
        Assert.Null(result.ErrorCode);
    }

    [Fact]
    public void Experimental256KiB_ShortSuccessWithout299IsNotPromoted()
    {
        var reads = 0;
        var result = WindowsMemoryScanner.ReadChunkWithStableRegionFallback(
            (_, _) => { reads++; return Chunk(true, 4096, null); },
            (_, _) => throw new InvalidOperationException("no fallback permitted"),
            256 * 1024,
            256 * 1024);
        Assert.True(result.Succeeded);
        Assert.NotEqual((nuint)(256 * 1024), result.BytesRead);
        Assert.Equal(1, reads);
    }

    [Fact]
    public void Default64KiB_DoesNotUseExperimentalSubreads()
    {
        var reads = 0;
        var result = WindowsMemoryScanner.ReadChunkWithStableRegionFallback(
            (_, size) => { reads++; return Chunk(false, 0, 299); },
            (_, _) => true,
            64 * 1024,
            64 * 1024);
        Assert.False(result.Succeeded);
        Assert.Equal(3, reads);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(128)]
    [InlineData(512)]
    public void UnsupportedChunkSize_FailsClosed(int value)
    {
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            WindowsMemoryScanner.ReadChunkWithStableRegionFallback(
                (_, _) => Chunk(true, 1, null),
                (_, _) => true,
                1,
                value));
        var invalid = LiveConfiguration.Defaults with { FullScanChunkKiB = value };
        Assert.Throws<InvalidDataException>(invalid.Validate);
    }

    [Fact]
    public void LegacyJsonWithoutOptionalChunkFieldPreserves64KiB()
    {
        const string original = """
        {"schemaVersion":1,"processName":"rift_x64","durationSeconds":300,
         "pollIntervalMilliseconds":500,"maxScanBytes":4294967296,
         "maxScanSeconds":10,"outputPath":null,"freshnessTimeoutSeconds":5,"delivery":null}
        """;
        var config = System.Text.Json.JsonSerializer.Deserialize<LiveConfiguration>(
            original, RiftReader2.Infrastructure.JsonFormat.Options);
        Assert.NotNull(config);
        Assert.Equal(64, config.FullScanChunkKiB);
        config.Validate();
        (config with { FullScanChunkKiB = 256 }).Validate();
    }

    private static WindowsMemoryScanner.ScanAttemptResult Attempt(
        bool completed,
        string status,
        byte marker,
        int? error) =>
        new(
            new(
                completed,
                status,
                100,
                completed ? 100 : 50,
                2,
                TimeSpan.FromSeconds(1),
                new ReadOnlyMemory<byte>[] { new byte[] { marker } },
                1,
                0,
                completed ? null : "test failure"),
            error);

    private static WindowsMemoryScanner.ChunkReadResult Chunk(
        bool succeeded,
        nuint bytesRead,
        int? error) => new(succeeded, bytesRead, error);
}
