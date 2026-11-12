using System.Buffers.Binary;
using System.Globalization;
using System.Text.Json.Serialization;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

internal sealed record CurrentBuildFacingCandidate(
    NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc,
    [property: JsonIgnore] ulong PlayerKey, [property: JsonIgnore] ulong PlayerEntity,
    [property: JsonIgnore] ulong PlayerSystem, uint[] RawBits,
    float PlayerSystemYawRadiansCandidate, double PlayerSystemBearingDegreesCandidate,
    CurrentBuildXyz PositionCandidate, CurrentBuildXyz CameraAimPointCandidate,
    double? CameraAimBearingDegreesCandidate, CurrentBuildOrientationCandidate PositionOrientationCandidate)
{
    public string PlayerKeyDecimal => PlayerKey.ToString(CultureInfo.InvariantCulture);
    public string PlayerEntityDecimal => PlayerEntity.ToString(CultureInfo.InvariantCulture);
    public string PlayerSystemDecimal => PlayerSystem.ToString(CultureInfo.InvariantCulture);
    public string BearingConvention => "degrees-from-positive-z-toward-positive-x";
    public int CaptureAttempts { get; init; } = 1;
    public bool HeadingQualified => false;
    public bool CameraYawQualified => false;
    public CurrentBuildOpticalCameraCandidate? OpticalCameraCandidate { get; init; }
    public CurrentBuildXyz? EntityPositionCandidate { get; init; }
    public uint[]? EntityPositionRawBits { get; init; }
    public CurrentBuildPairedPositionObservation? TargetPositionPairCandidate { get; init; }
    public CurrentBuildOpticalCameraCandidate? OpticalCameraAfterTargetCandidate { get; init; }
    public bool? TargetProjectionCameraStableCandidate { get; init; }
    public double? PrimaryBearingDegreesCandidate =>
        PositionOrientationCandidate.Primary is { Status: "structural-y-planar-matrix-candidate", RowMajorF32: { } matrix }
            ? Wrap180(Math.Atan2(matrix[2], matrix[8]) * 180 / Math.PI) : null;
    public double? BodyBearingDegreesCandidate => PositionOrientationCandidate.Secondary.PlanarAngleDegreesCandidate is double angle
        ? Wrap180(-angle) : null;
    public double? PlayerSystemMinusPrimaryDegreesCandidate => PrimaryBearingDegreesCandidate is double angle
        ? Wrap180(PlayerSystemBearingDegreesCandidate - angle) : null;
    public double? PlayerSystemMinusBodyDegreesCandidate => BodyBearingDegreesCandidate is double angle
        ? Wrap180(PlayerSystemBearingDegreesCandidate - angle) : null;
    public string Qualification => "facing-sources-candidate-only; see source-specific evidence; restart recovery unverified";
    private static double Wrap180(double value) => ((value + 180) % 360 + 360) % 360 - 180;
}

internal sealed record CurrentBuildFacingOwner(ulong Key, ulong Entity, ulong System, Action Verify);

// Only explicitly recognized pose values may defer a mismatch. All owner,
// epoch, refresh, type, read-hole and other failures still abort the caller.
internal sealed class PosePayloadCheck
{
    internal string? ChangedField { get; private set; }

    internal static void Verify(ReadOnlySpan<byte> current, ReadOnlySpan<byte> first,
        string field, PosePayloadCheck? attempt)
    {
        if (current.SequenceEqual(first)) return;
        if (attempt is null) throw new InvalidDataException($"Native pose payload changed: {field}.");
        attempt.ChangedField ??= field;
    }
}

internal static class CurrentBuildFacingCandidateReader
{
    internal static CurrentBuildFacingCandidate ReadStableObservation(
        IReadOnlyNativeMemorySession session, CancellationToken token)
    {
        var lookup = CurrentBuildPlayerLookup.Resolve(session);
        var component = lookup.ResolveComponent(CurrentBuildPositionCandidateReader.PositionIndexRva);
        var owner = new CurrentBuildFacingOwner(lookup.PlayerKey, lookup.EntityAddress,
            lookup.PlayerSystemAddress, lookup.VerifyUnchanged);
        var positionOwner = new CurrentBuildPositionOwnerSnapshot(lookup.PlayerKey,
            lookup.EntityAddress, component, lookup.VerifyUnchanged);
        return ReadStableObservation(check => Read(session, _ => owner,
            source => CurrentBuildOrientationCandidateReader.Read(source, _ => positionOwner, check), check),
            token, TimeProvider.System);
    }

    internal static CurrentBuildFacingCandidate ReadStableObservation(
        Func<PosePayloadCheck, CurrentBuildFacingCandidate> read, CancellationToken token, TimeProvider clock)
    {
        var started = clock.GetTimestamp();
        var budget = TimeSpan.FromMilliseconds(100);
        for (var number = 1; ; number++)
        {
            token.ThrowIfCancellationRequested();
            if (number > 1 && clock.GetElapsedTime(started) >= budget)
                throw new InvalidDataException("Native facing payload reacquisition exceeded 100 ms.");
            var check = new PosePayloadCheck();
            var sample = read(check);
            token.ThrowIfCancellationRequested();
            var elapsed = clock.GetElapsedTime(started);
            if (number > 1 && elapsed >= budget)
                throw new InvalidDataException("Native facing payload reacquisition exceeded 100 ms.");
            if (check.ChangedField is null)
                return sample with { CaptureAttempts = number };
            if (number == 3 || elapsed >= budget)
                throw new InvalidDataException($"Native facing {check.ChangedField} remained unstable after {number} attempt(s).");
        }
    }

