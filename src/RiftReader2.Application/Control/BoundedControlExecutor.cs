using RiftReader2.Domain;

namespace RiftReader2.Application;

/// <summary>
/// Executes exactly one validated, bounded input action. It does not schedule or repeat actions.
/// </summary>
public sealed class BoundedControlExecutor
{
    private static readonly HashSet<string> AllowedKeys =
        new(["w", "a", "s", "d", "q", "e"], StringComparer.Ordinal);
    private static readonly HashSet<string> AllowedButtons =
        new(["left", "right"], StringComparer.Ordinal);
    private static readonly (string Left, string Right)[] ConflictingKeys =
        [("w", "s"), ("a", "d"), ("q", "e")];
    private static readonly TimeSpan MaximumTargetCheckInterval = TimeSpan.FromMilliseconds(10);

    private readonly IControlInput input;
    private readonly TimeProvider timeProvider;
    private readonly Func<TimeSpan, CancellationToken, Task> delayAsync;

    public BoundedControlExecutor(
        IControlInput input,
        TimeProvider? timeProvider = null,
        Func<TimeSpan, CancellationToken, Task>? delayAsync = null)
    {
        ArgumentNullException.ThrowIfNull(input);
        this.input = input;
        this.timeProvider = timeProvider ?? TimeProvider.System;
        this.delayAsync = delayAsync
            ?? ((delay, cancellationToken) => Task.Delay(delay, this.timeProvider, cancellationToken));
    }

    public async Task<ControlExecutionResult> ExecuteAsync(
        ControlAction action,
        CancellationToken cancellationToken = default)
    {
        Validate(action);

        var startedAt = timeProvider.GetTimestamp();
        var deliverySucceeded = false;
        var cancelled = false;
        var targetLost = false;
        var releaseRequired = false;
        var holdDuration = TimeSpan.FromMilliseconds(action.HoldMilliseconds);
        long? holdStartedAt = null;
        string? deliveryError = null;
        List<string> releaseErrors = [];

        try
        {
            cancellationToken.ThrowIfCancellationRequested();

            if (!CheckTarget())
                throw new TargetChangedException("The selected target is no longer current.");

            releaseRequired = action.Keys.Length != 0 || action.MouseButton is not null;
            foreach (var key in action.Keys)
            {
                if (!CheckTarget())
                    throw new TargetChangedException("The selected target changed before all keys were pressed.");
                ThrowIfHoldBudgetExpired("all keys were pressed");
                input.KeyDown(key);
                holdStartedAt ??= timeProvider.GetTimestamp();
            }

            if (action.MouseButton is not null)
            {
                if (!CheckTarget())
                    throw new TargetChangedException("The selected target changed before the mouse button was pressed.");
                ThrowIfHoldBudgetExpired("the mouse button was pressed");
                input.ButtonDown(action.MouseButton);
                holdStartedAt ??= timeProvider.GetTimestamp();
            }

            if (action.DeltaX != 0 || action.DeltaY != 0)
            {
                if (!CheckTarget())
                    throw new TargetChangedException("The selected target changed before relative mouse movement.");
                ThrowIfHoldBudgetExpired("relative mouse movement was delivered");
                input.MoveRelative(action.DeltaX, action.DeltaY);
                holdStartedAt ??= timeProvider.GetTimestamp();
            }

            if (action.WheelNotches != 0)
            {
                if (!CheckTarget())
                    throw new TargetChangedException("The selected target changed before wheel input.");
                input.Wheel(action.WheelNotches);
            }

            if (holdStartedAt is not null && !CheckTarget())
                throw new TargetChangedException("The selected target changed during input setup.");

            while (holdStartedAt is not null
                && timeProvider.GetElapsedTime(holdStartedAt.Value) < holdDuration)
            {
                if (!CheckTarget())
                    throw new TargetChangedException("The selected target changed during the bounded hold.");

                var remaining = holdDuration - timeProvider.GetElapsedTime(holdStartedAt.Value);
                if (remaining <= TimeSpan.Zero)
                    break;
                var interval = remaining < MaximumTargetCheckInterval
                    ? remaining
                    : MaximumTargetCheckInterval;
                var beforeDelay = timeProvider.GetTimestamp();
                await delayAsync(interval, cancellationToken).ConfigureAwait(false);
                if (timeProvider.GetElapsedTime(beforeDelay) <= TimeSpan.Zero)
                    throw new InvalidOperationException("The bounded hold delay completed without monotonic time advancing.");
                if (!CheckTarget())
                    throw new TargetChangedException("The selected target changed during the bounded hold.");
            }

            deliverySucceeded = true;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            cancelled = true;
            deliveryError = "The bounded action was cancelled.";
        }
        catch (TargetChangedException exception)
        {
            targetLost = true;
            deliveryError = exception.Message;
        }
        catch (Exception exception)
        {
            deliveryError = $"{exception.GetType().Name}: {exception.Message}";
        }
        finally
        {
            if (releaseRequired)
            {
                if (action.MouseButton is not null)
                    TryRelease(() => input.ButtonUp(action.MouseButton), $"mouse button '{action.MouseButton}'");
                for (var index = action.Keys.Length - 1; index >= 0; index--)
                {
                    var key = action.Keys[index];
                    TryRelease(() => input.KeyUp(key), $"key '{key}'");
                }
            }
        }

        return BuildResult();

        bool CheckTarget()
        {
            cancellationToken.ThrowIfCancellationRequested();
            return input.IsTargetCurrent();
        }

        void ThrowIfHoldBudgetExpired(string pendingWork)
        {
            if (holdStartedAt is not null
                && timeProvider.GetElapsedTime(holdStartedAt.Value) >= holdDuration)
            {
                throw new TimeoutException(
                    $"The bounded hold elapsed before {pendingWork}.");
            }
        }

        void TryRelease(Action release, string control)
        {
            try
            {
                release();
            }
            catch (Exception exception)
            {
                releaseErrors.Add(
                    $"Failed to release {control}: {exception.GetType().Name}: {exception.Message}");
            }
        }

        ControlExecutionResult BuildResult()
        {
            var releaseSucceeded = releaseErrors.Count == 0;
            var errorParts = new List<string>();
            if (deliveryError is not null)
                errorParts.Add(deliveryError);
            errorParts.AddRange(releaseErrors);
            return new(
                deliverySucceeded,
                releaseSucceeded,
                cancelled,
                targetLost,
                !releaseSucceeded,
                !releaseSucceeded,
                timeProvider.GetElapsedTime(startedAt),
                ResponseVerified: false,
                errorParts.Count == 0 ? null : string.Join(" ", errorParts));
        }
    }

