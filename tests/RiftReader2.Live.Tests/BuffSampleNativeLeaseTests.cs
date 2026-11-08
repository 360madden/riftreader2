using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class BuffSampleNativeLeaseTests
{
    public static IEnumerable<object[]> Commands => new[] { "seed", "visibility", "details" }.Select(x => new object[] { x });
    public static IEnumerable<object[]> Failures =>
        from command in new[] { "seed", "visibility", "details" }
        from phase in new[] { "open", "read", "revalidate", "observation", "changed-identity", "wrong-pid", "wrong-ticks", "wrong-build" }
        select new object[] { command, phase };

    [Theory, MemberData(nameof(Commands))]
    public async Task LeaseBracketsSessionAndPreservesCandidateContract(string command)
    {
        using var f = new Fixture(command);
        Assert.Equal(0, await f.Run());
        Assert.Equal(new[] { "lease", "open", "read", "revalidate", "session-dispose-start", "session-dispose", "lease-dispose" }, f.Events);
        Assert.False(f.Held);
        using var report = JsonDocument.Parse(await File.ReadAllTextAsync(f.OutputPath));
        Assert.Equal("complete", report.RootElement.GetProperty("status").GetString());
        var suffix = command == "seed" ? "seeds" : command;
        Assert.Equal($"native-current-buff-{suffix}-candidate/1", report.RootElement.GetProperty("contractVersion").GetString());
        Assert.Contains("unverified", report.RootElement.GetProperty("observation").GetProperty("qualification").GetString()!);
    }

    [Theory, MemberData(nameof(Commands))]
    public async Task RefusedLeaseNeverOpensSession(string command)
    {
        using var f = new Fixture(command) { AcquireError = new TimeoutException("busy") };
        await Assert.ThrowsAsync<TimeoutException>(() => f.Run());
        Assert.Equal(new[] { "lease" }, f.Events);
        Assert.False(File.Exists(f.OutputPath));
    }

    [Theory, MemberData(nameof(Commands))]
    public async Task CancelledWaitNeverOpensSession(string command)
    {
        using var f = new Fixture(command);
        using var cts = new CancellationTokenSource();
        var waiting = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        f.AcquireOverride = async token =>
        {
            waiting.SetResult();
            await Task.Delay(Timeout.Infinite, token);
            throw new Exception("unreachable");
        };
        var run = f.Run(cts.Token);
        await waiting.Task.WaitAsync(TimeSpan.FromSeconds(3));
        cts.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => run);
        Assert.Equal(new[] { "lease" }, f.Events);
        Assert.False(File.Exists(f.OutputPath));
    }

    [Theory, MemberData(nameof(Commands))]
    public async Task PrecancelledOrInvalidOptionsNeverAcquire(string command)
    {
        using var f = new Fixture(command);
        using var cts = new CancellationTokenSource();
        cts.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => f.Run(cts.Token));
        f.Options["--pid"] = "0";
        await Assert.ThrowsAsync<ArgumentException>(() => f.Run());
        Assert.Empty(f.Events);
    }

    [Theory, MemberData(nameof(Failures))]
    public async Task FailureReleasesLeaseAndPublishesNothing(string command, string phase)
    {
        using var f = new Fixture(command) { Failure = phase };
        await Assert.ThrowsAsync<InvalidDataException>(() => f.Run());
        Assert.False(f.Held);
        Assert.Equal("lease-dispose", f.Events[^1]);
        if (phase != "open") Assert.Contains("session-dispose", f.Events);
        if (phase.StartsWith("wrong-")) Assert.DoesNotContain("read", f.Events);
        Assert.False(File.Exists(f.OutputPath));
    }

    [Theory, MemberData(nameof(Commands))]
    public async Task ActualFileLeaseRemainsHeldUntilAsyncSessionDisposalCompletes(string command)
    {
        using var f = new Fixture(command) { RealLease = true };
        f.DisposalGate = new(TaskCreationOptions.RunContinuationsAsynchronously);
        var run = f.Run();
        try
        {
            await f.Disposing.Task.WaitAsync(TimeSpan.FromSeconds(3));
            Assert.True(f.Held);
            await Assert.ThrowsAsync<TimeoutException>(() => NativeReadFileLease.AcquireAsync(
                123, 456, CurrentBuildPlayerLookup.GameSha256, TimeSpan.Zero, default, f.LeaseDirectory));
        }
        finally
        {
            f.DisposalGate.TrySetResult();
            await run;
        }
        await using var acquired = await NativeReadFileLease.AcquireAsync(
            123, 456, CurrentBuildPlayerLookup.GameSha256, TimeSpan.Zero, default, f.LeaseDirectory);
        Assert.False(f.Held);
    }

    [Fact]
    public async Task SeedTimingOptionStillPropagatesAndInvalidValueNeverAcquires()
    {
        using var f = new Fixture("seed");
        f.Options["--include-timing"] = "true";
        Assert.Equal(0, await f.Run());
        Assert.True(f.ObservedTiming);
        using var invalid = new Fixture("seed");
        invalid.Options["--include-timing"] = "false";
        await Assert.ThrowsAsync<ArgumentException>(() => invalid.Run());
        Assert.Empty(invalid.Events);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string root = Path.Combine(Path.GetTempPath(), "rr2-buff-lease-" + Guid.NewGuid().ToString("N"));
        private readonly string command;
        public string OutputPath => Path.Combine(root, "report.json");
        public string LeaseDirectory => Path.Combine(root, "leases");
        public Dictionary<string, string> Options { get; }
        public List<string> Events { get; } = [];
        public bool Held;
        public bool ObservedTiming;
        public bool RealLease { get; init; }
        public string? Failure { get; init; }
        public Exception? AcquireError { get; init; }
        public Func<CancellationToken, Task<IAsyncDisposable>>? AcquireOverride;
        public TaskCompletionSource? DisposalGate;
        public TaskCompletionSource Disposing { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public Fixture(string command)
        {
            this.command = command;
            Directory.CreateDirectory(root);
            Options = new() { ["--pid"] = "123", ["--start-ticks"] = "456", ["--output"] = OutputPath };
        }
        private async Task<IAsyncDisposable> Acquire(int pid, long ticks, string sha, CancellationToken ct)
        {
            Assert.Equal(123, pid); Assert.Equal(456, ticks);
            Assert.Equal(CurrentBuildPlayerLookup.GameSha256, sha);
            Events.Add("lease");
            if (AcquireError is not null) throw AcquireError;
            if (AcquireOverride is not null) return await AcquireOverride(ct);
            IAsyncDisposable? actual = RealLease
                ? await NativeReadFileLease.AcquireAsync(pid, ticks, sha, TimeSpan.Zero, ct, LeaseDirectory) : null;
            Held = true;
            return new Lease(this, actual);
        }
        private Task<IReadOnlyNativeMemorySession> Open(int pid, long ticks, CancellationToken ct)
        {
            Assert.True(Held); Assert.Equal(123, pid); Assert.Equal(456, ticks);
            ct.ThrowIfCancellationRequested(); Events.Add("open");
            if (Failure == "open") throw new InvalidDataException("open failure");
            return Task.FromResult<IReadOnlyNativeMemorySession>(new Session(this));
        }
        private NativeProcessIdentity ReadIdentity(IReadOnlyNativeMemorySession session)
        {
            Assert.True(Held); Events.Add("read");
            if (Failure == "read") throw new InvalidDataException("read failure");
            return Failure == "observation" ? session.Identity with { ProcessId = 124 } : session.Identity;
        }
        public Task<int> Run(CancellationToken token = default) => command switch
        {
            "seed" => CurrentBuildBuffSeedSampleCommand.RunAsync(Options, TextWriter.Null, token, Open,
                (s, timing) => { ObservedTiming = timing; return new(ReadIdentity(s), DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, 1, 2, 3, []); }, Acquire),
            "visibility" => CurrentBuildBuffVisibilitySampleCommand.RunAsync(Options, TextWriter.Null, token, Open,
                s => new(ReadIdentity(s), DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, 1, "unavailable", null, []), Acquire),
            "details" => CurrentBuildBuffDetailsSampleCommand.RunAsync(Options, TextWriter.Null, token, Open,
                s => new(ReadIdentity(s), DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, 1, 2, 3, []), Acquire),
            _ => throw new ArgumentException("Unknown command")
        };
        public void Dispose() => Directory.Delete(root, true);
        private sealed class Lease(Fixture f, IAsyncDisposable? actual) : IAsyncDisposable
        {
            public async ValueTask DisposeAsync()
            {
                Assert.True(f.Held);
                if (actual is not null) await actual.DisposeAsync();
                f.Events.Add("lease-dispose"); f.Held = false;
            }
        }
        private sealed class Session : IReadOnlyNativeMemorySession
        {
            private readonly Fixture f;
            public NativeProcessIdentity Identity { get; private set; } = new(123, 456, @"C:\RIFT\rift_x64.exe",
                CurrentBuildPlayerLookup.GameSha256, 0x140000000, 0x4000000);
            public Session(Fixture f)
            {
                this.f = f;
                Identity = f.Failure switch
                {
                    "wrong-pid" => Identity with { ProcessId = 124 },
                    "wrong-ticks" => Identity with { ProcessStartUtcTicks = 457 },
                    "wrong-build" => Identity with { ExecutableSha256 = new string('0', 64) },
                    _ => Identity
                };
            }
            public NativeReadResult Read(ulong address, int length) => throw new Exception("No live reads permitted.");
            public ValueTask<string?> RevalidateAsync(CancellationToken token)
            {
                Assert.True(f.Held); token.ThrowIfCancellationRequested(); f.Events.Add("revalidate");
                if (f.Failure == "changed-identity") Identity = Identity with { ProcessId = 124 };
                return ValueTask.FromResult<string?>(f.Failure == "revalidate" ? "invalidated" : null);
            }
            public async ValueTask DisposeAsync()
            {
                Assert.True(f.Held); f.Events.Add("session-dispose-start"); f.Disposing.TrySetResult();
                await Task.Yield();
                if (f.DisposalGate is not null) await f.DisposalGate.Task;
                Assert.True(f.Held); f.Events.Add("session-dispose");
            }
        }
    }
}
