using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

/// <summary>
/// Exact-build, read-only kind-3 Mana field acquisition. This field reader
/// verifies the retained live descriptor fingerprint, brackets stable pointer
/// and record inputs, samples the mutable game clock from the pinned session,
/// and rechecks the caller's player-owner snapshot. It never invokes a game
/// getter or updates the game's resource cache.
/// </summary>
internal static class CurrentBuildManaCandidateField
{
    private const ulong RecordVtableRva = 0x2A6ACD8;
    private const ulong DescriptorGetterRva = 0x1CCB460;
    private const ulong DescriptorGlobalRva = 0x34D8990;
    private const ulong DescriptorVtableRva = 0x2A7C418;
    private const ulong TypeGetterRva = 0x1CF9F10;

    internal static CurrentBuildVitalCandidate Read(IReadOnlyNativeMemorySession session,
        NativeProcessIdentity expectedIdentity, ulong componentAddress, ulong disallowedRecordAddress,
        Action verifyOwnerUnchanged)
    {
        ArgumentNullException.ThrowIfNull(session);
        ArgumentNullException.ThrowIfNull(verifyOwnerUnchanged);
        if (session.Identity != expectedIdentity || expectedIdentity.ProcessId <= 0 ||
            expectedIdentity.ProcessStartUtcTicks <= 0 ||
            !string.Equals(expectedIdentity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256,
                StringComparison.OrdinalIgnoreCase) ||
            expectedIdentity.ModuleSize < DescriptorGlobalRva + 8)
            throw new InvalidDataException("Mana requires the exact current-build process epoch.");

        var component = Pointer(componentAddress);
        var module = Pointer(expectedIdentity.ModuleBaseAddress);
        var anchors = new List<(ulong Address, byte[] Bytes)>();
        byte[] Take(ulong address, int length, bool bracket = true)
        {
            var bytes = CurrentBuildPlayerLookup.Exact(session, address, length);
            if (bracket) anchors.Add((address, bytes.ToArray()));
            return bytes;
        }
        ulong Ptr(ulong address) => Pointer(U64(Take(address, 8)));

        var clockOwner = Ptr(checked(module + 0x33DC2B0));
        // The clock value is sampled from this exact process and may advance
        // normally. Bracket its owner pointer, not the mutable clock bytes.
        var gameClock = F32(Take(checked(clockOwner + 0x18), 4, false));
        var kindOwner = Ptr(checked(component + 0x40));
        if (I32(Take(checked(kindOwner + 0x168), 4)) != 3)
            throw new InvalidDataException("Mana field requires resource kind three.");
        var wrapper = Ptr(checked(component + 0x38));
        var wrapperRaw = Take(wrapper, 48);
        var reference = Pointer(U64(wrapperRaw.AsSpan(0x10, 8)));
        var record = Ptr(reference);
        if (record == disallowedRecordAddress)
            throw new InvalidDataException("Health/resource record alias.");
        var recordRaw = Take(record, 64);

        if (U64(recordRaw) != checked(module + RecordVtableRva) ||
            U64(Take(checked(module + RecordVtableRva + 0x40), 8)) !=
                checked(module + DescriptorGetterRva) ||
            U64(Take(checked(module + DescriptorGlobalRva), 8)) !=
                checked(module + DescriptorVtableRva) ||
            U64(Take(checked(module + DescriptorVtableRva + 8), 8)) !=
                checked(module + TypeGetterRva))
            throw new InvalidDataException("Mana exact-build type fingerprint mismatch.");

        var candidate = Calculate(recordRaw, wrapperRaw, gameClock);
        foreach (var anchor in anchors)
            if (!Take(anchor.Address, anchor.Bytes.Length, false).AsSpan().SequenceEqual(anchor.Bytes))
                throw new InvalidDataException("Mana ownership, type or arithmetic inputs changed during capture.");
        verifyOwnerUnchanged();
        if (session.Identity != expectedIdentity)
            throw new InvalidDataException("Mana player owner or process epoch changed during capture.");
        return candidate;
    }

    internal static CurrentBuildVitalCandidate Calculate(byte[] record, byte[] wrapper, float gameClock)
    {
        if (record.Length != 64 || wrapper.Length != 48)
            return Missing("mana-input-size");
        var rate = I32(record.AsSpan(0x18));
        var baseline = I32(record.AsSpan(0x1C));
        var revision = I32(record.AsSpan(0x20));
        var maximum = I32(record.AsSpan(0x24));
        var wrapperRevision = I32(wrapper.AsSpan(0x1C));
        var wrapperClock = F32(wrapper.AsSpan(0x24));
        var inputs = new
        {
            baseRaw = baseline,
            maximumRaw = maximum,
            rateRaw = rate,
            recordRevision = revision,
            wrapperRevision,
            wrapperClock = FiniteOrNull(wrapperClock),
            gameClock = FiniteOrNull(gameClock),
            verifiedTypeCode = "0x072A"
        };
        if (revision != wrapperRevision)
            return Missing("revision-mismatch-needs-native-cache-write", inputs);
        if (baseline < 0 || maximum <= 0)
            return Missing("outside-normal-integer-domain", inputs);
        if (!float.IsFinite(gameClock) || !float.IsFinite(wrapperClock))
            return Missing("invalid-float-input", inputs);
        var elapsed = gameClock - wrapperClock;
        if (!float.IsFinite(elapsed) || elapsed < 0 || (double)elapsed >= 2147483648d)
            return Missing("clock-delta-outside-normal-domain", inputs);
        var scaledRate = (float)rate * BitConverter.Int32BitsToSingle(unchecked((int)0xBC23D70A));
        var product = scaledRate * elapsed;
        if (!float.IsFinite(product) || (double)product <= int.MinValue || (double)product >= int.MaxValue)
            return Missing("int32-conversion-overflow-or-sentinel", inputs);
        var adjusted = (long)baseline - (int)Math.Truncate(product);
        if (adjusted is < int.MinValue or > int.MaxValue)
            return Missing("signed32-subtraction-overflow", inputs);
        return new("calculated-candidate", null, Math.Clamp(adjusted, 0, maximum), maximum, inputs);
    }

    private static CurrentBuildVitalCandidate Missing(string reason, object? inputs = null) =>
        new("unavailable", reason, Inputs: inputs);
    private static float? FiniteOrNull(float value) => float.IsFinite(value) ? value : null;
    private static ulong Pointer(ulong value) => CurrentBuildPlayerLookup.Pointer(value);
    private static ulong U64(ReadOnlySpan<byte> bytes) => BinaryPrimitives.ReadUInt64LittleEndian(bytes);
    private static int I32(ReadOnlySpan<byte> bytes) => BinaryPrimitives.ReadInt32LittleEndian(bytes);
    private static float F32(ReadOnlySpan<byte> bytes) => BitConverter.Int32BitsToSingle(I32(bytes));
}
