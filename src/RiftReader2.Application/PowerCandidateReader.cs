using System.Buffers.Binary;
using RiftReader2.Domain;

namespace RiftReader2.Application;

public sealed record PowerCandidateObservation(
    string StartedAtUtc, string CompletedAtUtc, string Status, string? Reason,
    int? Power, int? Maximum, int? BaseValue, int? Rate, int? Sequence,
    float? ClockSeconds, float? AnchorSeconds, IReadOnlyList<string>? PointerChain,
    string? WrapperBytesBase64, string? RecordBytesBase64);

/// <summary>
/// Read-only reconstruction of this build's Inspect.Unit.Detail Power getter.
/// Exact-build candidate: no game calls, shared-reference writes, scans or fallback.
/// </summary>
public static class PowerCandidateReader
{
    public const string ExecutableSha256 = "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD";
    public const string Recipe = "player-power-7C356C9D-v1";

    public static async Task<PowerCandidateObservation> ReadAsync(
        IReadOnlyNativeMemorySession session, CancellationToken cancellationToken)
    {
        var started = DateTimeOffset.UtcNow.ToString("O");
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (session.Identity.ExecutableSha256 != ExecutableSha256)
                throw new InvalidDataException("exact-build-mismatch");
            var failure = await session.RevalidateAsync(cancellationToken);
            if (failure is not null) throw new InvalidDataException(failure);
            var module = session.Identity.ModuleBaseAddress;
            var first = Resolve(session);
            var wrapper = Read(session, first[2], 32);
            var record = Read(session, first[4], 48);
            RequireVtable(record, module, 0x2B378D8);
            var clock = Pointer(session, module + 0x335A0E0);
            var now = BinaryPrimitives.ReadSingleLittleEndian(Read(session, clock + 0x18, 4));
            var scale = Read(session, module + 0x2649B94, 4);
            if (BinaryPrimitives.ReadUInt32LittleEndian(scale) != 0xBC23D70A)
                throw new InvalidDataException("scale-constant-mismatch");
            var anchor = BinaryPrimitives.ReadSingleLittleEndian(wrapper.AsSpan(0x1C));
            var sequence = BinaryPrimitives.ReadInt32LittleEndian(record.AsSpan(0x1C));
            if (sequence != BinaryPrimitives.ReadInt32LittleEndian(wrapper.AsSpan(0x18)))
                throw new InvalidDataException("sequence-not-synchronized");
            var baseValue = BinaryPrimitives.ReadInt32LittleEndian(record.AsSpan(0x18));
            var maximum = BinaryPrimitives.ReadInt32LittleEndian(record.AsSpan(0x20));
            var rate = BinaryPrimitives.ReadInt32LittleEndian(record.AsSpan(0x2C));
            // Preserve the game's float32 operations and truncation toward zero.
            var elapsed = now - anchor;
            var ratePerSecond = (float)rate * BinaryPrimitives.ReadSingleLittleEndian(scale);
            var adjustment = ratePerSecond * elapsed;
            if (!float.IsFinite(now) || !float.IsFinite(anchor) || elapsed < 0 ||
                !float.IsFinite(adjustment) || adjustment <= int.MinValue || adjustment >= int.MaxValue ||
                maximum <= 0 || baseValue < 0 || baseValue > maximum)
                throw new InvalidDataException("invalid-power-inputs");
            var value = Math.Clamp((long)baseValue - (int)adjustment, 0, maximum);

            // Double collect: reject a concurrent resource update or owner change.
            var recordAfter = Read(session, first[4], 48);
            var wrapperAfter = Read(session, first[2], 32);
            var second = Resolve(session);
            if (!first.SequenceEqual(second) || Pointer(session, module + 0x335A0E0) != clock ||
                !record.AsSpan(0, 8).SequenceEqual(recordAfter.AsSpan(0, 8)) ||
                !record.AsSpan(0x18, 24).SequenceEqual(recordAfter.AsSpan(0x18, 24)) ||
                !wrapper.AsSpan().SequenceEqual(wrapperAfter))
                throw new InvalidDataException("resource-changed-during-read");
            failure = await session.RevalidateAsync(cancellationToken);
            if (failure is not null) throw new InvalidDataException(failure);
            return new(started, DateTimeOffset.UtcNow.ToString("O"), "complete", null,
                (int)value, maximum, baseValue, rate, sequence, now, anchor,
                first.Select(address => $"0x{address:X}").ToArray(),
                Convert.ToBase64String(wrapper), Convert.ToBase64String(record));
        }
        catch (InvalidDataException error)
        {
            return new(started, DateTimeOffset.UtcNow.ToString("O"), "unavailable", error.Message,
                null, null, null, null, null, null, null, null, null, null);
        }
    }

    private static ulong[] Resolve(IReadOnlyNativeMemorySession session)
    {
        var module = session.Identity.ModuleBaseAddress;
        var owner = Pointer(session, module + 0x32E0200);
        var component = Pointer(session, owner + 0x400);
        RequireVtable(Read(session, component, 8), module, 0x2648E90);
        var resourceType = Pointer(session, component + 0x40);
        if (BinaryPrimitives.ReadInt32LittleEndian(Read(session, resourceType + 0x168, 4)) != 1)
            throw new InvalidDataException("not-warrior-power");
        var wrapper = Pointer(session, component + 0x38);
        RequireVtable(Read(session, wrapper, 8), module, 0x27184F0);
        var handle = Pointer(session, wrapper + 0x10);
        var record = Pointer(session, handle);
        return [owner, component, wrapper, handle, record, resourceType];
    }

    private static void RequireVtable(byte[] bytes, ulong module, ulong rva)
    {
        if (BinaryPrimitives.ReadUInt64LittleEndian(bytes) != module + rva)
            throw new InvalidDataException("object-type-mismatch");
    }

    private static ulong Pointer(IReadOnlyNativeMemorySession session, ulong address)
    {
        var value = BinaryPrimitives.ReadUInt64LittleEndian(Read(session, address, 8));
        if (value < 0x10000 || value > 0x00007FFFFFFF0000 || value % 8 != 0)
            throw new InvalidDataException("invalid-pointer");
        return value;
    }

    private static byte[] Read(IReadOnlyNativeMemorySession session, ulong address, int count)
    {
        var result = session.Read(address, count);
        if (result.Status != "success" || result.Bytes.Length != count)
            throw new InvalidDataException($"incomplete-read:0x{address:X}:{result.Status}");
        return result.Bytes;
    }
}
