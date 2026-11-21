using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildUnitLevelsTests
{
    private const ulong Module = 0x140000000, Manager = 0x20000000,
        Table = 0x20010000, Bucket = 0x20020000, SelfNode = 0x20030000,
        TargetNode = 0x20030100, SelfEntity = 0x20040000,
        TargetEntity = 0x20050000, Components = 0x20060000,
        Health = 0x20070000, Owner = 0x20080000,
        Alternate = 0x20090000, First = 0x200A0000,
        Second = 0x200B0000, System = 0x200C0000,
        SelfKey = 42, TargetKey = 0x800000009A0026CE;

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void NativeExactKeyReturnsNumericAlternateLevelCandidate(bool updated)
    {
        var fixture = Fixture(updated);
        var source = CurrentBuildUnitLevelsSampleCommand.Read(fixture, [TargetKey]);
        Assert.Equal(SelfKey.ToString(), source.SelfKey);
        Assert.Equal("candidate-only; exact keyed native level source, no UI/API meaning, hostility, attackability, proximity freshness or world-instance proof",
                     source.Qualification);
        var row = Assert.Single(source.Rows);
        Assert.Equal(TargetKey.ToString(), row.UnitKey);
        Assert.Equal("u800000009A0026CE", row.UnitIdCandidate);
        Assert.Equal(TargetEntity.ToString(), row.EntityAddressDecimal);
        Assert.Equal("numeric-level-candidate", row.Status);
        Assert.Equal("alternate-primary", row.LevelBranch);
        Assert.Equal(10, row.NumericLevelCandidate);
        Assert.Null(row.UnavailableReason);
    }

    [Fact]
    public void AlternateSecondaryRouteReturnsLevelWhileOwnerRawLevelIsZero()
    {
        var fixture = Fixture(updated: true);
        fixture.Put(First + 0x64, BitConverter.GetBytes(-1));
        var row = Assert.Single(CurrentBuildUnitLevelsSampleCommand.Read(
            fixture, [TargetKey]).Rows);
        Assert.Equal("numeric-level-candidate", row.Status);
        Assert.Equal("alternate-secondary", row.LevelBranch);
        Assert.Equal(20, row.NumericLevelCandidate);
    }

    [Fact]
    public void WrongOwnerTypeNeverPublishesNumericLevel()
    {
        var fixture = Fixture(updated: true);
        fixture.Put(Module + 0x2933258, Q(Module + 0x19D21E0));
        var row = Assert.Single(CurrentBuildUnitLevelsSampleCommand.Read(
            fixture, [TargetKey]).Rows);
        Assert.Equal("unverified-owner-type", row.Status);
        Assert.Null(row.NumericLevelCandidate);
        Assert.Equal("owner-vptr-or-getter-mismatch", row.UnavailableReason);
    }

    [Fact]
    public void InvalidOrAbsentLevelDoesNotInventLevelZero()
    {
        foreach (var value in new[] { 0, 2000 })
        {
            var fixture = Fixture(updated: true);
            fixture.Put(First + 0x64, BitConverter.GetBytes(value));
            var row = Assert.Single(CurrentBuildUnitLevelsSampleCommand.Read(
                fixture, [TargetKey]).Rows);
            Assert.Equal("unavailable", row.Status);
            Assert.Null(row.NumericLevelCandidate);
            Assert.Equal("numeric-level-outside-bounds", row.UnavailableReason);
        }
        var unavailable = Fixture(updated: true);
        unavailable.Put(Components + 8, Q(0));
        var missing = Assert.Single(CurrentBuildUnitLevelsSampleCommand.Read(
            unavailable, [TargetKey]).Rows);
        Assert.Equal("unavailable", missing.Status);
        Assert.Null(missing.NumericLevelCandidate);
        Assert.Equal("alternate-level-component-unavailable", missing.UnavailableReason);
    }

    [Fact]
    public void MissingLoadedUnitReturnsExplicitUnavailable()
    {
        var fixture = Fixture(updated: true);
        var rows = CurrentBuildUnitLevelsSampleCommand.Read(
            fixture, [TargetKey, TargetKey + 1]).Rows;
        Assert.Equal("numeric-level-candidate", rows[0].Status);
        Assert.Equal("unavailable", rows[1].Status);
        Assert.Null(rows[1].NumericLevelCandidate);
        Assert.Equal("native-component-or-owner-unavailable",
                     rows[1].UnavailableReason);
    }

    [Fact]
    public void ChangedLevelSourceCannotBeReportedAsCandidate()
    {
        var fixture = Fixture(updated: true);
        fixture.Change(First + 0x64, BitConverter.GetBytes(99));
        var row = Assert.Single(CurrentBuildUnitLevelsSampleCommand.Read(
            fixture, [TargetKey]).Rows);
        Assert.Equal("unavailable", row.Status);
        Assert.Null(row.NumericLevelCandidate);
        Assert.Equal("native-component-or-owner-unavailable", row.UnavailableReason);
    }

    [Fact]
    public void InvalidOrDuplicateKeysRejectedBeforeNativeReads()
    {
        var fixture = Fixture(updated: true);
        foreach (var keys in new[] { Array.Empty<ulong>(), new[] { 0UL },
                     new[] { TargetKey, TargetKey },
                     Enumerable.Range(1,13).Select(n=>(ulong)n).ToArray() })
        {
            Assert.Throws<ArgumentException>(()=>
                CurrentBuildUnitLevelsSampleCommand.Read(fixture, keys));
        }
        Assert.Equal(0, fixture.ReadCount);
    }

    private static Fake Fixture(bool updated)
    {
        var s = new Fake(updated);
        s.Put(Module + (updated ? 0x3373BA0UL : 0x33623E0UL), Q(System));
        s.Put(Module + (updated ? 0x3373C68UL : 0x33624A8UL), Q(Manager));
        s.Put(System + 0x360, Q(SelfKey));
        s.Put(Manager + 0x50, Q(Table));
        s.Put(Table, Q(Bucket).Concat(Q(24)).Concat(Q(1)).ToArray());
        s.Put(Bucket, Node(SelfNode | 1, 0, 0));
        s.Put(SelfNode, Node(TargetNode, SelfKey, SelfEntity));
        s.Put(TargetNode, Node(0, TargetKey, TargetEntity));
        s.Put(SelfEntity, new byte[128]);
        var entity = new byte[128];
        entity[0x18] = 0;
        entity[0x19] = 1;
        Q(Components).CopyTo(entity, 0x78);
        s.Put(TargetEntity, entity);
        s.Put(Components, Q(Health).Concat(Q(Alternate)).ToArray());
        var health = new byte[0x50];
        Q(TargetEntity).CopyTo(health, 0x10);
        Q(Owner).CopyTo(health, 0x40);
        s.Put(Health, health);
        var owner = new byte[0x19E];
        Q(Module + (updated ? 0x2933218UL : 0x2927448UL)).CopyTo(owner);
        BitConverter.GetBytes(0).CopyTo(owner, 0x100);
        s.Put(Owner, owner);
        s.Put(Module + (updated ? 0x2933258UL : 0x2927488UL),
            Q(Module + (updated ? 0x19D2020UL : 0x19D21E0UL)));
        if (!updated)
        {
            s.Put(Module + 0x34731B0, Q(Module + 0x2929BD0));
            s.Put(Module + 0x2929BD8, Q(Module + 0x19F4D60));
        }
        s.Put(Module + (updated ? 0x2F68850UL : 0x2F57850UL),
            BitConverter.GetBytes(0));
        s.Put(Module + (updated ? 0x2F69270UL : 0x2F58270UL),
            BitConverter.GetBytes(1));
        var alternate = new byte[0x38];
        Q(First).CopyTo(alternate, 0x28);
        Q(Second).CopyTo(alternate, 0x30);
        s.Put(Alternate, alternate);
        var first = new byte[0x68];
        BitConverter.GetBytes(10).CopyTo(first, 0x64);
        s.Put(First, first);
        var second = new byte[0x68];
        BitConverter.GetBytes(20).CopyTo(second, 0x64);
        s.Put(Second, second);
        return s;
    }

    private static byte[] Node(ulong next, ulong key, ulong entity)
    {
        var bytes = new byte[24];
        Q(next).CopyTo(bytes, 0);
        Q(key).CopyTo(bytes, 8);
        Q(entity).CopyTo(bytes, 16);
        return bytes;
    }

    private static byte[] Q(ulong value)
    {
        var bytes = new byte[8];
        BinaryPrimitives.WriteUInt64LittleEndian(bytes, value);
        return bytes;
    }

    private sealed class Fake(bool updated) : IReadOnlyNativeMemorySession
    {
        private readonly Dictionary<ulong, byte[]> original = [];
        private readonly Dictionary<ulong, byte[]> changes = [];
        private readonly HashSet<ulong> seen = [];
        public int ReadCount { get; private set; }
        public NativeProcessIdentity Identity { get; } = new(
            123, 456, @"C:\RIFT\rift_x64.exe",
            updated ? CurrentBuildPlayerLookup.UpdatedGameSha256 :
                      CurrentBuildPlayerLookup.GameSha256,
            Module, 0x4000000);

        public void Put(ulong address, byte[] bytes) => original[address] = bytes;
        public void Change(ulong address, byte[] bytes) => changes[address] = bytes;
        public NativeReadResult Read(ulong address, int length)
        {
            ReadCount++;
            if (!seen.Add(address) && changes.TryGetValue(address, out var altered) &&
                altered.Length == length)
                return new("success", altered.ToArray(), null, null);
            // A narrow synthetic mutation takes precedence over a containing
            // broader memory block, matching the observed address bytes.
            if (original.TryGetValue(address, out var exact) &&
                exact.Length >= length)
                return new("success", exact.AsSpan(0, length).ToArray(), null, null);
            foreach (var (start, bytes) in original)
                if (address >= start &&
                    address + (ulong)length <= start + (ulong)bytes.Length)
                    return new("success",
                        bytes.AsSpan((int)(address-start), length).ToArray(), null, null);
            return new("unavailable", [], null, null);
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken ct)
            => ValueTask.FromResult<string?>(null);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
