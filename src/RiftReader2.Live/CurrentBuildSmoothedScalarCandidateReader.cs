using System.Buffers.Binary;
using System.Globalization;
using System.Text.Json.Serialization;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

/// <summary>Four raw float32 candidates from the exact-build entity component. No heading semantics claimed.</summary>
internal sealed record CurrentBuildSmoothedScalarCandidate(
    NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc,
    [property: JsonIgnore] ulong PlayerKey, [property: JsonIgnore] ulong PlayerEntity,
    [property: JsonIgnore] ulong ComponentAddress, uint[] RawBits,
    float CurrentCandidate, float SourceCandidate, float TargetCandidate, float FactorCandidate)
{
    public string PlayerKeyDecimal => PlayerKey.ToString(CultureInfo.InvariantCulture);
    public string PlayerEntityDecimal => PlayerEntity.ToString(CultureInfo.InvariantCulture);
    public string ComponentAddressDecimal => ComponentAddress.ToString(CultureInfo.InvariantCulture);
    public bool HeadingQualified => false;
    public string Qualification =>
        "entity-owned-smoothed-scalar-candidate-only; heading/body/camera semantics and turn response unverified";
}

/// <summary>
/// Selector 0x2F57850 and vtable 0x26AFBA0 are exact-build candidates corroborated
/// by retained health-component samples. Neither fact qualifies +0x88 as heading.
/// </summary>
internal static class CurrentBuildSmoothedScalarCandidateReader
{
    internal const ulong SelectorRva = 0x2F57850;
    internal const ulong ExpectedVtableRva = 0x26AFBA0;

    internal static CurrentBuildSmoothedScalarCandidate Read(IReadOnlyNativeMemorySession session)
    {
        ArgumentNullException.ThrowIfNull(session);
        var lookup = CurrentBuildPlayerLookup.Resolve(session);
        return ReadResolved(session, session.Identity, DateTimeOffset.UtcNow,
            lookup.PlayerKey, lookup.EntityAddress, lookup.ResolveComponent(SelectorRva),
            lookup.VerifyUnchanged);
    }

    internal static CurrentBuildSmoothedScalarCandidate ReadResolved(
        IReadOnlyNativeMemorySession session, NativeProcessIdentity identity,
        DateTimeOffset started, ulong playerKey, ulong playerEntity,
        ulong componentAddress, Action verifyOwner)
    {
        ArgumentNullException.ThrowIfNull(session);
        ArgumentNullException.ThrowIfNull(verifyOwner);
        if (session.Identity != identity || identity.ProcessId <= 0
            || identity.ProcessStartUtcTicks <= 0 || playerKey == 0
            || !string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256,
                StringComparison.OrdinalIgnoreCase)
            || identity.ModuleSize < SelectorRva + 4
            || identity.ModuleSize < ExpectedVtableRva + 8)
            throw new InvalidDataException("Smoothed scalar requires exact current-build process and owner.");
        CurrentBuildPlayerLookup.Pointer(playerEntity, 128);
        var component = CurrentBuildPlayerLookup.Pointer(componentAddress, 0x98);
        var vptr = CurrentBuildPlayerLookup.Exact(session, component, 8);
        if (BinaryPrimitives.ReadUInt64LittleEndian(vptr) !=
            checked(identity.ModuleBaseAddress + ExpectedVtableRva))
            throw new InvalidDataException("Smoothed scalar component vtable mismatch.");
        var backlink = CurrentBuildPlayerLookup.Exact(session, checked(component + 0x10), 8);
        if (BinaryPrimitives.ReadUInt64LittleEndian(backlink) != playerEntity)
            throw new InvalidDataException("Smoothed scalar owner backlink mismatch.");

        var raw = CurrentBuildPlayerLookup.Exact(session, checked(component + 0x88), 16);
        var bits = new uint[4];
        var values = new float[4];
        for (var i = 0; i < 4; i++)
        {
            bits[i] = BinaryPrimitives.ReadUInt32LittleEndian(raw.AsSpan(i * 4, 4));
            values[i] = BitConverter.Int32BitsToSingle(unchecked((int)bits[i]));
            if (!float.IsFinite(values[i]))
                throw new InvalidDataException("Smoothed scalar contains nonfinite candidate.");
        }
        verifyOwner();
        CurrentBuildPlayerLookup.RequireSame(CurrentBuildPlayerLookup.Exact(session, component, 8), vptr);
        CurrentBuildPlayerLookup.RequireSame(
            CurrentBuildPlayerLookup.Exact(session, checked(component + 0x10), 8), backlink);
        CurrentBuildPlayerLookup.RequireSame(
            CurrentBuildPlayerLookup.Exact(session, checked(component + 0x88), 16), raw);
        if (session.Identity != identity)
            throw new InvalidDataException("Smoothed scalar process identity changed.");

        return new(identity, started, DateTimeOffset.UtcNow, playerKey, playerEntity,
            component, bits, values[0], values[1], values[2], values[3]);
    }
}
