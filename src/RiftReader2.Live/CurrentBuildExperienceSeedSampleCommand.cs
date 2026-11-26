using System.Buffers.Binary;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
namespace RiftReader2.Live;

internal sealed record ExperienceReferenceSeed(ulong Address, ulong? VtableRva, ulong? GetterRva,
    long RawInt64_18, uint RawDword24, uint RawFloat20Bits, float? RawFloat20);
internal sealed record ExperienceSeedObservation(NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc,
    DateTimeOffset CompletedAtUtc, ulong UnitKey, ulong Entity, ulong Component, ulong Owner,
    ulong? OwnerVtableRva, ulong? OwnerGetterRva, int Index, uint RawDword160, byte RawByte24F,
    ulong VectorBegin, ulong VectorEnd, IReadOnlyList<ulong> References, string Branch,
    ExperienceReferenceSeed? Selected, ulong? Special7D8, ulong? Special7E0)
{
    public string Qualification => "raw experience inputs; calculated experience, freshness and restart unverified";
}
internal static class CurrentBuildExperienceSeedCandidateReader
{
    internal static ExperienceSeedObservation Read(IReadOnlyNativeMemorySession session)
    {
        // Build 1179 callback and producer were independently decoded against the exact SHA.
        // Only the raw indexed seed path is admitted here; the calculated-XP reader
        // still has its original build gate and separate typed provider requirements.
        var start = DateTimeOffset.UtcNow;
        var lookup = CurrentBuildPlayerLookup.Resolve(session);
        var updated = CurrentBuildPlayerLookup.IsUpdatedBuild(session.Identity.ExecutableSha256);
        var health = lookup.ResolveComponent(updated ? 0x2F68850UL : 0x2F57850UL);
        var component = lookup.ResolveComponent(updated ? 0x2F692E0UL : 0x2F582E0UL);
        return ReadResolved(session, session.Identity, start, lookup.PlayerKey, lookup.EntityAddress, health, component, lookup.VerifyUnchanged);
    }
    internal static ExperienceSeedObservation ReadResolved(IReadOnlyNativeMemorySession session, NativeProcessIdentity id,
        DateTimeOffset start, ulong key, ulong entity, ulong health, ulong component, Action verifyOwner)
    {
        var updated = CurrentBuildPlayerLookup.IsUpdatedBuild(id.ExecutableSha256);
        var systemRva = updated ? 0x3373BA0UL : 0x33623E0UL;
        if (session.Identity != id || id.ProcessId <= 0 || id.ProcessStartUtcTicks <= 0 ||
            key == 0 || id.ModuleSize < systemRva + 8 ||
            !CurrentBuildPlayerLookup.IsCoreBuild(id.ExecutableSha256))
            throw new InvalidDataException("Invalid experience seed identity.");
        ArgumentNullException.ThrowIfNull(verifyOwner);
        var anchors = new Dictionary<(ulong, int), byte[]>(); int budget = 0;
        byte[] Read(ulong address, int length, bool remember = true)
        {
            budget = checked(budget + length); if (budget > 2 * 1024 * 1024) throw new InvalidDataException("Experience seed budget exceeded.");
            var b = CurrentBuildPlayerLookup.Exact(session, address, length);
            if (remember) { if (anchors.TryGetValue((address, length), out var previous) && !previous.AsSpan().SequenceEqual(b)) throw new InvalidDataException("Experience seed changed."); anchors[(address, length)] = b.ToArray(); }
            return b;
        }
        ulong Q(ulong a) => BinaryPrimitives.ReadUInt64LittleEndian(Read(a, 8));
        uint D(ulong a) => BinaryPrimitives.ReadUInt32LittleEndian(Read(a, 4));
        ulong Ptr(ulong v, int n = 8) => CurrentBuildPlayerLookup.Pointer(v, n);
        ulong? Rva(ulong v) => v >= id.ModuleBaseAddress && v - id.ModuleBaseAddress < id.ModuleSize ? v - id.ModuleBaseAddress : null;
        (ulong?, ulong?) Vtable(ulong obj)
        {
            var vt = Q(obj); var rva = Rva(vt); ulong? getter = null;
            if (rva.HasValue && rva.Value <= id.ModuleSize - 0x48) getter = Rva(Q(checked(vt + 0x40)));
            return (rva, getter);
        }
        var system = Ptr(Q(checked(id.ModuleBaseAddress + systemRva)), 0x400);
        // The 1179 callback resolves the cached self entity and its progression
        // component; its producer traverses the health component back to self.
        // Verify both component back-references and the current player key.
        if (Q(system + 0x3F8) != entity ||
            Q(checked(Ptr(health, 0x18) + 0x10)) != entity ||
            Q(checked(Ptr(component, 0x50) + 0x10)) != entity ||
            (updated && (health == component || Q(system + 0x360) != key)))
            throw new InvalidDataException("Experience self entity mismatch.");
        var owner = Ptr(Q(component + 0x48), 0xDF0); var (vt, getter) = Vtable(owner);
        if (updated && (!vt.HasValue || !getter.HasValue || vt.Value == 0 || getter.Value == 0))
            throw new InvalidDataException("Experience owner module reference unavailable.");
        var index = unchecked((int)D(owner + 0x1D8)); var d160 = D(owner + 0x160); var flag = Read(owner + 0x24F, 1)[0];
        var begin = Q(owner + 0xDE0); var end = Q(owner + 0xDE8);
        if ((begin == 0) != (end == 0) || end < begin || (end - begin) % 8 != 0 || (end - begin) / 8 > 256) throw new InvalidDataException("Invalid experience vector.");
        if (begin != 0) Ptr(begin, checked((int)Math.Max(8UL, end - begin)));
        var references = new List<ulong>(); for (var cursor = begin; cursor < end; cursor += 8) references.Add(Q(cursor));
        ExperienceReferenceSeed? selected = null; ulong? specialA = null, specialB = null; string branch;
        if (index == -1)
        {
            branch = flag != 0 ? "special-index-minus-one" : "index-minus-one";
            if (flag != 0) { specialA = Q(owner + 0x7D8); specialB = Q(owner + 0x7E0); }
        }
        else if (index < 0 || index >= references.Count) branch = "index-out-of-range";
        else if (references[index] == 0) branch = "selected-null";
        else
        {
            var address = Ptr(references[index], 0x28); var (rvt, rgetter) = Vtable(address);
            if (updated && (!rvt.HasValue || !rgetter.HasValue || rvt.Value == 0 || rgetter.Value == 0))
                throw new InvalidDataException("Experience record module reference unavailable.");
            var i64 = BinaryPrimitives.ReadInt64LittleEndian(Read(address + 0x18, 8)); var bits = D(address + 0x20); var f = BitConverter.Int32BitsToSingle(unchecked((int)bits)); var d24 = D(address + 0x24);
            selected = new(address, rvt, rgetter, i64, d24, bits, float.IsFinite(f) ? f : null); branch = "indexed-raw-candidate";
        }
        foreach (var a in anchors) CurrentBuildPlayerLookup.RequireSame(Read(a.Key.Item1, a.Key.Item2, false), a.Value);
        verifyOwner(); if (session.Identity != id) throw new InvalidDataException("Experience process epoch changed.");
        return new(id, start, DateTimeOffset.UtcNow, key, entity, component, owner, vt, getter, index, d160, flag, begin, end, references, branch, selected, specialA, specialB);
    }
}
internal static class CurrentBuildExperienceSeedSampleCommand
{
    internal static Task<int> RunAsync(IReadOnlyDictionary<string, string> options, TextWriter output, CancellationToken ct)
    {
        var sha = ExpectedSha(options);
        return RunAsync(options, output, ct,
            async (pid, ticks, token) => await NativeReadFileLease.AcquireAsync(pid, ticks, sha, TimeSpan.FromSeconds(1), token),
            async (pid, ticks, token) => await WindowsNativeMemorySession.OpenAsync(pid, ticks, sha, token),
            CurrentBuildExperienceSeedCandidateReader.Read);
    }

