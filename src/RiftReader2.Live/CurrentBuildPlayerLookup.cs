using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

/// <summary>
/// Per-acquisition exact-build player ownership snapshot. Resolve afresh for each
/// sample; verify after reading field payloads. Sequential checks cannot exclude ABA.
/// </summary>
internal sealed class CurrentBuildPlayerLookup
{
    internal const string GameSha256 =
        "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8";
    // Historical SHA remains the default for older candidate tools and tests.
    // Only the source-verified player/position/facing path is admitted on 1179.
    internal const string UpdatedGameSha256 =
        "DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01";
    private const ulong ManagerRva = 0x33624A8;
    private const ulong PlayerSystemRva = 0x33623E0;
    private const ulong UpdatedManagerRva = 0x3373C68;
    private const ulong UpdatedPlayerSystemRva = 0x3373BA0;
    internal static bool IsUpdatedBuild(string? sha) =>
        string.Equals(sha, UpdatedGameSha256, StringComparison.OrdinalIgnoreCase);
    internal static bool IsCoreBuild(string? sha) => IsUpdatedBuild(sha) ||
        string.Equals(sha, GameSha256, StringComparison.OrdinalIgnoreCase);
    internal static ulong PositionIndexRvaFor(string? sha) =>
        IsUpdatedBuild(sha) ? 0x2F698A0UL : 0x2F588A0UL;
    private const ulong MinimumUserAddress = 0x10000;
    private const ulong MaximumUserAddress = 0x7FFF_FFFF_FFFF;
    private readonly IReadOnlyNativeMemorySession session;
    private readonly NativeProcessIdentity identity;
    private readonly List<(ulong Address, byte[] Bytes)> anchors = [];
    private byte[] entityBytes = [];

    private CurrentBuildPlayerLookup(IReadOnlyNativeMemorySession session)
    {
        this.session = session;
        identity = session.Identity;
    }

    internal ulong EntityAddress { get; private set; }
    internal ulong PlayerKey { get; private set; }
    internal ulong PlayerSystemAddress { get; private set; }

    internal static CurrentBuildPlayerLookup Resolve(IReadOnlyNativeMemorySession session)
    {
        ArgumentNullException.ThrowIfNull(session);
        var lookup = new CurrentBuildPlayerLookup(session);
        var identity = lookup.identity;
        if (!IsCoreBuild(identity.ExecutableSha256))
            throw new InvalidDataException("Player lookup requires a qualified exact executable SHA256.");
        var managerRva = IsUpdatedBuild(identity.ExecutableSha256) ? UpdatedManagerRva : ManagerRva;
        var playerSystemRva = IsUpdatedBuild(identity.ExecutableSha256) ? UpdatedPlayerSystemRva : PlayerSystemRva;
        if (identity.ProcessId <= 0 || identity.ProcessStartUtcTicks <= 0 ||
            identity.ModuleBaseAddress < MinimumUserAddress ||
            identity.ModuleBaseAddress > MaximumUserAddress ||
            identity.ModuleSize < managerRva + 8 ||
            identity.ModuleSize > MaximumUserAddress - identity.ModuleBaseAddress)
            throw new InvalidDataException("Invalid current RIFT process/module identity.");

        var module = identity.ModuleBaseAddress;
        var system = Pointer(ReadU64(lookup.Take(checked(module + playerSystemRva), 8)));
        lookup.PlayerSystemAddress = system;
        var key = ReadU64(lookup.Take(checked(system + 0x360), 8));
        if (key == 0)
            throw new InvalidDataException("Player unit key missing.");
        lookup.PlayerKey = key;
        lookup.EntityAddress = lookup.ResolveEntity(key);
        lookup.entityBytes = lookup.Take(lookup.EntityAddress, 128);
        return lookup;
    }

    // The key is an inline value, not a pointer; all traversed bytes remain in
    // this lookup's anchors even on failure, for the caller's final recheck.
    private ulong ResolveEntity(ulong key)
    {
        if (key == 0) throw new InvalidDataException("Native unit key missing.");
        var managerRva = IsUpdatedBuild(identity.ExecutableSha256) ? UpdatedManagerRva : ManagerRva;
        var manager = Pointer(ReadU64(Take(checked(identity.ModuleBaseAddress + managerRva), 8)));
        var table = Pointer(ReadU64(Take(checked(manager + 0x50), 8)));
        var header = Take(table, 24);
        var buckets = Pointer(ReadU64(header.AsSpan(0, 8)));
        var stride = ReadU64(header.AsSpan(8, 8));
        var count = ReadU64(header.AsSpan(16, 8));
        if (stride is < 24 or > 4096 || stride % 8 != 0 || count is < 1 or > (1 << 24))
            throw new InvalidDataException("Invalid native unit-table layout.");

        var bucket = Pointer(checked(buckets + BucketIndex(key, count) * stride), 24);
        var visited = new HashSet<ulong>();
        var current = bucket;
        for (var index = 0; index < 8; ++index)
        {
            if (!visited.Add(current))
                throw new InvalidDataException("Native entity bucket chain is cyclic.");
            var bytes = Take(current, 24);
            var taggedNext = ReadU64(bytes.AsSpan(0, 8));
            var candidateKey = ReadU64(bytes.AsSpan(8, 8));
            if ((index > 0 || (taggedNext & 1) == 0) && candidateKey == key)
            {
                return Pointer(ReadU64(bytes.AsSpan(16, 8)), 128);
            }
            var next = taggedNext & ~1UL;
            if (next == 0)
                throw new InvalidDataException("Player key is absent from the exact native table.");
            current = Pointer(next, 24);
        }
        throw new InvalidDataException("Native lookup exceeded its eight-node bound.");
    }

