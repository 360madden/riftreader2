using System.Buffers.Binary;
using System.Globalization;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

internal sealed record UnitPositionCandidateRow(string UnitKey, string UnitIdCandidate,
    string EntityAddressDecimal, CurrentBuildXyz PositionCandidate, uint[] RawBits,
    DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc, double HorizontalDistanceCandidate);

internal sealed record CurrentBuildUnitPositionsObservation(NativeProcessIdentity Identity,
    DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc, string SelfKey,
    CurrentBuildXyz SelfPositionCandidate, uint[] SelfPositionRawBits, int UnitLimit,
    int Examined, int NoPosition, int Unavailable, int UnavailableChains, int BucketsExamined,
    ulong StartBucket, ulong BucketCount, bool UnitLimitReached, int ReadBytes,
    CurrentBuildOpticalCameraCandidate OpticalCameraCandidate,
    CurrentBuildOpticalCameraCandidate OpticalCameraAfterCandidate, bool CameraStableCandidate,
    IReadOnlyList<UnitPositionCandidateRow> Rows)
{
    public string Qualification => "bounded loaded-unit subset; stored positions, world coverage, freshness and restart unqualified";
    public string WorldIdentityStatus => "unavailable";
}

internal static class CurrentBuildUnitPositionsCandidateReader
{
    internal static CurrentBuildUnitPositionsObservation Read(IReadOnlyNativeMemorySession source,
        int unitLimit = 512, ulong startBucket = 0)
    {
        if (unitLimit is < 1 or > 512) throw new ArgumentOutOfRangeException(nameof(unitLimit));
        var started = DateTimeOffset.UtcNow;
        var session = new BoundedSession(source);
        var id = session.Identity;
        if (id.ProcessId <= 0 || id.ProcessStartUtcTicks <= 0 || id.ModuleSize < 0x33624B0 ||
            !string.Equals(id.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Unit positions require the exact build and process epoch.");
        byte[] Take(ulong address, int count) => CurrentBuildPlayerLookup.Exact(session, address, count);
        ulong Ptr(ulong address, int count = 8) => CurrentBuildPlayerLookup.Pointer(address, count);
        var lookup = CurrentBuildPlayerLookup.Resolve(session);
        var selfComponent = lookup.ResolveComponent(0x2F588A0);
        CurrentBuildOwnedPosition ReadSelf() => CurrentBuildPositionCandidateReader.ReadOwned(session,
            _ => new(lookup.PlayerKey, lookup.EntityAddress, selfComponent, lookup.VerifyUnchanged));
        var self = ReadSelf();
        var camera = CurrentBuildOpticalCameraCandidateReader.TryRead(session, lookup.PlayerSystemAddress);
        var globals = new List<(ulong Address, byte[] Bytes)>();
        byte[] Global(ulong address, int count)
        {
            var bytes = Take(address, count);
            globals.Add((address, bytes));
            return bytes;
        }
        var manager = Ptr(U64(Global(id.ModuleBaseAddress + 0x33624A8, 8)));
        var table = Ptr(U64(Global(manager + 0x50, 8)));
        var header = Global(table, 24);
        var buckets = Ptr(U64(header));
        var stride = U64(header.AsSpan(8));
        var count = U64(header.AsSpan(16));
        if (stride is < 24 or > 4096 || stride % 8 != 0 || count is < 1 or > 4096)
            throw new InvalidDataException("Invalid unit-position table header.");
        Ptr(buckets, checked((int)((count - 1) * stride + 24)));
        var selector = BinaryPrimitives.ReadInt32LittleEndian(Global(id.ModuleBaseAddress + 0x2F588A0, 4));
        if (selector is < 0 or >= 0x60) throw new InvalidDataException("Invalid unit-position selector.");
        startBucket %= count;
        var rows = new List<UnitPositionCandidateRow>();
        var keys = new HashSet<ulong>();
        var examined = 0;
        var noPosition = 0;
        var unavailable = 0;
        var unavailableChains = 0;
        var visited = 0;
        var limited = false;
        for (ulong step = 0; step < count; step++)
        {
            if (examined >= unitLimit) { limited = true; break; }
            visited++;
            var bucketIndex = (startBucket + step) % count;
            var address = checked(buckets + bucketIndex * stride);
            var seen = new HashSet<ulong>();
            var path = new List<(ulong Address, byte[] Bytes)>();
            var head = true;
            for (var chain = 0; chain < 128; chain++)
            {
                if (examined >= unitLimit) { limited = true; break; }
                byte[] node;
                try
                {
                    if (!seen.Add(address)) throw new InvalidDataException("Cyclic unit-position chain.");
                    node = Take(Ptr(address, 24), 24);
                    path.Add((address, node));
                }
                catch (InvalidDataException)
                {
                    if (session.UsedBytes > BoundedSession.MaximumBytes) throw;
                    unavailableChains++;
                    break;
                }
                var link = U64(node);
                if (!head || (link & 1) == 0)
                {
                    examined++;
                    var unitStart = DateTimeOffset.UtcNow;
                    try
                    {
                        var anchors = new List<(ulong Address, byte[] Bytes)>(path);
                        byte[] Anchor(ulong location, int length)
                        {
                            var bytes = Take(location, length);
                            anchors.Add((location, bytes));
                            return bytes;
                        }
                        void Verify()
                        {
                            foreach (var anchor in anchors)
                                CurrentBuildPlayerLookup.RequireSame(Take(anchor.Address, anchor.Bytes.Length), anchor.Bytes);
                        }
                        var key = U64(node.AsSpan(8));
                        if (key == 0 || CurrentBuildPlayerLookup.BucketIndex(key, count) != bucketIndex || !keys.Add(key))
                            throw new InvalidDataException("Invalid, misplaced or duplicate unit key.");
                        var entity = Ptr(U64(node.AsSpan(16)), 128);
                        var entityBytes = Anchor(entity, 128);
                        var slot = entityBytes[0x18 + selector];
                        if (slot == 0xFF) { Verify(); noPosition++; }
                        else
                        {
                            var components = Ptr(U64(entityBytes.AsSpan(0x78)));
                            var component = Ptr(U64(Anchor(checked(components + slot * 8UL), 8)), 0x110);
                            var position = CurrentBuildPositionCandidateReader.ReadOwned(session,
                                _ => new(key, entity, component, Verify));
                            var dx = (double)position.Position.X - self.Position.X;
                            var dz = (double)position.Position.Z - self.Position.Z;
                            rows.Add(new(key.ToString(CultureInfo.InvariantCulture), $"u{key:X16}",
                                entity.ToString(CultureInfo.InvariantCulture), position.Position,
                                Bits(position.Position), unitStart, DateTimeOffset.UtcNow, Math.Sqrt(dx * dx + dz * dz)));
                        }
                    }
                    catch (InvalidDataException)
                    {
                        if (session.UsedBytes > BoundedSession.MaximumBytes) throw;
                        unavailable++;
                    }
                }
                var next = link & ~1UL;
                if (next == 0) break;
                try { address = Ptr(next, 24); }
                catch (InvalidDataException) { unavailableChains++; break; }
                if (chain == 127) unavailableChains++;
                head = false;
            }
        }
        var afterSelf = ReadSelf();
        if (afterSelf.Position != self.Position) throw new InvalidDataException("Self moved across unit-position scan.");
        var afterCamera = CurrentBuildOpticalCameraCandidateReader.TryRead(session, lookup.PlayerSystemAddress);
        foreach (var anchor in globals)
            CurrentBuildPlayerLookup.RequireSame(Take(anchor.Address, anchor.Bytes.Length), anchor.Bytes);
        lookup.VerifyUnchanged();
        if (session.Identity != id) throw new InvalidDataException("Unit-position process epoch changed.");
        return new(id, started, DateTimeOffset.UtcNow, self.UnitKeyText, self.Position, Bits(self.Position),
            unitLimit, examined, noPosition, unavailable, unavailableChains, visited, startBucket, count,
            limited, session.UsedBytes, camera, afterCamera,
            CurrentBuildOpticalCameraCandidateReader.SameProjectionSnapshot(camera, afterCamera), rows);
    }

    private static uint[] Bits(CurrentBuildXyz xyz) =>
        [BitConverter.SingleToUInt32Bits(xyz.X), BitConverter.SingleToUInt32Bits(xyz.Y), BitConverter.SingleToUInt32Bits(xyz.Z)];
    private static ulong U64(ReadOnlySpan<byte> bytes) => BinaryPrimitives.ReadUInt64LittleEndian(bytes);

    // The command owns source lifetime. This wrapper bounds every reader it reuses.
    private sealed class BoundedSession(IReadOnlyNativeMemorySession source) : IReadOnlyNativeMemorySession
    {
        internal const int MaximumBytes = 2 * 1024 * 1024;
        internal int UsedBytes { get; private set; }
        public NativeProcessIdentity Identity => source.Identity;
        public NativeReadResult Read(ulong address, int length)
        {
            UsedBytes = checked(UsedBytes + length);
            if (UsedBytes > MaximumBytes) throw new InvalidDataException("Unit-position read budget exceeded.");
            return source.Read(address, length);
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken ct) => source.RevalidateAsync(ct);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