    internal static CurrentBuildFacingCandidate Read(IReadOnlyNativeMemorySession session) =>
        Read(session, source =>
        {
            var lookup = CurrentBuildPlayerLookup.Resolve(source);
            return new(lookup.PlayerKey, lookup.EntityAddress, lookup.PlayerSystemAddress,
                       lookup.VerifyUnchanged);
        }, CurrentBuildOrientationCandidateReader.Read);

    internal static CurrentBuildFacingCandidate Read(IReadOnlyNativeMemorySession session,
        Func<IReadOnlyNativeMemorySession, CurrentBuildFacingOwner> resolve,
        Func<IReadOnlyNativeMemorySession, CurrentBuildOrientationCandidate> readOrientation,
        PosePayloadCheck? check = null)
    {
        var identity = session.Identity;
        if (identity.ProcessId <= 0 || identity.ProcessStartUtcTicks <= 0 ||
            !string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256,
                           StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Facing requires the exact current game build and epoch.");
        var started = DateTimeOffset.UtcNow;
        var owner = resolve(session);
        if (owner.Key == 0) throw new InvalidDataException("Facing player key is missing.");
        var system = CurrentBuildPlayerLookup.Pointer(owner.System, 0x400);
        var entity = CurrentBuildPlayerLookup.Pointer(owner.Entity, 128);
        var cached = CurrentBuildPlayerLookup.Exact(session, system + 0x3F8, 8);
        if (BinaryPrimitives.ReadUInt64LittleEndian(cached) != entity)
            throw new InvalidDataException("Facing cached player entity mismatch.");
        var yaw = CurrentBuildPlayerLookup.Exact(session, system + 0x304, 4);
        var aim = CurrentBuildPlayerLookup.Exact(session, system + 0x30C, 12);
        var xyz = CurrentBuildPlayerLookup.Exact(session, system + 0x320, 12);
        var payload = yaw.Concat(aim).Concat(xyz).ToArray();
        var bits = new uint[7];
        var values = new float[7];
        for (var i = 0; i < values.Length; i++)
        {
            bits[i] = BinaryPrimitives.ReadUInt32LittleEndian(payload.AsSpan(i * 4));
            values[i] = BitConverter.UInt32BitsToSingle(bits[i]);
        }
        if (values.Any(value => !float.IsFinite(value)))
            throw new InvalidDataException("Facing contains nonfinite yaw or coordinates.");
        var orientation = readOrientation(session);
        if (orientation.Identity != identity || orientation.UnitKey != owner.Key)
            throw new InvalidDataException("Facing orientation player or epoch mismatch.");
        // Use the entity position component, rather than the downstream player-system
        // copy, for current coordinate arithmetic. Reuse the existing type/backlink checks.
        var entityPosition = CurrentBuildPositionCandidateReader.ReadOwned(session,
            _ => new(owner.Key, entity, orientation.ComponentAddress, owner.Verify), check);
        var camera = CurrentBuildOpticalCameraCandidateReader.TryRead(session, system);
        PosePayloadCheck.Verify(CurrentBuildPlayerLookup.Exact(session, system + 0x304, 4), yaw, "yaw", check);
        PosePayloadCheck.Verify(CurrentBuildPlayerLookup.Exact(session, system + 0x30C, 12), aim, "aim", check);
        PosePayloadCheck.Verify(CurrentBuildPlayerLookup.Exact(session, system + 0x320, 12), xyz, "player-system XYZ", check);
        CurrentBuildPlayerLookup.RequireSame(CurrentBuildPlayerLookup.Exact(session, system + 0x3F8, 8), cached);
        owner.Verify();
        if (session.Identity != identity) throw new InvalidDataException("Facing process epoch changed.");
        var dx = (double)values[1] - values[4];
        var dz = (double)values[3] - values[6];
        var degrees = values[0] * 180.0 / Math.PI;
        var wrapped = ((degrees + 180) % 360 + 360) % 360 - 180;
        return new(identity, started, DateTimeOffset.UtcNow, owner.Key, entity, system, bits,
            values[0], wrapped, new(values[4], values[5], values[6]),
            new(values[1], values[2], values[3]),
            dx == 0 && dz == 0 ? null : Math.Atan2(dx, dz) * 180 / Math.PI, orientation)
        {
            OpticalCameraCandidate = camera,
            EntityPositionCandidate = entityPosition.Position,
            EntityPositionRawBits = [BitConverter.SingleToUInt32Bits(entityPosition.Position.X),
                                     BitConverter.SingleToUInt32Bits(entityPosition.Position.Y),
                                     BitConverter.SingleToUInt32Bits(entityPosition.Position.Z)]
        };
    }
}
