using System.ComponentModel;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

public sealed record PositionPanelState(
    string Status,
    string? Reason,
    NativeProcessIdentity? Identity,
    PositionCandidateObservation? Observation,
    bool IsMonitoring,
    bool IsReading);

/// <summary>
/// Owns the bounded Start / Read / Stop state machine for the position panel.
/// It never retains coordinates after stop, expiry, or an unavailable read.
/// </summary>
public sealed class PositionPanelController : IDisposable
{
    private static readonly TimeSpan MinimumFreshnessTimeout = TimeSpan.FromMilliseconds(250);
    private static readonly TimeSpan MaximumFreshnessTimeout = TimeSpan.FromSeconds(30);
    private static readonly TimeSpan MinimumMonitoringLimit = TimeSpan.FromSeconds(1);
    private static readonly TimeSpan MaximumMonitoringLimit = TimeSpan.FromHours(1);

    private readonly Lock gate = new();
    private readonly Func<CancellationToken, Task<NativePositionSamplesReport>> read;
    private readonly TimeProvider timeProvider;
    private readonly TimeSpan freshnessTimeout;
    private readonly TimeSpan monitoringLimit;
    private PositionPanelState state = new("stopped", null, null, null, false, false);
    private CancellationTokenSource? sessionCancellation;
    private CancellationTokenSource? physicalReadSession;
    private bool physicalReadInFlight;
    private long generation;
    private long monitoringStartedAt;
    private long successfulReadStartedAt;
    private long successfulReadCompletedAt;
    private bool disposed;

    public PositionPanelController(
        Func<CancellationToken, Task<NativePositionSamplesReport>> read,
        TimeProvider? timeProvider = null,
        TimeSpan? freshnessTimeout = null,
        TimeSpan? monitoringLimit = null)
    {
        ArgumentNullException.ThrowIfNull(read);
        this.read = read;
        this.timeProvider = timeProvider ?? TimeProvider.System;
        this.freshnessTimeout = freshnessTimeout ?? TimeSpan.FromSeconds(3);
        this.monitoringLimit = monitoringLimit ?? TimeSpan.FromMinutes(10);
        if (this.freshnessTimeout < MinimumFreshnessTimeout ||
            this.freshnessTimeout > MaximumFreshnessTimeout)
            throw new ArgumentOutOfRangeException(nameof(freshnessTimeout),
                "Freshness timeout must be between 250 milliseconds and 30 seconds.");
        if (this.monitoringLimit < MinimumMonitoringLimit ||
            this.monitoringLimit > MaximumMonitoringLimit)
            throw new ArgumentOutOfRangeException(nameof(monitoringLimit),
                "Monitoring limit must be between 1 second and 1 hour.");
    }

    public PositionPanelState State
    {
        get
        {
            lock (gate)
                return state;
        }
    }

    public event Action<PositionPanelState>? Changed;

