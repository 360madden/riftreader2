using System.Buffers.Binary;
using System.Text.RegularExpressions;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

internal sealed record CurrentBuildFastManaAnchor(ulong Address, byte[] Bytes);
internal sealed record CurrentBuildFastManaProvenance(
    string VmIdentitySha256, string DescriptorReviewSha256,
    string BeforeOwnerReviewSha256, string AfterOwnerReviewSha256,
    string ReaderSha256, string WorkflowSha256, string OwnerProbeSha256,
    string DescriptorProbeSha256, string SamplerSourceSha256);
internal sealed record CurrentBuildFastManaPinnedRequest(
    NativeProcessIdentity Identity, ulong PlayerUnitKey, ulong ComponentAddress,
    ulong HealthRecordAddress, ulong ResourceWrapperAddress, ulong ReferenceSlotAddress,
    ulong ResourceRecordAddress, ulong ClockOwnerAddress,
    IReadOnlyList<CurrentBuildFastManaAnchor> CachedImmutableAnchors,
    CurrentBuildFastManaProvenance Provenance);
internal sealed record CurrentBuildFastManaStateObservation(
    DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc,
    int RateRaw, int BaseRaw, int MaximumRaw, int RecordRevision,
    int WrapperRevision, int SecondaryRevision, float WrapperClockA,
    float WrapperClockB, float GameClock);
internal sealed record CurrentBuildFastManaPinnedObservation(
    NativeProcessIdentity Identity, ulong PlayerUnitKey,
    DateTimeOffset VerificationStartedAtUtc, DateTimeOffset VerificationCompletedAtUtc,
    CurrentBuildFastManaStateObservation StateA, CurrentBuildFastManaStateObservation StateB,
    CurrentBuildVitalCandidate Mana, string TransitionStatus,
    CurrentBuildFastManaProvenance Provenance)
{
    public string EvidenceKind => "native-mana-fast-sample/1";
    public string Source => "native-process-memory";
    public string Qualification => "candidate-only; semantics/passive-freshness/restart-unverified";
}

/// <summary>
/// Unregistered, bounded fast-path reader for a hash-pinned same-epoch Mana
/// descriptor. Cached bytes are checked, never trusted as current values. The
/// live player chain and resource/type route are verified before and after two
/// live mutable observations. Sequential reads cannot exclude ABA transitions.
/// </summary>
internal static partial class CurrentBuildFastManaPinnedSampler
{
    private const ulong HealthSelectorRva = 0x2F57850, ClockRootRva = 0x33DC2B0;
    private const ulong RecordVtableRva = 0x2A6ACD8, DescriptorGetterRva = 0x1CCB460;
    private const ulong DescriptorGlobalRva = 0x34D8990, DescriptorVtableRva = 0x2A7C418;
    private const ulong TypeGetterRva = 0x1CF9F10;
    [GeneratedRegex("^[0-9A-F]{64}$", RegexOptions.CultureInvariant)]
    private static partial Regex Sha256Pattern();

