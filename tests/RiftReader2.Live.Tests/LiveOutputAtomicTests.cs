using System.Text.Json;

namespace RiftReader2.Live.Tests;

public sealed class LiveOutputAtomicTests
{
    private static LiveReaderSnapshot Snapshot(long sequence) => new(
        1, Guid.NewGuid(), new string('a', 32), sequence,
        "2026-11-08T12:00:00Z", 0, "running", null, null,
        new LiveRiftReader2Report(1, "unbound", "unavailable", null,
            0, 0, null, null, 5000, null, "no-matching-candidate",
            null, null, null, null, null,
            new LiveScanReport("complete", true, 0, 0, 0, 0, 0, 0, 0, 0, null)),
        new LiveDeliveryReport(false, "disabled", null, null, null));

    private static string NewDirectory()
    {
        var path = Path.Combine(Path.GetTempPath(), "rr2-atomic-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(path);
        return path;
    }

    private static long SequenceAt(string path)
    {
        using var json = JsonDocument.Parse(File.ReadAllText(path));
        return json.RootElement.GetProperty("sequence").GetInt64();
    }

    [Fact]
    public async Task RepeatedWritesReplaceCompleteSnapshotAndLeaveNoTemporaryFiles()
    {
        var directory = NewDirectory();
        try
        {
            var output = Path.Combine(directory, "latest.json");
            await LiveOutput.WriteAtomicAsync(output, Snapshot(1), CancellationToken.None);
            await LiveOutput.WriteAtomicAsync(output, Snapshot(2), CancellationToken.None);
            Assert.Equal(2, SequenceAt(output));
            Assert.Equal("latest.json", Path.GetFileName(Assert.Single(Directory.GetFiles(directory))));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public async Task TemporaryExclusiveReaderLock_DoesNotTerminatePublication()
    {
        if (!OperatingSystem.IsWindows())
            return;
        var directory = NewDirectory();
        try
        {
            var output = Path.Combine(directory, "latest.json");
            await LiveOutput.WriteAtomicAsync(output, Snapshot(1), CancellationToken.None);
            using (var blockingReader = new FileStream(output, FileMode.Open, FileAccess.Read, FileShare.None))
            {
                var replacement = LiveOutput.WriteAtomicAsync(output, Snapshot(2), CancellationToken.None);
                await Task.Delay(300);
                Assert.False(replacement.IsCompleted);
                blockingReader.Dispose();
                await replacement.WaitAsync(TimeSpan.FromSeconds(5));
            }
            Assert.Equal(2, SequenceAt(output));
            Assert.Single(Directory.GetFiles(directory));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public async Task PermanentExclusiveReaderLock_FailsClosedAndKeepsPreviousSnapshot()
    {
        if (!OperatingSystem.IsWindows())
            return;
        var directory = NewDirectory();
        try
        {
            var output = Path.Combine(directory, "latest.json");
            await LiveOutput.WriteAtomicAsync(output, Snapshot(1), CancellationToken.None);
            using (var blockingReader = new FileStream(output, FileMode.Open, FileAccess.Read, FileShare.None))
            {
                var error = await Record.ExceptionAsync(
                    () => LiveOutput.WriteAtomicAsync(output, Snapshot(2), CancellationToken.None));
                Assert.True(error is IOException or UnauthorizedAccessException,
                    $"Expected bounded file contention failure; got {error?.GetType().Name ?? "success"}");
            }
            Assert.Equal(1, SequenceAt(output));
            Assert.Single(Directory.GetFiles(directory));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public async Task CancellationDuringContention_KeepsOldCompleteSnapshot()
    {
        if (!OperatingSystem.IsWindows())
            return;
        var directory = NewDirectory();
        try
        {
            var output = Path.Combine(directory, "latest.json");
            await LiveOutput.WriteAtomicAsync(output, Snapshot(1), CancellationToken.None);
            using (var blockingReader = new FileStream(output, FileMode.Open, FileAccess.Read, FileShare.None))
            using (var cancellation = new CancellationTokenSource(TimeSpan.FromMilliseconds(150)))
            {
                await Assert.ThrowsAnyAsync<OperationCanceledException>(
                    () => LiveOutput.WriteAtomicAsync(output, Snapshot(2), cancellation.Token));
            }
            Assert.Equal(1, SequenceAt(output));
            Assert.Single(Directory.GetFiles(directory));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }
}