    private sealed class TargetChangedException(string message) : Exception(message);

    public static void Validate(ControlAction action)
    {
        ArgumentNullException.ThrowIfNull(action);
        if (action.Keys is null)
            throw new InvalidDataException("Control action keys cannot be null.");
        if (action.Keys.Length > AllowedKeys.Count)
            throw new InvalidDataException("Control action contains too many keys.");

        var uniqueKeys = new HashSet<string>(StringComparer.Ordinal);
        foreach (var key in action.Keys)
        {
            if (key is null || !AllowedKeys.Contains(key))
                throw new InvalidDataException("Control action keys must be lowercase w, a, s, d, q, or e.");
            if (!uniqueKeys.Add(key))
                throw new InvalidDataException($"Control action contains duplicate key '{key}'.");
        }
        foreach (var pair in ConflictingKeys)
            if (uniqueKeys.Contains(pair.Left) && uniqueKeys.Contains(pair.Right))
                throw new InvalidDataException($"Control action cannot combine '{pair.Left}' and '{pair.Right}'.");

        if (action.MouseButton is not null && !AllowedButtons.Contains(action.MouseButton))
            throw new InvalidDataException("Mouse button must be 'left' or 'right'.");
        if (action.DeltaX is < -200 or > 200 || action.DeltaY is < -200 or > 200)
            throw new InvalidDataException("Relative mouse deltas must each be between -200 and 200.");
        if (action.WheelNotches is < -3 or > 3)
            throw new InvalidDataException("Wheel input must be between -3 and 3 notches.");

        var hasMovement = action.Keys.Length != 0;
        var hasCamera = action.MouseButton is not null || action.DeltaX != 0 || action.DeltaY != 0;
        var hasWheel = action.WheelNotches != 0;
        if (!hasMovement && !hasCamera && !hasWheel)
            throw new InvalidDataException("Control action cannot be empty.");
        if (hasWheel && (hasMovement || hasCamera))
            throw new InvalidDataException("Wheel input must be a standalone bounded action.");

        if (hasWheel)
        {
            if (action.HoldMilliseconds != 0)
                throw new InvalidDataException("A standalone wheel action must have a zero millisecond hold.");
        }
        else if (action.HoldMilliseconds is < 20 or > 250)
        {
            throw new InvalidDataException("Movement and camera holds must be between 20 and 250 milliseconds.");
        }
    }
}