    internal static async ValueTask<CurrentBuildFastManaPinnedObservation> SampleAsync(
        IReadOnlyNativeMemorySession session, CurrentBuildFastManaPinnedRequest request,
        CancellationToken cancellationToken = default, Func<DateTimeOffset>? utcNow = null)
    {
        ArgumentNullException.ThrowIfNull(session);
        ArgumentNullException.ThrowIfNull(request);
        ValidateRequest(session, request);
        var now = utcNow ?? (() => DateTimeOffset.UtcNow);
        var anchors = request.CachedImmutableAnchors
            .Select(value => new CurrentBuildFastManaAnchor(value.Address, value.Bytes.ToArray())).ToArray();
        var verificationStarted = now();

        var lookup = CurrentBuildPlayerLookup.Resolve(session);
        var component = lookup.ResolveComponent(HealthSelectorRva);
        if (lookup.PlayerKey != request.PlayerUnitKey || component != request.ComponentAddress)
            throw new InvalidDataException("Fast Mana current-player owner differs from the pinned receipt.");
        VerifyCachedAnchors(session, anchors);
        VerifyRoute(session, request);
        var stateA = ReadState(session, request, now);
        var stateB = ReadState(session, request, now);
        var transition = ValidateTransition(stateA, stateB);
        var candidate = CurrentBuildManaCandidateField.Calculate(
            stateB.RecordBytes, stateB.WrapperBytes, stateB.Observation.GameClock);

        // These are intentionally after state B. Cached anchors supplement a
        // fresh full-chain re-resolution; they never replace it.
        VerifyRoute(session, request);
        VerifyCachedAnchors(session, anchors);
        lookup.VerifyUnchanged();
        var invalidated = await session.RevalidateAsync(cancellationToken);
        if (invalidated is not null || session.Identity != request.Identity)
            throw new InvalidDataException("Fast Mana process identity changed during verification.");
        var verificationCompleted = now();
        if (stateA.Observation.StartedAtUtc < verificationStarted ||
            stateA.Observation.CompletedAtUtc < stateA.Observation.StartedAtUtc ||
            stateB.Observation.StartedAtUtc < stateA.Observation.CompletedAtUtc ||
            stateB.Observation.CompletedAtUtc < stateB.Observation.StartedAtUtc ||
            verificationCompleted < stateB.Observation.CompletedAtUtc)
            throw new InvalidDataException("Fast Mana acquisition timestamps are not ordered.");
        if (new[] { verificationStarted, stateA.Observation.StartedAtUtc,
                stateA.Observation.CompletedAtUtc, stateB.Observation.StartedAtUtc,
                stateB.Observation.CompletedAtUtc, verificationCompleted }
            .Any(value => value.Offset != TimeSpan.Zero))
            throw new InvalidDataException("Fast Mana acquisition timestamps must be UTC.");
        return new(request.Identity, request.PlayerUnitKey, verificationStarted, verificationCompleted,
            stateA.Observation, stateB.Observation, candidate, transition, request.Provenance);
    }

    private static void ValidateRequest(IReadOnlyNativeMemorySession session,
        CurrentBuildFastManaPinnedRequest request)
    {
        if (session.Identity != request.Identity || request.Identity.ProcessId <= 0 ||
            request.Identity.ProcessStartUtcTicks <= 0 ||
            !string.Equals(request.Identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256,
                StringComparison.OrdinalIgnoreCase) ||
            request.Identity.ModuleSize < DescriptorGlobalRva + 8 || request.PlayerUnitKey == 0)
            throw new InvalidDataException("Fast Mana requires the exact pinned current-build process epoch.");
        foreach (var (address, length) in new[] { (request.ComponentAddress, 8),
                     (request.HealthRecordAddress, 8), (request.ResourceWrapperAddress, 48),
                     (request.ReferenceSlotAddress, 8), (request.ResourceRecordAddress, 64),
                     (request.ClockOwnerAddress, 8) })
            _ = CurrentBuildPlayerLookup.Pointer(address, length);
        if (request.HealthRecordAddress == request.ResourceRecordAddress)
            throw new InvalidDataException("Fast Mana health/resource records alias.");
        if (request.CachedImmutableAnchors is not { Count: > 0 and <= 256 })
            throw new InvalidDataException("Fast Mana requires bounded cached owner anchors.");
        var ranges = request.CachedImmutableAnchors.Select(anchor =>
        {
            ArgumentNullException.ThrowIfNull(anchor);
            ArgumentNullException.ThrowIfNull(anchor.Bytes);
            if (anchor.Bytes.Length is < 1 or > 4096)
                throw new InvalidDataException("Fast Mana cached anchor size is invalid.");
            if (anchor.Address < 0x10000 ||
                anchor.Address > 0x7FFF_FFFF_FFFFUL - (ulong)anchor.Bytes.Length)
                throw new InvalidDataException("Fast Mana cached anchor range is invalid.");
            return (anchor.Address, End: checked(anchor.Address + (ulong)anchor.Bytes.Length));
        }).OrderBy(value => value.Address).ToArray();
        for (var index = 1; index < ranges.Length; ++index)
            if (ranges[index].Address < ranges[index - 1].End)
                throw new InvalidDataException("Fast Mana cached anchors overlap.");
        ArgumentNullException.ThrowIfNull(request.Provenance);
        foreach (var hash in new[] { request.Provenance.VmIdentitySha256,
                     request.Provenance.DescriptorReviewSha256, request.Provenance.BeforeOwnerReviewSha256,
                     request.Provenance.AfterOwnerReviewSha256, request.Provenance.ReaderSha256,
                     request.Provenance.WorkflowSha256, request.Provenance.OwnerProbeSha256,
                     request.Provenance.DescriptorProbeSha256, request.Provenance.SamplerSourceSha256 })
            if (hash is null || !Sha256Pattern().IsMatch(hash))
                throw new InvalidDataException("Fast Mana provenance SHA256 is invalid.");
    }

