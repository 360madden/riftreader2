using System.Buffers.Binary;
using System.Diagnostics;
using System.Security.Cryptography;
using RiftReader2.Domain;

namespace RiftReader2.Application;

public sealed record PositionCandidateStep(
    double DeltaX,
    double DeltaY,
    double DeltaZ,
    double DistanceGameUnits,
    double ElapsedMilliseconds);

public sealed record PositionCandidateObservation(
    int Sequence,
    string StartedAtUtc,
    string CompletedAtUtc,
    double MonotonicStartMilliseconds,
    double MonotonicEndMilliseconds,
    string Status,
    string? Reason,
    float? X,
    float? Y,
    float? Z,
    string? OwnerAddress,
    string? TerminalBytesSha256,
    PositionCandidateStep? ChangeFromPrevious);

public sealed record PositionCandidateMotionSummary(
    string Status,
    double ThresholdGameUnits,
    int CompleteSamples,
    double? FirstLastDistanceGameUnits,
    double? MaxExcursionFromFirstGameUnits,
    double? MaxConsecutiveChangeGameUnits);

public sealed record PositionCandidateSampleSummary(
    string Status,
    string? Reason,
    NativeProcessIdentity Identity,
    string StartedAtUtc,
    string CompletedAtUtc,
    int RequestedSamples,
    int CompletedSamples,
    IReadOnlyList<PositionCandidateObservation> Observations,
    PositionCandidateMotionSummary Motion);

/// <summary>
/// A short, read-only, exact-build sampling path using the existing pointer resolver.
/// No heap search, source qualification, or automatic field promotion occurs.
/// </summary>
public static class PositionCandidateSampler
{
    private const double CandidateChangeThresholdGameUnits = 0.1;

