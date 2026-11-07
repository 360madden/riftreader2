using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

internal sealed record BuffRawObject(string Status, ulong? VtableRva = null, uint? Dword08 = null,
    ulong? Qword10 = null, ulong? Qword20 = null, ulong? Qword28 = null,
    uint? Dword3C = null, ulong? Qword48 = null, uint? DescriptorDword38 = null,
    ulong? DescriptorVtableRva = null, string? DescriptorStatus = null,
    string? StateStatus = null, uint? StateDword88 = null, string? ClockStatus = null,
    ulong? ClockAddress = null, ulong? ClockVtableRva = null,
    ulong? ClockSlot30Rva = null, ulong? ClockSlot38Rva = null, ulong? ClockSlot48Rva = null);
internal sealed record BuffTimingCandidate(string Status, uint? BeginRawBits = null, float? Begin = null,
    ulong? TimerReference = null, ulong? ReferenceVtableRva = null, ulong? ReferenceGetterRva = null,
    long? DurationTicks = null, float? Duration = null, float? Remaining = null, ulong? ReferenceSlot48Rva = null, uint? DurationInputRawBits = null);
internal sealed record BuffRawNode(ulong Address, ulong Next, ulong Object, ulong Control, BuffRawObject RawObject)
{
    public BuffTimingCandidate? Timing { get; init; }
}
internal sealed record CurrentBuildBuffSeedObservation(NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc,
    DateTimeOffset CompletedAtUtc, ulong UnitKey, ulong Context, ulong Sentinel, IReadOnlyList<BuffRawNode> Nodes)
{
    public string Qualification => "raw-list-candidates; visibility, buff IDs, names, freshness and restart unverified";
    public float? ClockBefore { get; init; }
    public float? ClockAfter { get; init; }
}

internal static class CurrentBuildBuffSeedCandidateReader
{
    internal static CurrentBuildBuffSeedObservation Read(IReadOnlyNativeMemorySession session, bool includeTiming = false)
    {
        var started = DateTimeOffset.UtcNow;
        var lookup = CurrentBuildPlayerLookup.Resolve(session);
        var health = lookup.ResolveComponent(0x2F57850);
        var context = lookup.ResolveComponent(0x2F57260);
        return ReadResolved(session, session.Identity, started, lookup.PlayerKey, lookup.EntityAddress,
            health, context, lookup.VerifyUnchanged, includeTiming);
    }

