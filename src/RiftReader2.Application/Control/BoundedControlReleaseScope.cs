using RiftReader2.Domain;

namespace RiftReader2.Application;

/// <summary>
/// One action's insertion/release gate. Target inspection must stay outside this gate.
/// A dedicated thread releases independently of blocked probes and async continuations.
/// This is not a hard real-time guarantee against OS suspension or a blocked native send.
/// </summary>
internal sealed class BoundedControlReleaseScope : IDisposable
{
    private readonly object gate = new();
    private readonly IControlInput input;
    private readonly ControlAction action;
    private readonly TimeProvider clock;
    private readonly CancellationToken cancellation;
    private readonly AutoResetEvent wake = new(false);
    private readonly ManualResetEventSlim workerReady = new();
    private readonly Thread worker;
    private readonly CancellationTokenRegistration registration;
    private readonly List<string> errors = [];
    private long? startedAt;
    private bool sealedForInput;
    private bool releaseAttempted;
    private bool disposed;

    public BoundedControlReleaseScope(
        IControlInput input, ControlAction action, TimeProvider clock, CancellationToken cancellation)
    {
        this.input = input;
        this.action = action;
        this.clock = clock;
        this.cancellation = cancellation;
        worker = new Thread(WatchDeadline) { IsBackground = true, Name = "RR2 bounded input release" };
        registration = cancellation.Register(() => wake.Set());
        try
        {
            worker.Start();
            workerReady.Wait(); // Establish the release worker before permitting any down.
        }
        catch
        {
            registration.Dispose();
            wake.Dispose();
            workerReady.Dispose();
            throw;
        }
    }

    // Called only for bounded down/move operations, never wheel or inspection.
    public long Deliver(Action deliver)
    {
        lock (gate)
        {
            cancellation.ThrowIfCancellationRequested();
            if (sealedForInput || DeadlineExpired())
            {
                ReleaseLocked();
                throw new TimeoutException("The bounded hold elapsed before further input could be delivered.");
            }
            // Arm BEFORE any possible insertion, including partial/throwing sends.
            startedAt ??= clock.GetTimestamp();
            wake.Set();
            deliver();
            return startedAt.Value;
        }
    }

    public void Release()
    {
        lock (gate)
            ReleaseLocked();
        wake.Set();
    }

    public string[] ReleaseErrors
    {
        get { lock (gate) return errors.ToArray(); }
    }

    private bool DeadlineExpired() => startedAt is { } start
        && clock.GetElapsedTime(start) >= TimeSpan.FromMilliseconds(action.HoldMilliseconds);

    private void WatchDeadline()
    {
        workerReady.Set();
        try
        {
            while (true)
            {
                var wait = Timeout.Infinite;
                lock (gate)
                {
                    if (sealedForInput)
                        return;
                    if (cancellation.IsCancellationRequested)
                    {
                        if (startedAt is not null)
                            ReleaseLocked();
                        else
                            sealedForInput = true;
                        return;
                    }
                    if (startedAt is { } start)
                    {
                        var remaining = TimeSpan.FromMilliseconds(action.HoldMilliseconds)
                            - clock.GetElapsedTime(start);
                        if (remaining <= TimeSpan.Zero)
                        {
                            ReleaseLocked();
                            return;
                        }
                        wait = Math.Clamp((int)Math.Ceiling(remaining.TotalMilliseconds), 1, 10);
                    }
                }
                wake.WaitOne(wait);
            }
        }
        catch (Exception exception)
        {
            // Never let a watchdog exception terminate the process with input down.
            lock (gate)
            {
                errors.Add($"Release watchdog failed: {exception.GetType().Name}: {exception.Message}");
                ReleaseLocked();
            }
        }
    }

    private void ReleaseLocked()
    {
        sealedForInput = true;
        if (releaseAttempted)
            return;
        releaseAttempted = true;
        if (action.MouseButton is not null)
            TryRelease(() => input.ButtonUp(action.MouseButton), $"mouse button '{action.MouseButton}'");
        for (var index = action.Keys.Length - 1; index >= 0; index--)
        {
            var key = action.Keys[index];
            TryRelease(() => input.KeyUp(key), $"key '{key}'");
        }
    }

    private void TryRelease(Action release, string control)
    {
        try { release(); }
        catch (Exception exception)
        {
            errors.Add($"Failed to release {control}: {exception.GetType().Name}: {exception.Message}");
        }
    }

    public void Dispose()
    {
        if (disposed)
            return;
        disposed = true;
        lock (gate)
        {
            if (startedAt is not null)
                ReleaseLocked();
            else
                sealedForInput = true;
        }
        wake.Set();
        // Unregister before disposing the event; no callback waits on the injection gate.
        registration.Dispose();
        worker.Join();
        wake.Dispose();
        workerReady.Dispose();
    }
}
