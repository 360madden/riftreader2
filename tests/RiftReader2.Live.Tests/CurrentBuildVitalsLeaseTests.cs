using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildVitalsLeaseTests
{
    [Fact]
    public async Task LeaseSpansOpenReadRevalidationPublicationAndAsyncSessionDisposal()
    {
        using var f = new Fixture();
        Assert.Equal(0, await f.Run());
        Assert.Equal(new[] { "lease", "open", "read", "revalidate", "session-dispose", "lease-dispose" }, f.Events);
        Assert.True(File.Exists(f.Path));
        Assert.True(f.LeaseDisposed);
    }

    [Fact]
    public async Task LeaseRefusalNeverOpensOrPublishes()
    {
        using var f = new Fixture { LeaseError = new TimeoutException("busy") };
        await Assert.ThrowsAsync<TimeoutException>(() => f.Run());
        Assert.Equal(new[] { "lease" }, f.Events);
        Assert.False(File.Exists(f.Path));
    }

    [Fact]
    public async Task WaitingLeaseCancellationNeverOpensOrPublishes()
    {
        using var f = new Fixture();
        using var cts = new CancellationTokenSource();
        var requested = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        f.AcquireOverride = async token =>
        {
            requested.SetResult();
            await Task.Delay(Timeout.Infinite, token);
            throw new Exception("unreachable");
        };
        var run = f.Run(cts.Token);
        await requested.Task.WaitAsync(TimeSpan.FromSeconds(3));
        cts.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => run);
        Assert.Equal(new[] { "lease" }, f.Events);
        Assert.False(File.Exists(f.Path));
    }

    [Theory]
    [InlineData("open")]
    [InlineData("read")]
    [InlineData("revalidate")]
    public async Task FailureReleasesLeaseAndPublishesNothing(string phase)
    {
        using var f = new Fixture { Failure = phase };
        await Assert.ThrowsAsync<InvalidDataException>(() => f.Run());
        Assert.True(f.LeaseDisposed);
        Assert.Equal("lease-dispose", f.Events[^1]);
        if (phase != "open") Assert.Contains("session-dispose", f.Events);
        Assert.False(File.Exists(f.Path));
    }

    private sealed class Fixture : IDisposable
    {
        public string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "rr2-vitals-lease-" + Guid.NewGuid().ToString("N") + ".json");
        public List<string> Events { get; } = [];
        public bool LeaseDisposed;
        public string? Failure { get; init; }
        public Exception? LeaseError { get; init; }
        public Func<CancellationToken, Task<IAsyncDisposable>>? AcquireOverride;
        public Task<int> Run(CancellationToken token = default) =>
            CurrentBuildVitalsSampleCommand.RunAsync(
                new Dictionary<string, string> { ["--pid"] = "123", ["--start-ticks"] = "456", ["--output"] = Path },
                new StringWriter(), token,
                (pid, ticks, _) =>
                {
                    Assert.Equal(123, pid); Assert.Equal(456, ticks); Assert.False(LeaseDisposed);
                    Events.Add("open");
                    if (Failure == "open") throw new InvalidDataException("open failed");
                    return Task.FromResult<IReadOnlyNativeMemorySession>(new Session(this));
                },
                session =>
                {
                    Assert.False(LeaseDisposed); Events.Add("read");
                    if (Failure == "read") throw new InvalidDataException("read failed");
                    return new(session.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, 123,
                        new("unavailable", "test"), new("unavailable", "test"));
                },
                (pid, ticks, sha, ct) =>
                {
                    Assert.Equal(123, pid); Assert.Equal(456, ticks);
                    Assert.Equal(CurrentBuildPlayerLookup.GameSha256, sha);
                    Events.Add("lease");
                    if (LeaseError is not null) throw LeaseError;
                    return AcquireOverride is not null ? AcquireOverride(ct) :
                        Task.FromResult<IAsyncDisposable>(new Lease(this));
                });
        public void Dispose() { if (File.Exists(Path)) File.Delete(Path); }
        private sealed class Lease(Fixture f) : IAsyncDisposable
        {
            public ValueTask DisposeAsync() { f.Events.Add("lease-dispose"); f.LeaseDisposed = true; return ValueTask.CompletedTask; }
        }
        private sealed class Session(Fixture f) : IReadOnlyNativeMemorySession
        {
            public NativeProcessIdentity Identity { get; } = new(123, 456, @"C:\RIFT\rift_x64.exe",
                CurrentBuildPlayerLookup.GameSha256, 0x140000000, 0x4000000);
            public NativeReadResult Read(ulong address, int length) => throw new Exception("no native reads");
            public ValueTask<string?> RevalidateAsync(CancellationToken token)
            {
                token.ThrowIfCancellationRequested(); Assert.False(f.LeaseDisposed); f.Events.Add("revalidate");
                return ValueTask.FromResult<string?>(f.Failure == "revalidate" ? "changed" : null);
            }
            public async ValueTask DisposeAsync()
            {
                Assert.False(f.LeaseDisposed);
                await Task.Yield();
                Assert.False(f.LeaseDisposed);
                f.Events.Add("session-dispose");
                if (f.Failure is null) Assert.True(File.Exists(f.Path));
            }
        }
    }
}
