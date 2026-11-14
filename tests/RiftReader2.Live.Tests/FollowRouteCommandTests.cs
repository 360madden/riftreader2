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

    private static FollowRouteCommand.SurvivalSnapshot Survival(
        long? health = 100, long? maximum = 100, bool? combat = false,
        string status = "available-candidate", byte? rawCombat = 0,
        string? reason = null)
    {
        var completed = DateTimeOffset.UtcNow;
        return new(status, health, maximum, combat, rawCombat,
            completed.AddMilliseconds(-2), completed, reason);
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
    public async Task DenseGuidesAndAdmissionUseOneHoldAndOrderedReceipts()
    {
        var input = new Input();
        var streamed = new List<FollowRouteCommand.WaypointPass>();
        var options = Options(z: 3) with { RoutePoints = [
            new("start", 0, .1), new("one", 0, .45), new("two", 0, .8), new("three", 0, 1.1)] };
        var result = await FollowRouteCommand.FollowAsync(options,
            Reader(Pose(0, 0), Pose(0, .4), Pose(0, .75), Pose(0, 1.06),
                Pose(0, 2.8), Pose(0, 2.8), Pose(0, 2.8)),
            input, () => null, NoDelay, onWaypointPassed: p =>
            {
                if (p.Index > 0) Assert.Equal(new[] { "down:w" }, input.Events);
                streamed.Add(p);
            });
        Assert.Equal("arrived", result.Status);
        Assert.Equal(new[] { "down:w", "up:w" }, input.Events);
        Assert.Equal(new[] { "start", "one", "two", "three" }, streamed.Select(p => p.Name));
        Assert.Equal(streamed, result.PassedWaypoints);
        Assert.Equal(streamed, FollowRouteCommand.ProjectResult(result).PassedWaypoints);
        Assert.Empty(FollowRouteCommand.ProjectResult(null).PassedWaypoints);
    }

    [Theory]
    [InlineData(3.5, 90.0)]
    [InlineData(6.25, 25.0)]
    [InlineData(6.25, 90.0)]
    public async Task SimulatedTwoBendsKeepForwardHeldWithinCorridor(double speed, double angle)
    {
        var input = new Input();
        var turnAngle = angle * Math.PI / 180;
        var bendX = 5 * Math.Sin(turnAngle);
        var bendZ = 5 + 5 * Math.Cos(turnAngle);
        var options = Options(bendX, bendZ + 5) with { RoutePoints = [
            new("north", 0, 5), new("bend", bendX, bendZ)] };
        double x = 0, z = 0, bearing = 0;
        var count = 0;
        var lastTurn = 0;
        var coast = 0.0;
        var forwardCoast = 0.0;
        var simulatedTime = DateTimeOffset.UtcNow;
        bool Held(string key) => input.Events.LastOrDefault(e => e.EndsWith(":" + key)) == "down:" + key;
        async Task Delay(TimeSpan duration, CancellationToken _)
        {
            var seconds = duration.TotalSeconds;
            var turn = (Held("a") ? 1 : 0) - (Held("d") ? 1 : 0);
            if (turn != 0) { lastTurn = turn; coast = .045; }
            var turningFor = turn == 0 ? Math.Min(coast, seconds) : seconds;
            var delta = lastTurn * 175 * turningFor;
            if (turn == 0) coast -= turningFor;
            var mid = (bearing + delta / 2) * Math.PI / 180;
            var forward = Held("w");
            if (forward) forwardCoast = .025;
            var movingFor = forward ? seconds : Math.Min(forwardCoast, seconds);
            x += speed * movingFor * Math.Sin(mid);
            z += speed * movingFor * Math.Cos(mid);
            if (!forward) forwardCoast -= movingFor;
            bearing += delta;
            simulatedTime += duration;
            var wait = simulatedTime - DateTimeOffset.UtcNow;
            if (wait > TimeSpan.Zero) await Task.Delay(wait);
        }
        Task<FollowRouteCommand.Pose> Read(CancellationToken _)
        {
            if (++count > 500) throw new InvalidOperationException("Simulation read bound.");
            return Task.FromResult(Pose(x, z, bearing) with { StartedAtUtc = simulatedTime,
                CompletedAtUtc = simulatedTime });
        }
        var result = await FollowRouteCommand.FollowAsync(options, Read, input, () => null, Delay,
            onWaypointPassed: _ =>
            {
                Assert.Equal(1, input.Events.Count(e => e == "down:w"));
                Assert.DoesNotContain("up:w", input.Events);
            });
        if (speed > 6 && angle == 90 && result.Status == "halted")
        {
            Assert.Contains("route corridor", result.Reason);
            Assert.True(result.ReleaseSucceeded);
            Assert.Contains("up:w", input.Events);
            return;
        }
        Assert.True(result.Status == "arrived", $"{result.Reason}; {x:F2},{z:F2}, bearing {bearing:F1}");
        Assert.Equal(new[] { "north", "bend" }, result.PassedWaypoints!.Select(p => p.Name));
        Assert.Contains("down:a", input.Events);
        Assert.Contains("down:d", input.Events);
        Assert.Equal(input.Events.Count(e => e == "down:w"), input.Events.Count(e => e == "up:w"));
        Assert.True(result.ReleaseSucceeded);
    }

    [Fact]
    public async Task CrossingBetweenSamplesHasBoundedEvidenceAndOneRelease()
    {
        var input = new Input();
        var options = Options(z: 3) with { RoutePoints = [new("gate", 0, 1.4)] };
        var at = DateTimeOffset.UtcNow.AddMilliseconds(-620);
        var samples = new Queue<(double Z, int Time)>([(0, 0), (.82, 100), (2, 200),
            (2.85, 300), (2.85, 400), (2.85, 500)]);
        Task<FollowRouteCommand.Pose> Read(CancellationToken _)
        {
            var (z, ms) = samples.Dequeue();
            return Task.FromResult(Pose(0, z) with { StartedAtUtc = at.AddMilliseconds(ms),
                CompletedAtUtc = at.AddMilliseconds(ms) });
        }
        var result = await FollowRouteCommand.FollowAsync(options, Read, input, () => null, NoDelay);
        Assert.Equal("arrived", result.Status);
        var pass = Assert.Single(result.PassedWaypoints!);
        Assert.Equal("segment-crossing", pass.Source);
        Assert.Equal(1.4, pass.Position.Z, 5);
        Assert.Equal(.82, pass.CrossingBefore!.Position.Z);
        Assert.Equal(2, pass.CrossingAfter!.Position.Z);
        Assert.InRange(pass.ObservedAtUtc, pass.CrossingBefore.ObservedAtUtc, pass.CrossingAfter.ObservedAtUtc);
        Assert.Equal(new[] { "down:w", "up:w" }, input.Events);
    }

    [Fact]
    public async Task StopAfterPassReleasesAndReceiptsOnlyTheVerifiedPrefix()
    {
        var input = new Input();
        bool stop = false;
        var read = Reader(Pose(0, 0), Pose(0, 1));
        var result = await FollowRouteCommand.FollowAsync(Options() with
            { RoutePoints = [new("one", 0, 1), new("two", 0, 3)] }, read, input,
            () => stop ? "stop-file-requested" : null,
            (delay, ct) => stop ? Task.Delay(Timeout.InfiniteTimeSpan, ct) : Task.CompletedTask,
            onWaypointPassed: _ => stop = true);
        Assert.Equal("stopped", result.Status);
        Assert.Equal("one", Assert.Single(result.PassedWaypoints!).Name);
        Assert.Equal(new[] { "down:w", "up:w" }, input.Events);
        Assert.True(result.ReleaseSucceeded);
    }

    [Fact]
    public async Task PolylineLengthAndEachPlannedGradeAreBoundedBeforeInput()
    {
        foreach (var point in new FollowRouteCommand.RoutePoint[] {
            new("far", 0, 506), new("steep", 0, 1, 12), new("invalid", double.NaN, 0) })
        {
            var input = new Input();
            var result = await FollowRouteCommand.FollowAsync(Options() with { RoutePoints = [point] },
                Reader(Pose(0, 0)), input, () => null, NoDelay);
            Assert.Equal("blocked", result.Status);
            Assert.Empty(input.Events);
        }
    }

    [Fact]
    public async Task HairpinCannotSkipOutgoingGuideOrCreditOffPathPass()
    {
        var input = new Input();
        var options = Options(z: 4) with { RoutePoints = [new("out", 0, 3), new("back", 0, .5)] };
        var result = await FollowRouteCommand.FollowAsync(options,
            Reader(Pose(0, 0), Pose(0, .5), Pose(0, 1.5), Pose(0, 2.8), Pose(.51, 3)),
            input, () => null, NoDelay);
        Assert.Equal("halted", result.Status);
        Assert.Contains("Cross-track drift", result.Reason);
        Assert.Equal("out", Assert.Single(result.PassedWaypoints!).Name);
        Assert.True(result.ReleaseSucceeded);
        Assert.Contains("up:w", input.Events);
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
    public async Task SurvivalHealthDropReleasesForwardAndRetainsTriggeringSnapshot()
    {
        var input = new Input();
        var result = await FollowRouteCommand.FollowAsync(
            Options() with { SurvivalInterrupt = true },
            Reader(Pose(0, 0) with { Survival = Survival() },
                Pose(0, 1) with { Survival = null },
                Pose(0, 2) with { Survival = Survival(99) }),
            input, () => null, NoDelay);

        Assert.Equal("halted", result.Status);
        Assert.Equal("survival-hp-drop", result.Reason);
        Assert.Contains("down:w", input.Events);
        Assert.Contains("up:w", input.Events);
        Assert.Equal(99, result.SurvivalSnapshot?.HealthCurrent);
        Assert.True(result.ReleaseSucceeded);
    }

    [Fact]
    public async Task SurvivalCombatReleasesForwardWithoutWaitingForRouteFailure()
    {
        var input = new Input();
        var result = await FollowRouteCommand.FollowAsync(
            Options() with { SurvivalInterrupt = true },
            Reader(Pose(0, 0) with { Survival = Survival() },
                Pose(0, 1) with { Survival = Survival(combat: true, rawCombat: 1) }),
            input, () => null, NoDelay);

        Assert.Equal("halted", result.Status);
        Assert.Equal("survival-combat", result.Reason);
        Assert.Contains("up:w", input.Events);
        Assert.True(result.SurvivalSnapshot?.CombatCandidate);
    }

    [Fact]
    public async Task BaselineCombatRetainsFiniteSerializableTerminalReceipt()
    {
        var result = await FollowRouteCommand.FollowAsync(
            Options() with { SurvivalInterrupt = true },
            Reader(Pose(1, 2, 15) with { Survival = Survival(combat: true, rawCombat: 1) }),
            new Input(), () => null, NoDelay);
        var receipt = FollowRouteCommand.ProjectResult(result);

        var json = JsonSerializer.SerializeToElement(new
        {
            result.Status,
            result.Reason,
            receipt.Position,
            receipt.BodyBearingDegreesCandidate,
            receipt.OpticalCameraBearingDegreesCandidate,
            receipt.OpticalCameraPitchDegreesCandidate,
            receipt.OpticalCameraStatus,
            receipt.InitialDistance,
            receipt.FinalDistance,
            receipt.ReadCount,
            receipt.Path,
            receipt.ElapsedMilliseconds,
            receipt.InputSent,
            receipt.ReleaseSucceeded,
            receipt.SurvivalSnapshot
        }, JsonFormat.Options);

        Assert.Equal("halted", json.GetProperty("status").GetString());
        Assert.Equal("survival-combat", json.GetProperty("reason").GetString());
        Assert.Equal(JsonValueKind.Object, json.GetProperty("position").ValueKind);
        Assert.Equal(15, json.GetProperty("bodyBearingDegreesCandidate").GetDouble());
        Assert.Equal(JsonValueKind.Number, json.GetProperty("initialDistance").ValueKind);
        Assert.Equal(JsonValueKind.Number, json.GetProperty("finalDistance").ValueKind);
        Assert.Equal(1, json.GetProperty("readCount").GetInt32());
        Assert.Single(json.GetProperty("path").EnumerateArray());
        Assert.False(json.GetProperty("inputSent").GetBoolean());
        Assert.True(json.GetProperty("releaseSucceeded").GetBoolean());
    }

    [Fact]
    public void ReceiptProjectionConvertsAllNonfiniteTopLevelMetricsToNull()
    {
        var result = new FollowRouteCommand.Result("blocked", "read-failed", null,
            double.NaN, double.PositiveInfinity, 0, [], double.NegativeInfinity,
            false, true);

        var receipt = FollowRouteCommand.ProjectResult(result);
        var json = JsonSerializer.SerializeToElement(receipt, JsonFormat.Options);

        Assert.Equal(JsonValueKind.Null, json.GetProperty("initialDistance").ValueKind);
        Assert.Equal(JsonValueKind.Null, json.GetProperty("finalDistance").ValueKind);
        Assert.Equal(0, json.GetProperty("elapsedMilliseconds").GetDouble());
    }

    [Fact]
    public async Task SurvivalBaselineCancellationCallbackFaultCannotEscapeControllerReceipt()
    {
        var input = new Input();
        var registration = default(CancellationTokenRegistration);
        Task<FollowRouteCommand.Pose> Read(CancellationToken token)
        {
            registration = token.Register(() => throw new InvalidOperationException("callback failed"));
            var now = DateTimeOffset.UtcNow;
            return Task.FromResult(Pose(0, 0) with
            {
                StartedAtUtc = now,
                CompletedAtUtc = now,
                Survival = Survival(combat: true, rawCombat: 1)
            });
        }

        var result = await FollowRouteCommand.FollowAsync(
            Options() with { SurvivalInterrupt = true }, Read,
            input, () => null, NoDelay);
        registration.Dispose();

        Assert.Equal("halted", result.Status);
        Assert.Equal("survival-combat", result.Reason);
        Assert.Empty(input.Events);
        Assert.True(result.ReleaseSucceeded);
    }

    [Theory]
    [InlineData(0L, "available-candidate", "survival-dead")]
    [InlineData(null, "unavailable", "survival-unavailable")]
    public async Task CriticalBaselineSurvivalStateHaltsBeforeAnyInput(
        long? health, string snapshotStatus, string expectedReason)
    {
        var input = new Input();
        var snapshot = Survival(health, status: snapshotStatus,
            combat: snapshotStatus == "available-candidate" ? false : null,
            rawCombat: snapshotStatus == "available-candidate" ? (byte)0 : null,
            reason: snapshotStatus == "unavailable" ? "capture-failed" : null);
        var result = await FollowRouteCommand.FollowAsync(
            Options() with { SurvivalInterrupt = true },
            Reader(Pose(0, 0) with { Survival = snapshot }),
            input, () => null, NoDelay);

        Assert.Equal("halted", result.Status);
        Assert.Equal(expectedReason, result.Reason);
        Assert.Empty(input.Events);
        Assert.Same(snapshot, result.SurvivalSnapshot);
        Assert.True(result.ReleaseSucceeded);
    }

    [Fact]
    public void SurvivalInterruptIsExplicitOptIn()
    {
        var options = FollowRouteCommand.Parse([
            "--expected-host", "AMD-DESKTOP", "--pid", "5",
            "--expect-start-ticks", "100", "--expect-sha256", new string('A', 64),
            "--expect-hwnd", "8", "--expect-player-key", Player.ToString(),
            "--owner-pid", "10", "--owner-start-ticks", "200",
            "--x", "0", "--z", "10", "--stop-file", @"C:\temp\stop.signal",
            "--survival-interrupt", "--execute", "--json"
        ]);
        Assert.True(options.SurvivalInterrupt);
        Assert.False(options.SurvivalRetreat);
        Assert.Equal("interrupt", FollowRouteCommand.SurvivalMode(options));
    }

    [Fact]
    public void SurvivalRetreatRequiresInterruptAndHasExplicitMode()
    {
        string[] Args(params string[] flags) => [
            "--expected-host", "AMD-DESKTOP", "--pid", "5",
            "--expect-start-ticks", "100", "--expect-sha256", new string('A', 64),
            "--expect-hwnd", "8", "--expect-player-key", Player.ToString(),
            "--owner-pid", "10", "--owner-start-ticks", "200",
            "--x", "0", "--z", "10", "--stop-file", @"C:\temp\stop.signal",
            .. flags, "--execute", "--json"
        ];

        Assert.Throws<InvalidDataException>(() =>
            FollowRouteCommand.Parse(Args("--survival-retreat")));
        var options = FollowRouteCommand.Parse(Args("--survival-interrupt", "--survival-retreat"));
        Assert.True(options.SurvivalInterrupt);
        Assert.True(options.SurvivalRetreat);
        Assert.Equal("retreat", FollowRouteCommand.SurvivalMode(options));
    }

    [Fact]
    public async Task RetreatSurvivalPermitsCombatAndHealthLossWhileForwardRemainsOwned()
    {
        var input = new Input();
        var result = await FollowRouteCommand.FollowAsync(
            Options() with { SurvivalInterrupt = true, SurvivalRetreat = true },
            Reader(Pose(0, 0) with { Survival = Survival(combat: true, rawCombat: 1) },
                Pose(0, 4) with { Survival = Survival(99, combat: true, rawCombat: 1) },
                Pose(0, 9.8) with { Survival = Survival(98, combat: true, rawCombat: 1) },
                Pose(0, 9.8) with { Survival = Survival(98, combat: true, rawCombat: 1) },
                Pose(0, 9.8) with { Survival = Survival(98, combat: true, rawCombat: 1) }),
            input, () => null, NoDelay);

        Assert.Equal("arrived", result.Status);
        Assert.Null(result.Reason);
        Assert.Equal(1, input.Events.Count(x => x == "down:w"));
        Assert.Equal(1, input.Events.Count(x => x == "up:w"));
        Assert.Equal(98, result.SurvivalSnapshot?.HealthCurrent);
        Assert.True(result.SurvivalSnapshot?.CombatCandidate);
        Assert.True(result.ReleaseSucceeded);
    }

    [Theory]
    [InlineData(0L, "available-candidate", "survival-dead")]
    [InlineData(null, "unavailable", "survival-unavailable")]
    public async Task RetreatSurvivalStillHaltsAndReleasesForDeathOrUnavailable(
        long? health, string snapshotStatus, string expectedReason)
    {
        var input = new Input();
        var critical = Survival(health, status: snapshotStatus,
            combat: snapshotStatus == "available-candidate" ? true : null,
            rawCombat: snapshotStatus == "available-candidate" ? (byte)1 : null,
            reason: snapshotStatus == "unavailable" ? "capture-failed" : null);
        var result = await FollowRouteCommand.FollowAsync(
            Options() with { SurvivalInterrupt = true, SurvivalRetreat = true },
            Reader(Pose(0, 0) with { Survival = Survival(combat: true, rawCombat: 1) },
                Pose(0, 1) with { Survival = critical }),
            input, () => null, NoDelay);

        Assert.Equal("halted", result.Status);
        Assert.Equal(expectedReason, result.Reason);
        Assert.Contains("down:w", input.Events);
        Assert.Contains("up:w", input.Events);
        Assert.Same(critical, result.SurvivalSnapshot);
        Assert.True(result.ReleaseSucceeded);
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
    public async Task OvershotBrakeEndpointTurnsInPlaceBeforeBoundedFinishPulse()
    {
        var input = new Input();
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(Pose(0, 0), Pose(0, 9.7), Pose(0, 10.31),
                Pose(0, 10.309), Pose(0, 10.309),
                Pose(0, 10.309, -170), Pose(0, 10.309, -179),
                Pose(0, 10.309, 180), Pose(0, 10.309, 180),
                Pose(0, 10.20, 180), Pose(0, 10.20, 180)),
            input, () => null, NoDelay);

        Assert.Equal("arrived", result.Status);
        Assert.Equal(2, input.Events.Count(x => x == "down:w"));
        Assert.Equal(2, input.Events.Count(x => x == "up:w"));
        Assert.True(input.Events.IndexOf("up:w") < input.Events.IndexOf("down:d"));
        Assert.True(input.Events.LastIndexOf("up:d") < input.Events.LastIndexOf("down:w"));
        Assert.True(result.ReleaseSucceeded);
    }

    [Fact]
    public async Task FinishAlignmentRemainsBoundedAndNeverMovesForwardUnverified()
    {
        var input = new Input();
        var poses = new List<FollowRouteCommand.Pose>
        {
            Pose(0, 0), Pose(0, 9.7), Pose(0, 10.31),
            Pose(0, 10.31), Pose(0, 10.31)
        };
        poses.AddRange(Enumerable.Repeat(Pose(0, 10.31), 8));
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(poses.ToArray()), input, () => null, NoDelay);

        Assert.Equal("halted", result.Status);
        Assert.Equal("post-release-finish-alignment-not-settled", result.Reason);
        Assert.Equal(1, input.Events.Count(x => x == "down:w"));
        Assert.Equal(1, input.Events.Count(x => x == "up:w"));
        Assert.True(result.ReleaseSucceeded);
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
        var poses = new List<FollowRouteCommand.Pose>
        {
            Pose(0, 0), Pose(0, 9.5), Pose(0, 10.5),
            Pose(0, 10.5), Pose(0, 10.5)
        };
        poses.AddRange(Enumerable.Repeat(Pose(0, 10.5), 8));
        var result = await FollowRouteCommand.FollowAsync(Options(),
            Reader(poses.ToArray()),
            input, () => null, NoDelay);
        Assert.Equal("halted", result.Status);
        Assert.Equal("post-release-finish-alignment-not-settled", result.Reason);
        Assert.Equal(1, input.Events.Count(x => x == "down:w"));
        Assert.DoesNotContain("down:a", input.Events);
        Assert.True(input.Events.IndexOf("up:w") < input.Events.IndexOf("down:d"));
    }

    [Fact]
    public async Task LongStraightLegRejectsShallowSettledMissBeforeForwardStarts()
    {
        var input = new Input();
        // The physical 12.79u leg's 1.61-degree residual projected a .36u miss.
        // One stationary nudge brings the heading within the arrival budget.
        var result = await FollowRouteCommand.FollowAsync(Options(z: 12.79),
            Reader(Pose(0, 0, 1.61), Pose(0, 0, .5), Pose(0, 0, .5),
                Pose(.05, 6, .5), Pose(.11, 12.65, .5),
                Pose(.11, 12.65, .5), Pose(.11, 12.65, .5)),
            input, () => null, NoDelay);
        Assert.Equal("arrived", result.Status);
        Assert.Equal(new[] { "down:d", "up:d", "down:w", "up:w" }, input.Events);
        Assert.True(result.ReleaseSucceeded);
    }

    [Fact]
    public async Task ShallowLongLegNearMissBrakesAndCompletesStationarySideTurn()
    {
        var input = new Input();
        var delays = new List<TimeSpan>();
        // Rotate actual 24.56u leg into route coordinates. At <1 degree
        // residual the path passes beside the .30u disk at about .40u.
        var result = await FollowRouteCommand.FollowAsync(Options(z:24.56),
            Reader(Pose(0,0,.924), Pose(.36,22.40,.924), Pose(.386,24.10,.924),
                Pose(.394,24.30,.924), Pose(.396,24.48,.924),
                Pose(.398,24.53,.924), Pose(.398,24.53,.924),
                Pose(.398,24.53,-30), Pose(.398,24.53,-61),
                Pose(.398,24.53,-78), Pose(.398,24.53,-85.7), Pose(.398,24.53,-85.7),
                Pose(.18,24.55,-85.7), Pose(.18,24.55,-85.7)), input, () => null,
            (duration, token) => { delays.Add(duration); return Task.CompletedTask; });
        Assert.Equal("arrived", result.Status);
        Assert.Equal(2, input.Events.Count(e => e == "down:w"));
        Assert.True(input.Events.IndexOf("down:d") > input.Events.IndexOf("up:w"));
        Assert.DoesNotContain("down:a",input.Events);
        Assert.Contains(TimeSpan.FromMilliseconds(180), delays);
        Assert.True(result.FinalDistance <= FollowRouteCommand.ArrivalRadius && result.ReleaseSucceeded);
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

    [Theory]
    [InlineData(1)]
    [InlineData(-1)]
    public async Task ExpectedHeightAllowsContinuousMeasuredGradeInEitherDirection(int sign)
    {
        var input = new Input();
        const double length = 10.77;
        const double startY = 873.267;
        var poses = Enumerable.Range(0, 22).Select(i =>
            Pose(0, i * .5, y: startY + sign * i * .5 * .355)).ToList();
        poses.AddRange(Enumerable.Repeat(poses[^1], 2));
        var result = await FollowRouteCommand.FollowAsync(Options(z: length) with
            { GoalY = startY + sign * length * .355 }, Reader(poses.ToArray()), input, () => null, NoDelay);
        Assert.Equal("arrived", result.Status);
        Assert.Equal(new[] { "down:w", "up:w" }, input.Events);
        Assert.True(result.ReleaseSucceeded);
    }

    [Theory]
    [InlineData(true, false, "arrived")]
    [InlineData(false, false, "arrived")]
    [InlineData(false, true, "halted")]
    public async Task MeasuredDownhillBrakeSettlesCoastOrMakesOneBoundedFinish(
        bool coasts, bool finishStalled, string expectedStatus)
    {
        var input = new Input();
        double[] travel = [0, .45, .90, 1.35, 1.95];
        // The 11.3-unit physical leg coasted ~1.50 units between W-up
        // and the independent stationary verification, ~.95 by +150 ms.
        var postRelease = new List<double>();
        if (coasts) postRelease.AddRange([2.41, 2.90, 3.30, 3.44, 3.44]);
        else
        {
            postRelease.AddRange([1.95, 1.95, 1.95]); // settled + stationary bearing
            if (finishStalled) postRelease.AddRange(Enumerable.Repeat(1.95, 18));
            else postRelease.AddRange([2.10, 2.25, 2.40, 2.55, 2.70, 2.85, 3.00, 3.15,
                3.31, 3.33, 3.33]);
        }
        var start = DateTimeOffset.UtcNow.AddMilliseconds(-650);
        var index = 0;
        Task<FollowRouteCommand.Pose> Read(CancellationToken _)
        {
            var beforeRelease = index < travel.Length;
            var post = index - travel.Length;
            var z = beforeRelease ? travel[index] : postRelease[post];
            if (post == 0) Assert.Equal(new[] { "down:w", "up:w" }, input.Events);
            var at = start.AddMilliseconds(beforeRelease ? z * 1000 / 6 : 335 + (post + 1) * 10);
            index++;
            return Task.FromResult(Pose(0, z, y: 7 - z * .29) with
                { StartedAtUtc = at, CompletedAtUtc = at });
        }
        var result = await FollowRouteCommand.FollowAsync(Options(z: 3.5) with { GoalY = 7 - 3.5 * .29 },
            Read, input, () => null, NoDelay);
        Assert.Equal(expectedStatus, result.Status);
        Assert.True(result.ReleaseSucceeded);
        Assert.Equal(coasts ? new[] { "down:w", "up:w" } : ["down:w", "up:w", "down:w", "up:w"],
            input.Events);
        if (expectedStatus == "arrived") Assert.InRange(result.FinalDistance, 0, .30);
        else Assert.Equal("post-release-arrival-not-settled", result.Reason);
    }

    [Theory]
    [InlineData(.473, true, "arrived")]
    [InlineData(.473, false, "halted")]
    [InlineData(.51, false, "halted")]
    public async Task DownhillFinishCrossingAllowsOneStationaryUphillReturn(
        double overshoot, bool returnMoves, string expectedStatus)
    {
        var input = new Input();
        const double goal = 3.78;
        var stopZ = goal + overshoot;
        var samples = new List<(double Z, double Bearing, int Ms)>();
        void Sample(double z, double bearing = 0) =>
            samples.Add((z, bearing, samples.Count == 0 ? 0 : samples[^1].Ms + 10));
        foreach (var z in new[] { 0.0, .45, .90, 1.35, 1.80, 2.19 })
            samples.Add((z, 0, (int)(z / 6 * 1000)));
        foreach (var z in new[] { 2.50, 2.50, 2.50, 2.68, 2.86, 3.04, 3.22, 3.42,
            goal + .18, stopZ, stopZ }) Sample(z);
        if (overshoot <= .50)
        {
            foreach (var bearing in new[] { -30, -60, -90, -120, -150, -170, -176, -179, -179 })
                Sample(stopZ, bearing);
            Sample(returnMoves ? goal + .14 : stopZ, -179);
            Sample(returnMoves ? goal + .14 : stopZ, -179);
        }
        var at = DateTimeOffset.UtcNow.AddMilliseconds(-705);
        var index = 0;
        Task<FollowRouteCommand.Pose> Read(CancellationToken _)
        {
            var (z, bearing, ms) = samples[index++];
            return Task.FromResult(Pose(0, z, bearing, y: 7 - z * .30) with
                { StartedAtUtc = at.AddMilliseconds(ms), CompletedAtUtc = at.AddMilliseconds(ms) });
        }
        var result = await FollowRouteCommand.FollowAsync(Options(z: goal) with { GoalY = 7 - goal * .30 },
            Read, input, () => null, NoDelay);
        Assert.Equal(expectedStatus, result.Status);
        if (expectedStatus == "halted") Assert.Equal("post-release-arrival-not-settled", result.Reason);
        var expectedHolds = overshoot <= .50 ? 3 : 2;
        Assert.Equal(expectedHolds, input.Events.Count(e => e == "down:w"));
        Assert.Equal(expectedHolds, input.Events.Count(e => e == "up:w"));
        var holdingW = false;
        foreach (var e in input.Events)
        {
            if (e == "down:w") holdingW = true;
            else if (e == "up:w") holdingW = false;
            else Assert.False(holdingW);
        }
        Assert.True(result.ReleaseSucceeded);
    }

    [Theory]
    [InlineData(20, 21)]
    [InlineData(200, 51)]
    public async Task ExpectedHeightRejectsExcessiveGradeOrDeltaBeforeInput(double z, double rise)
    {
        var input = new Input();
        var result = await FollowRouteCommand.FollowAsync(Options(z: z) with { GoalY = 7 + rise },
            Reader(Pose(0,0)), input, () => null, NoDelay);
        Assert.Equal("blocked",result.Status);
        Assert.Contains("height bound",result.Reason);
        Assert.Empty(input.Events);
    }

    [Fact]
    public async Task ExpectedHeightStillHaltsAbruptFallWithinInterpolatedEnvelope()
    {
        var input = new Input();
        var result = await FollowRouteCommand.FollowAsync(Options(z:10) with { GoalY=9 },
            Reader(Pose(0,0),Pose(0,.2,y:6.1)),input,() => null,NoDelay);
        Assert.Equal("halted",result.Status);
        Assert.Contains("Abrupt vertical step",result.Reason);
        Assert.True(result.ReleaseSucceeded);
    }

    [Fact]
    public async Task ExpectedHeightRejectsWrongGradualFloorAndOffHeightSettledArrival()
    {
        var floor = await FollowRouteCommand.FollowAsync(Options(z:10) with { GoalY=10 },
            Reader(Pose(0,0),Pose(0,2),Pose(0,4),Pose(0,6)),new Input(),() => null,NoDelay);
        Assert.Contains("Vertical drift",floor.Reason);
        var finish = await FollowRouteCommand.FollowAsync(Options(z:5) with { GoalY=8 },
            Reader(Pose(0,0),Pose(0,2),Pose(0,4.9),Pose(0,4.9),Pose(0,4.9)),
            new Input(),() => null,NoDelay);
        Assert.Equal("halted",finish.Status);
        Assert.Equal("post-release-arrival-not-settled",finish.Reason);
        Assert.True(finish.ReleaseSucceeded);
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
