using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

/// <summary>Offline command-seam test using the real shared file lease.</summary>
public sealed class CrossCommandNativeReadLeaseTests
{
    [Fact]
    public async Task PositionBlocksTargetUntilSessionDisposes()
    {
        var root = Path.Combine(Path.GetTempPath(), "rr2-cross-command-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var positionPath = Path.Combine(root, "position.json");
        var targetPath = Path.Combine(root, "target.json");
        var firstEntered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var proceed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var positionSession = new FakeSession();
        var targetSession = new FakeSession();
        var targetOpens = 0;
        Task<IAsyncDisposable> Lease(int pid, long ticks, CancellationToken ct) =>
            Acquire(pid, ticks, ct);
        async Task<IAsyncDisposable> Acquire(int pid, long ticks, CancellationToken ct) =>
            await NativeReadFileLease.AcquireAsync(pid, ticks, CurrentBuildPlayerLookup.GameSha256,
                TimeSpan.FromMilliseconds(150), ct, Path.Combine(root, "lease"));
        var positionOptions = Options(positionPath);
        positionOptions["--samples"] = "1";
        var targetOptions = Options(targetPath);
        Task<int>? first = null;
        try
        {
            first = CurrentBuildPositionSampleCommand.RunAsync(positionOptions, TextWriter.Null, default, Lease,
                async (_, _, _) => {
                    firstEntered.SetResult();
                    await proceed.Task.WaitAsync(TimeSpan.FromSeconds(5));
                    return positionSession;
                }, _ => new CurrentBuildOwnedPosition(1, new(1, 2, 3)));
            await firstEntered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Task<IReadOnlyNativeMemorySession> OpenTarget(int _, long __, CancellationToken ___)
            { targetOpens++; return Task.FromResult<IReadOnlyNativeMemorySession>(targetSession); }
            SelectedTargetObservation Target(IReadOnlyNativeMemorySession s, bool _, bool __, bool ___) =>
                new(s.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, 1,
                    "unavailable", "raw-getter-zero-candidate", null, null, null, null, null);

            await Assert.ThrowsAsync<TimeoutException>(() =>
                CurrentBuildSelectedTargetSampleCommand.RunAsync(targetOptions, TextWriter.Null, default,
                    Lease, OpenTarget, Target));
            Assert.Equal(0, targetOpens);
            Assert.False(File.Exists(targetPath));
            proceed.SetResult();
            Assert.Equal(0, await first.WaitAsync(TimeSpan.FromSeconds(5)));
            Assert.True(positionSession.Disposed);
            Assert.Equal(0, await CurrentBuildSelectedTargetSampleCommand.RunAsync(targetOptions, TextWriter.Null,
                default, Lease, OpenTarget, Target));
            Assert.Equal(1, targetOpens);
            Assert.True(targetSession.Disposed);
        }
        finally
        {
            proceed.TrySetResult();
            if (first is not null) { try { await first; } catch { } }
            Directory.Delete(root, recursive: true);
        }
    }

    static Dictionary<string,string> Options(string path) =>
        new() { ["--pid"] = "123", ["--start-ticks"] = "456", ["--output"] = path };

    sealed class FakeSession : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; } = new(123, 456, "rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 64 * 1024 * 1024);
        public bool Disposed { get; private set; }
        public NativeReadResult Read(ulong _, int __) => throw new InvalidOperationException("Synthetic only");
        public ValueTask<string?> RevalidateAsync(CancellationToken _) => ValueTask.FromResult<string?>(null);
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
