using RiftReader2.Domain;

namespace RiftReader2.Application;

public sealed class LiveAddonFreshnessTracker
{
    private static readonly TimeSpan MinimumTimeout = TimeSpan.FromMilliseconds(500);
    private static readonly TimeSpan MaximumTimeout = TimeSpan.FromSeconds(60);
    private static readonly TimeSpan MaximumClockSkew = TimeSpan.FromSeconds(5);

    private readonly TimeProvider timeProvider;
    private readonly LiveFreshnessOptions options;
    private LiveAddonFrame? previous;
    private long previousObservedAt;
    private bool previousTimingUsable;
    private bool needsWarmup;
    private string? lastAdvanceEnvelopeSha256;
    private long? lastAdvanceObservedAt;
    private LiveAddonFrame? fresh;
    private long freshObservedAt;
    private bool invalidated;
    private LiveFreshnessStatus currentStatus = LiveFreshnessStatus.Unavailable;
    private string? currentReason = "awaiting-first-complete-scan";

    public LiveAttachmentIdentity Identity { get; }

    public LiveAddonFreshnessTracker(
        LiveAttachmentIdentity attachment,
        LiveFreshnessOptions? options = null,
        TimeProvider? timeProvider = null)
    {
        Identity = NormalizeIdentity(attachment);
        this.options = options ?? new LiveFreshnessOptions();
        ValidateOptions(this.options);
        this.timeProvider = timeProvider ?? TimeProvider.System;
    }

    public LiveAddonFreshness Observe(
        LiveAttachmentIdentity observedIdentity,
        LiveAddonSelection selection,
        long observedAtTimestamp)
    {
        ArgumentNullException.ThrowIfNull(selection);
        if (invalidated)
            return Invalidated(currentReason ?? "attachment-invalidated");

        LiveAttachmentIdentity normalizedIdentity;
        try
        {
            normalizedIdentity = NormalizeIdentity(observedIdentity);
        }
        catch (ArgumentException)
        {
            return Invalidate("source-identity-invalid");
        }
        if (normalizedIdentity != Identity)
            return Invalidate("source-identity-mismatch");

        if (selection.Status == LiveAddonSelectionStatus.Conflict)
            return Invalidate(selection.Reason ?? "candidate-conflict");
        if (selection.Status is LiveAddonSelectionStatus.IncompleteScan or LiveAddonSelectionStatus.NoMatchingCandidate)
            return Withhold(selection.Reason ?? "source-unavailable");
        if (selection.Status != LiveAddonSelectionStatus.Selected || selection.Frame is null)
            return Invalidate("candidate-selection-invalid");

        var candidate = selection.Frame;
        if (!string.Equals(candidate.Challenge, Identity.ReaderSessionNonce, StringComparison.Ordinal))
            return Invalidate("attachment-challenge-mismatch");

        var now = timeProvider.GetTimestamp();
        var scanAge = timeProvider.GetElapsedTime(observedAtTimestamp, now);
        if (scanAge < TimeSpan.Zero)
            return Invalidate("observation-time-in-future");

        if (previous is null)
        {
            SetBaseline(candidate, observedAtTimestamp, TryClock(candidate.Observation, out _));
            if (scanAge > options.FreshnessTimeout || !previousTimingUsable)
                return Withhold(scanAge > options.FreshnessTimeout ? "observation-already-expired" : "source-clock-unavailable");
            needsWarmup = false;
            currentStatus = LiveFreshnessStatus.Warming;
            currentReason = "baseline-warming";
            return Snapshot(LiveFreshnessStatus.Warming, null, null, null, currentReason);
        }

        var prior = previous;
        if (candidate.Observation.Epoch != prior.Observation.Epoch)
            return Invalidate("source-epoch-changed");
        if (candidate.Observation.Sequence < prior.Observation.Sequence)
            return Invalidate("source-sequence-regressed");
        if (candidate.Observation.Sequence == prior.Observation.Sequence)
        {
            if (!string.Equals(candidate.EnvelopeSha256, prior.EnvelopeSha256, StringComparison.Ordinal))
                return Invalidate("same-sequence-payload-changed");
            currentReason = "duplicate-does-not-renew";
            return GetCurrent();
        }

        if (!TryClock(candidate.Observation, out var clock))
        {
            SetBaseline(candidate, observedAtTimestamp, timingUsable: false);
            return Withhold("source-clock-unavailable");
        }
        if (scanAge > options.FreshnessTimeout)
        {
            SetBaseline(candidate, observedAtTimestamp, timingUsable: false);
            return Withhold("observation-already-expired");
        }
        if (!previousTimingUsable || !TryClock(prior.Observation, out var priorClock))
        {
            SetBaseline(candidate, observedAtTimestamp, timingUsable: true);
            needsWarmup = false;
            currentStatus = LiveFreshnessStatus.Warming;
            currentReason = "baseline-warming";
            return Snapshot(LiveFreshnessStatus.Warming, null, null, null, currentReason);
        }
        if (clock <= priorClock)
            return Invalidate("source-clock-not-advanced");

        var receiptDelta = timeProvider.GetElapsedTime(previousObservedAt, observedAtTimestamp);
        if (receiptDelta <= TimeSpan.Zero)
            return Invalidate("receiver-time-not-advanced");
        var sourceDeltaSeconds = clock - priorClock;
        if (!double.IsFinite(sourceDeltaSeconds) ||
            Math.Abs(sourceDeltaSeconds - receiptDelta.TotalSeconds) > options.MaxClockSkew.TotalSeconds)
            return Invalidate("source-clock-delta-implausible");

        if (receiptDelta > options.FreshnessTimeout || needsWarmup)
        {
            SetBaseline(candidate, observedAtTimestamp, timingUsable: true);
            needsWarmup = false;
            fresh = null;
            currentStatus = LiveFreshnessStatus.Warming;
            currentReason = receiptDelta > options.FreshnessTimeout
                ? "observation-gap-requires-warmup"
                : "recovery-requires-warmup";
            return Snapshot(LiveFreshnessStatus.Warming, null, null, null, currentReason);
        }

        SetBaseline(candidate, observedAtTimestamp, timingUsable: true);
        fresh = candidate;
        freshObservedAt = observedAtTimestamp;
        currentStatus = LiveFreshnessStatus.Fresh;
        currentReason = null;
        return GetCurrent();
    }

