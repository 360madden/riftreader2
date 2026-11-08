using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildPairedZoneKeyCandidateReaderTests
{
    const ulong M = 0x140000000, System = 0x20000000, SelfEntity = 0x20010000,
        SelfHealth = 0x20020000, SelfOwner = 0x20030000, Manager = 0x20040000,
        Table = 0x20050000, Bucket = 0x20060000, TargetEntity = 0x20070000,
        Components = 0x20080000, TargetHealth = 0x20090000, TargetOwner = 0x200A0000,
        Key = 0x80000002CD0034D1;
    static readonly DateTimeOffset Utc = new(2026, 11, 8, 0, 0, 0, TimeSpan.Zero);

    [Fact] public void IndependentEqualKeysAreOnlyMatchingCandidates()
    {
        var s = Fixture();
        var result = Read(s);
        Assert.Equal("matching-zone-key-candidate", result.ZoneKeyRelation);
        Assert.Equal(123U, result.SelfZone.RawZoneKey);
        Assert.Equal(123U, result.TargetZone.RawZoneKey);
        Assert.Equal(SelfOwner, result.SelfZone.Owner);
        Assert.Equal(TargetOwner, result.TargetZone.Owner);
        Assert.Equal("44", result.SelfZone.UnitKey);
        Assert.Equal(Key.ToString(), result.TargetZone.UnitKey);
        Assert.Equal("unavailable", result.SameWorldStatus);
        Assert.Equal("not-derived", result.PublicZoneIdStatus);
        Assert.False(result.AtomicityQualified);
        Assert.Equal("paired-candidate", result.Positions.Status);
    }

    [Fact] public void DifferentTargetKeyIsNotReplacedBySelf()
    {
        var s = Fixture(); s.Put(TargetOwner + 0x150, BitConverter.GetBytes(999U));
        var result = Read(s);
        Assert.Equal("different-zone-key-candidate", result.ZoneKeyRelation);
        Assert.Equal(123U, result.SelfZone.RawZoneKey); Assert.Equal(999U, result.TargetZone.RawZoneKey);
    }

    [Fact] public void MissingTargetHealthKeepsXyzAndUnavailableZone()
    {
        var s = Fixture(); s.Put(TargetEntity + 0x18, [255]);
        var result = Read(s);
        Assert.Equal("health-component-absent", result.TargetZone.UnavailableReason);
        Assert.Null(result.TargetZone.RawZoneKey); Assert.Equal("unavailable", result.ZoneKeyRelation);
        Assert.Equal(7f, result.Positions.Target!.Position!.X);
        Assert.Equal(123U, result.SelfZone.RawZoneKey);
    }

    [Fact] public void NoGuardedTargetAndUnknownOwnerRemainUnavailable()
    {
        var s = Fixture();
        var result = Read(s, context: _ => Context(s, null), pair: _ => Pair(s, null));
        Assert.Equal("guarded-target-unavailable", result.TargetZone.UnavailableReason);
        Assert.Null(result.TargetZone.RawZoneKey);
        s = Fixture(); s.Put(TargetOwner, Q(M + 0x1000));
        result = Read(s);
        Assert.Equal("unverified-0294-owner", result.TargetZone.UnavailableReason);
        Assert.Null(result.TargetZone.RawZoneKey);
        Assert.Equal("unavailable", result.ZoneKeyRelation);
    }

    [Fact] public void ZeroIsPreservedAsRawCandidateNotInventedMissingZone()
    {
        var s = Fixture(); s.Put(SelfOwner + 0x150, BitConverter.GetBytes(0U));
        s.Put(TargetOwner + 0x150, BitConverter.GetBytes(0U));
        var result = Read(s);
        Assert.Equal("raw-zone-key-candidate", result.SelfZone.Status);
        Assert.Equal(0U, result.SelfZone.RawZoneKey);
        Assert.Equal("matching-zone-key-candidate", result.ZoneKeyRelation);
        Assert.Equal("unavailable", result.SameWorldStatus);
    }

    [Fact] public void ChangedZoneOwnerLookupAndSelectorAnchorsRejectAcrossPair()
    {
        foreach (var address in new[] { SelfOwner + 0x150, TargetOwner + 0x150,
            TargetHealth + 0x40, TargetHealth + 0x10, TargetEntity + 0x18,
            M + 0x2F57850, TargetOwner, M + 0x34731B0, Bucket })
        {
            var s = Fixture();
            Assert.Throws<InvalidDataException>(() => Read(s, pair: _ =>
            {
                var original = s.Data[address]; var changed = original.ToArray(); changed[0] ^= 8;
                s.Put(address, changed); return Pair(s);
            }));
        }
    }

    [Fact] public void SelectionChangeAndForeignPairReject()
    {
        var s = Fixture(); int calls = 0;
        Assert.Throws<InvalidDataException>(() => Read(s, context: _ => Context(s, ++calls == 1 ? Key : Key + 1)));
        s = Fixture();
        Assert.Throws<InvalidDataException>(() => Read(s, pair: _ => Pair(s) with { Identity = s.Identity with { ProcessStartUtcTicks = 457 } }));
        s = Fixture();
        Assert.Throws<InvalidDataException>(() => Read(s, pair: _ => Pair(s) with { Target = Pair(s).Target! with { UnitKey = "44" } }));
    }

    [Fact] public void WrongHighBitsAndBacklinkCannotJoin()
    {
        var s = Fixture(); s.Put(Bucket, Node(0x10000002CD0034D1, TargetEntity));
        Assert.Throws<InvalidDataException>(() => Read(s));
        s = Fixture(); s.Put(TargetHealth + 0x10, Q(SelfEntity));
        Assert.Throws<InvalidDataException>(() => Read(s));
        s = Fixture(); s.Put(System + 0x3F8, Q(TargetEntity));
        Assert.Throws<InvalidDataException>(() => Read(s));
    }

    [Fact] public void WrongBuildAndBoundedClockReject()
    {
        var s = Fixture(); s.Identity = s.Identity with { ExecutableSha256 = new string('A', 64) };
        Assert.Throws<InvalidDataException>(() => Read(s));
        s = Fixture(); int n = 0;
        Assert.Throws<InvalidDataException>(() => Read(s, elapsed: () => n++ == 0 ? 0 : 1001));
        s = Fixture();
        Assert.Throws<ArgumentOutOfRangeException>(() => Read(s, bound: 0));
    }

    static CurrentBuildPairedZoneKeyObservation Read(Fake s,
        Func<IReadOnlyNativeMemorySession, CurrentBuildPlayerContextObservation>? context = null,
        Func<IReadOnlyNativeMemorySession, CurrentBuildPairedPositionObservation>? pair = null,
        Func<double>? elapsed = null, int bound = 1000) =>
        CurrentBuildPairedZoneKeyCandidateReader.Read(s, context ?? (_ => Context(s)),
            (session, _) => (pair ?? (_ => Pair(s)))(session), bound, elapsed ?? (() => 1));

    static CurrentBuildPlayerContextObservation Context(Fake s, ulong? key = Key) =>
        new(s.Identity, Utc, Utc, 44, SelfEntity, SelfHealth, SelfOwner, SelfHealth, key ?? 0,
            key.HasValue ? "fallback-key-candidate" : "override-unavailable", key, null, 41, "candidate", 0, "raw-byte-candidate", false);
    static CurrentBuildPairedPositionObservation Pair(Fake s, ulong? key = Key)
    {
        var self = new PairedPositionCandidateSample("candidate", "44", "u000000000000002C", new(1, 2, 3), Utc, Utc, 0, 1);
        var target = key.HasValue ? new PairedPositionCandidateSample("candidate", key.Value.ToString(), $"u{key:X16}", new(7, 8, 9), Utc, Utc, 2, 3) : null;
        return new(s.Identity, Utc, Utc, "one-pair-clock", self, target, target is null ? "unavailable" : "candidate",
            key.HasValue ? "fallback-key-candidate" : "override-unavailable",
            key.HasValue ? "fallback-key-candidate" : "override-unavailable", 4, target is null ? null : 2, target is null ? null : 3);
    }
    static Fake Fixture()
    {
        var s = new Fake();
        s.Put(M + 0x33623E0, Q(System)); s.Put(System + 0x360, Q(44)); s.Put(System + 0x3F8, Q(SelfEntity));
        Owner(s, SelfEntity, SelfHealth, SelfOwner); Owner(s, TargetEntity, TargetHealth, TargetOwner);
        s.Put(M + 0x33624A8, Q(Manager)); s.Put(Manager + 0x50, Q(Table));
        var header = new byte[24]; Q(Bucket).CopyTo(header, 0); Q(24).CopyTo(header, 8); Q(1).CopyTo(header, 16);
        s.Put(Table, header); s.Put(Bucket, Node(Key, TargetEntity));
        s.Put(M + 0x2F57850, BitConverter.GetBytes(0)); s.Put(TargetEntity + 0x18, [0]);
        s.Put(TargetEntity + 0x78, Q(Components)); s.Put(Components, Q(TargetHealth)); return s;
    }
    static void Owner(Fake s, ulong entity, ulong health, ulong owner)
    {
        s.Put(health + 0x10, Q(entity)); s.Put(health + 0x40, Q(owner)); s.Put(owner, Q(M + 0x2927448));
        s.Put(M + 0x2927488, Q(M + 0x19D21E0)); s.Put(M + 0x34731B0, Q(M + 0x2929BD0));
        s.Put(M + 0x2929BD8, Q(M + 0x19F4D60)); s.Put(owner + 0x150, BitConverter.GetBytes(123U));
    }
    static byte[] Q(ulong v) { var b = new byte[8]; BinaryPrimitives.WriteUInt64LittleEndian(b, v); return b; }
    static byte[] Node(ulong key, ulong entity) { var b = new byte[24]; Q(key).CopyTo(b, 8); Q(entity).CopyTo(b, 16); return b; }
    sealed class Fake : IReadOnlyNativeMemorySession
    {
        public Dictionary<ulong, byte[]> Data { get; } = [];
        public NativeProcessIdentity Identity { get; set; } = new(123, 456, "rift_x64.exe", CurrentBuildPlayerLookup.GameSha256, M, 0x4000000);
        public void Put(ulong a, byte[] b) => Data[a] = b;
        public NativeReadResult Read(ulong a, int n) => Data.TryGetValue(a, out var b) && b.Length == n
            ? new("success", b.ToArray(), null, null) : new("unavailable", [], null, null);
        public ValueTask<string?> RevalidateAsync(CancellationToken c) => ValueTask.FromResult<string?>(null);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
