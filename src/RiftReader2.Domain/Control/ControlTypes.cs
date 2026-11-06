namespace RiftReader2.Domain;

/// <summary>
/// One bounded, supervised movement, camera or targeted button action.
/// </summary>
public sealed record ControlAction(
    string[] Keys,
    int HoldMilliseconds,
    string? MouseButton = null,
    int DeltaX = 0,
    int DeltaY = 0,
    int WheelNotches = 0,
    ClickTarget? ClickTarget = null);

/// <summary>A reviewed button rectangle in captured client pixels; right/bottom are exclusive.</summary>
public sealed record ClickTarget(int X, int Y, int Width, int Height);

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
