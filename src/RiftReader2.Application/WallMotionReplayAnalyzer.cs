using RiftReader2.Domain;

namespace RiftReader2.Application;

public sealed class WallMotionReplayAnalyzer
{
    public async Task<WallMotionReplaySummary> AnalyzeAsync(
        IAsyncEnumerable<WallMotionSample> samples,
        IReadOnlyList<WallMotionTrial> trials,
        WallMotionReplayOptions options,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(samples);
        ArgumentNullException.ThrowIfNull(trials);
        ValidateInputs(trials, options);

        var states = trials.Select(static trial => new TrialState(trial)).ToArray();
        long count = 0;
        long firstSequence = 0;
        long lastSequence = 0;
        await foreach (var sample in samples.WithCancellation(cancellationToken))
        {
            if (count++ == 0)
                firstSequence = sample.Sequence;
            lastSequence = sample.Sequence;
            foreach (var state in states)
                state.Observe(sample);
        }
        if (count == 0)
            throw new InvalidDataException("Wall-motion evidence has no samples.");

        var results = states.Select(state => state.Complete(options)).ToArray();
        var freeTravel = results.Where(static result => result.Role == "free-travel").ToArray();
        var walls = results.Where(static result => result.Role == "wall-contact").ToArray();
        var reproduced = freeTravel.Length > 0 && walls.Length >= 2
            && freeTravel.All(static result => result.Classification == "free-travel-plausible")
            && walls.All(static result => result.Classification == "decisive-wall-disagreement");
        return new(
            count,
            firstSequence,
            lastSequence,
            results,
            reproduced ? "unknown-unconstrained-projection" : "unresolved",
            reproduced ? "rejected-as-realized-velocity" : "not-disproved",
            reproduced);
    }

    private static void ValidateInputs(IReadOnlyList<WallMotionTrial> trials, WallMotionReplayOptions options)
    {
        if (trials.Count is < 3 or > 32)
            throw new InvalidDataException("Wall-motion replay requires between 3 and 32 trials.");
        if (trials.Select(static trial => trial.Phase).Distinct(StringComparer.Ordinal).Count() != trials.Count)
            throw new InvalidDataException("Wall-motion trial phases must be unique.");
        foreach (var trial in trials)
        {
            if (trial.Role is not ("free-travel" or "wall-contact"))
                throw new InvalidDataException($"Trial '{trial.Phase}' has an unsupported role.");
            if (trial.KeyUpAtUtc <= trial.KeyDownAtUtc)
                throw new InvalidDataException($"Trial '{trial.Phase}' has invalid key timing.");
            var sentHold = (trial.KeyUpAtUtc - trial.KeyDownAtUtc).TotalMilliseconds;
            if (!double.IsFinite(trial.ObservedHoldMilliseconds) || trial.ObservedHoldMilliseconds <= 0
                || Math.Abs(sentHold - trial.ObservedHoldMilliseconds) > 5)
                throw new InvalidDataException($"Trial '{trial.Phase}' observed hold disagrees with its key timestamps.");
        }
        foreach (var (value, label) in new[]
        {
            (options.MaxBoundaryGapMilliseconds, "boundary-gap"),
            (options.MaxProjectionGapMilliseconds, "projection-gap"),
            (options.FreeTravelMaxDirectionErrorDegrees, "free-travel direction"),
            (options.FreeTravelMaxVectorErrorFraction, "free-travel vector"),
            (options.WallMinDirectionErrorDegrees, "wall direction"),
            (options.WallMinVectorErrorFraction, "wall vector")
        })
            if (!double.IsFinite(value) || value <= 0)
                throw new InvalidDataException($"The {label} limit must be finite and positive.");
        if (options.FreeTravelMaxDirectionErrorDegrees > 180 || options.WallMinDirectionErrorDegrees > 180)
            throw new InvalidDataException("Direction limits cannot exceed 180 degrees.");
    }

    private sealed class TrialState(WallMotionTrial trial)
    {
        private WallMotionSample? before;
        private WallMotionSample? after;
        private readonly List<double> projectionX = [];
        private readonly List<double> projectionZ = [];
        private readonly List<DateTimeOffset> projectionTimes = [];

        public void Observe(WallMotionSample sample)
        {
            if (sample.CapturedAtUtc <= trial.KeyDownAtUtc)
                before = sample;
            if (sample.CapturedAtUtc >= trial.KeyDownAtUtc && sample.CapturedAtUtc <= trial.KeyUpAtUtc)
            {
                projectionX.Add(sample.ProjectionX);
                projectionZ.Add(sample.ProjectionZ);
                projectionTimes.Add(sample.CapturedAtUtc);
            }
            if (after is null && sample.CapturedAtUtc >= trial.KeyUpAtUtc)
                after = sample;
        }

