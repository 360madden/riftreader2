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
/// A measured candidate-angle response to one A probe. Even a valid calibration
/// describes the sampled matrix, not an independently established actor heading.
/// </summary>
public sealed record TurnSkeletonProbeAnalysis(
    string Status, double SignedCandidateDeltaDegrees, TurnSkeletonCalibration? Calibration)
{
    public string Qualification => "candidate-matrix-calibration-only";
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
        ValidateFacing(before);
        ArgumentNullException.ThrowIfNull(calibration);
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

    /// <summary>
    /// Interpret one already-completed A probe; does not send input. Refuses to
    /// calibrate if release was uncertain, another input contaminated the
    /// measurement, or observations differ in process/player/source identity.
    /// </summary>
    public static TurnSkeletonProbeAnalysis AnalyzeAProbe(
        TurnSkeletonFacing before, TurnSkeletonFacing after,
        ControlAction action, ControlExecutionResult execution,
        bool uncontaminatedInputWindow, double minimumChangeDegrees = 0.5)
    {
        ValidateFacing(before);
        ValidateFacing(after);
        ArgumentNullException.ThrowIfNull(action);
        ArgumentNullException.ThrowIfNull(execution);
        if (!double.IsFinite(minimumChangeDegrees) || minimumChangeDegrees is < 0.01 or > 20)
            throw new ArgumentOutOfRangeException(nameof(minimumChangeDegrees));
        if (action.Keys is not { Length: 1 } || action.Keys[0] != "a"
            || action.HoldMilliseconds is < 75 or > 125
            || action.MouseButton is not null || action.DeltaX != 0 || action.DeltaY != 0
            || action.WheelNotches != 0 || action.ClickTarget is not null)
            throw new ArgumentException("Expected one bounded, keyboard-only A probe.", nameof(action));
        BoundedControlExecutor.Validate(action);
        if (before.GameProcessId != after.GameProcessId
            || before.GameStartUtcTicks != after.GameStartUtcTicks
            || !string.Equals(before.UnitKey, after.UnitKey, StringComparison.Ordinal)
            || !string.Equals(before.Source, after.Source, StringComparison.Ordinal))
            return new("different-source-or-epoch", 0, null);
        if (before.IsCached || after.IsCached || after.ObservedAtUtc <= before.ObservedAtUtc)
            return new("nonfresh-observation", 0, null);
        if (!uncontaminatedInputWindow)
            return new("contaminated-input-window", 0, null);
        if (!execution.DeliverySucceeded || !execution.ReleaseSucceeded
            || execution.Cancelled || execution.TargetLost || execution.StateUncertain
            || execution.RequiresCallerDisarm)
            return new("input-or-release-unconfirmed", 0, null);

        var delta = NormalizeSigned(after.CandidateDegrees - before.CandidateDegrees);
        if (Math.Abs(delta) < minimumChangeDegrees)
            return new("no-measurable-candidate-turn", delta, null);
        if (Math.Abs(delta) == 180)
            return new("ambiguous-half-turn", delta, null);
        var rate = Math.Abs(delta) * 1000 / action.HoldMilliseconds;
        if (rate is < 0.1 or > 10000)
            return new("candidate-rate-out-of-bounds", delta, null);
        return new("candidate-rate-observed", delta,
            new TurnSkeletonCalibration(rate, delta > 0));
    }

    public static double NormalizeSigned(double degrees)
    {
        if (!double.IsFinite(degrees))
            throw new ArgumentOutOfRangeException(nameof(degrees));
        var normalized = (degrees % 360 + 540) % 360 - 180;
        return normalized == 0 ? 0 : normalized;
    }

    private static void ValidateFacing(TurnSkeletonFacing sample)
    {
        ArgumentNullException.ThrowIfNull(sample);
        if (string.IsNullOrWhiteSpace(sample.Source) || string.IsNullOrWhiteSpace(sample.UnitKey)
            || sample.GameProcessId <= 0 || sample.GameStartUtcTicks <= 0
            || !double.IsFinite(sample.CandidateDegrees) || sample.ObservedAtUtc == default)
            throw new ArgumentException("A finite, source-tagged, epoch-pinned facing sample is required.", nameof(sample));
    }

    private static double Normalize(double degrees)
    {
        var angle = degrees % 360;
        return angle < 0 ? angle + 360 : angle;
    }
}