    public static async Task<PositionCandidateSampleSummary> SampleAsync(
        PositionCandidateProfile profile,
        IReadOnlyNativeMemorySession session,
        int sampleCount,
        int intervalMilliseconds,
        CancellationToken cancellationToken,
        Func<PositionCandidateObservation, Task>? onSample = null)
    {
        ArgumentNullException.ThrowIfNull(profile);
        ArgumentNullException.ThrowIfNull(session);
        profile.Validate();
        if (sampleCount is < 1 or > 30 || intervalMilliseconds is < 0 or > 2000 ||
            (long)(sampleCount - 1) * intervalMilliseconds > 60_000)
            throw new ArgumentOutOfRangeException(nameof(sampleCount), "Sampling requires 1-30 reads, a 0-2000 ms interval, and a schedule of at most 60 seconds.");
        if (!string.Equals(profile.ExecutableSha256, session.Identity.ExecutableSha256, StringComparison.Ordinal))
            throw new InvalidDataException("The known position recipe does not match the current RIFT executable build.");

        var identity = session.Identity;
        var startedAtUtc = DateTimeOffset.UtcNow.ToString("O");
        var elapsed = Stopwatch.StartNew();
        var observations = new List<PositionCandidateObservation>(sampleCount);
        PositionCandidateObservation? previousComplete = null;
        for (var index = 0; index < sampleCount; index++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var startMs = elapsed.Elapsed.TotalMilliseconds;
            var sampleStarted = DateTimeOffset.UtcNow.ToString("O");
            var resolved = await MemoryDiscovery.ResolvePointerChainAsync(
                new MemoryPointerChain(profile.RootRva, [0]), identity, session,
                profile.TerminalByteLength, cancellationToken);
            var status = resolved.Status;
            var reason = resolved.Reason;
            float? x = null;
            float? y = null;
            float? z = null;
            string? bytesSha256 = null;
            if (status == "complete")
            {
                var bytes = resolved.TerminalRead!.Bytes;
                bytesSha256 = Convert.ToHexString(SHA256.HashData(bytes));
                var rawX = BinaryPrimitives.ReadSingleLittleEndian(bytes.AsSpan(checked((int)profile.XOffset), 4));
                var rawY = BinaryPrimitives.ReadSingleLittleEndian(bytes.AsSpan(checked((int)profile.YOffset), 4));
                var rawZ = BinaryPrimitives.ReadSingleLittleEndian(bytes.AsSpan(checked((int)profile.ZOffset), 4));
                if (float.IsFinite(rawX) && float.IsFinite(rawY) && float.IsFinite(rawZ))
                {
                    x = rawX;
                    y = rawY;
                    z = rawZ;
                }
                else
                {
                    status = "invalid-value";
                    reason = "Terminal owner bytes contain non-finite XYZ float32 values.";
                }
            }
            PositionCandidateStep? change = null;
            if (status == "complete" && previousComplete is not null)
            {
                var deltaX = (double)x!.Value - previousComplete.X!.Value;
                var deltaY = (double)y!.Value - previousComplete.Y!.Value;
                var deltaZ = (double)z!.Value - previousComplete.Z!.Value;
                change = new(
                    deltaX, deltaY, deltaZ, Distance(deltaX, deltaY, deltaZ),
                    Math.Max(0, startMs - previousComplete.MonotonicStartMilliseconds));
            }
            var observation = new PositionCandidateObservation(
                index + 1,
                sampleStarted,
                DateTimeOffset.UtcNow.ToString("O"),
                startMs,
                elapsed.Elapsed.TotalMilliseconds,
                status,
                reason,
                x,
                y,
                z,
                resolved.TerminalAddress is null ? null : $"0x{resolved.TerminalAddress.Value:X}",
                bytesSha256,
                change);
            observations.Add(observation);
            if (status == "complete")
                previousComplete = observation;
            if (onSample is not null)
                await onSample(observation);
            if (status != "complete")
                break;
            if (index + 1 < sampleCount && intervalMilliseconds > 0)
                await Task.Delay(intervalMilliseconds, cancellationToken);
        }

        var complete = observations.Count == sampleCount &&
            observations.All(observation => observation.Status == "complete");
        var statusSummary = complete ? "complete" :
            observations.Any(observation => observation.Status == "complete") ? "partial" : "failed";
        var reasonSummary = complete ? null :
            $"Sampling stopped at observation {observations[^1].Sequence}: {observations[^1].Status}.";
        var motion = SummarizeCandidateChanges(observations);
        return new(statusSummary, reasonSummary, identity, startedAtUtc,
            DateTimeOffset.UtcNow.ToString("O"), sampleCount, observations.Count, observations, motion);
    }

    private static PositionCandidateMotionSummary SummarizeCandidateChanges(
        IReadOnlyList<PositionCandidateObservation> observations)
    {
        var complete = observations.Where(item => item.Status == "complete").ToArray();
        if (complete.Length < 2)
            return new("insufficient-complete-samples", CandidateChangeThresholdGameUnits,
                complete.Length, null, null, null);

        var first = complete[0];
        var maxExcursion = complete.Max(item => Distance(
            (double)item.X!.Value - first.X!.Value,
            (double)item.Y!.Value - first.Y!.Value,
            (double)item.Z!.Value - first.Z!.Value));
        var last = complete[^1];
        var firstLast = Distance(
            (double)last.X!.Value - first.X!.Value,
            (double)last.Y!.Value - first.Y!.Value,
            (double)last.Z!.Value - first.Z!.Value);
        var maxStep = complete.Max(item => item.ChangeFromPrevious?.DistanceGameUnits ?? 0);
        return new(
            Math.Max(maxExcursion, maxStep) >= CandidateChangeThresholdGameUnits
                ? "native-candidate-change-observed" : "no-significant-native-change-observed",
            CandidateChangeThresholdGameUnits,
            complete.Length, firstLast, maxExcursion, maxStep);
    }

    private static double Distance(double x, double y, double z) =>
        Math.Sqrt(x * x + y * y + z * z);
}