        public WallMotionTrialResult Complete(WallMotionReplayOptions options)
        {
            if (before is null || after is null)
                throw new InvalidDataException($"Trial '{trial.Phase}' is not bracketed by source samples.");
            if (projectionX.Count == 0)
                throw new InvalidDataException($"Trial '{trial.Phase}' has no projection samples during its key hold.");
            var startAge = (trial.KeyDownAtUtc - before.CapturedAtUtc).TotalMilliseconds;
            var endAge = (after.CapturedAtUtc - trial.KeyUpAtUtc).TotalMilliseconds;
            if (startAge > options.MaxBoundaryGapMilliseconds || endAge > options.MaxBoundaryGapMilliseconds)
                throw new InvalidDataException($"Trial '{trial.Phase}' exceeds the sample boundary-gap limit.");
            var projectionGaps = new List<double>
            {
                (projectionTimes[0] - trial.KeyDownAtUtc).TotalMilliseconds,
                (trial.KeyUpAtUtc - projectionTimes[^1]).TotalMilliseconds
            };
            for (var index = 1; index < projectionTimes.Count; index++)
                projectionGaps.Add((projectionTimes[index] - projectionTimes[index - 1]).TotalMilliseconds);
            var maximumProjectionGap = projectionGaps.Max();
            if (maximumProjectionGap > options.MaxProjectionGapMilliseconds)
                throw new InvalidDataException($"Trial '{trial.Phase}' exceeds the projection sample-gap limit.");

            var holdSeconds = (trial.KeyUpAtUtc - trial.KeyDownAtUtc).TotalSeconds;
            var actualX = after.X - before.X;
            var actualZ = after.Z - before.Z;
            var actualMagnitude = double.Hypot(actualX, actualZ);
            if (!double.IsFinite(actualMagnitude))
                throw new InvalidDataException($"Trial '{trial.Phase}' has nonfinite realized displacement.");
            if (actualMagnitude == 0)
                throw new InvalidDataException($"Trial '{trial.Phase}' has zero realized displacement.");
            var projectedXPerSecond = Median(projectionX);
            var projectedZPerSecond = Median(projectionZ);
            var projectionMagnitude = double.Hypot(projectedXPerSecond, projectedZPerSecond);
            if (!double.IsFinite(projectionMagnitude))
                throw new InvalidDataException($"Trial '{trial.Phase}' has nonfinite projection magnitude.");
            if (projectionMagnitude == 0)
                throw new InvalidDataException($"Trial '{trial.Phase}' has a zero projection vector.");
            var projectedX = projectedXPerSecond * holdSeconds;
            var projectedZ = projectedZPerSecond * holdSeconds;
            var projectedMagnitude = double.Hypot(projectedX, projectedZ);
            if (!double.IsFinite(projectedMagnitude) || projectedMagnitude == 0)
                throw new InvalidDataException($"Trial '{trial.Phase}' has an invalid projected displacement.");
            // Normalize before computing the dot product: raw vector products overflow
            // for legitimate large finite coordinates even when their angle is zero.
            var dot = (actualX / actualMagnitude) * (projectedX / projectedMagnitude)
                + (actualZ / actualMagnitude) * (projectedZ / projectedMagnitude);
            var directionError = Math.Acos(Math.Clamp(dot, -1, 1)) * (180 / Math.PI);
            var errorX = projectedX - actualX;
            var errorZ = projectedZ - actualZ;
            var vectorError = double.Hypot(errorX, errorZ) / actualMagnitude;
            var actualSpeed = actualMagnitude / holdSeconds;
            if (!double.IsFinite(directionError) || !double.IsFinite(vectorError) || !double.IsFinite(actualSpeed))
                throw new InvalidDataException($"Trial '{trial.Phase}' has nonfinite derived motion.");
            var classification = trial.Role == "free-travel"
                ? directionError <= options.FreeTravelMaxDirectionErrorDegrees
                    && vectorError <= options.FreeTravelMaxVectorErrorFraction
                        ? "free-travel-plausible"
                        : "free-travel-disagreement"
                : projectedZ != 0 && actualZ != 0 && Math.Sign(projectedZ) != Math.Sign(actualZ)
                    && directionError >= options.WallMinDirectionErrorDegrees
                    && vectorError >= options.WallMinVectorErrorFraction
                        ? "decisive-wall-disagreement"
                        : "wall-result-inconclusive";
            return new(
                trial.Phase,
                trial.Role,
                trial.KeyDownAtUtc,
                trial.KeyUpAtUtc,
                trial.ObservedHoldMilliseconds,
                before.Sequence,
                after.Sequence,
                projectionX.Count,
                startAge,
                endAge,
                maximumProjectionGap,
                holdSeconds * 1000,
                [actualX, actualZ],
                actualSpeed,
                [projectedXPerSecond, projectedZPerSecond],
                projectionMagnitude,
                [projectedX, projectedZ],
                directionError,
                vectorError,
                classification,
                trial.GameResponseVerified,
                trial.RunSha256);
        }

        private static double Median(List<double> values)
        {
            values.Sort();
            var middle = values.Count / 2;
            return values.Count % 2 == 0 ? (values[middle - 1] + values[middle]) / 2 : values[middle];
        }
    }
}
