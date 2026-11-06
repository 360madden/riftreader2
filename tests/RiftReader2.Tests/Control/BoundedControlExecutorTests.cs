using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Tests;

public sealed class BoundedControlExecutorTests
{
    [Fact]
    public async Task ExecuteAsync_DeliversChordChecksEveryTenMillisecondsAndReleasesInReverseOrder()
    {
        var input = new RecordingInput();
        var clock = new ManualTimeProvider();
        var delays = new List<TimeSpan>();
        var executor = Executor(input, clock, delay => delays.Add(delay));

        var result = await executor.ExecuteAsync(new(["w", "a"], 25));

        Assert.True(result.DeliverySucceeded);
        Assert.True(result.ReleaseSucceeded);
        Assert.False(result.Cancelled);
        Assert.False(result.TargetLost);
        Assert.False(result.StateUncertain);
        Assert.False(result.RequiresCallerDisarm);
        Assert.False(result.ResponseVerified);
        Assert.Null(result.Error);
        Assert.Equal(TimeSpan.FromMilliseconds(25), result.ObservedDuration);
        Assert.Equal(
            [TimeSpan.FromMilliseconds(10), TimeSpan.FromMilliseconds(10), TimeSpan.FromMilliseconds(5)],
            delays);
        Assert.Equal(["KeyDown:w", "KeyDown:a", "KeyUp:a", "KeyUp:w"], input.ControlOperations);
    }

    [Fact]
    public async Task ExecuteAsync_ValidatesEntireActionBeforeTargetOrInputIo()
    {
        ControlAction[] invalidActions =
        [
            new(null!, 20),
            new(["w", "w"], 20),
            new(["w", "s"], 20),
            new(["a", "d"], 20),
            new(["q", "e"], 20),
            new(["W"], 20),
            new([], 0),
            new(["w"], 19),
            new(["w"], 251),
            new([], 20, "middle"),
            new([], 20, DeltaX: 201),
            new([], 20, DeltaY: -201),
            new([], 0, WheelNotches: 4),
            new(["w"], 20, WheelNotches: 1),
            new([], 20, DeltaX: 1, WheelNotches: 1),
            new([], 20, WheelNotches: 1)
        ];

        foreach (var action in invalidActions)
        {
            var input = new RecordingInput();
            var executor = Executor(input);

            await Assert.ThrowsAsync<InvalidDataException>(() => executor.ExecuteAsync(action));

            Assert.Empty(input.Operations);
        }
    }

    [Theory]
    [InlineData(20)]
    [InlineData(250)]
    public async Task ExecuteAsync_AcceptsInclusiveMovementHoldBounds(int holdMilliseconds)
    {
        var result = await Executor(new RecordingInput())
            .ExecuteAsync(new(["d"], holdMilliseconds));

        Assert.True(result.DeliverySucceeded);
    }

    [Fact]
    public void Validate_IsPublicAndDoesNotRequireAnInputAdapter()
    {
        BoundedControlExecutor.Validate(new(["w", "d"], 20));

        Assert.Throws<InvalidDataException>(() =>
            BoundedControlExecutor.Validate(new(["w", "s"], 20)));
    }

    [Fact]
    public async Task ExecuteAsync_UsesElapsedDeadlineInsteadOfAccumulatingRequestedDelays()
    {
        var input = new RecordingInput();
        var clock = new ManualTimeProvider();
        var delayCount = 0;
        var executor = new BoundedControlExecutor(
            input,
            clock,
            (_, _) =>
            {
                delayCount++;
                clock.Advance(TimeSpan.FromMilliseconds(17));
                return Task.CompletedTask;
            });

        var result = await executor.ExecuteAsync(new(["w"], 100));

        Assert.True(result.DeliverySucceeded);
        Assert.Equal(6, delayCount);
        Assert.Equal(TimeSpan.FromMilliseconds(102), result.ObservedDuration);
    }

    [Fact]
    public async Task ExecuteAsync_CountsCameraSetupAgainstHoldFromFirstSuccessfulPress()
    {
        var input = new RecordingInput();
        var clock = new ManualTimeProvider();
        var delays = new List<TimeSpan>();
        var buttonDownAt = TimeSpan.Zero;
        var buttonUpAt = TimeSpan.Zero;
        input.OperationRecorded = operation =>
        {
            if (operation == "ButtonDown:right")
                buttonDownAt = clock.GetElapsedTime(0);
            else if (operation == "MoveRelative:10,-15")
                clock.Advance(TimeSpan.FromMilliseconds(27));
            else if (operation == "ButtonUp:right")
                buttonUpAt = clock.GetElapsedTime(0);
        };
        var executor = Executor(input, clock, delay => delays.Add(delay));

        var result = await executor.ExecuteAsync(
            new([], 100, "right", DeltaX: 10, DeltaY: -15));

        Assert.True(result.DeliverySucceeded);
        Assert.Equal(TimeSpan.FromMilliseconds(73), delays.Aggregate(TimeSpan.Zero, (sum, delay) => sum + delay));
        Assert.Equal(TimeSpan.FromMilliseconds(100), buttonUpAt - buttonDownAt);
        Assert.Equal(TimeSpan.FromMilliseconds(100), result.ObservedDuration);
    }

