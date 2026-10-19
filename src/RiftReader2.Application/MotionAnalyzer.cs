using System.IO;
using RiftReader2.Domain;

namespace RiftReader2.Application;

/// <summary>
/// Performs a single-pass analysis of ordered samples without retaining the stream.
/// </summary>
public sealed class MotionAnalyzer
{
    private const double FullTurnRadians = 2.0 * Math.PI;

    public async Task<AnalysisSummary> AnalyzeAsync(
        IAsyncEnumerable<MotionSample> samples,
        AnalysisOptions options,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(samples);
        ArgumentNullException.ThrowIfNull(options);
        ValidateOptions(options);

        MotionSample? first = null;
        MotionSample? previous = null;
        var sampleCount = 0;
        long missingSequenceCount = 0;
        var sequenceGapCount = 0;
        var timingGapCount = 0;
        var derivedIntervalCount = 0;
        var skippedDerivativeIntervalCount = 0;
        double? maxHorizontalDerivedSpeed = null;
        double? maxAbsoluteDerivedYawRate = null;

        await foreach (var sample in samples.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            cancellationToken.ThrowIfCancellationRequested();

            if (sample is null)
            {
                throw new InvalidDataException("The sample stream contains a null sample.");
            }

            ValidateSample(sample);

            if (sampleCount == options.MaxSamples)
            {
                throw new InvalidDataException(
                    $"The sample stream exceeds the configured limit of {options.MaxSamples} samples.");
            }

            sampleCount++;
            first ??= sample;

            if (previous is not null)
            {
                if (!string.Equals(sample.SessionId, first.SessionId, StringComparison.Ordinal))
                {
                    throw new InvalidDataException(
                        $"The sample stream mixes session '{first.SessionId}' with '{sample.SessionId}'.");
                }

                if (sample.Sequence <= previous.Sequence)
                {
                    throw new InvalidDataException(
                        "Sample sequence numbers must be strictly increasing; duplicates and backwards values are invalid.");
                }

                if (sample.TimestampSeconds <= previous.TimestampSeconds)
                {
                    throw new InvalidDataException(
                        "Sample timestamps must be strictly increasing; duplicates and backwards values are invalid.");
                }

                var sequenceDelta = sample.Sequence - previous.Sequence;
                var intervalSeconds = sample.TimestampSeconds - previous.TimestampSeconds;
                var hasSequenceGap = sequenceDelta != 1;
                var hasTimingGap = intervalSeconds > options.MaxGapSeconds;

                if (hasSequenceGap)
                {
                    sequenceGapCount++;
                    try
                    {
                        missingSequenceCount = checked(missingSequenceCount + sequenceDelta - 1);
                    }
                    catch (OverflowException exception)
                    {
                        throw new InvalidDataException("The missing sequence count exceeds Int64 capacity.", exception);
                    }
                }

                if (hasTimingGap)
                {
                    timingGapCount++;
                }

                if (hasSequenceGap || hasTimingGap)
                {
                    skippedDerivativeIntervalCount++;
                }
                else
                {
                    var horizontalSpeed = CalculateHorizontalSpeed(previous, sample, intervalSeconds);
                    var absoluteYawRate = CalculateAbsoluteYawRate(previous, sample, intervalSeconds);

                    maxHorizontalDerivedSpeed = maxHorizontalDerivedSpeed is null
                        ? horizontalSpeed
                        : Math.Max(maxHorizontalDerivedSpeed.Value, horizontalSpeed);
                    maxAbsoluteDerivedYawRate = maxAbsoluteDerivedYawRate is null
                        ? absoluteYawRate
                        : Math.Max(maxAbsoluteDerivedYawRate.Value, absoluteYawRate);
                    derivedIntervalCount++;
                }
            }

            previous = sample;
        }

        cancellationToken.ThrowIfCancellationRequested();

        if (sampleCount < 2 || first is null || previous is null)
        {
            throw new InvalidDataException("At least two samples are required for motion analysis.");
        }

        var durationSeconds = previous.TimestampSeconds - first.TimestampSeconds;
        if (!double.IsFinite(durationSeconds))
        {
            throw new InvalidDataException("The capture duration is outside the supported numeric range.");
        }

        return new AnalysisSummary(
            first.SessionId,
            sampleCount,
            first.Sequence,
            previous.Sequence,
            first.TimestampSeconds,
            previous.TimestampSeconds,
            durationSeconds,
            missingSequenceCount,
            sequenceGapCount,
            timingGapCount,
            derivedIntervalCount,
            skippedDerivativeIntervalCount,
            maxHorizontalDerivedSpeed,
            maxAbsoluteDerivedYawRate);
    }

    private static void ValidateOptions(AnalysisOptions options)
    {
        if (!double.IsFinite(options.MaxGapSeconds) || options.MaxGapSeconds <= 0.0)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                options.MaxGapSeconds,
                "MaxGapSeconds must be finite and greater than zero.");
        }

        if (options.MaxSamples < 2)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                options.MaxSamples,
                "MaxSamples must allow at least two samples.");
        }
    }

    private static void ValidateSample(MotionSample sample)
    {
        if (string.IsNullOrWhiteSpace(sample.SessionId))
        {
            throw new InvalidDataException("Every sample must have a nonblank session identifier.");
        }

        if (sample.Sequence < 0)
        {
            throw new InvalidDataException("Sample sequence numbers cannot be negative.");
        }

        if (!double.IsFinite(sample.TimestampSeconds) || sample.TimestampSeconds < 0.0)
        {
            throw new InvalidDataException("Sample timestamps must be finite and nonnegative.");
        }

        if (!double.IsFinite(sample.X)
            || !double.IsFinite(sample.Y)
            || !double.IsFinite(sample.Z)
            || !double.IsFinite(sample.YawRadians))
        {
            throw new InvalidDataException("Sample coordinates and yaw must be finite.");
        }
    }

    private static double CalculateHorizontalSpeed(
        MotionSample previous,
        MotionSample current,
        double intervalSeconds)
    {
        var deltaX = current.X - previous.X;
        var deltaZ = current.Z - previous.Z;

        if (!double.IsFinite(deltaX) || !double.IsFinite(deltaZ))
        {
            throw new InvalidDataException("A coordinate delta is outside the supported numeric range.");
        }

        var distance = double.Hypot(deltaX, deltaZ);
        var speed = distance / intervalSeconds;
        if (!double.IsFinite(distance) || !double.IsFinite(speed))
        {
            throw new InvalidDataException("A derived horizontal speed is outside the supported numeric range.");
        }

        return speed;
    }

    private static double CalculateAbsoluteYawRate(
        MotionSample previous,
        MotionSample current,
        double intervalSeconds)
    {
        // Reduce each operand first so subtracting two valid but extreme angles cannot overflow.
        var previousYaw = Math.IEEERemainder(previous.YawRadians, FullTurnRadians);
        var currentYaw = Math.IEEERemainder(current.YawRadians, FullTurnRadians);
        var shortestDelta = Math.IEEERemainder(currentYaw - previousYaw, FullTurnRadians);
        var rate = Math.Abs(shortestDelta) / intervalSeconds;

        if (!double.IsFinite(rate))
        {
            throw new InvalidDataException("A derived yaw rate is outside the supported numeric range.");
        }

        return rate;
    }
}
