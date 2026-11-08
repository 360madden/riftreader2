using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;

public sealed class PresentationVariantNativeLeaseTests
{
    [Theory][InlineData(0)][InlineData(1)][InlineData(2)][InlineData(3)]
    public async Task LeaseSpansPublicationAndAsyncSessionDisposal(int command)
    {
        using var f = new Fixture(command);
        Assert.Equal(0, await f.Run());
        Assert.Equal(new[] { "lease", "open", "read", "revalidate", "session-dispose", "lease-dispose" }, f.Events);
        Assert.True(File.Exists(f.Path));
    }

    [Theory][InlineData(0)][InlineData(1)][InlineData(2)][InlineData(3)]
    public async Task LeaseRefusalNeverOpens(int command)
    {
        using var f = new Fixture(command) { Phase = "lease" };
        await Assert.ThrowsAsync<TimeoutException>(() => f.Run());
        Assert.Equal(new[] { "lease" }, f.Events);
        Assert.False(File.Exists(f.Path));
        Assert.Equal("",f.Output.ToString());
    }

    [Theory]
    [InlineData(0,"open")][InlineData(1,"open")][InlineData(2,"open")][InlineData(3,"open")]
    [InlineData(0,"read")][InlineData(1,"read")][InlineData(2,"read")][InlineData(3,"read")]
    [InlineData(0,"revalidate")][InlineData(1,"revalidate")][InlineData(2,"revalidate")][InlineData(3,"revalidate")]
    [InlineData(0,"pid")][InlineData(1,"pid")][InlineData(2,"pid")][InlineData(3,"pid")]
    [InlineData(0,"start")][InlineData(1,"start")][InlineData(2,"start")][InlineData(3,"start")]
    [InlineData(0,"sha")][InlineData(1,"sha")][InlineData(2,"sha")][InlineData(3,"sha")]
    public async Task FailuresReleaseAndDoNotPublish(int command, string phase)
    {
        using var f = new Fixture(command) { Phase = phase };
        await Assert.ThrowsAsync<InvalidDataException>(() => f.Run());
        Assert.Equal("lease-dispose", f.Events[^1]);
        Assert.True(f.LeaseDisposed);
        if(phase is "pid" or "start" or "sha") Assert.DoesNotContain("read",f.Events);
        Assert.False(File.Exists(f.Path));
        Assert.Equal("",f.Output.ToString());
    }

    [Theory][InlineData(0)][InlineData(1)][InlineData(2)][InlineData(3)]
    public async Task CancelWaitingLeaseDoesNotOpen(int command)
    {
        using var f = new Fixture(command) { Phase = "wait" };
        using var cts = new CancellationTokenSource();
        var run = f.Run(cts.Token);
        await f.WaitEntered.Task.WaitAsync(TimeSpan.FromSeconds(3));
        cts.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => run);
        Assert.Equal(new[] { "lease" }, f.Events);
        Assert.False(File.Exists(f.Path));
        Assert.Equal("",f.Output.ToString());
    }

    private sealed class Fixture(int command) : IDisposable
    {
        public string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "rr2-presentation-variant-lease-" + Guid.NewGuid().ToString("N") + ".json");
        public string? Phase { get; init; }
        public bool LeaseDisposed;
        public StringWriter Output { get; } = new();
        public List<string> Events { get; } = [];
        public TaskCompletionSource WaitEntered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public Task<int> Run(CancellationToken token = default)
        {
            var options = new Dictionary<string,string> { ["--pid"]="123", ["--start-ticks"]="456", ["--output"]=Path };
            return command switch
            {
                0 => CurrentBuildVariantGuardSampleCommand.RunAsync(options,Output,token,Open,s=>{ Read(); return null!; },Acquire),
                1 => CurrentBuildPlayerDecorationSampleCommand.RunAsync(options,Output,token,Open,s=>{ Read(); return null!; },Acquire),
                2 => CurrentBuildPlayerNameSampleCommand.RunAsync(options,Output,token,Open,s=>{ Read(); return null!; },Acquire),
                3 => CurrentBuildPlayerRaceSampleCommand.RunAsync(options,Output,token,Open,s=>{ Read(); return null!; },Acquire),
                _ => throw new ArgumentOutOfRangeException()
            };
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
        private void Read()
        {
            Assert.False(LeaseDisposed); Events.Add("read");
            if(Phase=="read") throw new InvalidDataException("read failed");
        }
        public void Dispose() { if(File.Exists(Path)) File.Delete(Path); }
        private sealed class Lease(Fixture f) : IAsyncDisposable
        {
            public ValueTask DisposeAsync() { f.Events.Add("lease-dispose"); f.LeaseDisposed=true; return ValueTask.CompletedTask; }
        }
        private sealed class Session(Fixture f) : IReadOnlyNativeMemorySession
        {
            public NativeProcessIdentity Identity { get; } = new(f.Phase=="pid"?124:123,f.Phase=="start"?457:456,@"C:\RIFT\rift_x64.exe",f.Phase=="sha"?new string('A',64):CurrentBuildPlayerLookup.GameSha256,0x140000000,0x4000000);
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