    public LiveAddonFreshness GetCurrent()
    {
        if (invalidated)
            return Invalidated(currentReason ?? "attachment-invalidated");
        if (fresh is null)
        {
            return Snapshot(currentStatus, null, null, null, currentReason);
        }

        var age = timeProvider.GetElapsedTime(freshObservedAt, timeProvider.GetTimestamp());
        if (age < TimeSpan.Zero)
            return Invalidate("receiver-time-regressed");
        if (age > options.FreshnessTimeout)
            return Snapshot(LiveFreshnessStatus.Expired, null, fresh.EnvelopeSha256, freshObservedAt, "freshness-timeout", age);
        return Snapshot(LiveFreshnessStatus.Fresh, fresh.Observation, fresh.EnvelopeSha256, freshObservedAt, null, age);
    }

    private LiveAddonFreshness Withhold(string reason)
    {
        fresh = null;
        needsWarmup = true;
        currentStatus = LiveFreshnessStatus.Unavailable;
        currentReason = reason;
        return Snapshot(LiveFreshnessStatus.Unavailable, null, null, null, reason);
    }

    private LiveAddonFreshness Invalidate(string reason)
    {
        invalidated = true;
        previous = null;
        fresh = null;
        currentReason = reason;
        return Invalidated(reason);
    }

    private LiveAddonFreshness Invalidated(string reason) =>
        Snapshot(LiveFreshnessStatus.Invalidated, null, null, null, reason);

    private LiveAddonFreshness Snapshot(
        LiveFreshnessStatus status,
        AddonObservation? observation,
        string? envelopeSha256,
        long? observedAt,
        string? reason,
        TimeSpan? age = null)
    {
        envelopeSha256 ??= lastAdvanceEnvelopeSha256;
        observedAt ??= lastAdvanceObservedAt;
        if (age is null && observedAt is { } timestamp)
        {
            var elapsed = timeProvider.GetElapsedTime(timestamp, timeProvider.GetTimestamp());
            age = elapsed >= TimeSpan.Zero ? elapsed : null;
        }
        return new(status, Identity, observation, envelopeSha256, observedAt, age, reason);
    }

    private void SetBaseline(LiveAddonFrame frame, long observedAtTimestamp, bool timingUsable)
    {
        previous = frame;
        previousObservedAt = observedAtTimestamp;
        previousTimingUsable = timingUsable;
        lastAdvanceEnvelopeSha256 = frame.EnvelopeSha256;
        lastAdvanceObservedAt = observedAtTimestamp;
    }

    private static bool TryClock(AddonObservation observation, out double clock)
    {
        clock = observation.Clock.Value ?? double.NaN;
        return observation.Clock.Status == AddonFieldStatus.Ok && double.IsFinite(clock) && clock >= 0;
    }

    private static LiveAttachmentIdentity NormalizeIdentity(LiveAttachmentIdentity identity)
    {
        ArgumentNullException.ThrowIfNull(identity);
        if (identity.ProcessId <= 0)
            throw new ArgumentException("ProcessId must be positive.", nameof(identity));
        if (identity.ProcessStartUtcTicks <= 0)
            throw new ArgumentException("ProcessStartUtcTicks must be positive.", nameof(identity));
        if (identity.ExecutableSha256 is null || identity.ExecutableSha256.Length != 64 ||
            identity.ExecutableSha256.Any(character => !Uri.IsHexDigit(character)))
            throw new ArgumentException("ExecutableSha256 must contain 64 hexadecimal characters.", nameof(identity));
        if (identity.ReaderSessionNonce is null || identity.ReaderSessionNonce.Length != 32 ||
            identity.ReaderSessionNonce.Any(character =>
                character is not (>= '0' and <= '9') and not (>= 'a' and <= 'f')))
            throw new ArgumentException("ReaderSessionNonce must contain 32 lowercase hexadecimal characters.", nameof(identity));
        return identity with { ExecutableSha256 = identity.ExecutableSha256.ToUpperInvariant() };
    }

    private static void ValidateOptions(LiveFreshnessOptions options)
    {
        if (options.FreshnessTimeout < MinimumTimeout || options.FreshnessTimeout > MaximumTimeout)
            throw new ArgumentOutOfRangeException(nameof(options), "FreshnessTimeout must be from 0.5 through 60 seconds.");
        if (options.MaxClockSkew < TimeSpan.Zero || options.MaxClockSkew > MaximumClockSkew)
            throw new ArgumentOutOfRangeException(nameof(options), "MaxClockSkew must be from 0 through 5 seconds.");
    }
}
