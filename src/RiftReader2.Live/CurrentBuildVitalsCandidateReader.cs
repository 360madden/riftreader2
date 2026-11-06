using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

internal sealed record CurrentBuildVitalsOwnerSnapshot(ulong UnitKey, ulong ComponentAddress, Action VerifyUnchanged);
internal sealed record CurrentBuildVitalCandidate(string Status, string? UnavailableReason,
    long? Current = null, long? Maximum = null, object? Inputs = null);
internal sealed record CurrentBuildVitalsObservation(NativeProcessIdentity Identity,
    DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc, ulong UnitKey,
    CurrentBuildVitalCandidate Health, CurrentBuildVitalCandidate Energy)
{
    public CurrentBuildVitalCandidate Mana { get; init; } =
        new("unavailable", "not-mana-kind-three");
    public string Source => "native-process-memory";
    public string Qualification => "candidate-only; semantics/passive-freshness/restart-unverified";
}

/// <summary>
/// Exact-build passive HP/Mana/Energy candidate acquisition. The caller supplies the shared
/// current-player/dynamic-health-component snapshot; its required verification closure
/// must retain and compare the original lookup-path anchors across this capture.
/// No native getter is called and no revision, clock or reference count is written.
/// </summary>
internal static class CurrentBuildVitalsCandidateReader
{
    internal static CurrentBuildVitalsObservation Read(IReadOnlyNativeMemorySession session) =>
        Read(session, source =>
        {
            var snapshot = CurrentBuildPlayerLookup.Resolve(source);
            var component = snapshot.ResolveComponent(0x2F57850);
            return new(snapshot.PlayerKey, component, snapshot.VerifyUnchanged);
        });

    internal static CurrentBuildVitalsObservation Read(IReadOnlyNativeMemorySession session,
        Func<IReadOnlyNativeMemorySession, CurrentBuildVitalsOwnerSnapshot> resolveOwner)
    {
        ArgumentNullException.ThrowIfNull(session);
        ArgumentNullException.ThrowIfNull(resolveOwner);
        var identity = session.Identity;
        if (!string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256,
                StringComparison.OrdinalIgnoreCase) || identity.ProcessId <= 0 ||
            identity.ProcessStartUtcTicks <= 0 || identity.ModuleSize < 0x35AEB88)
            throw new InvalidDataException("Current-build vitals require exact build and process epoch.");
        var started = DateTimeOffset.UtcNow;
        var owner = resolveOwner(session);
        ArgumentNullException.ThrowIfNull(owner.VerifyUnchanged);
        if (owner.UnitKey == 0) throw new InvalidDataException("Missing current-player owner.");
        var anchors = new List<(ulong Address, byte[] Bytes)>();
        byte[] Take(ulong address, int length, bool bracket = true)
        {
            if (address < 0x10000 || length is < 1 or > 4096 || address > 0x7FFF_FFFF_FFFFUL - (ulong)length)
                throw new InvalidDataException("Vitals range is outside bounded user memory.");
            var result = session.Read(address, length);
            if (result.Status != "success" || result.Bytes.Length != length)
                throw new InvalidDataException("Vitals memory is unavailable or incomplete.");
            if (bracket) anchors.Add((address, result.Bytes.ToArray()));
            return result.Bytes;
        }
        ulong Ptr(ulong address) => Pointer(U64(Take(address, 8)));
        var component = Pointer(owner.ComponentAddress);
        var module = Pointer(identity.ModuleBaseAddress);
        var clockOwner = Ptr(checked(module + 0x33DC2B0));
        // Clock itself may advance normally; bracket the pointer, not its value.
        var clock = F32(Take(checked(clockOwner + 0x18), 4, false));
        var healthOwner = Ptr(checked(component + 0x28));
        var container = Ptr(checked(healthOwner + 0x40));
        var healthRecord = Ptr(checked(container + 0x640));
        var healthRaw = Take(healthRecord, 128);
        var hpCache = Take(checked(component + 0x30), 8);
        CheckType(healthRaw, 0x2C0EE88, 0x20CCC60, 0x355F430, 0x2C281B0, 0x20F2480);
        var health = CalculateHealth(healthRaw, hpCache, clock);
        var kindOwner = Ptr(checked(component + 0x40));
        var kind = I32(Take(checked(kindOwner + 0x168), 4));
        CurrentBuildVitalCandidate mana;
        CurrentBuildVitalCandidate energy;
        if (kind == 3)
        {
            mana = CurrentBuildManaCandidateField.Read(
                session, identity, component, healthRecord, owner.VerifyUnchanged);
            energy = new("unavailable", "not-energy-kind-four");
        }
        else if (kind == 4)
        {
            mana = new("unavailable", "not-mana-kind-three");
            var wrapper = Ptr(checked(component + 0x38));
            var reference = Ptr(checked(wrapper + 0x10));
            var record = Ptr(reference);
            if (record == healthRecord) throw new InvalidDataException("Health/resource record alias.");
            var raw = Take(record, 64);
            var cache = Take(checked(wrapper + 0x18), 8);
            CheckType(raw, 0x2D19498, 0x231BEB0, 0x35AEB80, 0x2D1D420, 0x233E9B0);
            energy = CalculateEnergy(raw, cache, clock);
        }
        else
        {
            mana = new("unavailable", "not-mana-kind-three");
            energy = new("unavailable", "not-energy-kind-four");
        }
        foreach (var anchor in anchors)
            if (!Take(anchor.Address, anchor.Bytes.Length, false).AsSpan().SequenceEqual(anchor.Bytes))
                throw new InvalidDataException("Vitals ownership, type or mutable inputs changed during capture.");
        owner.VerifyUnchanged();
        if (session.Identity != identity)
            throw new InvalidDataException("Vitals player owner or process epoch changed during capture.");
        return new(identity, started, DateTimeOffset.UtcNow, owner.UnitKey, health, energy)
        {
            Mana = mana
        };

