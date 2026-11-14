using System.Diagnostics;
using System.Globalization;
using RiftReader2.Application;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live.Control;

internal static class FollowRouteCommand
{
    internal const int PoseTimeoutMilliseconds = 800;
    internal const int WatchdogPollMilliseconds = 25;
    internal const double ArrivalRadius = .30;
    internal const double MaximumDistance = 1000;
    internal const int SteeringPulseMilliseconds = 20;
    internal const int SteeringSettleMilliseconds = 600;
    internal const double SteeringDeadbandDegrees = 8;
    internal const double NearGoalStraightDistance = 1.5;

    internal sealed record Options(
        string ExpectedHost, int Pid, long ExpectedStartTicks, string ExpectedSha256,
        long ExpectedHwnd, ulong ExpectedPlayerKey, int OwnerPid, long OwnerStartTicks,
        double X, double Z, string StopFile, int MaxSeconds, bool Execute, bool Json,
        double? ExpectedX = null, double? ExpectedZ = null, double? ExpectedBearing = null,
        bool SurvivalInterrupt = false, bool SurvivalRetreat = false);

    internal sealed record SurvivalSnapshot(string Status, long? HealthCurrent,
        long? HealthMaximum, bool? CombatCandidate, byte? RawCombat,
        DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc, string? Reason = null)
    {
        public string Qualification =>
            "candidate-only native self health/combat guard; changed-state and restart qualification remain limited";
    }

    internal sealed record Pose(double X, double Y, double Z, double Bearing, ulong PlayerKey,
        ulong PlayerEntity, ulong PlayerSystem, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc,
        double? OpticalCameraBearingDegreesCandidate = null,
        double? OpticalCameraPitchDegreesCandidate = null,
        string? OpticalCameraStatus = null,
        SurvivalSnapshot? Survival = null);
    internal sealed record PathPoint(double X, double Y, double Z, double Bearing,
        double Distance, DateTimeOffset ObservedAtUtc,
        double? OpticalCameraBearingDegreesCandidate = null,
        double? OpticalCameraPitchDegreesCandidate = null,
        string? OpticalCameraStatus = null);
    internal sealed record Result(string Status, string? Reason, Pose? FinalPose,
        double InitialDistance, double FinalDistance, int ReadCount, PathPoint[] Path,
        double ElapsedMilliseconds, bool InputSent, bool ReleaseSucceeded,
        SurvivalSnapshot? SurvivalSnapshot = null);
    internal sealed record ReceiptPosition(double X, double Y, double Z);
    internal sealed record ResultReceiptProjection(
        ReceiptPosition? Position,
        double? BodyBearingDegreesCandidate,
        double? OpticalCameraBearingDegreesCandidate,
        double? OpticalCameraPitchDegreesCandidate,
        string? OpticalCameraStatus,
        double? InitialDistance,
        double? FinalDistance,
        int ReadCount,
        PathPoint[] Path,
        double ElapsedMilliseconds,
        bool InputSent,
        bool ReleaseSucceeded,
        SurvivalSnapshot? SurvivalSnapshot);

    internal interface IInput
    {
        bool IsTargetCurrent();
        IReadOnlyList<string> ReadPressedInputs();
        void KeyDown(string key);
        void KeyUp(string key);
    }

