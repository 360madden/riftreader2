using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;

public sealed class LocalizationNativeLeaseTests
{
    [Theory][InlineData(false)][InlineData(true)]
    public async Task LeaseSpansPublicationAndAsyncSessionDisposal(bool dictionary)
    {
        using var f = new Fixture(dictionary);
        Assert.Equal(0, await f.Run());
        Assert.Equal(new[] { "lease", "open", "read", "revalidate", "session-dispose", "lease-dispose" }, f.Events);
        Assert.True(File.Exists(f.Path));
    }

    [Theory][InlineData(false)][InlineData(true)]
    public async Task LeaseRefusalNeverOpens(bool dictionary)
    {
        using var f = new Fixture(dictionary) { Phase = "lease" };
        await Assert.ThrowsAsync<TimeoutException>(() => f.Run());
        Assert.Equal(new[] { "lease" }, f.Events);
        Assert.False(File.Exists(f.Path));
    }

    [Theory][InlineData(false,"open")][InlineData(true,"open")]
    [InlineData(false,"read")][InlineData(true,"read")]
    [InlineData(false,"revalidate")][InlineData(true,"revalidate")]
    public async Task FailuresReleaseAndDoNotPublish(bool dictionary, string phase)
    {
        using var f = new Fixture(dictionary) { Phase = phase };
        await Assert.ThrowsAsync<InvalidDataException>(() => f.Run());
        Assert.Equal("lease-dispose", f.Events[^1]);
        Assert.True(f.LeaseDisposed);
        Assert.False(File.Exists(f.Path));
    }

    [Theory][InlineData(false)][InlineData(true)]
    public async Task CancelWaitingLeaseDoesNotOpen(bool dictionary)
    {
        using var f = new Fixture(dictionary) { Phase = "wait" };
        using var cts = new CancellationTokenSource();
        var run = f.Run(cts.Token);
        await f.WaitEntered.Task.WaitAsync(TimeSpan.FromSeconds(3));
        cts.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => run);
        Assert.Equal(new[] { "lease" }, f.Events);
        Assert.False(File.Exists(f.Path));
    }

    [Theory][InlineData(false)][InlineData(true)]
    public async Task DuplicateKeysFailBeforeAcquiring(bool dictionary)
    {
        using var f = new Fixture(dictionary) { Keys = "7,7" };
        await Assert.ThrowsAsync<ArgumentException>(() => f.Run());
        Assert.Empty(f.Events);
        Assert.False(File.Exists(f.Path));
    }

    private sealed class Fixture(bool dictionary) : IDisposable
    {
        public string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "rr2-localization-lease-" + Guid.NewGuid().ToString("N") + ".json");
        public string Keys { get; init; } = "7,8";
        public string? Phase { get; init; }
        public bool LeaseDisposed;
        public List<string> Events { get; } = [];
        public TaskCompletionSource WaitEntered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public Task<int> Run(CancellationToken token = default)
        {
            var options = new Dictionary<string,string> { ["--pid"]="123", ["--start-ticks"]="456", ["--keys"]=Keys, ["--output"]=Path };
            return dictionary ?
                CurrentBuildLocalizationDictionarySampleCommand.RunAsync(options, new StringWriter(), token, Open,
                    (s,k) => { Read(k); return new(s.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,0,0,0,0,0,0,0,0,0,"",[]); }, Acquire) :
                CurrentBuildLocalizationSampleCommand.RunAsync(options, new StringWriter(), token, Open,
                    (s,k) => { Read(k); return new(s.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,0,0,0,0,0,0,0,[]); }, Acquire);
        }
        private async Task<IAsyncDisposable> Acquire(int pid,long ticks,string sha,CancellationToken token)
        {
            Assert.Equal(123,pid); Assert.Equal(456,ticks); Assert.Equal(CurrentBuildPlayerLookup.GameSha256,sha);
            Events.Add("lease");
            if (Phase=="lease") throw new TimeoutException("busy");
            if (Phase=="wait") { WaitEntered.SetResult(); await Task.Delay(Timeout.Infinite,token); }
            return new Lease(this);
        }
        private Task<IReadOnlyNativeMemorySession> Open(int pid,long ticks,CancellationToken token)
        {
            Assert.False(LeaseDisposed); Assert.Equal(123,pid); Assert.Equal(456,ticks); Events.Add("open");
            if(Phase=="open") throw new InvalidDataException("open failed");
            return Task.FromResult<IReadOnlyNativeMemorySession>(new Session(this));
        }
        private void Read(IReadOnlyList<uint> keys)
        {
            Assert.False(LeaseDisposed); Assert.Equal(new uint[] {7,8},keys); Events.Add("read");
            if(Phase=="read") throw new InvalidDataException("read failed");
        }
        public void Dispose() { if(File.Exists(Path)) File.Delete(Path); }
        private sealed class Lease(Fixture f) : IAsyncDisposable
        {
            public ValueTask DisposeAsync() { f.Events.Add("lease-dispose"); f.LeaseDisposed=true; return ValueTask.CompletedTask; }
        }
        private sealed class Session(Fixture f) : IReadOnlyNativeMemorySession
        {
            public NativeProcessIdentity Identity { get; } = new(123,456,@"C:\RIFT\rift_x64.exe",CurrentBuildPlayerLookup.GameSha256,0x140000000,0x4000000);
            public NativeReadResult Read(ulong address,int count) => throw new Exception("no native reads");
            public ValueTask<string?> RevalidateAsync(CancellationToken token)
            {
                token.ThrowIfCancellationRequested(); Assert.False(f.LeaseDisposed); f.Events.Add("revalidate");
                return ValueTask.FromResult<string?>(f.Phase=="revalidate" ? "changed" : null);
            }
            public async ValueTask DisposeAsync()
            {
                Assert.False(f.LeaseDisposed); await Task.Yield(); Assert.False(f.LeaseDisposed);
                f.Events.Add("session-dispose");
                if(f.Phase is null) Assert.True(File.Exists(f.Path));
            }
        }
    }
}
