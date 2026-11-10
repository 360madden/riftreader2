using System.Collections.Concurrent;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Tests.Control;

public sealed class BoundedControlDeadlineTests
{
    [Fact]
    public async Task DeadlineReleasesOnDedicatedThreadWhileTargetInspectionIsBlocked()
    {
        using var input = new BlockingInput();
        var clock = new ManualClock();
        var execution = RunDedicated(() => new BoundedControlExecutor(input, clock)
            .ExecuteAsync(new(["s"], 150)));
        try
        {
            Assert.True(input.ProbeEntered.Wait(TimeSpan.FromSeconds(5)));
            clock.Advance(150);
            Assert.True(input.Released.Wait(TimeSpan.FromSeconds(5)));
            Assert.False(execution.IsCompleted);
            Assert.False(input.ReleaseWasThreadPool);
            Assert.Equal(["down:s", "up:s"], input.Events.ToArray());
        }
        finally { input.ResumeProbe.Set(); }
        var result = await execution.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.True(result.DeliverySucceeded);
        Assert.True(result.ReleaseSucceeded);
        Assert.Equal(["down:s", "up:s"], input.Events.ToArray());
    }

    [Theory]
    [InlineData("chord")]
    [InlineData("button")]
    [InlineData("move")]
    public async Task ExpiryDuringInspectionPreventsEveryLaterInputKind(string kind)
    {
        using var input = new BlockingInput();
        var clock = new ManualClock();
        var action = kind switch
        {
            "chord" => new ControlAction(["w", "a"], 150),
            "button" => new ControlAction(["w"], 150, "right"),
            _ => new ControlAction([], 150, "right", DeltaX: 10)
        };
        var execution = RunDedicated(() => new BoundedControlExecutor(input, clock).ExecuteAsync(action));
        try
        {
            Assert.True(input.ProbeEntered.Wait(TimeSpan.FromSeconds(5)));
            clock.Advance(150);
            Assert.True(input.Released.Wait(TimeSpan.FromSeconds(5)));
        }
        finally { input.ResumeProbe.Set(); }
        var result = await execution.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.False(result.DeliverySucceeded);
        Assert.True(result.ReleaseSucceeded);
        Assert.Contains("bounded hold elapsed", result.Error, StringComparison.Ordinal);
        var expected = kind switch
        {
            "chord" => new[] { "down:w", "up:a", "up:w" },
            "button" => ["down:w", "button-up:right", "up:w"],
            _ => ["button-down:right", "button-up:right"]
        };
        Assert.Equal(expected, input.Events.ToArray());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task CancellationWakesReleaseWorkerWithoutWaitingForBlockedProbeOrDeadline(bool expireBeforeProbeReturns)
    {
        using var input = new BlockingInput();
        using var cancellation = new CancellationTokenSource();
        var clock = new ManualClock(); // deliberately never advances
        var execution = RunDedicated(() => new BoundedControlExecutor(input, clock)
            .ExecuteAsync(new(["w"], 250), cancellation.Token));
        try
        {
            Assert.True(input.ProbeEntered.Wait(TimeSpan.FromSeconds(5)));
            cancellation.Cancel();
            Assert.True(input.Released.Wait(TimeSpan.FromSeconds(5)));
            if (expireBeforeProbeReturns)
                clock.Advance(250);
            Assert.False(execution.IsCompleted);
        }
        finally { input.ResumeProbe.Set(); }
        var result = await execution.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.True(result.Cancelled);
        Assert.True(result.ReleaseSucceeded);
        Assert.Equal(["down:w", "up:w"], input.Events.ToArray());
    }

    [Fact]
    public async Task WatchdogReleaseFailuresAreRetainedAndEveryIntendedUpIsAttemptedOnce()
    {
        using var input = new BlockingInput { FailRelease = true };
        var clock = new ManualClock();
        var execution = RunDedicated(() => new BoundedControlExecutor(input, clock)
            .ExecuteAsync(new(["w", "a"], 150, "right")));
        try
        {
            Assert.True(input.ProbeEntered.Wait(TimeSpan.FromSeconds(5)));
            clock.Advance(150);
            Assert.True(input.Released.Wait(TimeSpan.FromSeconds(5)));
        }
        finally { input.ResumeProbe.Set(); }
        var result = await execution.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.False(result.ReleaseSucceeded);
        Assert.True(result.StateUncertain);
        Assert.True(result.RequiresCallerDisarm);
        Assert.Contains("mouse button 'right'", result.Error, StringComparison.Ordinal);
        Assert.Contains("key 'a'", result.Error, StringComparison.Ordinal);
        Assert.Contains("key 'w'", result.Error, StringComparison.Ordinal);
        Assert.Equal(["down:w", "button-up:right", "up:a", "up:w"], input.Events.ToArray());
    }

    [Fact]
    public async Task DeadlineReleaseDoesNotRequireDelayedContinuationToResume()
    {
        using var input = new BlockingInput { BlockProbe = false };
        var clock = new ManualClock();
        var delayEntered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var resumeDelay = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var executor = new BoundedControlExecutor(input, clock, (_, _) =>
        {
            delayEntered.TrySetResult();
            return resumeDelay.Task;
        });
        var execution = executor.ExecuteAsync(new(["s"], 150));
        await delayEntered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        try
        {
            clock.Advance(150);
            Assert.True(input.Released.Wait(TimeSpan.FromSeconds(5)));
            Assert.False(execution.IsCompleted);
            Assert.False(input.ReleaseWasThreadPool);
        }
        finally { resumeDelay.TrySetResult(); }
        var result = await execution.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.True(result.ReleaseSucceeded);
        Assert.Equal(["down:s", "up:s"], input.Events.ToArray());
    }

    [Fact]
    public async Task HoldStartsAtSuccessfulInsertionAfterFiftyMillisecondsOfNativePreparation()
    {
        using var input = new BlockingInput { BlockProbe = false };
        var clock = new ManualClock();
        long downAt = -1;
        long upAt = -1;
        input.BeforeDown = () => clock.Advance(50);
        input.OnDown = () => downAt = clock.GetTimestamp();
        input.OnUp = () => upAt = clock.GetTimestamp();
        var executor = new BoundedControlExecutor(input, clock, (delay, _) =>
        {
            clock.Advance((int)Math.Ceiling(delay.TotalMilliseconds));
            return Task.CompletedTask;
        });

        var result = await executor.ExecuteAsync(new(["a"], 100));

        Assert.True(result.DeliverySucceeded);
        Assert.True(result.ReleaseSucceeded);
        Assert.Equal(["down:a", "up:a"], input.Events.ToArray());
        Assert.InRange(upAt - downAt, TimeSpan.FromMilliseconds(100).Ticks,
            TimeSpan.FromMilliseconds(110).Ticks);
    }

    [Fact]
    public async Task SingleKeySlowInsertionUsesBoundedSlackInsteadOfRejectingValidTurn()
    {
        using var input = new BlockingInput { BlockProbe = false };
        var clock = new ManualClock();
        long downAt = -1, upAt = -1;
        input.BeforeDown = () => clock.Advance(120); // Native delivery consumed >100 ms.
        input.OnDown = () => downAt = clock.GetTimestamp();
        input.OnUp = () => upAt = clock.GetTimestamp();
        var executor = new BoundedControlExecutor(input, clock, (delay, _) =>
        {
            clock.Advance((int)Math.Ceiling(delay.TotalMilliseconds));
            return Task.CompletedTask;
        });

        var result = await executor.ExecuteAsync(new(["a"], 100));

        Assert.True(result.DeliverySucceeded);
        Assert.True(result.ReleaseSucceeded);
        Assert.Equal(["down:a", "up:a"], input.Events.ToArray());
        // The insertion clock targets 100 ms; the independent 200 ms absolute
        // watchdog may cap it to 80 ms after a 120 ms slow native delivery.
        Assert.InRange(upAt - downAt, TimeSpan.FromMilliseconds(75).Ticks,
            TimeSpan.FromMilliseconds(110).Ticks);
    }

    [Fact]
    public async Task SingleKeyInsertionBeyondAbsoluteSlackFailsAndReleases()
    {
        using var input = new BlockingInput { BlockProbe = false };
        var clock = new ManualClock();
        input.OnDown = () => clock.Advance(210);
        var result = await new BoundedControlExecutor(input, clock)
            .ExecuteAsync(new(["a"], 100));
        Assert.False(result.DeliverySucceeded);
        Assert.True(result.ReleaseSucceeded);
        Assert.Equal(["down:a", "up:a"], input.Events.ToArray());
    }

    [Fact]
    public async Task HoldBudgetStartsBeforeTheFirstInsertionReturns()
    {
        using var input = new BlockingInput { BlockProbe = false };
        var clock = new ManualClock();
        input.OnDown = () => clock.Advance(150);
        var result = await new BoundedControlExecutor(input, clock)
            .ExecuteAsync(new(["w", "a"], 150));
        Assert.False(result.DeliverySucceeded);
        Assert.True(result.ReleaseSucceeded);
        Assert.Equal(["down:w", "up:a", "up:w"], input.Events.ToArray());
    }

    [Fact]
    public async Task DeadlineIsRecheckedInsideInjectionGateAfterOuterBudgetCheck()
    {
        using var input = new BlockingInput { BlockProbe = false };
        var clock = new ManualClock();
        var prepared = false;
        input.OnProbeAfterDown = () =>
        {
            if (!prepared)
            {
                prepared = true;
                // The outer check reads time 0, but the gate must observe time 150.
                clock.AdvanceAfterNextReadOnThisThread(150);
            }
        };
        var result = await new BoundedControlExecutor(input, clock)
            .ExecuteAsync(new(["w", "a"], 150));
        Assert.True(prepared);
        Assert.False(result.DeliverySucceeded);
        Assert.True(result.ReleaseSucceeded);
        Assert.Equal(["down:w", "up:a", "up:w"], input.Events.ToArray());
    }

    private static Task<ControlExecutionResult> RunDedicated(Func<Task<ControlExecutionResult>> execute)
    {
        var completion = new TaskCompletionSource<ControlExecutionResult>(
            TaskCreationOptions.RunContinuationsAsynchronously);
        new Thread(() =>
        {
            try { completion.SetResult(execute().GetAwaiter().GetResult()); }
            catch (Exception exception) { completion.SetException(exception); }
        }) { IsBackground = true }.Start();
        return completion.Task;
    }

    private sealed class ManualClock : TimeProvider
    {
        private long ticks;
        public override long TimestampFrequency => TimeSpan.TicksPerSecond;
        private int deferredThread;
        private long deferredAdvance;
        public override long GetTimestamp()
        {
            var value = Interlocked.Read(ref ticks);
            if (Environment.CurrentManagedThreadId == Volatile.Read(ref deferredThread))
                Interlocked.Add(ref ticks, Interlocked.Exchange(ref deferredAdvance, 0));
            return value;
        }
        public void AdvanceAfterNextReadOnThisThread(int milliseconds)
        {
            deferredAdvance = TimeSpan.FromMilliseconds(milliseconds).Ticks;
            Volatile.Write(ref deferredThread, Environment.CurrentManagedThreadId);
        }
        public void Advance(int milliseconds) => Interlocked.Add(ref ticks,
            TimeSpan.FromMilliseconds(milliseconds).Ticks);
    }

    private sealed class BlockingInput : IControlInput, IDisposable
    {
        public ConcurrentQueue<string> Events { get; } = new();
        public ManualResetEventSlim ProbeEntered { get; } = new();
        public ManualResetEventSlim ResumeProbe { get; } = new();
        public ManualResetEventSlim Released { get; } = new();
        public bool BlockProbe { get; init; } = true;
        public bool FailRelease { get; init; }
        public Action? BeforeDown { get; set; }
        public Action? OnDown { get; set; }
        public Action? OnUp { get; set; }
        public Action? OnProbeAfterDown { get; set; }
        public bool ReleaseWasThreadPool { get; private set; }
        private int pressed;
        private int probeBlocked;

        public bool IsTargetCurrent()
        {
            if (Volatile.Read(ref pressed) != 0)
                OnProbeAfterDown?.Invoke();
            if (BlockProbe && Volatile.Read(ref pressed) != 0
                && Interlocked.Exchange(ref probeBlocked, 1) == 0)
            {
                ProbeEntered.Set();
                if (!ResumeProbe.Wait(TimeSpan.FromSeconds(10)))
                    throw new TimeoutException("Test probe was not resumed.");
            }
            return true;
        }
        public void KeyDown(string key) => Down("down:" + key);
        public void ButtonDown(string button) => Down("button-down:" + button);
        private void Down(string operation)
        {
            BeforeDown?.Invoke();
            Events.Enqueue(operation);
            Volatile.Write(ref pressed, 1);
            OnDown?.Invoke();
        }
        public void KeyUp(string key) => Up("up:" + key);
        public void ButtonUp(string button) => Up("button-up:" + button);
        private void Up(string operation)
        {
            Events.Enqueue(operation);
            OnUp?.Invoke();
            ReleaseWasThreadPool = Thread.CurrentThread.IsThreadPoolThread;
            Released.Set();
            if (FailRelease)
                throw new InvalidOperationException("Synthetic release failure.");
        }
        public void MoveRelative(int x, int y) => Events.Enqueue("move");
        public void Wheel(int notches) => Events.Enqueue("wheel");
        public void Dispose()
        {
            ProbeEntered.Dispose();
            ResumeProbe.Dispose();
            Released.Dispose();
        }
    }
}