    [Fact]
    public async Task ExecuteAsync_ExhaustedHoldBudgetDoesNotPressAnotherChordKey()
    {
        var input = new RecordingInput();
        var clock = new ManualTimeProvider();
        var advanced = false;
        var delayCalled = false;
        input.OperationRecorded = operation =>
        {
            if (operation == "IsTargetCurrent"
                && input.ControlOperations.Contains("KeyDown:w", StringComparer.Ordinal)
                && !advanced)
            {
                advanced = true;
                clock.Advance(TimeSpan.FromMilliseconds(20));
            }
        };
        var executor = new BoundedControlExecutor(
            input,
            clock,
            (_, _) =>
            {
                delayCalled = true;
                return Task.CompletedTask;
            });

        var result = await executor.ExecuteAsync(new(["w", "a"], 20));

        Assert.False(result.DeliverySucceeded);
        Assert.True(result.ReleaseSucceeded);
        Assert.Contains("bounded hold elapsed", result.Error, StringComparison.Ordinal);
        Assert.False(delayCalled);
        Assert.Equal(["KeyDown:w", "KeyUp:a", "KeyUp:w"], input.ControlOperations);
        Assert.Equal(TimeSpan.FromMilliseconds(20), result.ObservedDuration);
    }

    [Fact]
    public async Task ExecuteAsync_CancellationAfterFirstPressPreventsRemainingChordPresses()
    {
        using var cancellation = new CancellationTokenSource();
        var input = new RecordingInput();
        input.OperationRecorded = operation =>
        {
            if (operation == "KeyDown:w")
                cancellation.Cancel();
        };

        var result = await Executor(input)
            .ExecuteAsync(new(["w", "a"], 20), cancellation.Token);

        Assert.True(result.Cancelled);
        Assert.False(result.DeliverySucceeded);
        Assert.True(result.ReleaseSucceeded);
        Assert.Equal(["KeyDown:w", "KeyUp:a", "KeyUp:w"], input.ControlOperations);
    }

    [Fact]
    public async Task ExecuteAsync_RechecksTargetAfterTheFinalDelayBeforeReportingDelivery()
    {
        var input = new RecordingInput();
        for (var index = 0; index < 5; index++)
            input.TargetResponses.Enqueue(true);
        input.TargetResponses.Enqueue(false);

        var result = await Executor(input).ExecuteAsync(new(["w"], 20));

        Assert.False(result.DeliverySucceeded);
        Assert.True(result.TargetLost);
        Assert.Equal(["KeyDown:w", "KeyUp:w"], input.ControlOperations);
    }

    [Fact]
    public async Task ExecuteAsync_PartialPressFailureStillReleasesEveryIntendedKey()
    {
        var input = new RecordingInput("KeyDown:a");

        var result = await Executor(input).ExecuteAsync(new(["w", "a"], 20));

        Assert.False(result.DeliverySucceeded);
        Assert.True(result.ReleaseSucceeded);
        Assert.False(result.StateUncertain);
        Assert.Contains("synthetic failure", result.Error, StringComparison.Ordinal);
        Assert.Equal(["KeyDown:w", "KeyDown:a", "KeyUp:a", "KeyUp:w"], input.ControlOperations);
    }

    [Fact]
    public async Task ExecuteAsync_ReleaseFailuresAreAllAttemptedAndRequireCallerDisarm()
    {
        var input = new RecordingInput("ButtonUp:right", "KeyUp:a");

        var result = await Executor(input)
            .ExecuteAsync(new(["w", "a"], 20, "right", DeltaX: 4, DeltaY: -3));

        Assert.True(result.DeliverySucceeded);
        Assert.False(result.ReleaseSucceeded);
        Assert.True(result.StateUncertain);
        Assert.True(result.RequiresCallerDisarm);
        Assert.Contains("mouse button 'right'", result.Error, StringComparison.Ordinal);
        Assert.Contains("key 'a'", result.Error, StringComparison.Ordinal);
        Assert.Equal(
            ["KeyDown:w", "KeyDown:a", "ButtonDown:right", "MoveRelative:4,-3",
                "ButtonUp:right", "KeyUp:a", "KeyUp:w"],
            input.ControlOperations);
    }

    [Fact]
    public async Task ExecuteAsync_TargetLossDuringHoldStopsAndReleasesWithoutFurtherInput()
    {
        var input = new RecordingInput();
        input.TargetResponses.Enqueue(true);
        input.TargetResponses.Enqueue(true);
        input.TargetResponses.Enqueue(true);
        input.TargetResponses.Enqueue(false);

        var result = await Executor(input).ExecuteAsync(new(["w"], 30));

        Assert.False(result.DeliverySucceeded);
        Assert.True(result.TargetLost);
        Assert.True(result.ReleaseSucceeded);
        Assert.Equal(["KeyDown:w", "KeyUp:w"], input.ControlOperations);
    }

