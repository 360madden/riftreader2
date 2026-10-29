namespace RiftReader2.Live.Tests;

public sealed class WindowsMemoryScannerRetryTests
{
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
}
