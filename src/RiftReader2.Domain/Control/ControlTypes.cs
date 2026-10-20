namespace RiftReader2.Domain;

/// <summary>
/// One bounded, supervised movement or camera action.
/// </summary>
public sealed record ControlAction(
    string[] Keys,
    int HoldMilliseconds,
    string? MouseButton = null,
    int DeltaX = 0,
    int DeltaY = 0,
    int WheelNotches = 0);

/// <summary>
/// Reports input delivery independently from release certainty. Game response requires
/// separate observation and is therefore never inferred by the input executor. ObservedDuration
/// covers the complete executor call, including delivery, the hold, and release attempts.
/// </summary>
public sealed record ControlExecutionResult(
    bool DeliverySucceeded,
    bool ReleaseSucceeded,
    bool Cancelled,
    bool TargetLost,
    bool StateUncertain,
    bool RequiresCallerDisarm,
    TimeSpan ObservedDuration,
    bool ResponseVerified,
    string? Error);