    private static void VerifyCachedAnchors(IReadOnlyNativeMemorySession session,
        IReadOnlyList<CurrentBuildFastManaAnchor> anchors)
    {
        foreach (var anchor in anchors)
            CurrentBuildPlayerLookup.RequireSame(
                CurrentBuildPlayerLookup.Exact(session, anchor.Address, anchor.Bytes.Length), anchor.Bytes);
    }

    private static void VerifyRoute(IReadOnlyNativeMemorySession session,
        CurrentBuildFastManaPinnedRequest request)
    {
        var module = request.Identity.ModuleBaseAddress;
        ulong PointerAt(ulong address) => CurrentBuildPlayerLookup.Pointer(U64(
            CurrentBuildPlayerLookup.Exact(session, address, 8)));
        var healthOwner = PointerAt(checked(request.ComponentAddress + 0x28));
        var healthContainer = PointerAt(checked(healthOwner + 0x40));
        if (PointerAt(checked(healthContainer + 0x640)) != request.HealthRecordAddress ||
            PointerAt(checked(request.ComponentAddress + 0x38)) != request.ResourceWrapperAddress ||
            checked(request.ResourceWrapperAddress + 0x10) != request.ReferenceSlotAddress ||
            PointerAt(request.ReferenceSlotAddress) != request.ResourceRecordAddress ||
            PointerAt(checked(module + ClockRootRva)) != request.ClockOwnerAddress)
            throw new InvalidDataException("Fast Mana cached resource route detached.");
        var kindOwner = PointerAt(checked(request.ComponentAddress + 0x40));
        if (I32(CurrentBuildPlayerLookup.Exact(session, checked(kindOwner + 0x168), 4)) != 3)
            throw new InvalidDataException("Fast Mana resource kind is not three.");
        if (U64(CurrentBuildPlayerLookup.Exact(session, request.ResourceRecordAddress, 8)) !=
                checked(module + RecordVtableRva) ||
            PointerAt(checked(module + RecordVtableRva + 0x40)) != checked(module + DescriptorGetterRva) ||
            PointerAt(checked(module + DescriptorGlobalRva)) != checked(module + DescriptorVtableRva) ||
            PointerAt(checked(module + DescriptorVtableRva + 8)) != checked(module + TypeGetterRva))
            throw new InvalidDataException("Fast Mana exact type fingerprint changed.");
    }