    [Fact]
    public async Task ExecuteAsync_TargetLossInsideChordDoesNotPressAgainButReleasesEveryIntendedKey()
    {
        var input = new RecordingInput();
        input.TargetResponses.Enqueue(true);
        input.TargetResponses.Enqueue(true);
        input.TargetResponses.Enqueue(false);

        var result = await Executor(input).ExecuteAsync(new(["w", "a"], 20));

        Assert.True(result.TargetLost);
        Assert.Equal(["KeyDown:w", "KeyUp:a", "KeyUp:w"], input.ControlOperations);
    }

    [Fact]
    public async Task ExecuteAsync_CancellationDuringHoldReleasesPressedControls()
    {
        using var cancellation = new CancellationTokenSource();
        var input = new RecordingInput();
        var executor = new BoundedControlExecutor(
            input,
            delayAsync: (_, token) =>
            {
                cancellation.Cancel();
                return Task.Delay(Timeout.InfiniteTimeSpan, token);
            });

        var result = await executor.ExecuteAsync(new(["d"], 20, "left"), cancellation.Token);

        Assert.False(result.DeliverySucceeded);
        Assert.True(result.Cancelled);
        Assert.True(result.ReleaseSucceeded);
        Assert.Equal(["KeyDown:d", "ButtonDown:left", "ButtonUp:left", "KeyUp:d"], input.ControlOperations);
    }

    [Fact]
    public async Task ExecuteAsync_PreCancelledActionDoesNoTargetOrInputIo()
    {
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        var input = new RecordingInput();

        var result = await Executor(input).ExecuteAsync(new(["w"], 20), cancellation.Token);

        Assert.True(result.Cancelled);
        Assert.True(result.ReleaseSucceeded);
        Assert.Empty(input.Operations);
    }

    [Fact]
    public async Task ExecuteAsync_DeliversCameraDragThenReleasesButton()
    {
        var input = new RecordingInput();

        var result = await Executor(input)
            .ExecuteAsync(new([], 20, "right", DeltaX: -200, DeltaY: 200));

        Assert.True(result.DeliverySucceeded);
        Assert.Equal(
            ["ButtonDown:right", "MoveRelative:-200,200", "ButtonUp:right"],
            input.ControlOperations);
    }

    [Fact]
    public async Task ExecuteAsync_DeliversStandaloneWheelWithoutDelayOrRelease()
    {
        var input = new RecordingInput();
        var delayCalled = false;
        var executor = new BoundedControlExecutor(
            input,
            delayAsync: (_, _) =>
            {
                delayCalled = true;
                return Task.CompletedTask;
            });

        var result = await executor.ExecuteAsync(new([], 0, WheelNotches: -3));

        Assert.True(result.DeliverySucceeded);
        Assert.True(result.ReleaseSucceeded);
        Assert.False(delayCalled);
        Assert.Equal(["Wheel:-3"], input.ControlOperations);
    }

    private static BoundedControlExecutor Executor(
        RecordingInput input,
        ManualTimeProvider? clock = null,
        Action<TimeSpan>? observeDelay = null)
    {
        clock ??= new ManualTimeProvider();
        return new(
            input,
            clock,
            (delay, _) =>
            {
                observeDelay?.Invoke(delay);
                clock.Advance(delay);
                return Task.CompletedTask;
            });
    }

    private sealed class ManualTimeProvider : TimeProvider
    {
        private long timestamp;

        public override long TimestampFrequency => TimeSpan.TicksPerSecond;

        public override long GetTimestamp() => timestamp;

        internal void Advance(TimeSpan duration) => timestamp = checked(timestamp + duration.Ticks);
    }

    private sealed class RecordingInput(params string[] failingOperations) : IControlInput
    {
        private readonly HashSet<string> failures = new(failingOperations, StringComparer.Ordinal);

        internal Queue<bool> TargetResponses { get; } = new();

        internal List<string> Operations { get; } = [];

        internal Action<string>? OperationRecorded { get; set; }

        internal string[] ControlOperations => Operations
            .Where(static operation => operation != "IsTargetCurrent")
            .ToArray();

        public bool IsTargetCurrent()
        {
            Record("IsTargetCurrent");
            return TargetResponses.Count == 0 || TargetResponses.Dequeue();
        }

        public void KeyDown(string key) => Record($"KeyDown:{key}");

        public void KeyUp(string key) => Record($"KeyUp:{key}");

        public void ButtonDown(string button) => Record($"ButtonDown:{button}");

        public void ButtonUp(string button) => Record($"ButtonUp:{button}");

        public void MoveRelative(int deltaX, int deltaY) => Record($"MoveRelative:{deltaX},{deltaY}");

        public void Wheel(int notches) => Record($"Wheel:{notches}");

        private void Record(string operation)
        {
            Operations.Add(operation);
            OperationRecorded?.Invoke(operation);
            if (failures.Contains(operation))
                throw new InvalidOperationException($"synthetic failure: {operation}");
        }
    }
}
