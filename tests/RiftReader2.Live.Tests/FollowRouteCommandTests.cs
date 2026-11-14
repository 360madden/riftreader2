using System.Text.Json;
using RiftReader2.Infrastructure;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class FollowRouteCommandTests
{
    private const ulong Player = 42;

    private static FollowRouteCommand.Options Options(double x = 0, double z = 10) =>
        new("AMD-DESKTOP", 5, 100, new string('A', 64), 8, Player,
            10, 200, x, z, @"C:\temp\stop.signal", 1800, true, true);

    private static FollowRouteCommand.Pose Pose(
        double x, double z, double bearing = 0, ulong player = Player, double y = 7)
    {
        var completed = DateTimeOffset.UtcNow;
        return new(x, y, z, bearing, player, 1000, 2000,
            completed.AddMilliseconds(-2), completed);
    }

    private sealed class Input : FollowRouteCommand.IInput
    {
        public readonly List<string> Events = [];
        public bool Current = true;
        public bool ThrowDown;
        public bool ThrowUp;
        public bool ThrowCurrent;
        public IReadOnlyList<string> HeldInputs = [];
        public bool IsTargetCurrent() => ThrowCurrent ? throw new IOException("inspect failed") : Current;
        public IReadOnlyList<string> ReadPressedInputs() => HeldInputs;
        public void KeyDown(string key)
        {
            Events.Add("down:" + key);
            if (ThrowDown) throw new IOException("down uncertain");
        }
        public void KeyUp(string key)
        {
            Events.Add("up:" + key);
            if (ThrowUp) throw new IOException("up failed");
        }
    }

    private static Func<CancellationToken, Task<FollowRouteCommand.Pose>> Reader(
        params FollowRouteCommand.Pose[] poses)
    {
        var queue = new Queue<FollowRouteCommand.Pose>(poses);
        return _ =>
        {
            var now = DateTimeOffset.UtcNow;
            return Task.FromResult(queue.Dequeue() with { StartedAtUtc = now, CompletedAtUtc = now });
        };
    }

    private static Task NoDelay(TimeSpan _, CancellationToken __) => Task.CompletedTask;

    [Fact]
    public void ParseRequiresExactOwnerAndOriginTriplet()
    {
        var args = new[] { "--expected-host", "AMD-DESKTOP", "--pid", "5",
            "--expect-start-ticks", "100", "--expect-sha256", new string('a',64),
            "--expect-hwnd", "0x8", "--expect-player-key", "42",
            "--owner-pid", "10", "--owner-start-ticks", "200",
            "--x", "3.5", "--z", "4.5", "--stop-file", @"C:\temp\stop.signal",
            "--expect-x", "1", "--expect-z", "2", "--expect-bearing", "-3",
            "--max-seconds", "1800", "--execute", "--json" };
        var parsed = FollowRouteCommand.Parse(args);
        Assert.Equal(1800, parsed.MaxSeconds);
        Assert.Equal(1, parsed.ExpectedX);
        Assert.Equal(-3, parsed.ExpectedBearing);
        Assert.Throws<InvalidDataException>(() =>
            FollowRouteCommand.Parse(args.Where(x => x != "--expect-bearing" && x != "-3").ToArray()));
    }

    [Fact]
    public void ReviewedOriginRejectsPoseOrBearingDrift()
    {
        var options = Options() with { ExpectedX = 1, ExpectedZ = 2, ExpectedBearing = 3 };
        FollowRouteCommand.ValidateExpectedOrigin(options, Pose(1.04, 2, 3.4));
        Assert.Throws<InvalidOperationException>(() =>
            FollowRouteCommand.ValidateExpectedOrigin(options, Pose(1.051, 2, 3)));
        Assert.Throws<InvalidOperationException>(() =>
            FollowRouteCommand.ValidateExpectedOrigin(options, Pose(1, 2, 3.51)));
    }

    [Fact]
    public async Task ReviewedOriginIsRepeatedImmediatelyBeforeInput()
    {
        var input = new Input();
        var options = Options() with { ExpectedX = 0, ExpectedZ = 0, ExpectedBearing = 0 };
        var result = await FollowRouteCommand.FollowAsync(options,
            Reader(Pose(.051, 0, 0)), input, () => null, NoDelay);
        Assert.Equal("blocked", result.Status);
        Assert.False(result.InputSent);
        Assert.Empty(input.Events);
    }

    [Fact]
    public async Task ForwardRemainsDownAcrossFeedbackUntilArrival()
    {
        var input = new Input();
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0,0), Pose(0,3), Pose(0,7), Pose(0,9.8),
                Pose(0,9.8), Pose(0,9.8)),
            input, () => null, NoDelay);
        Assert.Equal("arrived", result.Status);
        Assert.True(result.ReleaseSucceeded);
        Assert.Equal(6, result.ReadCount);
        Assert.Equal(result.ReadCount, result.Path.Length);
        Assert.Equal(1, input.Events.Count(x => x == "down:w"));
        Assert.Equal(1, input.Events.Count(x => x == "up:w"));
        Assert.Equal("down:w", input.Events.First());
        Assert.Equal("up:w", input.Events.Last());
    }

    [Fact]
    public async Task AlignmentObservesTurnInertiaBeforeStartingForward()
    {
        var input = new Input();
        var result = await FollowRouteCommand.FollowAsync(Options(10,0),
            Reader(Pose(0,0,0), Pose(0,0,80), Pose(0,0,88), Pose(0,0,92), Pose(0,0,91.5),
                Pose(5,0,95), Pose(9.8,0,90),
                Pose(9.8,0,90), Pose(9.8,0,90)),
            input, () => null, NoDelay);
        Assert.Equal("arrived", result.Status);
        Assert.Contains("down:a", input.Events);
        Assert.Contains("up:a", input.Events);
        Assert.Equal(1, input.Events.Count(x => x == "down:w"));
        Assert.Equal(1, input.Events.Count(x => x == "up:w"));
        Assert.True(input.Events.IndexOf("up:a") < input.Events.IndexOf("down:w"));
        Assert.Equal(result.ReadCount, result.Path.Length);
    }

    [Fact]
    public async Task LongTurnCoastIsSettledAndNudgedBeforeForwardStarts()
    {
        var input = new Input();
        const double goalX = 1.039558454;
        const double goalZ = 4.890738004;
        var result = await FollowRouteCommand.FollowAsync(Options(goalX, goalZ),
            Reader(Pose(0,0,-168), Pose(0,0,-138), Pose(0,0,-108), Pose(0,0,-78),
                Pose(0,0,-48), Pose(0,0,-18), Pose(0,0,0),
                Pose(0,0,10.8), Pose(0,0,18.9), Pose(0,0,21.6), Pose(0,0,21.6),
                Pose(0,0,18), Pose(0,0,14), Pose(0,0,12.5), Pose(0,0,12.2),
                Pose(.52,2.45,12.2), Pose(1.0,4.7,12.2),
                Pose(1.0,4.7,12.2), Pose(1.0,4.7,12.2)),
            input, () => null, NoDelay);
        Assert.Equal("arrived", result.Status);
        Assert.Equal(1, input.Events.Count(x => x == "down:a"));
        Assert.Equal(1, input.Events.Count(x => x == "down:d"));
        Assert.True(input.Events.IndexOf("up:a") < input.Events.IndexOf("down:w"));
        Assert.True(input.Events.IndexOf("up:d") < input.Events.IndexOf("down:w"));
        var forwardRead = Array.FindIndex(result.Path,
            point => Math.Sqrt(point.X * point.X + point.Z * point.Z) > .1);
        Assert.True(forwardRead >= 15, "Forward movement began before coast and residual nudge settled.");
    }

    [Fact]
    public async Task ThreeUnitStraightRunUsesOneContinuousForwardHold()
    {
        var input = new Input();
        var result = await FollowRouteCommand.FollowAsync(Options(z: 3),
            Reader(Pose(0, 0), Pose(0, 1.5), Pose(0, 2.6), Pose(0, 2.8), Pose(0, 2.8)),
            input, () => null);
        Assert.Equal("arrived", result.Status);
        Assert.Equal(1, input.Events.Count(x => x == "down:w"));
        Assert.Equal(1, input.Events.Count(x => x == "up:w"));
        Assert.DoesNotContain("down:a", input.Events);
        Assert.DoesNotContain("down:d", input.Events);
    }

    [Fact]
    public async Task SameReadOpticalCameraTelemetryIsRetainedForEveryPathPoint()
    {
        var poses = new[]
        {
            Pose(0, 0) with { OpticalCameraBearingDegreesCandidate = 1,
                OpticalCameraPitchDegreesCandidate = -5, OpticalCameraStatus = "available-candidate" },
            Pose(0, 3) with { OpticalCameraBearingDegreesCandidate = 2,
                OpticalCameraPitchDegreesCandidate = -4, OpticalCameraStatus = "available-candidate" },
            Pose(0, 7) with { OpticalCameraBearingDegreesCandidate = 3,
                OpticalCameraPitchDegreesCandidate = -3, OpticalCameraStatus = "available-candidate" },
            Pose(0, 9.8) with { OpticalCameraBearingDegreesCandidate = 4,
                OpticalCameraPitchDegreesCandidate = -2, OpticalCameraStatus = "available-candidate" },
            Pose(0, 9.8) with { OpticalCameraBearingDegreesCandidate = 5,
                OpticalCameraPitchDegreesCandidate = -1, OpticalCameraStatus = "available-candidate" },
            Pose(0, 9.8) with { OpticalCameraBearingDegreesCandidate = 6,
                OpticalCameraPitchDegreesCandidate = 0, OpticalCameraStatus = "available-candidate" }
        };
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(poses), new Input(), () => null, NoDelay);

        Assert.Equal("arrived", result.Status);
        Assert.Equal(result.ReadCount, result.Path.Length);
        Assert.Equal(poses.Select(p => p.OpticalCameraBearingDegreesCandidate),
            result.Path.Select(p => p.OpticalCameraBearingDegreesCandidate));
        Assert.Equal(poses.Select(p => p.OpticalCameraPitchDegreesCandidate),
            result.Path.Select(p => p.OpticalCameraPitchDegreesCandidate));
        Assert.All(result.Path, point => Assert.Equal("available-candidate", point.OpticalCameraStatus));
        Assert.Equal(6, result.FinalPose?.OpticalCameraBearingDegreesCandidate);
        Assert.Equal(6, result.Path[^1].OpticalCameraBearingDegreesCandidate);
    }

    [Fact]
    public void PathPointSerializesExplicitNullableCandidateCameraFields()
    {
        var point = new FollowRouteCommand.PathPoint(1, 2, 3, 4, 5, DateTimeOffset.UnixEpoch);
        var json = JsonSerializer.SerializeToElement(point, JsonFormat.Options);

        Assert.Equal(JsonValueKind.Null, json.GetProperty("opticalCameraBearingDegreesCandidate").ValueKind);
        Assert.Equal(JsonValueKind.Null, json.GetProperty("opticalCameraPitchDegreesCandidate").ValueKind);
        Assert.Equal(JsonValueKind.Null, json.GetProperty("opticalCameraStatus").ValueKind);
    }

    [Fact]
    public async Task StopReleasesForwardAndReportsStopped()
    {
        var input = new Input();
        var stop = false;
        async Task Delay(TimeSpan _, CancellationToken __)
        {
            stop = true;
            await Task.Delay(Timeout.InfiniteTimeSpan, __);
        }
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0,0)), input, () => stop ? "stop-file-requested" : null, Delay);
        Assert.Equal("stopped", result.Status);
        Assert.Equal("stop-file-requested", result.Reason);
        Assert.Contains("up:w", input.Events);
        Assert.True(result.ReleaseSucceeded);
    }

    [Fact]
    public async Task ForwardSteeringIsOneBriefNudgeInsteadOfAlternatingCorrections()
    {
        var input = new Input();
        var delays = new List<TimeSpan>();
        Task Delay(TimeSpan duration, CancellationToken _) { delays.Add(duration); return Task.CompletedTask; }
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0,0), Pose(.3,3,8), Pose(.15,4,-12),
                Pose(.1,5,8), Pose(0,9.8), Pose(0,9.8), Pose(0,9.8)),
            input, () => null, Delay);
        Assert.Equal("arrived", result.Status);
        Assert.Equal(1, input.Events.Count(x => x == "down:d"));
        Assert.DoesNotContain("down:a", input.Events);
        Assert.Contains(TimeSpan.FromMilliseconds(FollowRouteCommand.SteeringPulseMilliseconds), delays);
        Assert.True(input.Events.IndexOf("up:d") < input.Events.IndexOf("up:w"));
        Assert.Equal(1, input.Events.Count(x => x == "down:w"));
    }

    [Fact]
    public async Task FinalApproachDoesNotChaseLeftRightHeadingChanges()
    {
        var input = new Input();
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0,0), Pose(.15,8.5,-12), Pose(.15,9.3,12),
                Pose(.15,9.8), Pose(.15,9.8), Pose(.15,9.8)),
            input, () => null, NoDelay);
        Assert.Equal("arrived", result.Status);
        Assert.DoesNotContain("down:a", input.Events);
        Assert.DoesNotContain("down:d", input.Events);
        Assert.True(result.ReleaseSucceeded);
    }

    [Fact]
    public async Task SmallRouteOffsetsDoNotTriggerHeadingOnlyCorrections()
    {
        var input = new Input();
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0,0), Pose(.1,1,-8), Pose(.1,3,8), Pose(.1,5,-8),
                Pose(.1,9.8), Pose(.1,9.8), Pose(.1,9.8)),
            input, () => null, NoDelay);
        Assert.Equal("arrived", result.Status);
        Assert.DoesNotContain("down:a", input.Events);
        Assert.DoesNotContain("down:d", input.Events);
        Assert.Equal(1, input.Events.Count(x => x == "down:w"));
    }

    [Fact]
    public async Task StopDuringSteeringNudgeReleasesBothKeys()
    {
        var input = new Input();
        var stop = false;
        async Task Delay(TimeSpan duration, CancellationToken cancellation)
        {
            if (duration.TotalMilliseconds != FollowRouteCommand.SteeringPulseMilliseconds) return;
            stop = true;
            await Task.Delay(Timeout.InfiniteTimeSpan, cancellation);
        }
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0,0), Pose(.3,3,8)), input,
            () => stop ? "stop-file-requested" : null, Delay);
        Assert.Equal("stopped", result.Status);
        Assert.Contains("up:w", input.Events);
        Assert.Contains("up:d", input.Events);
        Assert.True(result.ReleaseSucceeded);
    }

    [Fact]
    public async Task StalledPoseReadTriggersIndependentWatchdogRelease()
    {
        var input = new Input();
        var first = true;
        var never = new TaskCompletionSource<FollowRouteCommand.Pose>();
        Task<FollowRouteCommand.Pose> Read(CancellationToken _)
        {
            if (first) { first = false; return Task.FromResult(Pose(0,0)); }
            return never.Task;
        }
        var task = FollowRouteCommand.FollowAsync(Options(), Read, input, () => null);
        await Task.Delay(1000);
        Assert.Contains("up:w", input.Events);
        never.SetException(new IOException("read remained blocked"));
        var result = await task;
        Assert.Equal("halted", result.Status);
        Assert.Equal("pose-stale", result.Reason);
        Assert.True(result.ReleaseSucceeded);
    }

    [Fact]
    public async Task OwnerFailureAndLongGoalReleaseWithoutWeakeningDistanceLimit()
    {
        var input = new Input();
        var failed = false;
        async Task Delay(TimeSpan _, CancellationToken __)
        {
            failed = true;
            await Task.Delay(40);
        }
        var result = await FollowRouteCommand.FollowAsync(Options(0,999),
            Reader(Pose(0,0)), input, () => failed ? "owner-process-lost" : null, Delay);
        Assert.Equal("halted", result.Status);
        Assert.Equal(999, result.InitialDistance);
        Assert.Contains("up:w", input.Events);

        var blocked = await FollowRouteCommand.FollowAsync(Options(0,1000.01),
            Reader(Pose(0,0)), new Input(), () => null, NoDelay);
        Assert.Equal("blocked", blocked.Status);
        Assert.False(blocked.InputSent);
    }

    [Fact]
    public async Task PlayerOwnerChangeAfterInputHaltsAndReleases()
    {
        var input = new Input();
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0,0), Pose(0,1,player:99)), input, () => null, NoDelay);
        Assert.Equal("halted", result.Status);
        Assert.Contains("up:w", input.Events);
        Assert.True(result.ReleaseSucceeded);
    }

    [Fact]
    public async Task WatchdogFaultReleasesAndCannotRaceASecondKeyDown()
    {
        var input = new Input { ThrowCurrent = true };
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0,0)), input, () => null,
            (_, cancellation) => Task.Delay(Timeout.InfiniteTimeSpan, cancellation));
        Assert.Equal("blocked", result.Status);
        // Either independent watchdog or synchronous pre-input guard may win.
        Assert.True(result.Reason?.StartsWith("watchdog-fault:") == true
            || result.Reason?.StartsWith("safety-check-failed:") == true);
        Assert.Empty(input.Events);
    }

    [Fact]
    public async Task KeyDownAttemptIsReportedConservativelyAndReleased()
    {
        var input = new Input { ThrowDown = true };
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0,0)), input, () => null, NoDelay);
        Assert.Equal("halted", result.Status);
        Assert.True(result.InputSent);
        Assert.Contains("up:w", input.Events);
    }

    [Fact]
    public async Task ReleaseFailureCannotReportArrival()
    {
        var input = new Input { ThrowUp = true };
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0,0), Pose(0,9.8)), input, () => null, NoDelay);
        Assert.Equal("halted", result.Status);
        Assert.Equal("key-release-failed", result.Reason);
        Assert.False(result.ReleaseSucceeded);
        Assert.Equal(2, input.Events.Count(x => x == "up:w"));
    }

    [Fact]
    public async Task ArrivalRequiresTwoSettledPostReleaseObservations()
    {
        var input = new Input();
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0,0), Pose(0,9.8), Pose(0,9.9), Pose(0,10.01)),
            input, () => null, NoDelay);
        Assert.Equal("halted", result.Status);
        Assert.Equal("post-release-arrival-not-settled", result.Reason);
        Assert.Contains("up:w", input.Events);
    }

    [Fact]
    public async Task DirectPathAndTurnGuardsHaltAndRelease()
    {
        var turnInput = new Input();
        var turn = await FollowRouteCommand.FollowAsync(Options(10,0),
            Reader(Pose(0,0,0), Pose(0,0,0), Pose(0,0,0), Pose(0,0,0)),
            turnInput, () => null, NoDelay);
        Assert.Equal("halted", turn.Status);
        Assert.Contains("up:a", turnInput.Events);

        var pathInput = new Input();
        var path = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0,0), Pose(.51,1)), pathInput, () => null, NoDelay);
        Assert.Equal("halted", path.Status);
        Assert.Contains("up:w", pathInput.Events);
    }

    [Fact]
    public async Task PoseOwnerOrderAndFutureTimeAreCheckedAtCoreSeam()
    {
        var changed = Pose(0,1) with { PlayerEntity = 1001 };
        var owner = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0,0), changed), new Input(), () => null, NoDelay);
        Assert.Equal("halted", owner.Status);

        var future = Pose(0,0) with
        {
            StartedAtUtc = DateTimeOffset.UtcNow.AddSeconds(1),
            CompletedAtUtc = DateTimeOffset.UtcNow.AddSeconds(1)
        };
        var stale = await FollowRouteCommand.FollowAsync(Options(),
            _ => Task.FromResult(future), new Input(), () => null, NoDelay);
        Assert.Equal("blocked", stale.Status);
        Assert.False(stale.InputSent);
    }

    [Fact]
    public async Task CoarseSamplePassingGoalReleasesBeforeAnySteering()
    {
        var input = new Input();
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0, 0), Pose(0, 9.5), Pose(0, 10.5), Pose(0, 10.5), Pose(0, 10.5)),
            input, () => null, NoDelay);
        Assert.Equal("halted", result.Status);
        Assert.Equal("post-release-arrival-not-settled", result.Reason);
        Assert.Equal(1, input.Events.Count(x => x == "down:w"));
        Assert.DoesNotContain("down:a", input.Events);
        Assert.DoesNotContain("down:d", input.Events);
        Assert.True(input.Events.IndexOf("up:w") < input.Events.Count);
    }

    [Fact]
    public void CorridorLookaheadExposesSmallLongRouteLateralDrift()
    {
        var start = Pose(0, 0);
        var offset = Pose(.3, 10);
        var finalPointError = Math.Abs(FollowRouteCommand.HeadingError(
            FollowRouteCommand.BearingTo(offset, 0, 100), offset.Bearing));
        var corridorError = Math.Abs(FollowRouteCommand.HeadingError(
            FollowRouteCommand.CorridorBearing(offset, start, 0, 100), offset.Bearing));
        Assert.True(finalPointError < 1);
        Assert.True(corridorError > 5);
    }

    [Fact]
    public async Task NewlyHeldOperatorInputHaltsAndReleases()
    {
        var input = new Input();
        var first = true;
        async Task Delay(TimeSpan _, CancellationToken cancellation)
        {
            if (first)
            {
                first = false;
                input.HeldInputs = ["s"];
            }
            await Task.Delay(75, cancellation);
        }
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0, 0), Pose(0, 1)), input, () => null, Delay);
        Assert.Equal("halted", result.Status);
        Assert.StartsWith("external-input-held:", result.Reason);
        Assert.Contains("up:w", input.Events);
    }

    [Fact]
    public async Task OperatorInputIsRecheckedSynchronouslyBeforeFirstKeyDown()
    {
        var input = new Input { HeldInputs = ["s"] };
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0, 0)), input, () => null, NoDelay);
        Assert.Equal("blocked", result.Status);
        Assert.StartsWith("external-input-held:", result.Reason);
        Assert.Empty(input.Events);
    }

    [Fact]
    public async Task OverlappingPoseSamplesAreRejected()
    {
        var first = Pose(0, 0);
        var second = Pose(0, 1) with
        {
            StartedAtUtc = first.CompletedAtUtc.AddMilliseconds(-1),
            CompletedAtUtc = first.CompletedAtUtc.AddMilliseconds(1)
        };
        var queue = new Queue<FollowRouteCommand.Pose>([first, second]);
        var result = await FollowRouteCommand.FollowAsync(Options(),
            _ => Task.FromResult(queue.Dequeue()), new Input(), () => null, NoDelay);
        Assert.Equal("halted", result.Status);
        Assert.Contains("sample order", result.Reason);
    }

    [Fact]
    public async Task ArrivalTriggerCannotBypassAbsoluteVerticalPathGuard()
    {
        var input = new Input();
        var result = await FollowRouteCommand.FollowAsync(Options(z: 2),
            Reader(Pose(0, 0, y: 10), Pose(0, 2, y: 8)),
            input, () => null, NoDelay);
        Assert.Equal("halted", result.Status);
        Assert.Contains("Vertical drift", result.Reason);
        Assert.Contains("up:w", input.Events);
        Assert.True(result.ReleaseSucceeded);
    }
}
