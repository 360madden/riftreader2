using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

/// <summary>
/// Isolated, opt-in raw diagnostic. No native calls, initialization, pose resolution,
/// cached-position adjustment, or world-coordinate semantics. The caller owns admission
/// and supplies an owner/epoch guard. Sequential bracketing cannot exclude ABA changes.
/// Not wired to any public command; synthetic/offline validation only.
/// </summary>
internal static class CurrentBuildTranslationVectorCandidate
{
    internal const ulong SingletonRva = 0x33623E0;
    internal const ulong VectorOffset = 0x438;
    private const ulong MaximumUserAddress = 0x00007FFFFFFFFFFF;

    internal sealed record Sample(
        NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc,
        ulong SingletonAddress, float A, float B, float C, uint ABits, uint BBits, uint CBits)
    {
        public string SingletonAddressHex => $"0x{SingletonAddress:X16}";
        public string Qualification =>
            "optional-raw-global-translation-candidate; unqualified; ownership, meaning, freshness and world-coordinate semantics unverified";
    }

    internal static Sample? TryRead(IReadOnlyNativeMemorySession session,
        ulong exactModuleBase, ulong exactModuleSize, Action verifyOwnerEpoch)
    {
        ArgumentNullException.ThrowIfNull(session);
        ArgumentNullException.ThrowIfNull(verifyOwnerEpoch);
        var started = DateTimeOffset.UtcNow;
        var identity = session.Identity;
        if (identity.ProcessId <= 0 || identity.ProcessStartUtcTicks <= 0 ||
            !string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256,
                StringComparison.OrdinalIgnoreCase) ||
            identity.ModuleBaseAddress != exactModuleBase || identity.ModuleSize != exactModuleSize ||
            !Range(exactModuleBase, exactModuleSize) || exactModuleSize < SingletonRva + 8)
            return null;

        try
        {
            verifyOwnerEpoch();
            if (session.Identity != identity) return null;
            var pointerAddress = checked(exactModuleBase + SingletonRva);
            var pointerBytes = Read(session, pointerAddress, 8);
            if (pointerBytes is null) return null;
            var singleton = BinaryPrimitives.ReadUInt64LittleEndian(pointerBytes);
            if ((singleton & 7) != 0 || !Range(singleton, VectorOffset + 12)) return null;
            var vectorAddress = checked(singleton + VectorOffset);
            var payload = Read(session, vectorAddress, 12);
            if (payload is null) return null;
            uint aBits = BinaryPrimitives.ReadUInt32LittleEndian(payload);
            uint bBits = BinaryPrimitives.ReadUInt32LittleEndian(payload.AsSpan(4));
            uint cBits = BinaryPrimitives.ReadUInt32LittleEndian(payload.AsSpan(8));
            float a = BitConverter.UInt32BitsToSingle(aBits);
            float b = BitConverter.UInt32BitsToSingle(bBits);
            float c = BitConverter.UInt32BitsToSingle(cBits);
            if (!float.IsFinite(a) || !float.IsFinite(b) || !float.IsFinite(c)) return null;

            // Reverse-order bracket: both payload bytes and singleton pointer must agree.
            var payloadAgain = Read(session, vectorAddress, 12);
            var pointerAgain = Read(session, pointerAddress, 8);
            if (payloadAgain is null || pointerAgain is null ||
                !payloadAgain.AsSpan().SequenceEqual(payload) ||
                !pointerAgain.AsSpan().SequenceEqual(pointerBytes)) return null;
            verifyOwnerEpoch();
            if (session.Identity != identity) return null;
            return new(identity, started, DateTimeOffset.UtcNow, singleton,
                a, b, c, aBits, bBits, cBits);
        }
        catch (Exception ex) when (ex is InvalidDataException or OverflowException or IOException)
        {
            return null;
        }
    }

    private static byte[]? Read(IReadOnlyNativeMemorySession session, ulong address, int length)
    {
        if (!Range(address, (ulong)length)) return null;
        var result = session.Read(address, length);
        return result.Status == "success" && result.Bytes.Length == length
            ? result.Bytes.ToArray() : null;
    }

    private static bool Range(ulong address, ulong length) =>
        address >= 0x10000 && address <= MaximumUserAddress &&
        length > 0 && length - 1 <= MaximumUserAddress - address;
}
