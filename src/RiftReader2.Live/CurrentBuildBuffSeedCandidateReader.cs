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
internal sealed record BuffRawNode(ulong Address, ulong Next, ulong Object, ulong Control, BuffRawObject RawObject);
internal sealed record CurrentBuildBuffSeedObservation(NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc,
    DateTimeOffset CompletedAtUtc, ulong UnitKey, ulong Context, ulong Sentinel, IReadOnlyList<BuffRawNode> Nodes)
{
    public string Qualification => "raw-list-candidates; visibility, buff IDs, names, freshness and restart unverified";
}

internal static class CurrentBuildBuffSeedCandidateReader
{
    internal static CurrentBuildBuffSeedObservation Read(IReadOnlyNativeMemorySession session)
    {
        var started = DateTimeOffset.UtcNow;
        var lookup = CurrentBuildPlayerLookup.Resolve(session);
        var health = lookup.ResolveComponent(0x2F57850);
        var context = lookup.ResolveComponent(0x2F57260);
        return ReadResolved(session, session.Identity, started, lookup.PlayerKey, lookup.EntityAddress,
            health, context, lookup.VerifyUnchanged);
    }

    internal static CurrentBuildBuffSeedObservation ReadResolved(IReadOnlyNativeMemorySession session,
        NativeProcessIdentity id, DateTimeOffset started, ulong key, ulong entity, ulong health, ulong context,
        Action verifyOwner)
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
        var system = Ptr(Q(checked(id.ModuleBaseAddress + 0x33623E0)), 0x400);
        if (Q(checked(system + 0x3F8)) != entity || Q(checked(Ptr(health, 0x18) + 0x10)) != entity ||
            Q(checked(Ptr(context, 0x318) + 0x10)) != entity)
            throw new InvalidDataException("Buff seed owner mismatch.");
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
                        var clockAddress = Ptr(clock.Value); var vtable = Q(clockAddress); clockVt = Rva(vtable);
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
            nodes.Add(new(node, next, obj, control, raw));
        }
        foreach (var anchor in anchors)
            CurrentBuildPlayerLookup.RequireSame(Read(anchor.Key.Item1, anchor.Key.Item2, false), anchor.Value);
        verifyOwner();
        if (session.Identity != id) throw new InvalidDataException("Buff seed process identity changed.");
        return new(id, started, DateTimeOffset.UtcNow, key, context, sentinel, nodes);
    }
}
