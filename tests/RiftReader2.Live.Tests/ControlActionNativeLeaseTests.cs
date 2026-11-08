using System.Diagnostics;
using System.Reflection;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

/// <summary>Real lease/body boundary with synthetic input only; never Windows input or a game/VM.</summary>
public sealed class ControlActionNativeLeaseTests
{
    [Fact]
    public async Task LeaseContentionPreventsPendingPreparationAndInput()
    {
        using var f = new Fixture();
        f.Acquire = (_, _) => throw new TimeoutException("read held");
        var called = false;
        await Assert.ThrowsAsync<TimeoutException>(() => f.Run(() => { called = true; return Task.FromResult(1); }));
        Assert.False(called);
        Assert.False(File.Exists(f.Pending));
        Assert.Empty(f.Events);
    }

    [Fact]
    public async Task ActualExecutorReleaseAndJournalCleanupPrecedeLeaseDisposal()
    {
        using var f = new Fixture();
        var result = await f.Run(async () =>
        {
            File.WriteAllText(f.Pending, "synthetic intent");
            f.Events.Add("pending");
            f.Events.Add("prepare");
            var input = new SyntheticInput(f);
            var result = await ExecuteSynthetic(input, new(["w"], 20));
            Assert.True(f.Held);
            if (result.ReleaseSucceeded) { File.Delete(f.Pending); f.Events.Add("journal-clean"); }
            return result;
        });
        Assert.True(result.ReleaseSucceeded);
        Assert.True(result.DeliverySucceeded);
        Assert.False(f.Held);
        Assert.Equal(1, f.Acquires);
        Assert.Equal(new[] { "lease", "pending", "prepare", "down", "up", "journal-clean", "dispose" }, f.Events);
    }