    public void Start()
    {
        PositionPanelState next;
        CancellationTokenSource? abandoned;
        bool abandonedReadInFlight;
        lock (gate)
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            abandoned = sessionCancellation;
            abandonedReadInFlight = physicalReadSession == abandoned;
            generation++;
            sessionCancellation = new CancellationTokenSource();
            monitoringStartedAt = timeProvider.GetTimestamp();
            successfulReadStartedAt = 0;
            successfulReadCompletedAt = 0;
            next = state = new("waiting", "awaiting-fresh-read", null, null, true, physicalReadInFlight);
        }
        CancelSession(abandoned, !abandonedReadInFlight);
        Changed?.Invoke(next);
    }

    public void Stop()
    {
        PositionPanelState next;
        CancellationTokenSource? abandoned;
        bool abandonedReadInFlight;
        lock (gate)
        {
            if (disposed)
                return;
            generation++;
            abandoned = sessionCancellation;
            abandonedReadInFlight = physicalReadSession == abandoned;
            sessionCancellation = null;
            successfulReadStartedAt = 0;
            successfulReadCompletedAt = 0;
            next = state = new("stopped", null, null, null, false, false);
        }
        CancelSession(abandoned, !abandonedReadInFlight);
        Changed?.Invoke(next);
    }

    public async Task ReadAsync()
    {
        PositionPanelState readingState;
        CancellationTokenSource session;
        long expectedGeneration;
        long readStartedAt;
        lock (gate)
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            if (physicalReadInFlight)
                return;
            sessionCancellation ??= new CancellationTokenSource();
            expectedGeneration = generation;
            session = sessionCancellation;
            physicalReadSession = session;
            physicalReadInFlight = true;
            readStartedAt = timeProvider.GetTimestamp();
            readingState = state = state with
            {
                Status = "reading",
                Reason = null,
                Identity = null,
                Observation = null,
                IsReading = true
            };
        }
        Changed?.Invoke(readingState);

        NativePositionSamplesReport? report = null;
        string? failure = null;
        var canceled = false;
        try
        {
            report = await read(session.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (session.IsCancellationRequested)
        {
            canceled = true;
        }
        catch (OperationCanceledException)
        {
            failure = "read-canceled-unexpectedly";
        }
        catch (Exception exception) when (IsExpectedReadFailure(exception))
        {
            failure = exception.Message;
        }
        catch (Exception exception) when (!IsFatal(exception))
        {
            failure = $"Position read failed: {exception.Message}";
        }

        PositionPanelState? next = null;
        var disposeSession = false;
        lock (gate)
        {
            physicalReadInFlight = false;
            physicalReadSession = null;
            if (disposed || expectedGeneration != generation ||
                sessionCancellation != session)
            {
                disposeSession = true;
                if (!disposed && state.IsMonitoring && state.IsReading)
                    next = state = state with { IsReading = false };
            }
            else if (canceled)
            {
                disposeSession = true;
                sessionCancellation = null;
                next = state = new("stopped", null, null, null, false, false);
            }
            else
            {
                var isMonitoring = state.IsMonitoring;
                var readCompletedAt = timeProvider.GetTimestamp();
                if (failure is not null)
                {
                    next = state = Unavailable(failure, isMonitoring);
                }
                else if (!TrySelectFreshObservation(report, out var identity, out var observation, out var reason))
                {
                    next = state = Unavailable(reason, isMonitoring);
                }
                else if (timeProvider.GetElapsedTime(readStartedAt, readCompletedAt) > freshnessTimeout)
                {
                    next = state = new("stale", "read-completed-after-freshness-window",
                        null, null, isMonitoring, false);
                }
                else
                {
                    successfulReadStartedAt = readStartedAt;
                    successfulReadCompletedAt = readCompletedAt;
                    next = state = new("live", null, identity, observation, isMonitoring, false);
                }
                if (!isMonitoring)
                {
                    sessionCancellation = null;
                    disposeSession = true;
                }
            }
        }
        if (disposeSession)
            session.Dispose();
        if (next is not null)
            Changed?.Invoke(next);
    }

    public void RefreshFreshness()
    {
        PositionPanelState? next = null;
        CancellationTokenSource? expiredSession = null;
        var expiredReadInFlight = false;
        lock (gate)
        {
            if (disposed)
                return;
            var now = timeProvider.GetTimestamp();
            if (state.IsMonitoring && timeProvider.GetElapsedTime(monitoringStartedAt, now) > monitoringLimit)
            {
                generation++;
                expiredSession = sessionCancellation;
                expiredReadInFlight = physicalReadSession == expiredSession;
                sessionCancellation = null;
                successfulReadStartedAt = 0;
                successfulReadCompletedAt = 0;
                next = state = new("expired", "monitoring-limit-reached", null, null, false, false);
            }
            else if (state.Status == "live" &&
                (timeProvider.GetElapsedTime(successfulReadStartedAt, now) > freshnessTimeout ||
                 timeProvider.GetElapsedTime(successfulReadCompletedAt, now) > freshnessTimeout))
            {
                next = state = new("stale", "last-read-expired", null, null,
                    state.IsMonitoring, false);
            }
        }
        if (expiredSession is not null)
            CancelSession(expiredSession, !expiredReadInFlight);
        if (next is not null)
            Changed?.Invoke(next);
    }

    public void Dispose()
    {
        CancellationTokenSource? abandoned;
        bool abandonedReadInFlight;
        PositionPanelState? next = null;
        lock (gate)
        {
            if (disposed)
                return;
            disposed = true;
            generation++;
            abandoned = sessionCancellation;
            abandonedReadInFlight = physicalReadSession == abandoned;
            sessionCancellation = null;
            if (state.Status != "stopped" || state.IsMonitoring || state.IsReading || state.Observation is not null)
                next = state = new("stopped", null, null, null, false, false);
        }
        CancelSession(abandoned, !abandonedReadInFlight);
        if (next is not null)
            Changed?.Invoke(next);
    }

    private static PositionPanelState Unavailable(string? reason, bool isMonitoring) =>
        new("unavailable", string.IsNullOrWhiteSpace(reason) ? "position-unavailable" : reason,
            null, null, isMonitoring, false);

    private static bool TrySelectFreshObservation(
        NativePositionSamplesReport? report,
        out NativeProcessIdentity? identity,
        out PositionCandidateObservation? observation,
        out string reason)
    {
        identity = null;
        observation = null;
        if (report is null)
        {
            reason = "read-returned-no-report";
            return false;
        }
        if (report.Profile is null || report.Samples is null ||
            report.Samples.Identity is null || report.Samples.Observations is null)
        {
            reason = "read-returned-malformed-report";
            return false;
        }
        if (report.Samples.Status != "complete" || report.Samples.RequestedSamples != 1 ||
            report.Samples.CompletedSamples != 1 || report.Samples.Observations.Count != 1)
        {
            reason = report.Samples.Reason ?? "single-complete-sample-required";
            return false;
        }
        var candidate = report.Samples.Observations[0];
        if (candidate is null)
        {
            reason = "read-returned-malformed-report";
            return false;
        }
        if (candidate.Status != "complete" || candidate.X is not float x ||
            candidate.Y is not float y || candidate.Z is not float z ||
            !float.IsFinite(x) || !float.IsFinite(y) || !float.IsFinite(z))
        {
            reason = candidate.Reason ?? "finite-complete-xyz-required";
            return false;
        }
        if (float.IsSubnormal(x) || float.IsSubnormal(y) || float.IsSubnormal(z))
        {
            reason = "position-values-not-ready";
            return false;
        }
        if (!string.Equals(report.Profile.ExecutableSha256,
            report.Samples.Identity.ExecutableSha256, StringComparison.Ordinal))
        {
            reason = "profile-process-build-mismatch";
            return false;
        }
        identity = report.Samples.Identity;
        observation = candidate;
        reason = string.Empty;
        return true;
    }

    private static bool IsExpectedReadFailure(Exception exception) =>
        exception is IOException or InvalidDataException or Win32Exception or
            ArgumentException or InvalidOperationException or UnauthorizedAccessException or
            NotSupportedException or TimeoutException;

    private static bool IsFatal(Exception exception) =>
        exception is OutOfMemoryException or AccessViolationException or StackOverflowException;

    private static void CancelSession(CancellationTokenSource? source, bool dispose)
    {
        if (source is null)
            return;
        try
        {
            source.Cancel();
        }
        catch (ObjectDisposedException)
        {
            // A concurrently completing abandoned read owns final disposal.
        }
        if (dispose)
            source.Dispose();
    }

}
