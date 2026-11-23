using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class TargetZoneNativeReadLeaseTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task LeaseIsHeldThroughReadAndSessionDisposal(bool zone)
    {
        var path = Path.Combine(Path.GetTempPath(), "rr2-target-zone-lease-" + Guid.NewGuid().ToString("N") + ".json");
        var options = new Dictionary<string, string> { ["--pid"] = "123", ["--start-ticks"] = "456", ["--output"] = path };
        var session = new FakeSession(); var held = false; var disposedAfterSession = false; var read = false;
        var outputExistsAtRelease = false;
        Task<IAsyncDisposable> Acquire(int p, long t, CancellationToken _)
        {
            Assert.Equal(123, p); Assert.Equal(456, t); held = true;
            return Task.FromResult<IAsyncDisposable>(new FakeLease(() => { held = false; disposedAfterSession = session.Disposed; outputExistsAtRelease = File.Exists(path); }));
        }
        Task<IReadOnlyNativeMemorySession> Open(int _, long __, CancellationToken ___)
        { Assert.True(held); return Task.FromResult<IReadOnlyNativeMemorySession>(session); }
        try
        {
            int result;
            if (zone)
                result = await CurrentBuildZoneSeedSampleCommand.RunAsync(options, TextWriter.Null, default,
                    Acquire, Open, (s, pid) =>
                    {
                        Assert.True(held); Assert.Equal(123, pid); read = true;
                        return new(s.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, 1, 2, 3, 4, 0, "null-provider");
                    });
            else
                result = await CurrentBuildSelectedTargetSampleCommand.RunAsync(options, TextWriter.Null, default,
                    Acquire, Open, (s, a, b, c) =>
                    {
                        Assert.True(held); Assert.False(a); Assert.False(b); Assert.False(c); read = true;
                        return new(s.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, 1, "unavailable", "raw-getter-zero-candidate", null, null, null, null, null);
                    });
            Assert.Equal(0, result); Assert.True(read); Assert.True(session.Revalidated);
            Assert.True(session.Disposed); Assert.True(disposedAfterSession); Assert.False(held);
            Assert.Equal(!zone, outputExistsAtRelease);
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task LeaseTimeoutPreventsSessionOpen(bool zone)
    {
        var path = Path.Combine(Path.GetTempPath(), "rr2-target-zone-lease-" + Guid.NewGuid().ToString("N") + ".json");
        var options = new Dictionary<string, string> { ["--pid"] = "123", ["--start-ticks"] = "456", ["--output"] = path };
        var opened = false;
        Task<IAsyncDisposable> Deny(int _, long __, CancellationToken ___) => throw new TimeoutException("busy");
        Task<IReadOnlyNativeMemorySession> Open(int _, long __, CancellationToken ___)
        { opened = true; throw new Exception("unexpected"); }
        if (zone)
            await Assert.ThrowsAsync<TimeoutException>(() => CurrentBuildZoneSeedSampleCommand.RunAsync(options, TextWriter.Null, default,
                Deny, Open, (_, _) => throw new Exception("unexpected")));
        else
            await Assert.ThrowsAsync<TimeoutException>(() => CurrentBuildSelectedTargetSampleCommand.RunAsync(options, TextWriter.Null, default,
                Deny, Open, (_, _, _, _) => throw new Exception("unexpected")));
        Assert.False(opened); Assert.False(File.Exists(path));
    }

    [Fact]
    public async Task SelectedTargetSupportsExplicit1179ShaAndRejectsWrongBuild()
    {
        var path = Path.Combine(Path.GetTempPath(), "rr2-target-sha-" + Guid.NewGuid().ToString("N") + ".json");
        var options = new Dictionary<string, string>
        {
            ["--pid"] = "123",
            ["--start-ticks"] = "456",
            ["--output"] = path
        };
        var session = new FakeSession(updated: true);
        var calls = 0;
        Task<IAsyncDisposable> Acquire(int _, long __, CancellationToken ___)
            => Task.FromResult<IAsyncDisposable>(new FakeLease(() => { }));
        Task<IReadOnlyNativeMemorySession> Open(int _, long __, CancellationToken ___)
        { calls++; return Task.FromResult<IReadOnlyNativeMemorySession>(session); }
        SelectedTargetObservation Read(IReadOnlyNativeMemorySession s, bool _, bool __, bool ___)
            => new(s.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, 1,
                   "unavailable", "raw-getter-zero-candidate", null, null, null, null, null);
        try
        {
            await Assert.ThrowsAsync<InvalidDataException>(() =>
                CurrentBuildSelectedTargetSampleCommand.RunAsync(options, TextWriter.Null, default,
                    Acquire, Open, Read));
            Assert.Equal(1, calls);
            Assert.False(File.Exists(path));
            options["--sha256"] = CurrentBuildPlayerLookup.UpdatedGameSha256;
            Assert.Equal(0, await CurrentBuildSelectedTargetSampleCommand.RunAsync(
                options, TextWriter.Null, default, Acquire, Open, Read));
            Assert.True(File.Exists(path));
            Assert.Equal(2, calls);
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Fact]
    public async Task SelectedTargetRefusesUnsupportedBuildShaBeforeLease()
    {
        var options = new Dictionary<string, string>
        {
            ["--pid"] = "123",
            ["--start-ticks"] = "456",
            ["--sha256"] = new string('F', 64),
            ["--output"] = Path.Combine(Path.GetTempPath(), Guid.NewGuid() + ".json")
        };
        await Assert.ThrowsAsync<ArgumentException>(() =>
            CurrentBuildSelectedTargetSampleCommand.RunAsync(
                options, TextWriter.Null, default,
                (_, _, _) => throw new InvalidOperationException("no lease permitted"),
                (_, _, _) => throw new InvalidOperationException("no session permitted"),
                (_, _, _, _) => throw new InvalidOperationException("no read permitted")));
    }

    sealed class FakeLease(Action release) : IAsyncDisposable
    { public ValueTask DisposeAsync() { release(); return ValueTask.CompletedTask; } }

    sealed class FakeSession(bool updated = false) : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; } = new(123, 456, "rift_x64.exe",
            updated ? CurrentBuildPlayerLookup.UpdatedGameSha256 : CurrentBuildPlayerLookup.GameSha256, 0x140000000, 64 * 1024 * 1024);
        public bool Revalidated { get; private set; }
        public bool Disposed { get; private set; }
        public NativeReadResult Read(ulong _, int __) => throw new InvalidOperationException("Synthetic session only");
        public ValueTask<string?> RevalidateAsync(CancellationToken _) { Revalidated = true; return ValueTask.FromResult<string?>(null); }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