    private static State ReadState(IReadOnlyNativeMemorySession session,
        CurrentBuildFastManaPinnedRequest request, Func<DateTimeOffset> now)
    {
        var started = now();
        var wrapper = CurrentBuildPlayerLookup.Exact(session, request.ResourceWrapperAddress, 48);
        var record = CurrentBuildPlayerLookup.Exact(session, request.ResourceRecordAddress, 64);
        var gameClock = F32(CurrentBuildPlayerLookup.Exact(session,
            checked(request.ClockOwnerAddress + 0x18), 4));
        var completed = now();
        if (U64(wrapper.AsSpan(0x10, 8)) != request.ReferenceSlotAddress ||
            U64(record) != checked(request.Identity.ModuleBaseAddress + RecordVtableRva))
            throw new InvalidDataException("Fast Mana mutable snapshot detached from its owner/type.");
        var observation = new CurrentBuildFastManaStateObservation(started, completed,
            I32(record.AsSpan(0x18)), I32(record.AsSpan(0x1C)), I32(record.AsSpan(0x24)),
            I32(record.AsSpan(0x20)), I32(wrapper.AsSpan(0x1C)), I32(wrapper.AsSpan(0x18)),
            F32(wrapper.AsSpan(0x20)), F32(wrapper.AsSpan(0x24)), gameClock);
        return new(wrapper, record, observation);
    }

    private static string ValidateTransition(State before, State after)
    {
        if (!before.WrapperBytes.AsSpan(0, 0x18).SequenceEqual(after.WrapperBytes.AsSpan(0, 0x18)) ||
            !before.WrapperBytes.AsSpan(0x28).SequenceEqual(after.WrapperBytes.AsSpan(0x28)) ||
            !before.RecordBytes.AsSpan(0, 0x18).SequenceEqual(after.RecordBytes.AsSpan(0, 0x18)) ||
            !before.RecordBytes.AsSpan(0x38).SequenceEqual(after.RecordBytes.AsSpan(0x38)))
            throw new InvalidDataException("Fast Mana immutable wrapper or record bytes changed.");
        var a = before.Observation; var b = after.Observation;
        if (a.RecordRevision != a.WrapperRevision || b.RecordRevision != b.WrapperRevision ||
            a.SecondaryRevision != I32(before.RecordBytes.AsSpan(0x28)) ||
            b.SecondaryRevision != I32(after.RecordBytes.AsSpan(0x28)))
            throw new InvalidDataException("Fast Mana mutable revisions are incoherent.");
        var clocksA = new[] { a.WrapperClockA, a.WrapperClockB, a.GameClock };
        var clocksB = new[] { b.WrapperClockA, b.WrapperClockB, b.GameClock };
        if (a.RecordRevision > b.RecordRevision || a.SecondaryRevision > b.SecondaryRevision ||
            clocksA.Concat(clocksB).Any(value => !float.IsFinite(value)) ||
            clocksA.Zip(clocksB).Any(pair => pair.Second < pair.First))
            throw new InvalidDataException("Fast Mana mutable epoch moved backward or has an invalid clock.");
        var primaryPayloadChanged = a.RateRaw != b.RateRaw || a.BaseRaw != b.BaseRaw ||
            a.MaximumRaw != b.MaximumRaw || a.WrapperClockB != b.WrapperClockB;
        if (primaryPayloadChanged && b.RecordRevision <= a.RecordRevision)
            throw new InvalidDataException(
                "Fast Mana primary payload changed without a forward primary revision transition.");
        if (a.WrapperClockA != b.WrapperClockA && b.SecondaryRevision <= a.SecondaryRevision)
            throw new InvalidDataException(
                "Fast Mana secondary clock changed without a forward secondary revision transition.");
        return before.WrapperBytes.AsSpan().SequenceEqual(after.WrapperBytes) &&
            before.RecordBytes.AsSpan().SequenceEqual(after.RecordBytes)
            ? "unchanged" : "coherent-cache-transition";
    }

    private sealed record State(byte[] WrapperBytes, byte[] RecordBytes,
        CurrentBuildFastManaStateObservation Observation);
    private static ulong U64(ReadOnlySpan<byte> value) => BinaryPrimitives.ReadUInt64LittleEndian(value);
    private static int I32(ReadOnlySpan<byte> value) => BinaryPrimitives.ReadInt32LittleEndian(value);
    private static float F32(ReadOnlySpan<byte> value) => BitConverter.Int32BitsToSingle(I32(value));
}
