using System.Buffers.Binary;

namespace RiftReader2.Live;

/// <summary>
/// Offline-friendly, read-only candidate traversal of the current-build cache hit.
/// This does not establish actor/key identity, freshness, or world-coordinate semantics.
/// The caller owns process/build/epoch admission and supplies exact-length reads.
/// </summary>
internal static class CurrentBuildPoseCacheHitCandidate
{
    internal sealed record Hit(ulong PoseAddress, byte[] RawPosePayload);

    internal static Hit? TryRead(Func<ulong, int, byte[]?> read, ulong actor, ulong admittedKey)
    {
        ArgumentNullException.ThrowIfNull(read);
        try
        {
            var observations = new List<(ulong Address, byte[] Bytes)>();
            byte[]? Read(ulong address, int length)
            {
                if (!ValidRange(address, (ulong)length)) return null;
                var bytes = read(address, length);
                if (bytes is null || bytes.Length != length) return null;
                var copy = (byte[])bytes.Clone();
                observations.Add((address, copy));
                return copy;
            }
            ulong? Qword(ulong address)
            {
                var b = Read(address, 8);
                return b is null ? null : BinaryPrimitives.ReadUInt64LittleEndian(b);
            }
            ulong? At(ulong address, ulong offset) => Add(address, offset);

            if (!ValidPointer(actor)) return null;
            var headerAddress = At(actor, 0x5b0);
            if (headerAddress is null) return null;
            var header = Read(headerAddress.Value, 24);
            if (header is null) return null;
            ulong buckets = BinaryPrimitives.ReadUInt64LittleEndian(header.AsSpan(0, 8));
            ulong stride = BinaryPrimitives.ReadUInt64LittleEndian(header.AsSpan(8, 8));
            ulong count = BinaryPrimitives.ReadUInt64LittleEndian(header.AsSpan(16, 8));
            if (!ValidPointer(buckets) || stride < 24 || (stride & 7) != 0 || count == 0) return null;

            // Windows ldiv operates on signed 32-bit long. Match the native 32-bit wrap.
            int low = unchecked((int)(uint)admittedKey);
            int quotient = low / 0x1f31d;
            int remainder = low % 0x1f31d;
            int hash = unchecked(remainder * 0x41a7 - quotient * 0xb14);
            uint nonnegative = unchecked((uint)(hash < 0 ? hash + 0x7fffffff : hash));
            ulong index = nonnegative % count;
            if (index != 0 && stride > ulong.MaxValue / index) return null;
            var slot = Add(buckets, index * stride);
            if (slot is null || !ValidPointer(slot.Value)) return null;

            var visited = new HashSet<ulong>();
            ulong node = slot.Value;
            bool first = true;
            for (int i = 0; i < 8; i++)
            {
                if (!ValidPointer(node) || !visited.Add(node)) return null;
                var bytes = Read(node, 24);
                if (bytes is null) return null;
                ulong next = BinaryPrimitives.ReadUInt64LittleEndian(bytes.AsSpan(0, 8));
                ulong key = BinaryPrimitives.ReadUInt64LittleEndian(bytes.AsSpan(8, 8));
                ulong entry = BinaryPrimitives.ReadUInt64LittleEndian(bytes.AsSpan(16, 8));
                if ((!first || (next & 1) == 0) && key == admittedKey)
                {
                    if (!ValidPointer(entry)) return null;
                    var entryAddress = At(entry, 0x18);
                    if (entryAddress is null) return null;
                    var pose = Qword(entryAddress.Value);
                    if (pose is null || !ValidPointer(pose.Value)) return null;
                    var payloadAddress = At(pose.Value, 0xf8);
                    if (payloadAddress is null) return null;
                    var payload = Read(payloadAddress.Value, 12);
                    if (payload is null) return null;

                    // Recheck every anchor, including links, key, entry, pose, and payload.
                    foreach (var observation in observations)
                    {
                        var again = read(observation.Address, observation.Bytes.Length);
                        if (again is null || !again.AsSpan().SequenceEqual(observation.Bytes)) return null;
                    }
                    return new Hit(pose.Value, payload);
                }
                first = false;
                node = next & ~1UL;
                if (node == 0) return null;
            }
            return null;
        }
        catch (Exception ex) when (ex is not OutOfMemoryException and not StackOverflowException)
        {
            return null;
        }
    }

    private static ulong? Add(ulong address, ulong offset) =>
        address <= ulong.MaxValue - offset ? address + offset : null;

    private static bool ValidPointer(ulong value) =>
        value >= 0x10000 && value <= 0x00007fffffffffff && (value & 7) == 0;

    private static bool ValidRange(ulong address, ulong length) =>
        address >= 0x10000 && length > 0 && address <= 0x00007fffffffffff - (length - 1);
}
