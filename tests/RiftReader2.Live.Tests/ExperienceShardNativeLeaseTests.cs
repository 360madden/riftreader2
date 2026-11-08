using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class ExperienceShardNativeLeaseTests
{
    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public async Task HoldsLeaseThroughSessionAndRevalidation(int kind)
    {
        var path = Path.Combine(Path.GetTempPath(), "rr2-exp-lease-" + Guid.NewGuid().ToString("N") + ".json");
        var session = new FakeSession(); var held = false; var releasedAfter = false; var reads = 0;
        Task<IAsyncDisposable> Acquire(int pid, long ticks, CancellationToken _)
        {
            Assert.Equal(123, pid); Assert.Equal(456, ticks); held = true;
            return Task.FromResult<IAsyncDisposable>(new FakeLease(() => { held = false; releasedAfter = session.Disposed; }));
        }
        Task<IReadOnlyNativeMemorySession> Open(int _, long __, CancellationToken ___)
        { Assert.True(held); return Task.FromResult<IReadOnlyNativeMemorySession>(session); }
        try
        {
            Assert.Equal(0, await Run(kind, path, default, Acquire, Open, s =>
            {
                Assert.True(held); reads++; return Seed(s.Identity);
            }, s =>
            {
                Assert.True(held); reads++; return new(s.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, Seed(s.Identity), "seed-unavailable");
            }, s =>
            {
                Assert.True(held); reads++; return new(s.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, 1, 2, 0, "unavailable", null);
            }));
            Assert.Equal(1, reads); Assert.True(session.Revalidated); Assert.True(session.Disposed);
            Assert.True(releasedAfter); Assert.False(held);
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public async Task ContentionAndCancellationPreventOpen(int kind)
    {
        var path = Path.Combine(Path.GetTempPath(), "rr2-exp-lease-" + Guid.NewGuid().ToString("N") + ".json");
        var opened = false; var released = false;
        Task<IReadOnlyNativeMemorySession> Open(int _, long __, CancellationToken ___)
        { opened = true; throw new Exception("must not open"); }
        Task<IAsyncDisposable> Deny(int _, long __, CancellationToken ___) => throw new TimeoutException("busy");
        await Assert.ThrowsAsync<TimeoutException>(() => Run(kind, path, default, Deny, Open,
            _ => throw new Exception(), _ => throw new Exception(), _ => throw new Exception()));
        using var cancel = new CancellationTokenSource();
        Task<IAsyncDisposable> Acquire(int _, long __, CancellationToken ___)
        { cancel.Cancel(); return Task.FromResult<IAsyncDisposable>(new FakeLease(() => released = true)); }
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Run(kind, path, cancel.Token, Acquire, Open,
            _ => throw new Exception(), _ => throw new Exception(), _ => throw new Exception()));
        Assert.True(released); Assert.False(opened); Assert.False(File.Exists(path));
    }

    static Task<int> Run(int kind, string path, CancellationToken ct,
        Func<int,long,CancellationToken,Task<IAsyncDisposable>> acquire,
        Func<int,long,CancellationToken,Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession,ExperienceSeedObservation> seed,
        Func<IReadOnlyNativeMemorySession,ExperienceValuesObservation> values,
        Func<IReadOnlyNativeMemorySession,CurrentShardObservation> shard)
    {
        var options = new Dictionary<string,string> { ["--pid"]="123", ["--start-ticks"]="456", ["--output"]=path };
        return kind switch {
            0 => CurrentBuildExperienceSeedSampleCommand.RunAsync(options,TextWriter.Null,ct,acquire,open,seed),
            1 => CurrentBuildExperienceValuesSampleCommand.RunAsync(options,TextWriter.Null,ct,acquire,open,values),
            _ => CurrentBuildCurrentShardSampleCommand.RunAsync(options,TextWriter.Null,ct,acquire,open,shard)
        };
    }

    static ExperienceSeedObservation Seed(NativeProcessIdentity id) =>
        new(id,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,1,2,3,4,null,null,-1,0,0,0,0,[],"index-minus-one",null,null,null);

    sealed class FakeLease(Action release) : IAsyncDisposable
    { public ValueTask DisposeAsync() { release(); return ValueTask.CompletedTask; } }

    sealed class FakeSession : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; } = new(123,456,"rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256,0x140000000,64*1024*1024);
        public bool Revalidated { get; private set; }
        public bool Disposed { get; private set; }
        public NativeReadResult Read(ulong _,int __) => throw new InvalidOperationException("Synthetic only");
        public ValueTask<string?> RevalidateAsync(CancellationToken _) { Revalidated=true; return ValueTask.FromResult<string?>(null); }
        public ValueTask DisposeAsync() { Disposed=true; return ValueTask.CompletedTask; }
    }
}