    internal (ulong ReferencedEntityAddress, ulong SourceComponentAddress) ResolveReferencedComponent(ulong key, ulong indexRva)
    {
        var referencedEntity = ResolveEntity(key);
        var referencedBytes = Take(referencedEntity, 128);
        var component = ResolveComponent(indexRva, referencedBytes);
        if (ReadU64(Take(checked(Pointer(component, 0x18) + 0x10), 8)) != referencedEntity)
            throw new InvalidDataException("Referenced component owner mismatch.");
        return (referencedEntity, component);
    }

    internal ulong ResolveComponent(ulong indexRva) => ResolveComponent(indexRva, entityBytes);

    private ulong ResolveComponent(ulong indexRva, byte[] ownerBytes)
    {
        if (indexRva > identity.ModuleSize - 4)
            throw new InvalidDataException("Component selector lies outside the pinned module.");
        var indexRaw = Take(checked(identity.ModuleBaseAddress + indexRva), 4);
        var index = BinaryPrimitives.ReadInt32LittleEndian(indexRaw);
        if (index is < 0 or >= 0x60)
            throw new InvalidDataException("Invalid native component selector.");
        var componentTable = Pointer(ReadU64(ownerBytes.AsSpan(0x78, 8)));
        // The full anchored entity captures both selector slot and component table.
        var slot = ownerBytes[0x18 + index];
        if (slot == 0xFF)
            throw new InvalidDataException("Player has no requested native component.");
        var componentSlot = Pointer(checked(componentTable + (ulong)slot * 8));
        return Pointer(ReadU64(Take(componentSlot, 8)));
    }

    internal void VerifyUnchanged()
    {
        if (session.Identity != identity)
            throw new InvalidDataException("Native current-build process identity changed during capture.");
        foreach (var anchor in anchors)
            RequireSame(Exact(session, anchor.Address, anchor.Bytes.Length), anchor.Bytes);
        if (session.Identity != identity)
            throw new InvalidDataException("Native current-build process identity changed during capture.");
    }

    private byte[] Take(ulong address, int size)
    {
        var bytes = Exact(session, address, size);
        anchors.Add((address, (byte[])bytes.Clone()));
        return bytes;
    }

    internal static ulong BucketIndex(ulong key, ulong count)
    {
        if (count is < 1 or > (1 << 24))
            throw new ArgumentOutOfRangeException(nameof(count));
        var low = unchecked((int)(uint)key);
        var quotient = low / 127773;
        var remainder = low - quotient * 127773;
        var signed = unchecked((int)((long)remainder * 16807 - (long)quotient * 2836));
        var adjusted = signed >= 0 ? signed : (long)signed + 2147483647;
        return unchecked((uint)adjusted) % count;
    }

    internal static byte[] Exact(IReadOnlyNativeMemorySession source, ulong address, int size)
    {
        if (address < MinimumUserAddress || size is < 1 or > 4096 ||
            address > MaximumUserAddress - (ulong)size)
            throw new InvalidDataException("Native candidate range is outside bounded user memory.");
        var result = source.Read(address, size);
        if (result.Status != "success" || result.Bytes.Length != size)
            throw new InvalidDataException("Native candidate read was incomplete or unavailable.");
        return result.Bytes;
    }

    internal static ulong Pointer(ulong value, int length = 8)
    {
        if (length < 1 || value < MinimumUserAddress || value % 8 != 0 ||
            value > MaximumUserAddress - (ulong)length)
            throw new InvalidDataException("Native candidate pointer is invalid.");
        return value;
    }

    private static ulong ReadU64(ReadOnlySpan<byte> bytes) =>
        BinaryPrimitives.ReadUInt64LittleEndian(bytes);

    internal static void RequireSame(byte[] now, byte[] earlier)
    {
        if (!now.AsSpan().SequenceEqual(earlier))
            throw new InvalidDataException("Native current-build player ownership or payload changed during capture.");
    }
}
