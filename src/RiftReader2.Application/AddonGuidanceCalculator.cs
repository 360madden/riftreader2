using System.Globalization;
using System.Text.RegularExpressions;
using RiftReader2.Domain;

namespace RiftReader2.Application;

public sealed record AddonGuidanceOrigin(
    string SourcePath,
    string EnvelopeSha256,
    string AddonFrameSha256,
    string SourceKind,
    string BindingStatus,
    string FreshnessStatus,
    string HashProvenance,
    string? SnapshotFileSha256,
    AddonGuidanceSnapshotProvenance? Snapshot);

public sealed record AddonGuidanceSnapshotTarget(
    int ProcessId,
    long ProcessStartUtcTicks,
    string ExecutablePath,
    string ExecutableSha256);

public sealed record AddonGuidanceSnapshotReader(
    string InstanceId,
    long SnapshotSequence,
    string Nonce);

public sealed record AddonGuidanceSnapshotProvenance(
    AddonGuidanceSnapshotTarget Target,
    AddonGuidanceSnapshotReader Reader,
    string CapturedAtUtc,
    long ScanStartedAtTimestamp,
    long PublishedAtTimestamp,
    long LastAdvanceAtTimestamp,
    double SnapshotAgeMilliseconds,
    double EffectiveLastAdvanceAgeMilliseconds,
    double FreshnessTimeoutMilliseconds,
    double AssumedUtcSkewBoundMilliseconds,
    string ClockAssumption);

public sealed record AddonGuidancePoint(double X, double Y, double Z);

public sealed record AddonGuidanceVector(
    double DeltaX,
    double DeltaY,
    double DeltaZ,
    double VerticalDelta,
    double PlanarDistance,
    double? CoordinateAxisBearingDegrees,
    string BearingMeaning);

public sealed record AddonGuidanceReport(
    int SchemaVersion,
    string EvidenceKind,
    string Lab,
    string SessionId,
    long ResultSequence,
    long SourceEpoch,
    long SourceSequence,
    double SourceClock,
    string PlayerId,
    AddonGuidancePoint Source,
    AddonGuidancePoint Destination,
    AddonGuidanceVector Calculation,
    AddonGuidanceOrigin Origin,
    string FreshnessStatus,
    string DeliveryMode,
    string SlashCommand);

public static partial class AddonGuidanceCalculator
{
    public const long MaxExactInteger = 9_007_199_254_740_991;
    public const double MaxCoordinateMagnitude = 10_000_000;
    public const double MaxDeltaMagnitude = 20_000_000;
    public const double MaxPlanarDistance = 30_000_000;
    public const int MaxSlashCommandLength = 512;
    public const int MaxNumericTokenLength = 32;

    [GeneratedRegex("^[A-Za-z0-9_]{1,128}$", RegexOptions.CultureInvariant)]
    private static partial Regex PlayerIdPattern();

