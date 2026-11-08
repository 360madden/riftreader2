using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildLocationContextSampleCommandTests
{
    [Fact]
    public async Task PublishesCandidateWithUnavailableZoneAfterRevalidation()
    {
        using var f = new Fixture();
        var output = new StringWriter();
        Assert.Equal(0, await f.Run(output));
        Assert.True(f.Session.Revalidated);
        Assert.True(f.Session.Disposed);
        using var json = JsonDocument.Parse(await File.ReadAllTextAsync(f.Path));
        var root = json.RootElement;
        Assert.Equal("native-current-location-context-candidate/1", root.GetProperty("contractVersion").GetString());
        var observation = root.GetProperty("observation");
        Assert.Equal("candidate-only", observation.GetProperty("status").GetString());
        Assert.Equal("18446744073709551615", observation.GetProperty("unitKey").GetString());
        Assert.Equal("uFFFFFFFFFFFFFFFF", observation.GetProperty("unitIdCandidate").GetString());
        Assert.Equal("unavailable", observation.GetProperty("worldInstanceStatus").GetString());
        Assert.Equal("null-provider", observation.GetProperty("zone").GetProperty("status").GetString());
        Assert.Equal(JsonValueKind.Null, observation.GetProperty("zone").GetProperty("zoneIdCandidate").ValueKind);
        Assert.Contains("unverified", observation.GetProperty("qualification").GetString());
        Assert.Contains("native-current-location-context-summary/1", output.ToString());
    }

    [Theory]
    [InlineData("--pid", "0")]
    [InlineData("--pid", "abc")]
    [InlineData("--start-ticks", "-1")]
    [InlineData("--output", " ")]
    public async Task RejectsInvalidOptionsBeforeOpening(string key, string value)
    {
        using var f = new Fixture(); f.Options[key] = value;
        await Assert.ThrowsAsync<ArgumentException>(() => f.Run(new StringWriter()));
        Assert.False(f.Opened);
        Assert.False(File.Exists(f.Path));
    }

    [Fact]
    public async Task ExistingOutputIsPreservedWithoutOpening()
    {
        using var f = new Fixture();
        await File.WriteAllTextAsync(f.Path, "original");
        await Assert.ThrowsAsync<IOException>(() => f.Run(new StringWriter()));
        Assert.Equal("original", await File.ReadAllTextAsync(f.Path));
        Assert.False(f.Opened);
    }

    [Fact]
    public async Task InvalidatedProcessProducesNoReportOrSummary()
    {
        using var f = new Fixture(); f.Session.RevalidationError = "changed";
        var output = new StringWriter();
        await Assert.ThrowsAsync<InvalidDataException>(() => f.Run(output));
        Assert.False(File.Exists(f.Path));
        Assert.Equal("", output.ToString());
        Assert.True(f.Session.Disposed);
    }

    [Fact]
    public async Task CancellationBeforeOpenOrAfterRevalidationDoesNotPublish()
    {
        using var f = new Fixture(); using var cancelled = new CancellationTokenSource();
        cancelled.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => f.Run(new StringWriter(), cancelled.Token));
        Assert.False(f.Opened);
        using var after = new CancellationTokenSource(); f.Session.OnRevalidate = after.Cancel;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => f.Run(new StringWriter(), after.Token));
        Assert.False(File.Exists(f.Path));
        Assert.True(f.Session.Disposed);
    }

    [Theory]
    [InlineData("process")]
    [InlineData("start")]
    [InlineData("build")]
    public async Task RejectsOpenedIdentityMismatchBeforeCapture(string field)
    {
        using var f = new Fixture();
        f.Session.Identity = field switch
        {
            "process" => f.Session.Identity with { ProcessId = 999 },
            "start" => f.Session.Identity with { ProcessStartUtcTicks = 999 },
            _ => f.Session.Identity with { ExecutableSha256 = new string('0', 64) }
        };
        await Assert.ThrowsAsync<InvalidDataException>(() => f.Run(new StringWriter()));
        Assert.False(f.Captured);
        Assert.False(File.Exists(f.Path));
        Assert.True(f.Session.Disposed);
    }

    [Theory]
    [InlineData("observation-epoch")]
    [InlineData("zone-epoch")]
    [InlineData("zone-key")]
    [InlineData("zero-key")]
    [InlineData("formatted-id")]
    public async Task RejectsMixedSourceIdentitiesWithoutPublication(string change)
    {
        using var f = new Fixture(); f.Change = change; var output = new StringWriter();
        await Assert.ThrowsAsync<InvalidDataException>(() => f.Run(output));
        Assert.False(File.Exists(f.Path));
        Assert.Equal("", output.ToString());
        Assert.True(f.Session.Disposed);
    }

    [Fact]
    public async Task PublicationRaceDoesNotOverwriteOrEmitSuccess()
    {
        using var f = new Fixture(); f.Session.OnRevalidate = () => File.WriteAllText(f.Path, "racer");
        var output = new StringWriter();
        await Assert.ThrowsAsync<IOException>(() => f.Run(output));
        Assert.Equal("racer", await File.ReadAllTextAsync(f.Path));
        Assert.Equal("", output.ToString());
    }

    [Fact]
    public async Task LeaseCoversOpenReadRevalidationAndAwaitedSessionDisposal()
    {
        using var f = new Fixture(); var events = new List<string>();
        var lease = new TestLease { OnDispose = () => { Assert.True(f.Session.Disposed); events.Add("lease-dispose"); } };
        f.LeaseAcquire = (pid, ticks, sha, timeout, token) =>
        {
            Assert.Equal(123, pid); Assert.Equal(456, ticks); Assert.Equal(CurrentBuildPlayerLookup.GameSha256, sha);
            Assert.Equal(TimeSpan.FromSeconds(5), timeout); events.Add("lease-acquire");
            return Task.FromResult<IAsyncDisposable>(lease);
        };
        f.OnOpen = () => { Assert.False(lease.Disposed); events.Add("open"); };
        f.OnRead = () => { Assert.False(lease.Disposed); events.Add("read"); };
        f.Session.OnRevalidate = () => { Assert.False(lease.Disposed); events.Add("revalidate"); };
        f.Session.OnDisposeAsync = async () =>
        {
            Assert.False(lease.Disposed); events.Add("session-dispose-start");
            await Task.Yield(); Assert.False(lease.Disposed); events.Add("session-dispose-end");
        };
        await f.Run(new StringWriter());
        Assert.True(lease.Disposed);
        Assert.Equal(new[] { "lease-acquire", "open", "read", "revalidate", "session-dispose-start", "session-dispose-end", "lease-dispose" }, events);
    }

    [Theory] [InlineData(false)] [InlineData(true)]
    public async Task LeaseTimeoutOrCancellationCannotOpenOrPublish(bool cancellation)
    {
        using var f = new Fixture(); var output = new StringWriter();
        f.LeaseAcquire = (_, _, _, _, _) => cancellation
            ? Task.FromCanceled<IAsyncDisposable>(new CancellationToken(true))
            : Task.FromException<IAsyncDisposable>(new TimeoutException("lease busy"));
        if (cancellation) await Assert.ThrowsAnyAsync<OperationCanceledException>(() => f.Run(output));
        else await Assert.ThrowsAsync<TimeoutException>(() => f.Run(output));
        Assert.False(f.Opened); Assert.False(f.Session.Disposed);
        Assert.False(File.Exists(f.Path)); Assert.Equal("", output.ToString());
    }

    [Fact]
    public async Task CancellationAfterLeaseAndReadFailureBothReleaseWithoutEarlyUnlock()
    {
        using var f = new Fixture(); using var cancel = new CancellationTokenSource();
        var lease = new TestLease();
        f.LeaseAcquire = (_, _, _, _, _) => { cancel.Cancel(); return Task.FromResult<IAsyncDisposable>(lease); };
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => f.Run(new StringWriter(), cancel.Token));
        Assert.True(lease.Disposed); Assert.False(f.Opened); Assert.False(f.Session.Disposed);
        using var failed = new Fixture();
        var failedLease = new TestLease { OnDispose = () => Assert.True(failed.Session.Disposed) };
        failed.LeaseAcquire = (_, _, _, _, _) => Task.FromResult<IAsyncDisposable>(failedLease);
        failed.OnRead = () => throw new InvalidDataException("source changed");
        failed.Session.OnDisposeAsync = () => { Assert.False(failedLease.Disposed); return ValueTask.CompletedTask; };
        await Assert.ThrowsAsync<InvalidDataException>(() => failed.Run(new StringWriter()));
        Assert.True(failedLease.Disposed); Assert.False(File.Exists(failed.Path));
    }

    [Theory] [InlineData(false)] [InlineData(true)]
    public async Task OpenOrRevalidationFailureReleasesLease(bool failedRevalidation)
    {
        using var f = new Fixture(); var lease = new TestLease(); var output = new StringWriter();
        f.LeaseAcquire = (_, _, _, _, _) => Task.FromResult<IAsyncDisposable>(lease);
        if (failedRevalidation) f.Session.RevalidationError = "process changed";
        else f.OnOpen = () => throw new IOException("open failed");
        if (failedRevalidation) await Assert.ThrowsAsync<InvalidDataException>(() => f.Run(output));
        else await Assert.ThrowsAsync<IOException>(() => f.Run(output));
        Assert.True(lease.Disposed); Assert.Equal(failedRevalidation, f.Session.Disposed);
        Assert.False(File.Exists(f.Path)); Assert.Equal("", output.ToString());
    }

    sealed class TestLease : IAsyncDisposable
    {
        public bool Disposed { get; private set; }
        public Action? OnDispose { get; set; }
        public ValueTask DisposeAsync() { Disposed = true; OnDispose?.Invoke(); return ValueTask.CompletedTask; }
    }

    static Task<IAsyncDisposable> AcquireTestLease(int pid, long ticks, string sha, TimeSpan timeout, CancellationToken token)
    {
        Assert.Equal(123, pid); Assert.Equal(456, ticks);
        Assert.Equal(CurrentBuildPlayerLookup.GameSha256, sha);
        Assert.Equal(TimeSpan.FromSeconds(5), timeout);
        token.ThrowIfCancellationRequested();
        return Task.FromResult<IAsyncDisposable>(new TestLease());
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string directory = System.IO.Path.Combine(System.IO.Path.GetTempPath(),
            "rr2-location-command-test-" + Guid.NewGuid().ToString("N"));
        public string Path => System.IO.Path.Combine(directory, "candidate.json");
        public Fake Session { get; } = new();
        public bool Opened { get; private set; }
        public bool Captured { get; private set; }
        public string? Change { get; set; }
        public Func<int, long, string, TimeSpan, CancellationToken, Task<IAsyncDisposable>>? LeaseAcquire { get; set; }
        public Action? OnOpen { get; set; }
        public Action? OnRead { get; set; }
        public Dictionary<string, string> Options { get; }
        public Fixture()
        {
            Directory.CreateDirectory(directory);
            Options = new() { ["--pid"] = "123", ["--start-ticks"] = "456", ["--output"] = Path };
        }
        public Task<int> Run(TextWriter output, CancellationToken ct = default) =>
            CurrentBuildLocationContextSampleCommand.RunAsync(Options, output, ct,
                (pid, ticks, _) =>
                {
                    Assert.Equal(123, pid); Assert.Equal(456, ticks);
                    Opened = true; OnOpen?.Invoke(); return Task.FromResult<IReadOnlyNativeMemorySession>(Session);
                },
                (session, _) =>
                {
                    Captured = true; OnRead?.Invoke(); var now = DateTimeOffset.UtcNow;
                    var zone = new ZoneSeedObservation(session.Identity, now, now,
                        ulong.MaxValue, 0x20000000, 0x20010000, 0x20020000, 1234, "null-provider");
                    var result = new CurrentBuildLocationContextObservation(session.Identity, now, now,
                        "18446744073709551615", "uFFFFFFFFFFFFFFFF", now, now, new(1.5f, -2f, 3f), zone);
                    result = Change switch
                    {
                        "observation-epoch" => result with { Identity = session.Identity with { ProcessStartUtcTicks = 999 } },
                        "zone-epoch" => result with { Zone = zone with { Identity = session.Identity with { ProcessStartUtcTicks = 999 } } },
                        "zone-key" => result with { Zone = zone with { SelfKey = 123 } },
                        "zero-key" => result with { UnitKey = "0", UnitIdCandidate = "u0000000000000000" },
                        "formatted-id" => result with { UnitIdCandidate = "u000000000000007B" },
                        _ => result
                    };
                    return Task.FromResult(result);
                }, LeaseAcquire ?? AcquireTestLease);
        public void Dispose() => Directory.Delete(directory, true);
    }

    private sealed class Fake : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; set; } = new(123, 456, "rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 64 * 1024 * 1024);
        public bool Revalidated { get; private set; }
        public bool Disposed { get; private set; }
        public string? RevalidationError { get; set; }
        public Action? OnRevalidate { get; set; }
        public NativeReadResult Read(ulong address, int length) => throw new InvalidOperationException("No live read in command test.");
        public ValueTask<string?> RevalidateAsync(CancellationToken ct)
        {
            Revalidated = true; OnRevalidate?.Invoke(); ct.ThrowIfCancellationRequested();
            return ValueTask.FromResult(RevalidationError);
        }
        public Func<ValueTask>? OnDisposeAsync { get; set; }
        public async ValueTask DisposeAsync() { if (OnDisposeAsync is not null) await OnDisposeAsync(); Disposed = true; }
    }
}