        void CheckType(byte[] raw, ulong vtable, ulong getter, ulong descriptor,
            ulong descriptorVtable, ulong typeGetter)
        {
            if (U64(raw) != checked(module + vtable) ||
                U64(Take(checked(module + vtable + 0x40), 8)) != checked(module + getter) ||
                U64(Take(checked(module + descriptor), 8)) != checked(module + descriptorVtable) ||
                U64(Take(checked(module + descriptorVtable + 8), 8)) != checked(module + typeGetter))
                throw new InvalidDataException("Vitals exact-build type fingerprint mismatch.");
        }
    }

    internal static CurrentBuildVitalCandidate CalculateHealth(byte[] raw, byte[] cache, float clock)
    {
        if (raw.Length != 128 || cache.Length != 8) return Missing("health-input-size");
        var baseline = I64(raw.AsSpan(0x48));
        var maximum = I64(raw.AsSpan(0x50));
        var modifier = I64(raw.AsSpan(0x60));
        var revision = I32(raw.AsSpan(0x68));
        var cachedRevision = I32(cache);
        var cachedClock = F32(cache.AsSpan(4));
        var capA = F32(raw.AsSpan(0x6C));
        var capB = F32(raw.AsSpan(0x70));
        var inputs = new
        {
            baseRaw = baseline,
            maximumRaw = maximum,
            modifierRaw = modifier,
            recordRevision = revision,
            wrapperRevision = cachedRevision,
            wrapperClock = FiniteOrNull(cachedClock),
            gameClock = FiniteOrNull(clock),
            capA = FiniteOrNull(capA),
            capB = FiniteOrNull(capB)
        };
        if (revision != cachedRevision) return Missing("revision-mismatch-needs-native-cache-write", inputs);
        if (baseline is < int.MinValue or > int.MaxValue || maximum is <= 0 or > int.MaxValue ||
            modifier is < int.MinValue or > int.MaxValue) return Missing("outside-normal-integer-domain", inputs);
        if (!float.IsFinite(clock) || !float.IsFinite(cachedClock) || !float.IsFinite(capA) ||
            !float.IsFinite(capB) || capA is < 0 or > 1 || capB is < 0 or > 1)
            return Missing("invalid-float-input", inputs);
        var delta = clock - cachedClock;
        if (!float.IsFinite(delta) || delta < 0 || (double)delta >= int.MaxValue)
            return Missing("clock-delta-outside-normal-domain", inputs);
        var adjustment = Math.Truncate((double)(float)modifier * -0.009999999776482582 * (float)Math.Floor(delta));
        if (adjustment <= long.MinValue || adjustment >= long.MaxValue)
            return Missing("integer-conversion-or-subtraction-overflow", inputs);
        long adjusted;
        try { adjusted = checked(baseline - (long)adjustment); }
        catch (OverflowException) { return Missing("integer-conversion-or-subtraction-overflow", inputs); }
        var value = Math.Clamp(adjusted, 0, maximum);
        var cap = Math.Min(capA, capB);
        if (baseline == 0) value = 0;
        else if ((double)value / maximum > cap) value = (long)Math.Truncate(maximum * (double)cap);
        else if (baseline > 0 && value <= 0) value = 1;
        return new("calculated-candidate", null, value, maximum, inputs);
    }

    internal static CurrentBuildVitalCandidate CalculateEnergy(byte[] raw, byte[] cache, float clock)
    {
        if (raw.Length != 64 || cache.Length != 8) return Missing("energy-input-size");
        var baseline = I32(raw.AsSpan(0x20));
        var maximum = I32(raw.AsSpan(0x24));
        var rate = I32(raw.AsSpan(0x28));
        var revision = I32(raw.AsSpan(0x34));
        var cachedRevision = I32(cache);
        var cachedClock = F32(cache.AsSpan(4));
        var inputs = new
        {
            baseRaw = baseline,
            maximumRaw = maximum,
            rateRaw = rate,
            recordRevision = revision,
            wrapperRevision = cachedRevision,
            wrapperClock = FiniteOrNull(cachedClock),
            gameClock = FiniteOrNull(clock),
            verifiedTypeCode = "0x072B"
        };
        if (revision != cachedRevision) return Missing("revision-mismatch-needs-native-cache-write", inputs);
        if (baseline < 0 || maximum <= 0) return Missing("outside-normal-integer-domain", inputs);
        var elapsed = clock - cachedClock;
        if (!float.IsFinite(clock) || !float.IsFinite(cachedClock) || !float.IsFinite(elapsed) ||
            elapsed < 0 || (double)elapsed >= 2147483648d) return Missing("clock-delta-outside-normal-domain", inputs);
        // Keep the two native MULSS rounding steps separate; never fuse them.
        var scaledRate = (float)rate * BitConverter.Int32BitsToSingle(unchecked((int)0xBC23D70A));
        var product = scaledRate * elapsed;
        if (!float.IsFinite(product) || (double)product <= int.MinValue || (double)product >= int.MaxValue)
            return Missing("int32-conversion-overflow-or-sentinel", inputs);
        var adjusted = (long)baseline - (int)Math.Truncate(product);
        if (adjusted is < int.MinValue or > int.MaxValue) return Missing("signed32-subtraction-overflow", inputs);
        return new("calculated-candidate", null, Math.Clamp(adjusted, 0, maximum), maximum, inputs);
    }

    private static CurrentBuildVitalCandidate Missing(string reason, object? inputs = null) => new("unavailable", reason, Inputs: inputs);
    private static float? FiniteOrNull(float value) => float.IsFinite(value) ? value : null;
    private static ulong Pointer(ulong value) => value >= 0x10000 && value <= 0x7FFF_FFFF_FFFFUL - 8 && value % 8 == 0
        ? value : throw new InvalidDataException("Vitals pointer is invalid.");
    private static ulong U64(ReadOnlySpan<byte> bytes) => BinaryPrimitives.ReadUInt64LittleEndian(bytes);
    private static long I64(ReadOnlySpan<byte> bytes) => BinaryPrimitives.ReadInt64LittleEndian(bytes);
    private static int I32(ReadOnlySpan<byte> bytes) => BinaryPrimitives.ReadInt32LittleEndian(bytes);
    private static float F32(ReadOnlySpan<byte> bytes) => BitConverter.Int32BitsToSingle(I32(bytes));
}
