using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live;
internal sealed record LocalizationDictionaryRow(uint Key, string Status, ulong? NodeAddress = null, uint? Offset = null, uint? ApparentInputLength = null, uint? DecodedSize = null, string? CompressedBytesBase64 = null);
internal sealed record CurrentBuildLocalizationDictionaryObservation(NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc, ulong Manager, ulong Wrapper, ulong Inner, ulong Dictionary, ulong BucketBase, ulong BucketCount, ulong EntryCount, ulong BlobAddress, uint BlobSize, string FrequencyBytesBase64, IReadOnlyList<LocalizationDictionaryRow> Rows)
{
    public string Qualification => "candidate-only; framing, freshness and restart unverified";
    public string Source => "native-process-memory";
}
internal static class CurrentBuildLocalizationDictionaryCandidateReader
{
    internal static CurrentBuildLocalizationDictionaryObservation Read(IReadOnlyNativeMemorySession session, IReadOnlyList<uint> keys)
    {
        var started = DateTimeOffset.UtcNow; var id = session.Identity;
        if (id.ProcessId <= 0 || id.ProcessStartUtcTicks <= 0 || id.ModuleSize < 0x33623F0 || !string.Equals(id.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase) || keys.Count is < 1 or > 128 || keys.Distinct().Count() != keys.Count) throw new InvalidDataException("Invalid build, process identity or keys.");
        var anchors = new Dictionary<(ulong, int), byte[]>(); var budget = 0;
        byte[] ReadBytes(ulong a, int n, bool remember = true)
        {
            budget = checked(budget + n); if (budget > 2 * 1024 * 1024) throw new InvalidDataException("Read budget exceeded.");
            var bytes = CurrentBuildPlayerLookup.Exact(session, a, n);
            if (remember) { if (anchors.TryGetValue((a,n), out var old) && !old.AsSpan().SequenceEqual(bytes)) throw new InvalidDataException("Bytes changed during capture."); anchors[(a,n)] = bytes.ToArray(); }
            return bytes;
        }
        ulong Q(ulong a) => U64(ReadBytes(a,8));
        var manager = CurrentBuildPlayerLookup.Pointer(Q(checked(id.ModuleBaseAddress + 0x33623E8)), 0xA0);
        var wrapper = CurrentBuildPlayerLookup.Pointer(Q(manager + 0x98), 16);
        var provider = ReadBytes(wrapper,16); var vt = U64(provider); var inner = CurrentBuildPlayerLookup.Pointer(U64(provider.AsSpan(8)), 0x4C4);
        if (vt != checked(id.ModuleBaseAddress + 0x26C1EA8) || Q(vt) != checked(id.ModuleBaseAddress + 0x7D3230)) throw new InvalidDataException("Provider fingerprint mismatch.");
        var d = checked(inner + 0x78); var header = ReadBytes(d,32); var bucketBase = U64(header); var stride = U64(header.AsSpan(8)); var count = U64(header.AsSpan(16)); var entries = U64(header.AsSpan(24));
        if (stride != 16 || count > 1048576 || (count == 0 && (bucketBase != 0 || entries != 0))) throw new InvalidDataException("Invalid dictionary header.");
        if (count != 0) CurrentBuildPlayerLookup.Pointer(bucketBase, checked((int)(count * 16)));
        var frequency = ReadBytes(d + 0x40,1024); var meta = ReadBytes(d + 0x440,12); var blob = U64(meta); var size = BinaryPrimitives.ReadUInt32LittleEndian(meta.AsSpan(8));
        if (size != 0) CurrentBuildPlayerLookup.Pointer(blob, checked((int)Math.Min(size, int.MaxValue)));
        if (size > 0 && (blob > 0x7FFFFFFFFFFFUL - (size - 1UL))) throw new InvalidDataException("Invalid blob range.");
        var rows = new List<LocalizationDictionaryRow>();
        foreach (var key in keys)
        {
            if (count == 0) { rows.Add(new(key,"cache-miss")); continue; }
            var address = checked(bucketBase + CurrentBuildAbilityRecordsCandidateReader.Hash(key) % count * 16); var seen = new HashSet<ulong>(); var head = true; byte[]? node = null;
            for (var i = 0; i <= 128; i++)
            {
                if (!seen.Add(address)) throw new InvalidDataException("Cyclic dictionary chain.");
                node = ReadBytes(address,16); var link = U64(node);
                if ((!head || (link & 1) == 0) && BinaryPrimitives.ReadUInt32LittleEndian(node.AsSpan(8)) == key) break;
                var next = link & ~1UL; if (next == 0) { node = null; break; }
                if (i == 128) throw new InvalidDataException("Dictionary chain budget exceeded.");
                address = CurrentBuildPlayerLookup.Pointer(next,16); head = false;
            }
            if (node is null) { rows.Add(new(key,"cache-miss")); continue; }
            var offset = BinaryPrimitives.ReadUInt32LittleEndian(node.AsSpan(12)); if (offset >= size) throw new InvalidDataException("Invalid blob offset.");
            var at = checked(blob + offset); var prefix = ReadBytes(at, (int)Math.Min(10U,size-offset)); var position = 0;
            uint Varint() { uint value = 0; for (var i = 0; i < 5; i++) { if (position >= prefix.Length) throw new InvalidDataException("Truncated ULEB32."); var b = prefix[position++]; if (i == 4 && b > 15) throw new InvalidDataException("Invalid ULEB32."); value |= (uint)(b & 127) << (7*i); if ((b & 128) == 0) return value; } throw new InvalidDataException("Invalid ULEB32."); }
            var length = Varint(); var decoded = Varint();
            if (decoded >= 65536 || length > 4096 || length > size - offset - (uint)position) throw new InvalidDataException("Invalid candidate payload size.");
            var compressed = length == 0 ? Array.Empty<byte>() : ReadBytes(checked(at + (uint)position),checked((int)length));
            rows.Add(new(key,"raw-candidate",address,offset,length,decoded,Convert.ToBase64String(compressed)));
        }
        foreach (var anchor in anchors) CurrentBuildPlayerLookup.RequireSame(ReadBytes(anchor.Key.Item1,anchor.Key.Item2,false),anchor.Value);
        if (session.Identity != id) throw new InvalidDataException("Process identity changed.");
        return new(id,started,DateTimeOffset.UtcNow,manager,wrapper,inner,d,bucketBase,count,entries,blob,size,Convert.ToBase64String(frequency),rows);
    }
    private static ulong U64(ReadOnlySpan<byte> b) => BinaryPrimitives.ReadUInt64LittleEndian(b);
}