    private static string ExpectedSha(IReadOnlyDictionary<string, string> options)
    {
        var sha = options.TryGetValue("--sha256", out var requested) ? requested : CurrentBuildPlayerLookup.GameSha256;
        if (!CurrentBuildPlayerLookup.IsCoreBuild(sha))
            throw new ArgumentException("Unqualified executable SHA256 for raw experience seed.");
        return sha;
    }

    // Explicit offline test seam; production always supplies the real lease.
    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options, TextWriter output, CancellationToken ct,
        Func<int, long, CancellationToken, Task<IAsyncDisposable>> acquireLease,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession, ExperienceSeedObservation> read)
    {
        if (!options.TryGetValue("--pid", out var p) || !int.TryParse(p, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 || !options.TryGetValue("--start-ticks", out var t) || !long.TryParse(t, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 || !options.TryGetValue("--output", out var path) || string.IsNullOrWhiteSpace(path)) throw new ArgumentException("--pid, --start-ticks and --output required.");
        var expectedSha = ExpectedSha(options);
        if (File.Exists(path)) throw new IOException("Output exists.");
        await using var lease = await acquireLease(pid, ticks, ct);
        ct.ThrowIfCancellationRequested();
        await using var session = await open(pid, ticks, ct);
        ct.ThrowIfCancellationRequested();
        if (session.Identity.ProcessId != pid || session.Identity.ProcessStartUtcTicks != ticks ||
            !string.Equals(session.Identity.ExecutableSha256, expectedSha, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Experience seed source identity mismatch.");
        var observation = read(session);
        if (observation.Identity != session.Identity)
            throw new InvalidDataException("Experience seed observation identity mismatch.");
        if (await session.RevalidateAsync(ct) is not null) throw new InvalidDataException("Process identity invalidated."); ct.ThrowIfCancellationRequested();
        var report = new { schemaVersion = 1, contractVersion = "native-current-experience-seed-candidate/1", status = "complete", observation, limitations = new[] { "Raw inputs do not establish accumulated, needed or rested experience.", "Sequential reads are not atomic and cannot exclude ABA; freshness and restart unverified.", "Executable SHA identifies on-disk bytes; loaded module bytes not independently hashed.", "No getter, initializer, reference-count operation or memory write performed." } };
        await JsonReportWriter.WriteNewAsync(path, report, ct);
        await output.WriteLineAsync(JsonSerializer.Serialize(new { recordType = "native-current-experience-seed-summary/1", status = "complete", observation.Qualification, observation.Branch, output = Path.GetFullPath(path) }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false })); return 0;
    }
}