    [Theory]
    [InlineData("CancelActiveAction")]
    [InlineData("StopSession")]
    [InlineData("BeginRecovery")]
    public async Task ExistingStopReleaseAndRecoveryCancelLeaseWaitWithoutAcquiringAnother(string method)
    {
        using var f = new Fixture();
        using var cancel = new CancellationTokenSource();
        f.Set("actionCancellation", cancel);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        f.Acquire = async (_, token) =>
        {
            entered.SetResult();
            await Task.Delay(Timeout.InfiniteTimeSpan, token);
            throw new InvalidOperationException("unreachable");
        };
        var called = false;
        var pending = f.Run(() => { called = true; return Task.FromResult(1); }, cancel.Token);
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(3));
        f.Invoke(method); // Only existing cancellation/state methods, never RecoverAsync/Windows key-up.
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => pending);
        Assert.False(called);
        Assert.False(File.Exists(f.Pending));
        Assert.Equal(1, f.Acquires);
    }

    [Theory]
    [InlineData("token")]
    [InlineData("expired")]
    [InlineData("reviewed-target")]
    [InlineData("inspected-target")]
    public async Task PostWaitAdmissionRejectsChangedArmTimeTokenOrTarget(string change)
    {
        using var f = new Fixture();
        var originalArmedAt = f.Get<long>("armedAt");
        f.Acquire = async (_, _) =>
        {
            await Task.Yield();
            f.Held = true; f.Events.Add("lease");
            switch (change)
            {
                case "token": f.Set("armToken", "different"); break;
                case "expired": f.Set("armedAt", Stopwatch.GetTimestamp() - 16 * Stopwatch.Frequency); break;
                case "reviewed-target": f.Set("reviewedTarget", f.Target with { ProcessId = 124 }); break;
                case "inspected-target": f.Inspected = f.Target with { WindowHandle = "0x999" }; break;
            }
            return f.Lease();
        };
        var called = false;
        await Assert.ThrowsAsync<InvalidOperationException>(() => f.Run(() => { called = true; return Task.FromResult(1); }));
        Assert.False(called);
        Assert.False(f.Held);
        Assert.False(File.Exists(f.Pending));
        if (change != "expired") Assert.Equal(originalArmedAt, f.Get<long>("armedAt"));
    }

    [Fact]
    public async Task IdentityUsesExactReviewedEpochAndCanonicalUppercaseBuild()
    {
        using var f = new Fixture();
        f.Acquire = (identity, _) =>
        {
            Assert.Equal(f.Target.MachineName, identity.MachineName);
            Assert.Equal(f.Target.ProcessId, identity.ProcessId);
            Assert.Equal(f.Target.ProcessStartUtcTicks, identity.ProcessStartUtcTicks);
            Assert.Equal(f.Target.ExecutableSha256.ToUpperInvariant(), identity.ExecutableSha256);
            f.Held = true;
            return Task.FromResult(f.Lease());
        };
        Assert.Equal(7, await f.Run(() => Task.FromResult(7)));
        Assert.False(f.Held);
    }

    [Fact]
    public async Task CancelledExecutorReleasesBeforeLeaseEvenWithCancelledToken()
    {
        using var f = new Fixture();
        using var cancel = new CancellationTokenSource();
        var result = await f.Run(async () =>
        {
            File.WriteAllText(f.Pending, "synthetic intent");
            var input = new SyntheticInput(f) { AfterDown = cancel.Cancel };
            var result = await ExecuteSynthetic(input, new(["w"], 20), cancel.Token);
            Assert.True(result.ReleaseSucceeded);
            Assert.True(f.Held);
            File.Delete(f.Pending); f.Events.Add("journal-clean");
            return result;
        }, cancel.Token);
        Assert.True(result.Cancelled);
        Assert.Equal(new[] { "lease", "down", "up", "journal-clean", "dispose" }, f.Events);
    }

    [Fact]
    public async Task FailedReleaseKeepsPendingAndDoesNotClaimGloballyCleanInput()
    {
        using var f = new Fixture();
        var result = await f.Run(async () =>
        {
            File.WriteAllText(f.Pending, "synthetic uncertain release");
            var result = await ExecuteSynthetic(new SyntheticInput(f) { FailRelease = true }, new(["w"], 20));
            Assert.True(f.Held);
            if (result.ReleaseSucceeded) File.Delete(f.Pending);
            return result;
        });
        Assert.False(result.ReleaseSucceeded);
        Assert.True(result.StateUncertain);
        Assert.True(File.Exists(f.Pending));
        Assert.False(f.Held); // Action-scoped only: external clean/recovery fence remains required.
    }

    [Fact]
    public async Task BodyFailureDisposesLeaseWithoutErasingPendingEvidence()
    {
        using var f = new Fixture();
        await Assert.ThrowsAsync<InvalidDataException>(() => f.Run<int>(() =>
        {
            File.WriteAllText(f.Pending, "retain");
            throw new InvalidDataException("synthetic body failure");
        }));
        Assert.False(f.Held);
        Assert.Equal("retain", File.ReadAllText(f.Pending));
    }

    [Fact]
    public async Task RealFileLeaseExcludesStandaloneReadOnlyWhileActionBodyActive()
    {
        using var f = new Fixture();
        var directory = Path.Combine(f.Directory, "leases");
        f.Acquire = async (id, token) => await NativeReadFileLease.AcquireAsync(
            id.ProcessId, id.ProcessStartUtcTicks, id.ExecutableSha256, TimeSpan.Zero, token, directory);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var finish = new TaskCompletionSource<int>(TaskCreationOptions.RunContinuationsAsynchronously);
        var action = f.Run(async () => { entered.SetResult(); return await finish.Task; });
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(3));
        try
        {
            await Assert.ThrowsAsync<TimeoutException>(() => NativeReadFileLease.AcquireAsync(
                f.Target.ProcessId, f.Target.ProcessStartUtcTicks, f.Target.ExecutableSha256.ToUpperInvariant(),
                TimeSpan.Zero, default, directory));
        }
        finally { finish.TrySetResult(9); }
        Assert.Equal(9, await action);
        await using var read = await NativeReadFileLease.AcquireAsync(
            f.Target.ProcessId, f.Target.ProcessStartUtcTicks, f.Target.ExecutableSha256.ToUpperInvariant(),
            TimeSpan.Zero, default, directory);
    }

    static Task<ControlExecutionResult> ExecuteSynthetic(IControlInput input, ControlAction action,
        CancellationToken token = default)
    {
        var clock = new SyntheticClock();
        return new BoundedControlExecutor(input, clock, (duration, ct) =>
        {
            ct.ThrowIfCancellationRequested();
            clock.Advance(duration);
            return Task.CompletedTask;
        }).ExecuteAsync(action, token);
    }

    sealed class SyntheticClock : TimeProvider
    {
        long now;
        public override long TimestampFrequency => TimeSpan.TicksPerSecond;
        public override long GetTimestamp() => now;
        public void Advance(TimeSpan duration) => now += duration.Ticks;
    }

    sealed class SyntheticInput(Fixture f) : IControlInput
    {
        public Action? AfterDown { get; init; }
        public bool FailRelease { get; init; }
        public bool IsTargetCurrent() { Assert.True(f.Held); return true; }
        public void KeyDown(string key) { Assert.True(f.Held); f.Events.Add("down"); AfterDown?.Invoke(); }
        public void KeyUp(string key) { Assert.True(f.Held); f.Events.Add("up"); if (FailRelease) throw new IOException("synthetic release"); }
        public void ButtonDown(string button) => throw new InvalidOperationException("unexpected button");
        public void ButtonUp(string button) => throw new InvalidOperationException("unexpected button");
        public void MoveRelative(int x, int y) => throw new InvalidOperationException("unexpected pointer");
        public void Wheel(int count) => throw new InvalidOperationException("unexpected wheel");
    }

    sealed class Fixture : IDisposable
    {
        public string Directory { get; } = Path.Combine(Path.GetTempPath(), "rr2-action-read-lease-test-" + Guid.NewGuid().ToString("N"));
        public string Pending => Path.Combine(Directory, "pending.json");
        public DesktopTarget Target { get; } = new(Environment.MachineName, 123, 456, "0x789",
            @"C:\RIFT\rift_x64.exe", CurrentBuildPlayerLookup.GameSha256.ToLowerInvariant(), true, 0, 0, 800, 600);
        public DesktopTarget Inspected { get; set; }
        public ControlAgent Agent { get; }
        public bool Held { get; set; }
        public int Acquires { get; private set; }
        public List<string> Events { get; } = [];
        public Func<ControlIdentityRequest, CancellationToken, Task<IAsyncDisposable>> Acquire { get; set; }
        public Fixture()
        {
            Inspected = Target;
            Acquire = (_, _) => { Held = true; Events.Add("lease"); return Task.FromResult(Lease()); };
            var config = new ControlAgentConfiguration(1, "192.168.1.1", 12345, new string('T', 32),
                Environment.MachineName, "rift_x64", Target.ExecutablePath, Target.ExecutableSha256, Directory);
            Agent = new(config, (_, _, _) => throw new InvalidOperationException("unexpected vitals"),
                (_, _, _) => throw new InvalidOperationException("unexpected XYZ"),
                (id, token) => { Acquires++; return Acquire(id, token); });
            Set("armToken", "arm");
            Set("armedAt", Stopwatch.GetTimestamp());
            Set("reviewedTarget", Target);
        }
        public Task<T> Run<T>(Func<Task<T>> body, CancellationToken token = default) =>
            Agent.ExecuteActionUnderNativeLeaseAsync(Target, "arm", body, token, () => Inspected);
        public IAsyncDisposable Lease() => new CallbackLease(() => { Assert.True(Held); Held = false; Events.Add("dispose"); });
        public void Set(string name, object value) => typeof(ControlAgent).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(Agent, value);
        public T Get<T>(string name) => (T)typeof(ControlAgent).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(Agent)!;
        public void Invoke(string name) => typeof(ControlAgent).GetMethod(name, BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(Agent, null);
        public void Dispose() => System.IO.Directory.Delete(Directory, true);
    }

    sealed class CallbackLease(Action dispose) : IAsyncDisposable
    {
        public ValueTask DisposeAsync() { dispose(); return ValueTask.CompletedTask; }
    }
}
