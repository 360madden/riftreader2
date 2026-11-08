using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class AbilityRecordsMapsLeaseTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task LeaseHeldThroughReadRevalidationAndSessionDisposal(bool records)
    {
        var path = Path.Combine(Path.GetTempPath(), "rr2-ability-lease-" + Guid.NewGuid().ToString("N") + ".json");
        var options = Options(path);
        var session = new FakeSession(); var held = false; var releasedAfterSession = false;
        Task<IAsyncDisposable> Acquire(int pid, long ticks, CancellationToken _)
        {
            Assert.Equal(123, pid); Assert.Equal(456, ticks); held = true;
            return Task.FromResult<IAsyncDisposable>(new FakeLease(() => { held = false; releasedAfterSession = session.Disposed; }));
        }
        Task<IReadOnlyNativeMemorySession> Open(int _, long __, CancellationToken ___)
        { Assert.True(held); return Task.FromResult<IReadOnlyNativeMemorySession>(session); }
        try
        {
            int result;
            if (records)
                result = await CurrentBuildAbilityRecordsSampleCommand.RunAsync(options, TextWriter.Null, default,
                    Acquire, Open, (s, keys, costs, timing, range, variants) =>
                    {
                        Assert.True(held); Assert.Equal(new uint[] { 42 }, keys);
                        Assert.False(costs); Assert.False(timing); Assert.False(range); Assert.False(variants);
                        return new(s.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, 0, 0, 0, []);
                    });
            else
                result = await CurrentBuildAbilityMapsSampleCommand.RunAsync(options, TextWriter.Null, default,
                    Acquire, Open, s =>
                    {
                        Assert.True(held);
                        return new(s.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, 1, 2, 3, 0, 0, []);
                    });
            Assert.Equal(0, result); Assert.True(session.Revalidated); Assert.True(session.Disposed);
            Assert.True(releasedAfterSession); Assert.False(held);
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task BusyLeaseRefusesBeforeOpen(bool records)
    {
        var path = Path.Combine(Path.GetTempPath(), "rr2-ability-lease-" + Guid.NewGuid().ToString("N") + ".json");
        var opened = false;
        Task<IAsyncDisposable> Deny(int _, long __, CancellationToken ___) => throw new TimeoutException("busy");
        Task<IReadOnlyNativeMemorySession> Open(int _, long __, CancellationToken ___)
        { opened = true; throw new Exception("must not open"); }
        if (records)
            await Assert.ThrowsAsync<TimeoutException>(() => CurrentBuildAbilityRecordsSampleCommand.RunAsync(
                Options(path), TextWriter.Null, default, Deny, Open, (_, _, _, _, _, _) => throw new Exception()));
        else
            await Assert.ThrowsAsync<TimeoutException>(() => CurrentBuildAbilityMapsSampleCommand.RunAsync(
                Options(path), TextWriter.Null, default, Deny, Open, _ => throw new Exception()));
        Assert.False(opened); Assert.False(File.Exists(path));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task CancellationAfterLeaseBeforeOpenReleasesIt(bool records)
    {
        var path = Path.Combine(Path.GetTempPath(), "rr2-ability-lease-" + Guid.NewGuid().ToString("N") + ".json");
        using var cancel = new CancellationTokenSource();
        var released = false; var opened = false;
        Task<IAsyncDisposable> Acquire(int _, long __, CancellationToken ___)
        { cancel.Cancel(); return Task.FromResult<IAsyncDisposable>(new FakeLease(() => released = true)); }
        Task<IReadOnlyNativeMemorySession> Open(int _, long __, CancellationToken ___)
        { opened = true; throw new Exception("must not open"); }
        if (records)
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => CurrentBuildAbilityRecordsSampleCommand.RunAsync(
                Options(path), TextWriter.Null, cancel.Token, Acquire, Open, (_, _, _, _, _, _) => throw new Exception()));
        else
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => CurrentBuildAbilityMapsSampleCommand.RunAsync(
                Options(path), TextWriter.Null, cancel.Token, Acquire, Open, _ => throw new Exception()));
        Assert.True(released); Assert.False(opened); Assert.False(File.Exists(path));
    }

    static Dictionary<string,string> Options(string path) =>
        new() { ["--pid"] = "123", ["--start-ticks"] = "456", ["--output"] = path, ["--keys"] = "42" };

    sealed class FakeLease(Action release) : IAsyncDisposable
    { public ValueTask DisposeAsync() { release(); return ValueTask.CompletedTask; } }

    sealed class FakeSession : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; } = new(123,456,"rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256,0x140000000,64*1024*1024);
        public bool Revalidated { get; private set; }
        public bool Disposed { get; private set; }
        public NativeReadResult Read(ulong _,int __) => throw new InvalidOperationException("Synthetic only");
        public ValueTask<string?> RevalidateAsync(CancellationToken _) { Revalidated = true; return ValueTask.FromResult<string?>(null); }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
