using System.Buffers.Binary;
using System.Globalization;
using System.Text.Json.Serialization;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

internal sealed record CurrentBuildMatrixDescriptorCandidate(
    int SourceOffset, uint[] RawBits, float[]? RowMajorF32, string Status,
    double? OrthonormalError, double? Determinant, double? YPlanarError,
    double? PlanarAngleRadiansCandidate, double? PlanarAngleDegreesCandidate);

internal sealed record CurrentBuildOrientationCandidate(
    NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc,
    [property: JsonIgnore] ulong UnitKey, ulong ComponentAddress,
    [property: JsonIgnore] ulong RefreshHandleRaw, byte RefreshFlagRaw,
    CurrentBuildMatrixDescriptorCandidate Primary, CurrentBuildMatrixDescriptorCandidate Secondary)
{
    [JsonPropertyName("unitKey")]
    public string UnitKeyDecimal => UnitKey.ToString(CultureInfo.InvariantCulture);
    [JsonPropertyName("refreshHandleRaw")]
    public string RefreshHandleHex => $"0x{RefreshHandleRaw:X16}";
    public string Qualification => "matrix-descriptor-candidate-only; body-facing/axis/sign/passive-freshness/restart-unverified";
}

/// <summary>
/// Reads the exact-build player-owned position matrices, never a public heading.
/// Static provenance: native-current-coordinate-code-map.md, 6983F0/698410/6996C0.
/// Cached/fallback matrices can be stale even when every consumed byte is stable.
/// A future publishing caller must separately await session.RevalidateAsync before publication.
/// </summary>
internal static class CurrentBuildOrientationCandidateReader
{
    private const ulong PositionIndexRva = 0x2F588A0;
    internal static CurrentBuildOrientationCandidate Read(IReadOnlyNativeMemorySession session) =>
        Read(session, source =>
        {
            var owner = CurrentBuildPlayerLookup.Resolve(source);
            return new(owner.PlayerKey, owner.EntityAddress, owner.ResolveComponent(PositionIndexRva), owner.VerifyUnchanged);
        });

    internal static CurrentBuildOrientationCandidate Read(IReadOnlyNativeMemorySession session,
        Func<IReadOnlyNativeMemorySession, CurrentBuildPositionOwnerSnapshot> resolveOwner,
        PosePayloadCheck? check = null)
    {
        ArgumentNullException.ThrowIfNull(session);
        ArgumentNullException.ThrowIfNull(resolveOwner);
        var started = DateTimeOffset.UtcNow;
        var identity = session.Identity;
        if (!string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase)
            || identity.ProcessId <= 0 || identity.ProcessStartUtcTicks <= 0 || identity.ModuleSize < PositionIndexRva + 4)
            throw new InvalidDataException("Orientation candidate requires exact build and process epoch.");
        var owner = resolveOwner(session);
        ArgumentNullException.ThrowIfNull(owner.VerifyUnchanged);
        if (owner.UnitKey == 0) throw new InvalidDataException("Missing position owner.");
        var component = CurrentBuildPlayerLookup.Pointer(owner.ComponentAddress, 0x110);
        var raw = CurrentBuildPlayerLookup.Exact(session, component, 0x110);
        var primary = Decode(raw.AsSpan(0x60, 0x24), 0x60);
        var secondary = Decode(raw.AsSpan(0x94, 0x24), 0x94);
        var reread = CurrentBuildPlayerLookup.Exact(session, checked(component + 0x48), 0x70);
        // Unknown bytes between the XYZ/matrix fields keep their strict guard.
        CurrentBuildPlayerLookup.RequireSame(reread.AsSpan(0x0C, 12).ToArray(), raw.AsSpan(0x54, 12).ToArray());
        CurrentBuildPlayerLookup.RequireSame(reread.AsSpan(0x3C, 4).ToArray(), raw.AsSpan(0x84, 4).ToArray());
        PosePayloadCheck.Verify(reread.AsSpan(0, 12), raw.AsSpan(0x48, 12), "entity XYZ", check);
        PosePayloadCheck.Verify(reread.AsSpan(0x18, 0x24), raw.AsSpan(0x60, 0x24), "primary matrix", check);
        PosePayloadCheck.Verify(reread.AsSpan(0x40, 12), raw.AsSpan(0x88, 12), "secondary XYZ", check);
        PosePayloadCheck.Verify(reread.AsSpan(0x4C, 0x24), raw.AsSpan(0x94, 0x24), "secondary matrix", check);
        CurrentBuildPlayerLookup.RequireSame(
            CurrentBuildPlayerLookup.Exact(session, checked(component + 0x100), 9), raw.AsSpan(0x100, 9).ToArray());
        owner.VerifyUnchanged();
        if (session.Identity != identity) throw new InvalidDataException("Orientation process identity changed.");
        return new(identity, started, DateTimeOffset.UtcNow, owner.UnitKey, component,
            BinaryPrimitives.ReadUInt64LittleEndian(raw.AsSpan(0x100, 8)), raw[0x108], primary, secondary);
    }

    internal static CurrentBuildMatrixDescriptorCandidate Decode(ReadOnlySpan<byte> raw, int offset)
    {
        if (raw.Length != 0x24) throw new InvalidDataException("Matrix read hole.");
        var bits = new uint[9];
        var values = new float[9];
        for (var i = 0; i < 9; i++)
        {
            bits[i] = BinaryPrimitives.ReadUInt32LittleEndian(raw.Slice(i * 4, 4));
            values[i] = BitConverter.Int32BitsToSingle(unchecked((int)bits[i]));
        }
        if (values.Any(value => !float.IsFinite(value)))
            return new(offset, bits, null, "nonfinite-matrix", null, null, null, null, null);
        // Use doubles for diagnostics: finite float32 products must not overflow float32.
        var v = values.Select(value => (double)value).ToArray();
        double orthogonalError = 0;
        for (var row = 0; row < 3; row++)
            for (var other = 0; other < 3; other++)
            {
                double dot = 0;
                for (var col = 0; col < 3; col++) dot += v[row * 3 + col] * v[other * 3 + col];
                orthogonalError = Math.Max(orthogonalError, Math.Abs(dot - (row == other ? 1 : 0)));
            }
        var determinant = v[0] * (v[4] * v[8] - v[5] * v[7])
            - v[1] * (v[3] * v[8] - v[5] * v[6]) + v[2] * (v[3] * v[7] - v[4] * v[6]);
        var planarError = new[] { Math.Abs(v[1]), Math.Abs(v[3]), Math.Abs(v[5]), Math.Abs(v[7]),
            Math.Abs(v[4] - 1), Math.Abs(v[8] - v[0]), Math.Abs(v[2] + v[6]) }.Max();
        var structural = Math.Max(Math.Max(orthogonalError, Math.Abs(determinant - 1)), planarError) < 0.01;
        double? radians = structural ? Math.Atan2(v[6], v[0]) : null;
        return new(offset, bits, values, structural ? "structural-y-planar-matrix-candidate" : "unqualified-matrix-shape",
            orthogonalError, determinant, planarError, radians, radians * 180 / Math.PI);
    }
}
