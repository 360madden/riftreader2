using RiftReader2.Domain;

namespace RiftReader2.Application;

/// <summary>
/// An explicitly provisional player-owned orientation reading. A cached sample can
/// drive offline scaffolding but grants no control authority or body-yaw claim.
/// </summary>
public sealed record TurnSkeletonFacing(
    string Source, int GameProcessId, long GameStartUtcTicks, string UnitKey,
    double CandidateDegrees, DateTimeOffset ObservedAtUtc, bool IsCached);

/// <summary>
/// Provisional calibration supplied by the caller, not inferred from a matrix.
/// Direction refers to the candidate matrix angle and may differ from body yaw.
/// </summary>
public sealed record TurnSkeletonCalibration(
    double CandidateDegreesPerSecond, bool AIncreasesCandidateDegrees,
    int MinimumPulseMilliseconds = 75, int MaximumPulseMilliseconds = 125);

public sealed record TurnSkeletonPlan(
    string Status, TurnSkeletonFacing Facing, double TargetCandidateDegrees,
    double SignedCandidateDeltaDegrees, ControlAction? Action)
{
    public string Qualification =>
        "candidate-matrix-planning-only; never proof of player-facing or game-input success";
}

/// <summary>
/// Offline math/command skeleton for one future supervised turn. Never executes input.
/// The controller's fresh screenshot, epoch, disarm and key-up gates remain mandatory.
/// </summary>
public static class TurnSkeletonPlanner
{
    public static ControlAction ProbeA(int holdMilliseconds = 100)
    {
        if (holdMilliseconds is < 75 or > 125)
            throw new ArgumentOutOfRangeException(nameof(holdMilliseconds));
        var action = new ControlAction(["a"], holdMilliseconds);
        BoundedControlExecutor.Validate(action);
        return action;
    }

    public static TurnSkeletonPlan PlanNext(
        TurnSkeletonFacing before, double targetCandidateDegrees,
        TurnSkeletonCalibration calibration, double toleranceDegrees = 1)
    {
        ArgumentNullException.ThrowIfNull(before);
        ArgumentNullException.ThrowIfNull(calibration);
        if (string.IsNullOrWhiteSpace(before.Source) || string.IsNullOrWhiteSpace(before.UnitKey)
            || before.GameProcessId <= 0 || before.GameStartUtcTicks <= 0
            || !double.IsFinite(before.CandidateDegrees)
            || before.ObservedAtUtc == default)
            throw new ArgumentException("A finite, source-tagged, epoch-pinned facing sample is required.", nameof(before));
        if (!double.IsFinite(targetCandidateDegrees))
            throw new ArgumentOutOfRangeException(nameof(targetCandidateDegrees));
        if (!double.IsFinite(calibration.CandidateDegreesPerSecond)
            || calibration.CandidateDegreesPerSecond is < 0.1 or > 10000
            || calibration.MinimumPulseMilliseconds is < 20 or > 250
            || calibration.MaximumPulseMilliseconds is < 20 or > 250
            || calibration.MinimumPulseMilliseconds > calibration.MaximumPulseMilliseconds)
            throw new ArgumentException("Invalid bounded candidate-turn calibration.", nameof(calibration));
        if (!double.IsFinite(toleranceDegrees) || toleranceDegrees is < 0 or > 20)
            throw new ArgumentOutOfRangeException(nameof(toleranceDegrees));

        var current = Normalize(before.CandidateDegrees);
        var target = Normalize(targetCandidateDegrees);
        var delta = NormalizeSigned(target - current);
        if (Math.Abs(delta) <= toleranceDegrees)
            return new("within-tolerance", before, target, delta, null);

        var neededMilliseconds = Math.Abs(delta) * 1000 / calibration.CandidateDegreesPerSecond;
        if (neededMilliseconds < calibration.MinimumPulseMilliseconds)
            return new("below-minimum-pulse", before, target, delta, null);
        var pulse = (int)Math.Min(calibration.MaximumPulseMilliseconds, Math.Ceiling(neededMilliseconds));
        var key = (delta > 0) == calibration.AIncreasesCandidateDegrees ? "a" : "d";
        var action = new ControlAction([key], pulse);
        BoundedControlExecutor.Validate(action);
        return new("one-bounded-pulse-candidate", before, target, delta, action);
    }

    public static double NormalizeSigned(double degrees)
    {
        if (!double.IsFinite(degrees))
            throw new ArgumentOutOfRangeException(nameof(degrees));
        var normalized = (degrees % 360 + 540) % 360 - 180;
        return normalized == 0 ? 0 : normalized;
    }

    private static double Normalize(double degrees)
    {
        var angle = degrees % 360;
        return angle < 0 ? angle + 360 : angle;
    }
}