    internal static Options Parse(string[] args)
    {
        var values = new Dictionary<string, string>(StringComparer.Ordinal);
        var flags = new HashSet<string>(StringComparer.Ordinal);
        for (var i = 0; i < args.Length; i++)
        {
            var option = args[i];
            if (option is "--execute" or "--json" or "--survival-interrupt" or "--survival-retreat")
            {
                if (!flags.Add(option)) throw new InvalidDataException("Repeated option: " + option);
                continue;
            }
            if (!option.StartsWith("--", StringComparison.Ordinal) || i + 1 >= args.Length)
                throw new InvalidDataException("Missing value for " + option + ".");
            if (!values.TryAdd(option, args[++i]))
                throw new InvalidDataException("Repeated option: " + option);
        }
        var allowed = new HashSet<string>(StringComparer.Ordinal)
        {
            "--expected-host", "--pid", "--expect-start-ticks", "--expect-sha256",
            "--expect-hwnd", "--expect-player-key", "--owner-pid", "--owner-start-ticks",
            "--x", "--z", "--stop-file", "--max-seconds",
            "--expect-x", "--expect-z", "--expect-bearing"
        };
        var unknown = values.Keys.FirstOrDefault(key => !allowed.Contains(key));
        if (unknown is not null) throw new InvalidDataException("Unknown option: " + unknown);
        string Required(string name) => values.TryGetValue(name, out var value) && !string.IsNullOrWhiteSpace(value)
            ? value : throw new InvalidDataException("Required option missing: " + name);
        static int PositiveInt(string raw, string name) =>
            int.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out var value) && value > 0
                ? value : throw new InvalidDataException(name + " must be a positive integer.");
        static long PositiveTicks(string raw, string name) =>
            long.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out var value)
            && value > 0 && value <= DateTime.MaxValue.Ticks
                ? value : throw new InvalidDataException(name + " must be positive UTC ticks.");
        static double Finite(string raw, string name) =>
            double.TryParse(raw, NumberStyles.Float, CultureInfo.InvariantCulture, out var value)
            && double.IsFinite(value)
                ? value : throw new InvalidDataException(name + " must be finite.");
        var sha = Required("--expect-sha256");
        if (sha.Length != 64 || !sha.All(Uri.IsHexDigit))
            throw new InvalidDataException("--expect-sha256 must contain 64 hex digits.");
        if (!ulong.TryParse(Required("--expect-player-key"), NumberStyles.None,
            CultureInfo.InvariantCulture, out var player) || player == 0)
            throw new InvalidDataException("--expect-player-key must be a positive decimal key.");
        var stopRaw = Required("--stop-file");
        if (!Path.IsPathFullyQualified(stopRaw))
            throw new InvalidDataException("--stop-file must be absolute.");
        var maximum = values.TryGetValue("--max-seconds", out var rawMaximum)
            ? PositiveInt(rawMaximum, "--max-seconds") : 1800;
        if (maximum > 1800) throw new InvalidDataException("--max-seconds must be in 1..1800.");
        var originCount = new[] { "--expect-x", "--expect-z", "--expect-bearing" }.Count(values.ContainsKey);
        if (originCount is not (0 or 3))
            throw new InvalidDataException("--expect-x, --expect-z and --expect-bearing are all-or-none.");
        var survivalInterrupt = flags.Contains("--survival-interrupt");
        var survivalRetreat = flags.Contains("--survival-retreat");
        if (survivalRetreat && !survivalInterrupt)
            throw new InvalidDataException("--survival-retreat requires --survival-interrupt.");
        return new(Required("--expected-host"), PositiveInt(Required("--pid"), "--pid"),
            PositiveTicks(Required("--expect-start-ticks"), "--expect-start-ticks"),
            sha.ToUpperInvariant(), MoveKeyCommand.ParseWindowHandle(Required("--expect-hwnd")),
            player, PositiveInt(Required("--owner-pid"), "--owner-pid"),
            PositiveTicks(Required("--owner-start-ticks"), "--owner-start-ticks"),
            Finite(Required("--x"), "--x"), Finite(Required("--z"), "--z"),
            Path.GetFullPath(stopRaw), maximum, flags.Contains("--execute"), flags.Contains("--json"),
            originCount == 0 ? null : Finite(values["--expect-x"], "--expect-x"),
            originCount == 0 ? null : Finite(values["--expect-z"], "--expect-z"),
            originCount == 0 ? null : Finite(values["--expect-bearing"], "--expect-bearing"),
            survivalInterrupt, survivalRetreat);
    }

    internal static string SurvivalMode(Options options) => options.SurvivalRetreat
        ? "retreat" : options.SurvivalInterrupt ? "interrupt" : "disabled";

    internal static ResultReceiptProjection ProjectResult(Result? result)
    {
        static double? Finite(double? value) => value is double number && double.IsFinite(number)
            ? number : null;
        var pose = result?.FinalPose;
        var position = pose is not null && double.IsFinite(pose.X)
            && double.IsFinite(pose.Y) && double.IsFinite(pose.Z)
            ? new ReceiptPosition(pose.X, pose.Y, pose.Z) : null;
        return new(position, Finite(pose?.Bearing),
            Finite(pose?.OpticalCameraBearingDegreesCandidate),
            Finite(pose?.OpticalCameraPitchDegreesCandidate), pose?.OpticalCameraStatus,
            Finite(result?.InitialDistance), Finite(result?.FinalDistance),
            result?.ReadCount ?? 0, result?.Path ?? [],
            Finite(result?.ElapsedMilliseconds) ?? 0,
            result?.InputSent ?? false, result?.ReleaseSucceeded ?? true,
            result?.SurvivalSnapshot);
    }

    internal static void ValidateExpectedOrigin(Options options, Pose pose)
    {
        if (options.ExpectedX is not double x) return;
        if (Math.Sqrt(Math.Pow(pose.X - x, 2) + Math.Pow(pose.Z - options.ExpectedZ!.Value, 2)) > .05
            || Math.Abs(HeadingError(pose.Bearing, options.ExpectedBearing!.Value)) > .5)
            throw new InvalidOperationException("Current native pose differs from the rendered map origin.");
    }

    internal static double Distance(Pose pose, double x, double z) =>
        Math.Sqrt(Math.Pow(x - pose.X, 2) + Math.Pow(z - pose.Z, 2));
    internal static double BearingTo(Pose pose, double x, double z) =>
        Math.Atan2(x - pose.X, z - pose.Z) * 180 / Math.PI;
    internal static double HeadingError(double target, double current) =>
        ((target - current + 180) % 360 + 360) % 360 - 180;
    internal static double CrossTrack(Pose pose, Pose start, double goalX, double goalZ)
    {
        var dx = goalX - start.X;
        var dz = goalZ - start.Z;
        var lengthSquared = dx * dx + dz * dz;
        if (lengthSquared == 0) return Distance(pose, start.X, start.Z);
        var fraction = Math.Max(0, Math.Min(1,
            ((pose.X - start.X) * dx + (pose.Z - start.Z) * dz) / lengthSquared));
        var x = start.X + fraction * dx;
        var z = start.Z + fraction * dz;
        return Math.Sqrt(Math.Pow(pose.X - x, 2) + Math.Pow(pose.Z - z, 2));
    }
    internal static double SegmentDistanceToGoal(Pose before, Pose after, double goalX, double goalZ)
    {
        var dx = after.X - before.X;
        var dz = after.Z - before.Z;
        var lengthSquared = dx * dx + dz * dz;
        if (lengthSquared == 0) return Distance(after, goalX, goalZ);
        var fraction = Math.Max(0, Math.Min(1,
            ((goalX - before.X) * dx + (goalZ - before.Z) * dz) / lengthSquared));
        var x = before.X + fraction * dx;
        var z = before.Z + fraction * dz;
        return Math.Sqrt(Math.Pow(goalX - x, 2) + Math.Pow(goalZ - z, 2));
    }
    internal static double CorridorBearing(Pose pose, Pose start, double goalX, double goalZ,
        double lookahead = 3)
    {
        var dx = goalX - start.X;
        var dz = goalZ - start.Z;
        var length = Math.Sqrt(dx * dx + dz * dz);
        if (length == 0) return pose.Bearing;
        var fraction = Math.Max(0, Math.Min(1,
            ((pose.X - start.X) * dx + (pose.Z - start.Z) * dz) / (length * length)));
        var ahead = Math.Min(length, fraction * length + lookahead);
        var x = start.X + dx * ahead / length;
        var z = start.Z + dz * ahead / length;
        return BearingTo(pose, x, z);
    }
    private static bool FinitePose(Pose pose) =>
        double.IsFinite(pose.X) && double.IsFinite(pose.Y) && double.IsFinite(pose.Z)
        && double.IsFinite(pose.Bearing) && pose.PlayerKey != 0
        && pose.PlayerEntity != 0 && pose.PlayerSystem != 0
        && (pose.OpticalCameraBearingDegreesCandidate is not double cameraBearing
            || double.IsFinite(cameraBearing))
        && (pose.OpticalCameraPitchDegreesCandidate is not double cameraPitch
            || double.IsFinite(cameraPitch));

    internal static async Task<Result> FollowAsync(
        Options options, Func<CancellationToken, Task<Pose>> readPose, IInput input,
        Func<string?> safetyReason, Func<TimeSpan, CancellationToken, Task>? delay = null,
        CancellationToken token = default)
    {
        delay ??= Task.Delay;
        var clock = Stopwatch.StartNew();
        var down = new HashSet<string>(StringComparer.Ordinal);
        var gate = new object();
        var path = new List<PathPoint>();
        var reads = 0;
        var inputSent = false;
        var releaseSucceeded = true;
        string? terminalReason = null;
        ulong? poseEntity = null;
        ulong? poseSystem = null;
        DateTimeOffset? previousPoseCompleted = null;
        var lastPoseTick = Stopwatch.GetTimestamp();
        var initialDistance = double.NaN;
        var finalDistance = double.NaN;
        Pose? finalPose = null;
        long? survivalBaselineHealth = null;
        SurvivalSnapshot? survivalSnapshot = null;
        using var operationCancellation = CancellationTokenSource.CreateLinkedTokenSource(token);
        var operationToken = operationCancellation.Token;

        void CancelOperation()
        {
            try { operationCancellation.Cancel(); }
            catch (Exception error)
            {
                Interlocked.CompareExchange(ref terminalReason,
                    "cancellation-fault: " + error.GetType().Name, null);
            }
        }

        void ReleaseKeyLocked(string key)
        {
            if (!down.Contains(key)) return;
            for (var attempt = 0; attempt < 2; attempt++)
            {
                try
                {
                    input.KeyUp(key);
                    down.Remove(key);
                    return;
                }
                catch
                {
                    releaseSucceeded = false;
                    Interlocked.CompareExchange(ref terminalReason, "key-release-failed", null);
                }
            }
            down.Remove(key);
            CancelOperation();
        }
        void SetKey(string key, bool pressed)
        {
            lock (gate)
            {
                if (pressed)
                {
                    string? immediateReason;
                    try
                    {
                        immediateReason = safetyReason();
                        if (immediateReason is null && !input.IsTargetCurrent())
                            immediateReason = "target-window-lost";
                        if (immediateReason is null)
                        {
                            var external = input.ReadPressedInputs()
                                .Where(heldKey => !down.Contains(heldKey))
                                .ToArray();
                            if (external.Length != 0)
                                immediateReason = "external-input-held: " + string.Join(", ", external);
                        }
                    }
                    catch (Exception error)
                    {
                        immediateReason = "safety-check-failed: " + error.GetType().Name;
                    }
                    if (immediateReason is not null)
                    {
                        Interlocked.CompareExchange(ref terminalReason, immediateReason, null);
                        CancelOperation();
                    }
                    if (Volatile.Read(ref terminalReason) is not null || operationToken.IsCancellationRequested)
                        throw new OperationCanceledException(operationToken);
                    if (!down.Add(key)) return;
                    inputSent = true;
                    input.KeyDown(key);
                }
                else
                    ReleaseKeyLocked(key);
            }
        }
        void ReleaseAll()
        {
            lock (gate)
            {
                foreach (var key in down.ToArray())
                    ReleaseKeyLocked(key);
            }
        }
        bool HasDown()
        {
            lock (gate) return down.Count != 0;
        }
        string? ExternalInputReason()
        {
            lock (gate)
            {
                var external = input.ReadPressedInputs()
                    .Where(key => !down.Contains(key))
                    .ToArray();
                return external.Length == 0 ? null
                    : "external-input-held: " + string.Join(", ", external);
            }
        }
        string? SurvivalReason(SurvivalSnapshot snapshot)
        {
            survivalSnapshot = snapshot;
            if (snapshot.Status != "available-candidate"
                || snapshot.HealthCurrent is not long current
                || snapshot.HealthMaximum is not long maximum
                || snapshot.CombatCandidate is not bool combat
                || current < 0 || maximum <= 0 || current > maximum)
                return "survival-unavailable";
            if (current == 0)
                return "survival-dead";
            if (survivalBaselineHealth is null)
            {
                survivalBaselineHealth = current;
            }
            // The caller may authorize this only for an owned reverse-known-trail
            // retreat. Combat and ordinary damage are expected while disengaging;
            // unavailable survival data and death remain terminal above.
            if (options.SurvivalRetreat)
                return null;
            if (combat)
                return "survival-combat";
            return current < survivalBaselineHealth ? "survival-hp-drop" : null;
        }
        async Task<Pose> Read()
        {
            var pose = await readPose(operationToken);
            var now = DateTimeOffset.UtcNow;
            if (pose.PlayerKey != options.ExpectedPlayerKey || !FinitePose(pose)
                || pose.CompletedAtUtc < pose.StartedAtUtc
                || pose.CompletedAtUtc - pose.StartedAtUtc > TimeSpan.FromMilliseconds(PoseTimeoutMilliseconds)
                || now - pose.CompletedAtUtc > TimeSpan.FromMilliseconds(PoseTimeoutMilliseconds)
                || pose.CompletedAtUtc - now > TimeSpan.FromMilliseconds(100))
                throw new InvalidDataException("Native pose is stale, invalid or belongs to another player.");
            poseEntity ??= pose.PlayerEntity;
            poseSystem ??= pose.PlayerSystem;
            if (pose.PlayerEntity != poseEntity || pose.PlayerSystem != poseSystem
                || previousPoseCompleted is DateTimeOffset prior && pose.StartedAtUtc < prior)
                throw new InvalidDataException("Native pose owner or sample order changed.");
            previousPoseCompleted = pose.CompletedAtUtc;
            Volatile.Write(ref lastPoseTick, Stopwatch.GetTimestamp());
            reads++;
            finalPose = pose;
            finalDistance = Distance(pose, options.X, options.Z);
            // The first accepted pose is also the admission metric. Establish it
            // before a survival refusal so halted receipts retain finite position,
            // distance and path evidence instead of NaN/Infinity placeholders.
            if (!double.IsFinite(initialDistance))
                initialDistance = finalDistance;
            var point = new PathPoint(pose.X, pose.Y, pose.Z, pose.Bearing,
                finalDistance, pose.CompletedAtUtc,
                pose.OpticalCameraBearingDegreesCandidate,
                pose.OpticalCameraPitchDegreesCandidate,
                pose.OpticalCameraStatus);
            if (path.Count < 500)
                path.Add(point);
            else
            {
                // Preserve admission plus the most recent 499 observations.
                // Short live runs therefore retain every control-law sample.
                path.RemoveAt(1);
                path.Add(point);
            }
            var survivalReason = options.SurvivalInterrupt && pose.Survival is { } survival
                ? SurvivalReason(survival)
                : options.SurvivalInterrupt && survivalBaselineHealth is null
                    ? "survival-unavailable" : null;
            if (survivalReason is not null)
            {
                Interlocked.CompareExchange(ref terminalReason, survivalReason, null);
                ReleaseAll();
                CancelOperation();
                throw new OperationCanceledException(operationToken);
            }
            return pose;
        }

        using var watchdogCancellation = new CancellationTokenSource();
        var watchdog = Task.Run(async () =>
        {
            while (!watchdogCancellation.IsCancellationRequested)
            {
                string? reason;
                try
                {
                    reason = token.IsCancellationRequested ? "cancelled" : safetyReason();
                    if (reason is null && !input.IsTargetCurrent()) reason = "target-window-lost";
                    if (reason is null && HasDown()) reason = ExternalInputReason();
                    if (reason is null && clock.Elapsed >= TimeSpan.FromSeconds(options.MaxSeconds)) reason = "time-limit";
                    if (reason is null && HasDown()
                        && Stopwatch.GetElapsedTime(Volatile.Read(ref lastPoseTick)).TotalMilliseconds > PoseTimeoutMilliseconds)
                        reason = "pose-stale";
                }
                catch (Exception error)
                {
                    reason = "watchdog-fault: " + error.GetType().Name;
                }
                if (reason is not null)
                {
                    Interlocked.CompareExchange(ref terminalReason, reason, null);
                    ReleaseAll();
                    CancelOperation();
                    return;
                }
                await Task.Delay(WatchdogPollMilliseconds, CancellationToken.None);
            }
        }, CancellationToken.None);

        string status;
        try
        {
            var pose = await Read();
            ValidateExpectedOrigin(options, pose);
            initialDistance = finalDistance;
            if (initialDistance > MaximumDistance)
                throw new InvalidDataException("Destination exceeds 1000 world units.");
            if (initialDistance <= ArrivalRadius)
                status = "arrived";
            else
            {
                // Align first. Once forward starts, W remains continuously held
                // until arrival or a releasing terminal condition.
                var alignmentAnchor = pose;
                // Budget 90% of the arrival radius for initial lateral error. Keep a
                // one-degree floor for finite turn pulses; long legs still use corridor feedback.
                var alignmentTolerance = Math.Clamp(
                    Math.Atan2(ArrivalRadius * .90, finalDistance) * 180 / Math.PI, 1, 2);
                var alignmentStarted = clock.Elapsed;
                var unresponsiveTurns = 0;
                var residualNudges = 0;
                // Retained physical evidence is approximately 175 degrees/s.
                // Live samples refine this seed before the release decision.
                var observedTurnRate = 175.0;
                string? alignmentKey = null;
                var alignmentRequiresSettlement = false;
                void GuardAlignmentPose(Pose candidate)
                {
                    if (Math.Sqrt(Math.Pow(candidate.X - alignmentAnchor.X, 2)
                            + Math.Pow(candidate.Z - alignmentAnchor.Z, 2)) > .10
                        || Math.Abs(candidate.Y - alignmentAnchor.Y) > .10)
                        throw new InvalidOperationException("Position drifted during initial turn.");
                    if (clock.Elapsed - alignmentStarted > TimeSpan.FromSeconds(20))
                        throw new InvalidOperationException("Initial turn exceeded 20 seconds.");
                }
                async Task<bool> ObserveSettledAlignment()
                {
                    var previous = pose;
                    // A stable pair, not a single permissive sample, proves that
                    // key-up coast ended before forward movement begins.
                    for (var attempt = 0; attempt < 4; attempt++)
                    {
                        await delay(TimeSpan.FromMilliseconds(50), operationToken);
                        pose = await Read();
                        GuardAlignmentPose(pose);
                        var bearingMotion = Math.Abs(HeadingError(pose.Bearing, previous.Bearing));
                        var remaining = Math.Abs(HeadingError(
                            BearingTo(pose, options.X, options.Z), pose.Bearing));
                        if (bearingMotion <= .75 && remaining <= alignmentTolerance)
                            return true;
                        previous = pose;
                    }
                    return false;
                }
                while (Volatile.Read(ref terminalReason) is null)
                {
                    var error = HeadingError(BearingTo(pose, options.X, options.Z), pose.Bearing);
                    if (alignmentKey is null && Math.Abs(error) <= alignmentTolerance)
                    {
                        if (!alignmentRequiresSettlement || await ObserveSettledAlignment())
                            break;
                        continue;
                    }
                    if (alignmentKey is not null)
                    {
                        var coastAllowance = Math.Clamp(observedTurnRate * .060 + 2, 5, 14);
                        var crossedTarget = alignmentKey == "a" ? error <= 0 : error >= 0;
                        if (Math.Abs(error) <= coastAllowance || crossedTarget)
                        {
                            SetKey("a", false);
                            SetKey("d", false);
                            alignmentKey = null;
                            if (await ObserveSettledAlignment()) break;
                            continue;
                        }
                    }
                    if (clock.Elapsed - alignmentStarted > TimeSpan.FromSeconds(20))
                        throw new InvalidOperationException("Initial turn exceeded 20 seconds.");
                    var turn = error > 0 ? "a" : "d";
                    if (alignmentKey is null && Math.Abs(error) <= 12)
                    {
                        if (++residualNudges > 6)
                            throw new InvalidOperationException("Initial alignment did not settle after bounded nudges.");
                        var nudgeMilliseconds = Math.Clamp(
                            Math.Abs(error) / Math.Max(100, observedTurnRate) * 600, 6, 16);
                        alignmentRequiresSettlement = true;
                        SetKey(turn, true);
                        await delay(TimeSpan.FromMilliseconds(nudgeMilliseconds), operationToken);
                        SetKey(turn, false);
                        if (await ObserveSettledAlignment()) break;
                        continue;
                    }
                    var previousBearing = pose.Bearing;
                    var previousCompletedAt = pose.CompletedAtUtc;
                    var previousError = Math.Abs(error);
                    alignmentRequiresSettlement = true;
                    SetKey(turn, true);
                    SetKey(turn == "a" ? "d" : "a", false);
                    alignmentKey = turn;
                    await delay(TimeSpan.FromMilliseconds(Math.Abs(error) <= 30 ? 25 : 50), operationToken);
                    if (Volatile.Read(ref terminalReason) is not null) break;
                    pose = await Read();
                    GuardAlignmentPose(pose);
                    var delta = HeadingError(pose.Bearing, previousBearing);
                    var turnSeconds = (pose.CompletedAtUtc - previousCompletedAt).TotalSeconds;
                    if (turnSeconds is > .005 and < .5)
                    {
                        var rate = Math.Abs(delta) / turnSeconds;
                        if (rate is >= 20 and <= 400)
                            observedTurnRate = observedTurnRate * .65 + rate * .35;
                    }
                    var nextError = Math.Abs(HeadingError(BearingTo(pose, options.X, options.Z), pose.Bearing));
                    if (Math.Abs(delta) < .05 || Math.Abs(delta) > 45
                        || turn == "a" && delta <= 0 || turn == "d" && delta >= 0
                        || nextError >= previousError - .05)
                    {
                        if (++unresponsiveTurns >= 3)
                            throw new InvalidOperationException("Initial turn response was unavailable or divergent.");
                    }
                    else
                        unresponsiveTurns = 0;
                }
                SetKey("a", false);
                SetKey("d", false);
                if (Volatile.Read(ref terminalReason) is null) SetKey("w", true);
                var travelStart = pose;
                var best = finalDistance;
                var lastProgress = clock.Elapsed;
                var divergence = 0;
                var nextSteeringAt = clock.Elapsed;
                var nextOppositeSteeringAt = clock.Elapsed;
                string? lastSteeringKey = null;
                Pose? lastSteeringPose = null;
                var observedSpeed = 0.0;
                var arrivalObserved = finalDistance <= ArrivalRadius;
                while (Volatile.Read(ref terminalReason) is null && !arrivalObserved)
                {
                    var previousTravelPose = pose;
                    await delay(TimeSpan.FromMilliseconds(
                        finalDistance <= 2 ? 25 : 75), operationToken);
                    if (Volatile.Read(ref terminalReason) is not null) break;
                    pose = await Read();
                    var sampleSeconds = (pose.CompletedAtUtc - previousTravelPose.CompletedAtUtc).TotalSeconds;
                    if (sampleSeconds is > .005 and < 1)
                    {
                        var sampleDistance = Distance(pose, previousTravelPose.X, previousTravelPose.Z);
                        var sampleSpeed = sampleDistance / sampleSeconds;
                        if (sampleSpeed is > .05 and < 30)
                            observedSpeed = observedSpeed == 0 ? sampleSpeed : observedSpeed * .65 + sampleSpeed * .35;
                    }
                    // Project only a small part of the observed sample interval.
                    // Segment crossing remains the fail-safe for a skipped disk;
                    // this margin must not turn a .75-unit shortfall into arrival.
                    var brakingMargin = observedSpeed == 0 ? 0
                        : Math.Min(.12, observedSpeed * Math.Min(.02, sampleSeconds * .20));
                    var brakingRadius = ArrivalRadius + brakingMargin;
                    arrivalObserved = finalDistance <= brakingRadius
                        || SegmentDistanceToGoal(previousTravelPose, pose, options.X, options.Z) <= ArrivalRadius;
                    if (arrivalObserved)
                    {
                        SetKey("a", false);
                        SetKey("d", false);
                        SetKey("w", false);
                        if (Math.Abs(pose.Y - travelStart.Y) > 1.5)
                            Interlocked.CompareExchange(ref terminalReason,
                                "Vertical drift exceeded the direct-path guard.", null);
                        else if (CrossTrack(pose, travelStart, options.X, options.Z) > .50)
                            Interlocked.CompareExchange(ref terminalReason,
                                "Cross-track drift exceeded the direct-path guard.", null);
                        break;
                    }
                    if (Math.Abs(pose.Y - travelStart.Y) > 1.5)
                        throw new InvalidOperationException("Vertical drift exceeded the direct-path guard.");
                    if (CrossTrack(pose, travelStart, options.X, options.Z) > .50)
                        throw new InvalidOperationException("Cross-track drift exceeded the direct-path guard.");
                    var error = HeadingError(
                        CorridorBearing(pose, travelStart, options.X, options.Z), pose.Bearing);
                    var crossTrack = CrossTrack(pose, travelStart, options.X, options.Z);
                    var displacement = Distance(pose, previousTravelPose.X, previousTravelPose.Z);
                    var projectedCrossTrack = crossTrack;
                    if (displacement >= .10)
                    {
                        var lookahead = Math.Min(1.5, finalDistance);
                        var projected = pose with
                        {
                            X = pose.X + (pose.X - previousTravelPose.X) / displacement * lookahead,
                            Z = pose.Z + (pose.Z - previousTravelPose.Z) / displacement * lookahead
                        };
                        projectedCrossTrack = CrossTrack(projected, travelStart, options.X, options.Z);
                    }
                    var nextSteeringKey = error > 0 ? "a" : "d";
                    var departingCorridor = crossTrack >= .22 && projectedCrossTrack >= .32
                        && projectedCrossTrack >= crossTrack + .05;
                    var needsCorrection = Math.Abs(error) >= SteeringDeadbandDegrees && departingCorridor
                        || Math.Abs(error) >= 5 && crossTrack >= .38;
                    // Keep forward travel quiet: one brief nudge, then allow
                    // key-up and body response to settle before reconsidering.
                    // Small errors and final approach do not chase A/D at all.
                    if (finalDistance > NearGoalStraightDistance
                        && clock.Elapsed >= nextSteeringAt
                        && (lastSteeringPose is null || Distance(pose, lastSteeringPose.X, lastSteeringPose.Z) >= 1.5)
                        && (lastSteeringKey is null || lastSteeringKey == nextSteeringKey || clock.Elapsed >= nextOppositeSteeringAt)
                        && needsCorrection)
                    {
                        SetKey(nextSteeringKey, true);
                        await delay(TimeSpan.FromMilliseconds(SteeringPulseMilliseconds), operationToken);
                        SetKey(nextSteeringKey, false);
                        nextSteeringAt = clock.Elapsed + TimeSpan.FromMilliseconds(SteeringSettleMilliseconds);
                        nextOppositeSteeringAt = clock.Elapsed + TimeSpan.FromSeconds(1);
                        lastSteeringKey = nextSteeringKey;
                        lastSteeringPose = pose;
                    }
                    if (finalDistance + .03 < best)
                    {
                        best = finalDistance;
                        lastProgress = clock.Elapsed;
                        divergence = 0;
                    }
                    else if (finalDistance > best + .50 && ++divergence >= 5)
                        Interlocked.CompareExchange(ref terminalReason, "movement-diverged", null);
                    if (clock.Elapsed - lastProgress > TimeSpan.FromSeconds(8))
                        Interlocked.CompareExchange(ref terminalReason, "no-progress", null);
                }
                if (arrivalObserved && Volatile.Read(ref terminalReason) is null)
                {
                    await delay(TimeSpan.FromMilliseconds(75), operationToken);
                    var settledOne = await Read();
                    await delay(TimeSpan.FromMilliseconds(75), operationToken);
                    var settledTwo = await Read();
                    var settledMotion = Math.Sqrt(Math.Pow(settledTwo.X - settledOne.X, 2)
                        + Math.Pow(settledTwo.Z - settledOne.Z, 2));
                    var settleOneDistance = Distance(settledOne, options.X, options.Z);
                    var settleTwoDistance = Distance(settledTwo, options.X, options.Z);
                    var stationary = settledMotion <= .05 && Math.Abs(settledTwo.Y - settledOne.Y) <= .10;
                    var settledOnDirectPath = Math.Abs(settledOne.Y - travelStart.Y) <= 1.5
                        && Math.Abs(settledTwo.Y - travelStart.Y) <= 1.5
                        && CrossTrack(settledOne, travelStart, options.X, options.Z) <= .50
                        && CrossTrack(settledTwo, travelStart, options.X, options.Z) <= .50;
                    if (stationary && settleOneDistance > ArrivalRadius && settleTwoDistance > ArrivalRadius
                        && settledOnDirectPath
                        && settleTwoDistance <= .75)
                    {
                        // Braking can stop a few centimetres beyond the goal,
                        // leaving the body pointed away from the tiny remaining
                        // vector.  Turn in place and prove the turn has settled
                        // before the one bounded finish-forward pulse.  This is
                        // not moving steering: no W is held during alignment.
                        var finishAnchor = settledTwo;
                        var finishAligned = false;
                        for (var attempt = 0; attempt < 8
                            && Volatile.Read(ref terminalReason) is null; attempt++)
                        {
                            var finishError = HeadingError(
                                BearingTo(settledTwo, options.X, options.Z), settledTwo.Bearing);
                            if (Math.Abs(finishError) <= 2)
                            {
                                await delay(TimeSpan.FromMilliseconds(50), operationToken);
                                var confirmed = await Read();
                                var positionMotion = Distance(confirmed, finishAnchor.X, finishAnchor.Z);
                                var bearingMotion = Math.Abs(HeadingError(confirmed.Bearing, settledTwo.Bearing));
                                var confirmedError = Math.Abs(HeadingError(
                                    BearingTo(confirmed, options.X, options.Z), confirmed.Bearing));
                                var confirmedOnPath = Math.Abs(confirmed.Y - travelStart.Y) <= 1.5
                                    && CrossTrack(confirmed, travelStart, options.X, options.Z) <= .50;
                                settledTwo = confirmed;
                                if (positionMotion <= .10 && bearingMotion <= .75
                                    && confirmedError <= 2 && confirmedOnPath)
                                {
                                    finishAligned = true;
                                    break;
                                }
                                continue;
                            }
                            var finishTurn = finishError > 0 ? "a" : "d";
                            var pulseMilliseconds = Math.Clamp(
                                Math.Abs(finishError) / Math.Max(100, observedTurnRate) * 600, 6, 20);
                            SetKey(finishTurn, true);
                            await delay(TimeSpan.FromMilliseconds(pulseMilliseconds), operationToken);
                            SetKey(finishTurn, false);
                            await delay(TimeSpan.FromMilliseconds(50), operationToken);
                            settledTwo = await Read();
                            if (Distance(settledTwo, finishAnchor.X, finishAnchor.Z) > .10
                                || Math.Abs(settledTwo.Y - travelStart.Y) > 1.5
                                || CrossTrack(settledTwo, travelStart, options.X, options.Z) > .50)
                                break;
                        }
                        SetKey("a", false);
                        SetKey("d", false);
                        if (!finishAligned)
                            Interlocked.CompareExchange(ref terminalReason,
                                "post-release-finish-alignment-not-settled", null);
                        else
                        {
                            settleTwoDistance = Distance(settledTwo, options.X, options.Z);
                            SetKey("w", true);
                            var correctionMilliseconds = observedSpeed > .1
                                ? Math.Clamp((settleTwoDistance - .20) / observedSpeed * 1000, 20, 120)
                                : 50;
                            await delay(TimeSpan.FromMilliseconds(correctionMilliseconds), operationToken);
                            SetKey("w", false);
                            await delay(TimeSpan.FromMilliseconds(75), operationToken);
                            settledOne = await Read();
                            await delay(TimeSpan.FromMilliseconds(75), operationToken);
                            settledTwo = await Read();
                            settledMotion = Distance(settledTwo, settledOne.X, settledOne.Z);
                            settleOneDistance = Distance(settledOne, options.X, options.Z);
                            settleTwoDistance = Distance(settledTwo, options.X, options.Z);
                            stationary = settledMotion <= .05 && Math.Abs(settledTwo.Y - settledOne.Y) <= .10;
                            settledOnDirectPath = Math.Abs(settledOne.Y - travelStart.Y) <= 1.5
                                && Math.Abs(settledTwo.Y - travelStart.Y) <= 1.5
                                && CrossTrack(settledOne, travelStart, options.X, options.Z) <= .50
                                && CrossTrack(settledTwo, travelStart, options.X, options.Z) <= .50;
                        }
                    }
                    if (settleOneDistance > ArrivalRadius || settleTwoDistance > ArrivalRadius
                        || !stationary || !settledOnDirectPath)
                        Interlocked.CompareExchange(ref terminalReason, "post-release-arrival-not-settled", null);
                }
                status = terminalReason is null ? "arrived"
                    : terminalReason == "stop-file-requested" ? "stopped" : "halted";
            }
        }
        catch (OperationCanceledException)
        {
            Interlocked.CompareExchange(ref terminalReason, "cancelled", null);
            status = terminalReason == "stop-file-requested" ? "stopped"
                : terminalReason?.StartsWith("survival-", StringComparison.Ordinal) == true
                    ? "halted" : inputSent ? "halted" : "blocked";
        }
        catch (Exception error)
        {
            Interlocked.CompareExchange(ref terminalReason, error.Message, null);
            status = inputSent ? "halted" : "blocked";
        }
        finally
        {
            ReleaseAll();
            watchdogCancellation.Cancel();
            try { await watchdog; }
            catch (Exception error)
            {
                Interlocked.CompareExchange(ref terminalReason,
                    "watchdog-fault: " + error.GetType().Name, null);
                ReleaseAll();
            }
        }
        if (terminalReason is not null && status == "arrived")
            status = terminalReason == "stop-file-requested" ? "stopped" : "halted";
        if (!releaseSucceeded && status is "arrived" or "stopped")
            status = "halted";
        if (finalPose is not null && (path.Count == 0 || path[^1].ObservedAtUtc != finalPose.CompletedAtUtc))
            path.Add(new(finalPose.X, finalPose.Y, finalPose.Z, finalPose.Bearing,
                finalDistance, finalPose.CompletedAtUtc,
                finalPose.OpticalCameraBearingDegreesCandidate,
                finalPose.OpticalCameraPitchDegreesCandidate,
                finalPose.OpticalCameraStatus));
        return new(status, terminalReason, finalPose, initialDistance, finalDistance,
            reads, path.ToArray(), clock.Elapsed.TotalMilliseconds, inputSent, releaseSucceeded,
            survivalSnapshot);
    }

    internal static async Task<int> RunAsync(string[] args, CancellationToken token)
    {
        var json = args.Contains("--json", StringComparer.Ordinal);
        Options? options = null;
        Result? completedResult = null;
        object? completedTarget = null;
        try
        {
            options = Parse(args);
            if (!string.Equals(options.ExpectedHost, Environment.MachineName, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Current machine does not match --expected-host.");
            if (File.Exists(options.StopFile) || Directory.Exists(options.StopFile)
                || !Directory.Exists(Path.GetDirectoryName(options.StopFile)))
                throw new InvalidOperationException("Stop file must be a new absolute path in an existing directory.");
            using var ownerProcess = ExactProcess(options.OwnerPid, options.OwnerStartTicks, null);
            using var game = ExactProcess(options.Pid, options.ExpectedStartTicks, "rift_x64");
            var executable = game.MainModule?.FileName
                ?? throw new InvalidOperationException("Cannot resolve game executable path.");
            var sha = WindowsControlDesktop.GetFreshExecutableSha256(executable);
            if (!string.Equals(sha, options.ExpectedSha256, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(sha, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("RIFT executable hash does not match the supported exact build.");
            DesktopTarget Inspect()
            {
                var inspected = WindowsControlDesktop.InspectPinned("rift_x64", executable, sha,
                    options.Pid, options.ExpectedStartTicks);
                MoveKeyCommand.ValidateExpectedWindow(options.ExpectedHwnd, inspected.WindowHandle);
                return inspected;
            }
            var target = Inspect();
            await using var reader = await NativePoseReader.CreateAsync(options, executable, token);
            if (options.SurvivalInterrupt)
                reader.EnableSurvival();
            // The rendered map origin is checked against a fresh self pose before
            // focus can change. Default one-point CLI use may omit this triplet.
            var preFocusPose = await reader.ReadAsync(token);
            ValidateExpectedOrigin(options, preFocusPose);
            if (Distance(preFocusPose, options.X, options.Z) > MaximumDistance)
                throw new InvalidOperationException("Destination exceeds 1000 world units.");
            string? Safety()
            {
                if (File.Exists(options.StopFile)) return "stop-file-requested";
                if (Directory.Exists(options.StopFile)
                    || !Directory.Exists(Path.GetDirectoryName(options.StopFile)))
                    return "stop-path-unavailable";
                try { using var ignored = ExactProcess(options.OwnerPid, options.OwnerStartTicks, null); }
                catch { return "owner-process-lost"; }
                return null;
            }
            if (!options.Execute)
            {
                MoveKeyCommand.Report(options.Json, new
                {
                    status = "preview-only", target,
                    playerKey = options.ExpectedPlayerKey.ToString(CultureInfo.InvariantCulture),
                    goal = new { x = options.X, z = options.Z },
                    position = new { x = preFocusPose.X, y = preFocusPose.Y, z = preFocusPose.Z },
                    bodyBearingDegreesCandidate = preFocusPose.Bearing,
                    opticalCameraBearingDegreesCandidate = preFocusPose.OpticalCameraBearingDegreesCandidate,
                    opticalCameraPitchDegreesCandidate = preFocusPose.OpticalCameraPitchDegreesCandidate,
                    opticalCameraStatus = preFocusPose.OpticalCameraStatus,
                    opticalCameraYawQualified = false,
                    survivalInterrupt = options.SurvivalInterrupt,
                    survivalMode = SurvivalMode(options),
                    survivalSnapshot = preFocusPose.Survival,
                    initialDistance = Distance(preFocusPose, options.X, options.Z),
                    finalDistance = Distance(preFocusPose, options.X, options.Z),
                    stopFile = options.StopFile,
                    owner = new { processId = options.OwnerPid, processStartUtcTicks = options.OwnerStartTicks },
                    inputSent = false, releaseSucceeded = true
                });
                return 0;
            }
            using var owner = new Semaphore(1, 1, MoveKeyCommand.ControlOwnerName);
            if (!owner.WaitOne(0))
                throw new InvalidOperationException("Another RR2 control helper already owns game input.");
            try
            {
                if (Safety() is string beforeFocusReason)
                    throw new InvalidOperationException(beforeFocusReason);
                _ = await MoveKeyCommand.FocusOnlyAsync(target, Inspect,
                    WindowsControlDesktop.ReadPressedInputs,
                    () => MoveKeyCommand.RequestForegroundWithAttachedThreads(
                        new IntPtr(MoveKeyCommand.ParseWindowHandle(target.WindowHandle)), options.Pid),
                    cancellation => MoveKeyCommand.WaitForForegroundAsync(Inspect, 600, cancellation), token);
                var otherInputs = WindowsControlDesktop.ReadPressedInputs();
                if (otherInputs.Any())
                    throw new InvalidOperationException("Desktop inputs already held: " + string.Join(", ", otherInputs));
                var ready = Inspect();
                if (!ready.IsForeground) throw new InvalidOperationException("RIFT is not foreground.");
                var timeline = new MoveKeyCommand.KeySendTimeline();
                using var keyInput = new MoveKeyCommand.KeyInput(
                    WindowsControlDesktop.PinInputTarget(ready), timeline);
                if (options.SurvivalInterrupt)
                    reader.ForceSurvivalSample();
                var result = await FollowAsync(options, reader.ReadAsync,
                    new KeyInputAdapter(keyInput), Safety, token: token);
                completedResult = result;
                completedTarget = ready;
                var receipt = ProjectResult(result);
                MoveKeyCommand.Report(options.Json, new
                {
                    result.Status, result.Reason, target = ready,
                    playerKey = options.ExpectedPlayerKey.ToString(CultureInfo.InvariantCulture),
                    goal = new { x = options.X, z = options.Z }, receipt.Position,
                    receipt.BodyBearingDegreesCandidate,
                    receipt.OpticalCameraBearingDegreesCandidate,
                    receipt.OpticalCameraPitchDegreesCandidate,
                    receipt.OpticalCameraStatus,
                    opticalCameraYawQualified = false,
                    survivalInterrupt = options.SurvivalInterrupt,
                    survivalMode = SurvivalMode(options),
                    receipt.SurvivalSnapshot,
                    receipt.InitialDistance, receipt.FinalDistance, receipt.ReadCount, receipt.Path,
                    receipt.ElapsedMilliseconds, receipt.InputSent, receipt.ReleaseSucceeded,
                    keySendEvents = timeline.Snapshot(), releaseFallbacks = keyInput.ReleaseFallbacks,
                    desktopInputsDown = WindowsControlDesktop.ReadPressedInputs(),
                    stopFile = options.StopFile,
                    owner = new { processId = options.OwnerPid, processStartUtcTicks = options.OwnerStartTicks },
                    watchdog = new { poseTimeoutMilliseconds = PoseTimeoutMilliseconds,
                        pollMilliseconds = WatchdogPollMilliseconds, maxSeconds = options.MaxSeconds }
                });
                return result.Status is "arrived" or "stopped" ? 0 : 3;
            }
            finally { owner.Release(); }
        }
        catch (Exception error)
        {
            IReadOnlyList<string> inputsDown;
            try { inputsDown = WindowsControlDesktop.ReadPressedInputs(); }
            catch { inputsDown = ["input-state-unavailable"]; }
            var receipt = ProjectResult(completedResult);
            var executionStarted = receipt.InputSent;
            MoveKeyCommand.Report(json, new
            {
                status = executionStarted ? "halted" : "blocked",
                reason = error.Message, errorType = error.GetType().Name,
                target = completedTarget,
                playerKey = completedTarget is null ? null
                    : options?.ExpectedPlayerKey.ToString(CultureInfo.InvariantCulture),
                goal = options is null ? null : new { x = options.X, z = options.Z },
                receipt.Position,
                receipt.BodyBearingDegreesCandidate,
                receipt.OpticalCameraBearingDegreesCandidate,
                receipt.OpticalCameraPitchDegreesCandidate,
                receipt.OpticalCameraStatus,
                opticalCameraYawQualified = false,
                survivalInterrupt = options?.SurvivalInterrupt ?? false,
                survivalMode = options is null ? "unavailable" : SurvivalMode(options),
                receipt.SurvivalSnapshot,
                receipt.InitialDistance,
                receipt.FinalDistance,
                receipt.ReadCount,
                receipt.Path,
                receipt.ElapsedMilliseconds,
                keySendEvents = Array.Empty<object>(),
                releaseFallbacks = 0,
                desktopInputsDown = inputsDown,
                stopFile = options?.StopFile,
                owner = options is null ? null : new
                { processId = options.OwnerPid, processStartUtcTicks = options.OwnerStartTicks },
                inputSent = executionStarted,
                receipt.ReleaseSucceeded,
                watchdog = options is null ? null : new { poseTimeoutMilliseconds = PoseTimeoutMilliseconds,
                    pollMilliseconds = WatchdogPollMilliseconds, maxSeconds = options.MaxSeconds }
            });
            return executionStarted ? 3 : 2;
        }
    }

    private sealed class KeyInputAdapter(MoveKeyCommand.KeyInput source) : IInput
    {
        public bool IsTargetCurrent() => source.IsTargetCurrent();
        public IReadOnlyList<string> ReadPressedInputs() => WindowsControlDesktop.ReadPressedInputs();
        public void KeyDown(string key) => source.KeyDown(key);
        public void KeyUp(string key) => source.KeyUp(key);
    }

    private sealed class NativePoseReader(Options options, IAsyncDisposable pin) : IAsyncDisposable
    {
        private ulong? entity;
        private ulong? system;
        private readonly Stopwatch survivalClock = Stopwatch.StartNew();
        private TimeSpan nextSurvivalSample = TimeSpan.Zero;
        private bool survivalEnabled;

        internal static async Task<NativePoseReader> CreateAsync(
            Options options, string executablePath, CancellationToken token) =>
            new(options, await VerifiedNativeExecutablePin.OpenAsync(
                executablePath, options.ExpectedSha256, token));

        internal void EnableSurvival()
        {
            survivalEnabled = true;
            nextSurvivalSample = TimeSpan.Zero;
        }

        internal void ForceSurvivalSample() => nextSurvivalSample = TimeSpan.Zero;

        internal async Task<Pose> ReadAsync(CancellationToken token)
        {
            await using var lease = await NativeReadFileLease.AcquireAsync(
                options.Pid, options.ExpectedStartTicks, options.ExpectedSha256,
                TimeSpan.FromMilliseconds(500), token);
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                options.Pid, options.ExpectedStartTicks, options.ExpectedSha256,
                (VerifiedNativeExecutablePin)pin, token);
            var sample = CurrentBuildFacingCandidateReader.ReadStableObservation(session, token);
            if (sample.Identity != session.Identity || sample.PlayerKey != options.ExpectedPlayerKey
                || sample.BodyBearingDegreesCandidate is not double bearing
                || sample.EntityPositionCandidate is not { } position)
                throw new InvalidDataException("Native pose owner, body bearing or entity position is unavailable.");
            entity ??= sample.PlayerEntity;
            system ??= sample.PlayerSystem;
            if (sample.PlayerEntity != entity || sample.PlayerSystem != system)
                throw new InvalidDataException("Native player owner changed during follow.");
            SurvivalSnapshot? survival = null;
            if (survivalEnabled && survivalClock.Elapsed >= nextSurvivalSample)
            {
                survival = ReadSurvival(session, sample, token);
                nextSurvivalSample = survivalClock.Elapsed + TimeSpan.FromMilliseconds(250);
            }
            if (await session.RevalidateAsync(token) is not null || session.Identity != sample.Identity)
                throw new InvalidDataException("Native process identity changed during follow.");
            var camera = sample.OpticalCameraCandidate;
            return new(position.X, position.Y, position.Z, bearing, sample.PlayerKey,
                sample.PlayerEntity, sample.PlayerSystem, sample.StartedAtUtc, sample.CompletedAtUtc,
                camera?.BearingDegreesCandidate, camera?.PitchDegreesCandidate, camera?.Status, survival);
        }

        private static SurvivalSnapshot ReadSurvival(IReadOnlyNativeMemorySession session,
            CurrentBuildFacingCandidate pose, CancellationToken token)
        {
            var started = DateTimeOffset.UtcNow;
            try
            {
                token.ThrowIfCancellationRequested();
                var context = CurrentBuildPlayerContextCandidateReader.Read(session);
                var vitals = CurrentBuildVitalsCandidateReader.Read(session);
                token.ThrowIfCancellationRequested();
                if (context.Identity != pose.Identity || vitals.Identity != pose.Identity
                    || context.UnitKey != pose.PlayerKey || vitals.UnitKey != pose.PlayerKey
                    || context.Entity != pose.PlayerEntity)
                    throw new InvalidDataException("Survival self owner changed during capture.");
                var health = vitals.Health;
                var available = health.Status == "calculated-candidate"
                    && health.Current is long && health.Maximum is long
                    && context.CombatStatus == "raw-byte-candidate";
                return new(available ? "available-candidate" : "unavailable",
                    health.Current, health.Maximum,
                    available ? context.CombatCandidate : null,
                    available ? context.RawCombat : null,
                    started, DateTimeOffset.UtcNow,
                    available ? null : health.UnavailableReason ?? "health-or-combat-candidate-unavailable");
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception error) when (error is InvalidDataException or IOException or OverflowException)
            {
                return new("unavailable", null, null, null, null,
                    started, DateTimeOffset.UtcNow,
                    error.GetType().Name + ": " + error.Message);
            }
        }

        public ValueTask DisposeAsync() => pin.DisposeAsync();
    }

    private static Process ExactProcess(int pid, long ticks, string? name)
    {
        var process = Process.GetProcessById(pid);
        process.Refresh();
        if (process.HasExited || process.StartTime.ToUniversalTime().Ticks != ticks
            || name is not null && !string.Equals(process.ProcessName, name, StringComparison.OrdinalIgnoreCase))
        {
            process.Dispose();
            throw new InvalidOperationException("Expected process identity is unavailable.");
        }
        return process;
    }
}