    internal static CurrentBuildBuffSeedObservation ReadResolved(IReadOnlyNativeMemorySession session,
        NativeProcessIdentity id, DateTimeOffset started, ulong key, ulong entity, ulong health, ulong context,
        Action verifyOwner, bool includeTiming = false)
    {
        if (session.Identity != id || id.ProcessId <= 0 || id.ProcessStartUtcTicks <= 0 || key == 0 ||
            id.ModuleSize < 0x33623E8 || !string.Equals(id.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Invalid buff seed build or epoch.");
        ArgumentNullException.ThrowIfNull(verifyOwner);
        var anchors = new Dictionary<(ulong, int), byte[]>();
        var budget = 0;
        byte[] Read(ulong address, int count, bool anchor = true)
        {
            budget = checked(budget + count);
            if (budget > 2 * 1024 * 1024) throw new InvalidDataException("Buff seed budget exceeded.");
            var value = CurrentBuildPlayerLookup.Exact(session, address, count);
            if (anchor)
            {
                if (anchors.TryGetValue((address, count), out var previous) && !previous.AsSpan().SequenceEqual(value))
                    throw new InvalidDataException("Buff seed changed during capture.");
                anchors[(address, count)] = value.ToArray();
            }
            return value;
        }
        ulong Q(ulong address) => BinaryPrimitives.ReadUInt64LittleEndian(Read(address, 8));
        uint D(ulong address) => BinaryPrimitives.ReadUInt32LittleEndian(Read(address, 4));
        ulong Ptr(ulong value, int length = 8) => CurrentBuildPlayerLookup.Pointer(value, length);
        ulong? Rva(ulong value) => value >= id.ModuleBaseAddress && value - id.ModuleBaseAddress < id.ModuleSize
            ? value - id.ModuleBaseAddress : null;
        bool ValidFieldTable()
        {
            var table = Read(checked(id.ModuleBaseAddress + 0x303E8A8), 48);
            var expected = new HashSet<ulong> { 0x303E860, 0x303E720, 0x303E790, 0x303E828, 0x303E7E0 };
            for (int i = 0; i < 5; i++)
            {
                var pointer = BinaryPrimitives.ReadUInt64LittleEndian(table.AsSpan(i * 8, 8));
                if (pointer < id.ModuleBaseAddress || !expected.Remove(pointer - id.ModuleBaseAddress)) return false;
            }
            return expected.Count == 0 && BinaryPrimitives.ReadUInt64LittleEndian(table.AsSpan(40, 8)) == 0 &&
                Read(checked(id.ModuleBaseAddress + 0x345DE18), 10).AsSpan().SequenceEqual("!8dca2bf7\0"u8) &&
                Read(checked(id.ModuleBaseAddress + 0x345DE48), 10).AsSpan().SequenceEqual("!8f2b42db\0"u8) &&
                Read(checked(id.ModuleBaseAddress + 0x345DE28), 10).AsSpan().SequenceEqual("!a0843f13\0"u8) &&
                Read(checked(id.ModuleBaseAddress + 0x345DE58), 10).AsSpan().SequenceEqual("!1381549c\0"u8);
        }
        var system = Ptr(Q(checked(id.ModuleBaseAddress + 0x33623E0)), 0x400);
        if (Q(checked(system + 0x3F8)) != entity || Q(checked(Ptr(health, 0x18) + 0x10)) != entity ||
            Q(checked(Ptr(context, 0x318) + 0x10)) != entity)
            throw new InvalidDataException("Buff seed owner mismatch.");
        ulong clockAddress = 0; float? clockBefore = null, clockAfter = null;
        float F(uint bits) => BitConverter.Int32BitsToSingle(unchecked((int)bits));
        if (includeTiming)
        {
            clockAddress = Ptr(Q(checked(id.ModuleBaseAddress + 0x33DC2B0)), 0x1C);
            clockBefore = F(BinaryPrimitives.ReadUInt32LittleEndian(Read(clockAddress + 0x18, 4, false)));
            if (!float.IsFinite(clockBefore.Value)) throw new InvalidDataException("Invalid buff clock.");
        }
        var sentinel = checked(context + 0x310);
        var next = Q(sentinel);
        var nodes = new List<BuffRawNode>();
        var seen = new HashSet<ulong>();
        while (next != sentinel)
        {
            var node = Ptr(next, 0x20);
            if (!seen.Add(node) || seen.Count > 256) throw new InvalidDataException("Buff seed cycle or node budget exceeded.");
            next = Q(node);
            var obj = Q(checked(node + 0x10));
            var control = Q(checked(node + 0x18));
            BuffRawObject raw;
            try
            {
                var address = Ptr(obj, 0x50);
                var vt = Q(address); var d08 = D(address + 8); var q10 = Q(address + 0x10);
                var q20 = Q(address + 0x20); var q28 = Q(address + 0x28);
                var d3c = D(address + 0x3C); var q48 = Q(address + 0x48);
                uint? descriptor38 = null; ulong? descriptorVtableRva = null;
                string descriptorStatus = q10 == 0 ? "null" : "unavailable";
                if (q10 != 0)
                {
                    try { var desc = Ptr(q10, 0x3C); descriptorVtableRva = Rva(Q(desc)); descriptor38 = D(desc + 0x38); descriptorStatus = "raw-candidate"; }
                    catch (InvalidDataException) when (budget <= 2 * 1024 * 1024) { }
                }
                string stateStatus = q20 == 0 ? "null" : "unavailable"; uint? state88 = null;
                if (q20 != 0)
                {
                    try { state88 = D(checked(Ptr(q20, 0x8C) + 0x88)); stateStatus = "raw-candidate"; }
                    catch (InvalidDataException) when (budget <= 2 * 1024 * 1024) { }
                }
                string clockStatus = "unavailable"; ulong? clock = null, clockVt = null, slot30 = null, slot38 = null, slot48 = null;
                try
                {
                    clock = Q(checked(address + 0x68));
                    if (clock == 0) clockStatus = "null";
                    else
                    {
                        var timerAddress = Ptr(clock.Value); var vtable = Q(timerAddress); clockVt = Rva(vtable);
                        if (!clockVt.HasValue || clockVt.Value > id.ModuleSize - 0x50) clockStatus = "vtable-outside-module";
                        else
                        {
                            slot30 = Rva(Q(vtable + 0x30)); slot38 = Rva(Q(vtable + 0x38)); slot48 = Rva(Q(vtable + 0x48));
                            clockStatus = "raw-candidate";
                        }
                    }
                }
                catch (InvalidDataException) when (budget <= 2 * 1024 * 1024) { }
                raw = new("raw-candidate", Rva(vt), d08, q10, q20, q28, d3c, q48, descriptor38, descriptorVtableRva,
                    descriptorStatus, stateStatus, state88, clockStatus, clock, clockVt, slot30, slot38, slot48);
            }
            catch (InvalidDataException) when (budget <= 2 * 1024 * 1024) { raw = new("unavailable"); }
            BuffTimingCandidate? timing = null;
            if (includeTiming)
            {
                timing = new("unavailable");
                if (raw.StateDword88.HasValue && raw.ClockAddress is > 0 && raw.ClockVtableRva.HasValue)
                {
                    try
                    {
                        var timer = Ptr(raw.ClockAddress.Value, 0x1C);
                        var reference = Q(timer + 0x10);
                        var beginBits = D(timer + 0x18); var begin = F(beginBits);
                        if (!float.IsFinite(begin)) throw new InvalidDataException("Nonfinite timer begin.");
                        ulong? refVt = null, refGetter = null, refSlot48 = null;
                        if (reference != 0)
                        {
                            var refAddress = Ptr(reference, 0x20); var vtable = Q(refAddress); refVt = Rva(vtable);
                            if (refVt.HasValue && refVt.Value <= id.ModuleSize - 0x50)
                            {
                                refGetter = Rva(Q(vtable + 0x40));
                                refSlot48 = Rva(Q(vtable + 0x48));
                            }
                        }
                        timing = new("unsupported-clock-profile", beginBits, begin, reference, refVt, refGetter, ReferenceSlot48Rva: refSlot48);
                        var vt = raw.ClockVtableRva.Value;
                        ulong? expectedDuration = vt switch { 0x26BC950 => 0x72AE00, 0x26BC9A0 => 0x72AE70, 0x26BCE50 => 0x72B040, _ => null };
                        if (raw.StateDword88 == 5) timing = timing with { Status = "state-sentinel" };
                        else if (expectedDuration.HasValue && raw.ClockSlot30Rva == expectedDuration && raw.ClockSlot38Rva == 0x72B3C0 && raw.ClockSlot48Rva == 0x09D680)
                        {
                            timing = timing with { Status = "dynamic-duration-unavailable" };
                            if (vt == 0x26BCE50)
                            {
                                timing = timing with { Status = "dynamic-type-or-property-unavailable" };
                                if (reference != 0 && refVt == 0x28EC200 && refGetter == 0x194CCE0 && refSlot48 == 0x04F180 &&
                                    Q(checked(id.ModuleBaseAddress + 0x3462A70)) == checked(id.ModuleBaseAddress + 0x28F5968) &&
                                    Q(checked(id.ModuleBaseAddress + 0x28F5968 + 8)) == checked(id.ModuleBaseAddress + 0x1978670) &&
                                    Q(checked(id.ModuleBaseAddress + 0x28F5968 + 0x28)) == checked(id.ModuleBaseAddress + 0x197A330) &&
                                    Q(checked(id.ModuleBaseAddress + 0x28F5968 + 0x38)) == checked(id.ModuleBaseAddress + 0x197D520) &&
                                    ValidFieldTable() &&
                                    Q(checked(id.ModuleBaseAddress + 0x303E7E0)) == checked(id.ModuleBaseAddress + 0x28ED1E8) &&
                                    Q(checked(id.ModuleBaseAddress + 0x28ED1E8 + 0x58)) == checked(id.ModuleBaseAddress + 0x194DCC0) &&
                                    Q(checked(id.ModuleBaseAddress + 0x28ED1E8 + 0x68)) == checked(id.ModuleBaseAddress + 0x194DD00) &&
                                    Q(checked(id.ModuleBaseAddress + 0x28ED1E8 + 0x78)) == checked(id.ModuleBaseAddress + 0x194DD40) &&
                                    Read(checked(id.ModuleBaseAddress + 0x345DE38), 10).AsSpan().SequenceEqual("!6b50761c\0"u8))
                                {
                                    var bits = D(checked(reference + 0x24)); var duration = F(bits);
                                    var remaining = duration - (clockBefore!.Value - begin);
                                    if (float.IsFinite(duration) && float.IsFinite(remaining))
                                        timing = timing with { Status = "raw-timing-candidate", DurationInputRawBits = bits, Duration = duration, Remaining = remaining };
                                }
                            }
                            else
                            {
                                var expectedRef = vt == 0x26BC950 ? 0x286CDC8UL : 0x2CC0618UL;
                                var expectedGetter = vt == 0x26BC950 ? 0x18254A0UL : 0x225CA20UL;
                                var descriptor = vt == 0x26BC950 ? 0x343B3C0UL : 0x3598870UL;
                                var descVt = vt == 0x26BC950 ? 0x2876CA8UL : 0x2CD1DE8UL;
                                var descGetter = vt == 0x26BC950 ? 0x184B530UL : 0x22892E0UL;
                                timing = timing with { Status = "reference-type-unavailable" };
                                if (reference != 0 && refVt == expectedRef && refGetter == expectedGetter &&
                                    Q(checked(id.ModuleBaseAddress + descriptor)) == checked(id.ModuleBaseAddress + descVt) &&
                                    Q(checked(id.ModuleBaseAddress + descVt + 8)) == checked(id.ModuleBaseAddress + descGetter))
                                {
                                    var ticks = BinaryPrimitives.ReadInt64LittleEndian(Read(checked(reference + 0x18), 8));
                                    var duration = (float)(ticks / 10000L) * 0.001f;
                                    var remaining = duration - (clockBefore!.Value - begin);
                                    if (float.IsFinite(duration) && float.IsFinite(remaining))
                                        timing = timing with { Status = "raw-timing-candidate", DurationTicks = ticks, Duration = duration, Remaining = remaining };
                                }
                            }
                        }
                    }
                    catch (InvalidDataException) when (budget <= 2 * 1024 * 1024) { timing = timing with { Status = raw.StateDword88 == 5 ? "state-sentinel" : "read-or-type-unavailable" }; }
                }
                else if (raw.StateDword88 == 5) timing = new("state-sentinel");
            }
            nodes.Add(new BuffRawNode(node, next, obj, control, raw) { Timing = timing });
        }
        if (includeTiming)
        {
            clockAfter = F(BinaryPrimitives.ReadUInt32LittleEndian(Read(clockAddress + 0x18, 4, false)));
            if (!float.IsFinite(clockAfter.Value) || clockAfter.Value < clockBefore!.Value)
                throw new InvalidDataException("Buff clock invalid or moved backward.");
        }
        foreach (var anchor in anchors)
            CurrentBuildPlayerLookup.RequireSame(Read(anchor.Key.Item1, anchor.Key.Item2, false), anchor.Value);
        verifyOwner();
        if (session.Identity != id) throw new InvalidDataException("Buff seed process identity changed.");
        return new(id, started, DateTimeOffset.UtcNow, key, context, sentinel, nodes)
            { ClockBefore = clockBefore, ClockAfter = clockAfter };
    }
}