    public static AddonGuidanceReport Calculate(
        LiveAddonFrame frame,
        string sourcePath,
        string lab,
        string sessionId,
        long resultSequence,
        double destinationX,
        double destinationY,
        double destinationZ,
        AddonGuidanceOrigin? sourceOrigin = null)
    {
        ArgumentNullException.ThrowIfNull(frame);
        if (lab is not ("lab1" or "lab2"))
            throw new ArgumentException("Lab must be lab1 or lab2.", nameof(lab));
        if (!string.Equals(frame.Challenge, sessionId, StringComparison.Ordinal))
            throw new ArgumentException("Session id does not match the live addon envelope.", nameof(sessionId));
        ValidateSession(sessionId);
        ValidateCounter(resultSequence, nameof(resultSequence));

        var observation = frame.Observation;
        ValidateCounter(observation.Epoch, "source epoch");
        ValidateCounter(observation.Sequence, "source sequence");
        var clock = RequireNumber(observation.Clock, "clock", nonnegative: true);
        if (clock > MaxExactInteger)
            throw new InvalidDataException($"Addon clock must not exceed {MaxExactInteger}.");
        var player = RequirePlayer(observation.Player);
        var sourceX = RequireNumber(observation.Fields.CoordX, "coordX");
        var sourceY = RequireNumber(observation.Fields.CoordY, "coordY");
        var sourceZ = RequireNumber(observation.Fields.CoordZ, "coordZ");
        ValidateCoordinate(sourceX, "source X");
        ValidateCoordinate(sourceY, "source Y");
        ValidateCoordinate(sourceZ, "source Z");
        ValidateCoordinate(destinationX, "destination X");
        ValidateCoordinate(destinationY, "destination Y");
        ValidateCoordinate(destinationZ, "destination Z");

        var deltaX = destinationX - sourceX;
        var deltaY = destinationY - sourceY;
        var deltaZ = destinationZ - sourceZ;
        ValidateDelta(deltaX, "delta X");
        ValidateDelta(deltaY, "delta Y");
        ValidateDelta(deltaZ, "delta Z");
        var distance = Math.Sqrt((deltaX * deltaX) + (deltaZ * deltaZ));
        if (!double.IsFinite(distance) || distance > MaxPlanarDistance)
            throw new InvalidDataException("Planar distance is outside the supported range.");
        double? bearing = distance == 0
            ? null
            : NormalizeDegrees(Math.Atan2(deltaZ, deltaX) * 180 / Math.PI);

        var slash = string.Join(' ',
            "/rr2guide", "result", lab, sessionId,
            F(resultSequence), F(observation.Epoch), F(observation.Sequence), F(clock), player,
            F(sourceX), F(sourceY), F(sourceZ), F(distance), F(deltaX), F(deltaZ), F(deltaY));
        if (slash.Length > MaxSlashCommandLength || slash.Any(c => c is < (char)0x20 or > (char)0x7e))
            throw new InvalidDataException("Generated guidance command exceeds the bounded ASCII contract.");

        return new(
            1,
            "calculated-addon-guidance/1",
            lab,
            sessionId,
            resultSequence,
            observation.Epoch,
            observation.Sequence,
            clock,
            player,
            new(sourceX, sourceY, sourceZ),
            new(destinationX, destinationY, destinationZ),
            new(deltaX, deltaY, deltaZ, deltaY, distance, bearing,
                "Degrees from positive coordinate X toward positive coordinate Z; not player facing or a cardinal bearing."),
            sourceOrigin ?? new(Path.GetFullPath(sourcePath), frame.EnvelopeSha256, frame.AddonFrameSha256,
                "saved-rr2l1-envelope", "unbound-saved-envelope", "unverified",
                "computed-from-source-bytes", null, null),
            "unverified-until-addon-receipt",
            "operator-mediated-slash-command",
            slash);
    }

    private static double RequireNumber(AddonNumberField field, string name, bool nonnegative = false)
    {
        if (field.Status != AddonFieldStatus.Ok || field.Value is not double value || !double.IsFinite(value) || nonnegative && value < 0)
            throw new InvalidDataException($"Addon {name} must be an available finite value{(nonnegative ? " at least zero" : "")}.");
        return value;
    }

    private static string RequirePlayer(AddonStringField field)
    {
        if (field.Status != AddonFieldStatus.Ok || field.Value is not string value || !PlayerIdPattern().IsMatch(value))
            throw new InvalidDataException("Addon player id must contain 1 to 128 ASCII letters, digits, or underscores.");
        return value;
    }

    private static void ValidateCounter(long value, string name)
    {
        if (value is < 1 or > MaxExactInteger)
            throw new ArgumentOutOfRangeException(name, $"{name} must be from 1 through {MaxExactInteger}.");
    }

    private static void ValidateSession(string value)
    {
        if (value.Length != 32 || value.Any(c => c is not (>= '0' and <= '9') and not (>= 'a' and <= 'f')))
            throw new ArgumentException("Session id must be 32 lowercase hexadecimal characters.", nameof(value));
    }

    private static void ValidateCoordinate(double value, string name)
    {
        if (!double.IsFinite(value) || Math.Abs(value) > MaxCoordinateMagnitude)
            throw new ArgumentOutOfRangeException(name, $"{name} must be finite and within +/-{MaxCoordinateMagnitude}.");
    }

    private static void ValidateDelta(double value, string name)
    {
        if (!double.IsFinite(value) || Math.Abs(value) > MaxDeltaMagnitude)
            throw new InvalidDataException($"{name} is outside the supported range.");
    }

    private static double NormalizeDegrees(double value) => value < 0 ? value + 360 : value;
    private static string F(double value) => BoundedNumericToken(value.ToString("R", CultureInfo.InvariantCulture));
    private static string F(long value) => BoundedNumericToken(value.ToString(CultureInfo.InvariantCulture));

    private static string BoundedNumericToken(string value)
    {
        if (value.Length > MaxNumericTokenLength)
            throw new InvalidDataException("Generated guidance numeric token exceeds 32 ASCII characters.");
        return value;
    }
}
