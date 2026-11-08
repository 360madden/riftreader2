using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildPairedPositionCandidateReaderTests
{
    const ulong M = 0x140000000, Manager = 0x20000000, Table = 0x20010000,
        Bucket = 0x20020000, Entity = 0x20040000, Components = 0x20050000,
        Health = 0x20060000, Position = 0x20070000, SelfPosition = 0x20080000,
        SelfEntity = 0x20090000, TargetKey = 0x80000002CD0034D1;
    static readonly DateTimeOffset Epoch = new(2026, 11, 8, 0, 0, 0, TimeSpan.Zero);

    [Fact] public void SameSessionMissingTargetHealthHasOwnedPairAndLocalClock()
    {
        var s = Fixture(); var calls = 0;
        var result = Read(s, _ => { calls++; return Context(s); });
        Assert.True(calls >= 3);
        Assert.Equal("paired-candidate", result.Status);
        Assert.Equal("123", result.Self.UnitKey);
        Assert.Equal(TargetKey.ToString(), result.Target!.UnitKey);
        Assert.Equal("u80000002CD0034D1", result.Target.UnitIdCandidate);
        Assert.Equal(1.5f, result.Self.Position!.X);
        Assert.Equal(7f, result.Target.Position!.X);
        Assert.NotEqual(result.Self.UnitKey, result.Target.UnitKey);
        Assert.Equal(32, result.ClockDomain.Length);
        Assert.True(result.StartSkewMilliseconds >= 0);
        Assert.True(result.MaximumSampleSeparationMilliseconds >= result.StartSkewMilliseconds);
        Assert.Equal("unavailable", result.ZoneIdentityStatus);
        Assert.Equal("unavailable", result.WorldIdentityStatus);
        Assert.False(result.AtomicityQualified);
        Assert.Contains("candidate-only", result.Qualification);
    }

    [Fact] public void PresentHealthCannotBypassRealVitalsReader()
    {
        var s = Fixture(); s.Put(Entity + 0x18, [0]);
        s.Put(Components, Q(Health)); s.Put(Health + 0x10, Q(Entity));
        // No typed vitals fixture is supplied. A synthetic/fake-vitals shortcut
        // would allow XYZ; the real reader must instead reject unavailable bytes.
        Assert.Throws<InvalidDataException>(() => Read(s));
    }

    [Fact] public void MissingTargetAndPositionStayExplicit()
    {
        var s = Fixture(); var noTarget = Read(s, _ => Context(s, null));
        Assert.Equal("target-unavailable", noTarget.Status);
        Assert.Null(noTarget.Target);
        Assert.Null(noTarget.StartSkewMilliseconds);
        s = Fixture(); s.Put(Entity + 0x19, [255]);
        var noPosition = Read(s);
        Assert.Equal("target-unavailable", noPosition.Status);
        Assert.Equal("component-unavailable", noPosition.Target!.Status);
        Assert.Null(noPosition.Target.Position);
        Assert.NotNull(noPosition.Self.Position);
    }

    [Fact] public void SelectionSelfAndProcessIdentityChangesReject()
    {
        foreach (var change in new[] { "target", "self", "entity", "build", "module" })
        {
            var s = Fixture(); int n = 0;
            Assert.Throws<InvalidDataException>(() => Read(s, _ =>
            {
                var c = Context(s);
                if (++n == 1) return c;
                return change switch
                {
                    "target" => c with { TargetKeyCandidate = TargetKey + 1 },
                    "self" => c with { UnitKey = 124 },
                    "entity" => c with { Entity = SelfEntity + 8 },
                    "build" => c with { Identity = s.Identity with { ExecutableSha256 = new string('A', 64) } },
                    _ => c with { Identity = s.Identity with { ModuleBaseAddress = M + 8 } }
                };
            }));
        }
    }

    [Fact] public void SelfMutationDuringTargetAcquisitionRejects()
    {
        var s = Fixture();
        s.OnRead = (address, _) =>
        {
            if (address == M + 0x33624A8) s.Put(SelfPosition + 0x48, Xyz(99, 2, 3));
        };
        Assert.Throws<InvalidDataException>(() => Read(s));
    }

    [Fact] public void SourceOwnerAndBacklinksReject()
    {
        var s = Fixture(); s.Put(SelfPosition + 0x10, Q(SelfEntity + 8));
        Assert.Throws<InvalidDataException>(() => Read(s));
        s = Fixture(); s.Put(Position + 0x10, Q(SelfEntity));
        Assert.Throws<InvalidDataException>(() => Read(s));
        s = Fixture();
        Assert.Throws<InvalidDataException>(() => Read(s, verify: () => throw new InvalidDataException("owner changed")));
    }

    [Fact] public void ClockSkewBudgetAndUtcRegressionReject()
    {
        var s = Fixture(); int n = 0;
        Assert.Throws<InvalidDataException>(() => Read(s, clock: () => (Epoch.AddMilliseconds(++n * 300), n * 300), maxSpan: 1000));
        s = Fixture(); n = 0;
        Assert.Throws<InvalidDataException>(() => Read(s, clock: () => (Epoch.AddMilliseconds(-++n), n)));
        s = Fixture();
        Assert.Throws<ArgumentOutOfRangeException>(() => Read(s, maxSpan: 0));
    }

    [Fact] public void WrongFullTargetKeyAndInvalidBuildReject()
    {
        var s = Fixture(); s.Put(Bucket, Node(0x10000002CD0034D1, Entity));
        Assert.Throws<InvalidDataException>(() => Read(s));
        s = Fixture(); s.Identity = s.Identity with { ExecutableSha256 = new string('A', 64) };
        Assert.Throws<InvalidDataException>(() => Read(s));
    }

    static CurrentBuildPairedPositionObservation Read(Fake s,
        Func<IReadOnlyNativeMemorySession, CurrentBuildPlayerContextObservation>? context = null,
        Action? verify = null, Func<(DateTimeOffset Utc, double Milliseconds)>? clock = null, int maxSpan = 1000)
    {
        int n = 0;
        return CurrentBuildPairedPositionCandidateReader.Read(s, context ?? (_ => Context(s)),
            (_, _) => new(123, SelfPosition, verify ?? (() => { })), maxSpan,
            clock ?? (() => (Epoch.AddMilliseconds(n), n++)));
    }

    static CurrentBuildPlayerContextObservation Context(Fake s, ulong? key = TargetKey) =>
        new(s.Identity, Epoch, Epoch, 123, SelfEntity, 0, 0, 0, key ?? 0,
            key.HasValue ? "fallback-key-candidate" : "override-unavailable", key, null,
            41, "raw-candidate", 0, "raw-byte-candidate", false);

    static Fake Fixture()
    {
        var s = new Fake();
        s.Put(M + 0x33624A8, Q(Manager)); s.Put(Manager + 0x50, Q(Table));
        var header = new byte[24]; Q(Bucket).CopyTo(header, 0); Q(24).CopyTo(header, 8); Q(1).CopyTo(header, 16);
        s.Put(Table, header); s.Put(Bucket, Node(TargetKey, Entity));
        s.Put(M + 0x2F57850, BitConverter.GetBytes(0)); s.Put(Entity + 0x18, [255]);
        s.Put(Entity + 0x78, Q(Components)); s.Put(M + 0x2F588A0, BitConverter.GetBytes(1));
        s.Put(Entity + 0x19, [1]); s.Put(Components + 8, Q(Position));
        PositionBytes(s, Position, Entity, 7, 8, 9);
        PositionBytes(s, SelfPosition, SelfEntity, 1.5f, 2, 3);
        return s;
    }

    static void PositionBytes(Fake s, ulong address, ulong entity, float x, float y, float z)
    {
        s.Put(address + 0x10, Q(entity));
        var raw = new byte[0x110]; Xyz(x, y, z).CopyTo(raw, 0x48);
        s.Put(address, raw); s.Put(address + 0x48, Xyz(x, y, z));
    }
    static byte[] Xyz(float x, float y, float z)
    {
        var b = new byte[12]; BinaryPrimitives.WriteSingleLittleEndian(b, x);
        BinaryPrimitives.WriteSingleLittleEndian(b.AsSpan(4), y); BinaryPrimitives.WriteSingleLittleEndian(b.AsSpan(8), z); return b;
    }
    static byte[] Q(ulong v) { var b = new byte[8]; BinaryPrimitives.WriteUInt64LittleEndian(b, v); return b; }
    static byte[] Node(ulong key, ulong entity) { var b = new byte[24]; Q(key).CopyTo(b, 8); Q(entity).CopyTo(b, 16); return b; }

    sealed class Fake : IReadOnlyNativeMemorySession
    {
        readonly Dictionary<ulong, byte[]> data = [];
        public NativeProcessIdentity Identity { get; set; } = new(123, 456, "rift_x64.exe", CurrentBuildPlayerLookup.GameSha256, M, 0x4000000);
        public Action<ulong, int>? OnRead { get; set; }
        public void Put(ulong a, byte[] b) => data[a] = b;
        public NativeReadResult Read(ulong a, int n)
        {
            OnRead?.Invoke(a, n);
            return data.TryGetValue(a, out var b) && b.Length == n ? new("success", b.ToArray(), null, null) : new("unavailable", [], null, null);
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken c) => ValueTask.FromResult<string?>(null);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
