using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildLocationContextCandidateReaderTests
{
    private const ulong M = 0x140000000, Manager = 0x20000000, System = 0x20010000,
        Table = 0x20020000, Buckets = 0x20030000, Entity = 0x20040000,
        Components = 0x20050000, Position = 0x20060000, Health = 0x20070000,
        Owner = 0x20080000, Provider = 0x20090000, Wrapper = 0x200A0000,
        Registry = 0x200B0000, Teb = 0x200C0000, Cache = 0x200D0000,
        Holder = 0x200E0000, Zone = 0x200F0000;
    private static readonly NativeThreadEpoch Epoch = new(77, 456, Teb);

    [Fact]
    public async Task NullZoneProviderKeepsRawKeyAndSeparatelyTimedPosition()
    {
        var session = Fixture();
        var result = await Read(session, () => throw new InvalidOperationException("TLS not needed"));
        Assert.Equal(session.Identity, result.Identity);
        Assert.Equal("123", result.UnitKey);
        Assert.Equal("u000000000000007B", result.UnitIdCandidate);
        Assert.Equal(new CurrentBuildXyz(1.5f, -2f, 3f), result.Position);
        Assert.Equal("null-provider", result.Zone.Status);
        Assert.Equal(1234U, result.Zone.RawZoneKey);
        Assert.Null(result.Zone.ZoneIdCandidate);
        Assert.Equal(123UL, result.Zone.SelfKey);
        Assert.Equal(Entity, result.Zone.SelfEntity);
        Assert.Equal(Health, result.Zone.Health);
        Assert.Equal("candidate-only", result.Status);
        Assert.Equal("unavailable", result.WorldInstanceStatus);
        Assert.Contains("not atomic", result.Qualification);
        Assert.True(result.StartedAtUtc <= result.PositionStartedAtUtc);
        Assert.True(result.PositionStartedAtUtc <= result.PositionCompletedAtUtc);
        Assert.True(result.PositionCompletedAtUtc <= result.Zone.StartedAtUtc);
        Assert.True(result.Zone.StartedAtUtc <= result.Zone.CompletedAtUtc);
        Assert.True(result.Zone.CompletedAtUtc <= result.CompletedAtUtc);
        Assert.Equal(1, session.Revalidations);
    }

    [Fact]
    public async Task ResidentZoneUsesExistingTypedReaderAndThreadEpochChecks()
    {
        var session = Fixture(); AddResidentZone(session);
        var threadReads = 0;
        var result = await Read(session, () => { threadReads++; return [Epoch]; });
        Assert.Equal(2, threadReads);
        Assert.Equal("type-0073-candidate", result.Zone.Status);
        Assert.Equal("null", result.Zone.ChildStatus);
        Assert.StartsWith("z000004D2", result.Zone.ZoneIdCandidate);
        Assert.Equal(Zone, result.Zone.RecordAddress);
    }

    [Theory]
    [InlineData("player-key")]
    [InlineData("position-slot")]
    [InlineData("health-slot")]
    public async Task OwnerChangeBetweenPositionAndZoneRejectsCombinedSnapshot(string field)
    {
        var session = Fixture();
        session.OnRead = (address, _) =>
        {
            if (address != Owner + 0x150) return;
            session.OnRead = null;
            if (field == "player-key") session.Q(System + 0x360, 999);
            else session.Q(Components + (field == "health-slot" ? 8UL : 16UL), 0x21000000);
        };
        await Assert.ThrowsAsync<InvalidDataException>(() => Read(session));
    }

    [Fact]
    public async Task ZoneMutationOrThreadEpochChangeRejectsCombinedSnapshot()
    {
        var session = Fixture();
        session.ChangeAfterFirst(Owner + 0x150, BitConverter.GetBytes(4321U));
        await Assert.ThrowsAsync<InvalidDataException>(() => Read(session));
        session = Fixture(); AddResidentZone(session); var calls = 0;
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            Read(session, () => [++calls == 1 ? Epoch : Epoch with { Created = 789 }]));
    }

    [Fact]
    public async Task InvalidBuildAndCancelledRequestReadNothing()
    {
        var session = Fixture();
        session.Identity = session.Identity with { ExecutableSha256 = new string('0', 64) };
        await Assert.ThrowsAsync<InvalidDataException>(() => Read(session));
        Assert.Equal(0, session.Reads);
        session = Fixture();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            CurrentBuildLocationContextCandidateReader.ReadAsync(session, () => [], new CancellationToken(true)));
        Assert.Equal(0, session.Reads);
    }

    [Fact]
    public async Task FailedRevalidationOrOwnerChangeDuringRevalidationRejectsSnapshot()
    {
        var session = Fixture(); session.Invalidation = "process exited";
        await Assert.ThrowsAsync<InvalidDataException>(() => Read(session));
        session = Fixture();
        session.OnRevalidate = () => session.Q(System + 0x360, 999);
        await Assert.ThrowsAsync<InvalidDataException>(() => Read(session));
        session = Fixture();
        session.OnRevalidate = () => session.Identity = session.Identity with { ProcessStartUtcTicks = 999 };
        await Assert.ThrowsAsync<InvalidDataException>(() => Read(session));
    }

    private static Task<CurrentBuildLocationContextObservation> Read(Fake session,
        Func<IReadOnlyList<NativeThreadEpoch>>? threads = null) =>
        CurrentBuildLocationContextCandidateReader.ReadAsync(session, threads ?? (() => []), CancellationToken.None);

    private static Fake Fixture()
    {
        var s = new Fake();
        s.Q(M + 0x33624A8, Manager); s.Q(Manager + 0x50, Table); s.Q(M + 0x33623E0, System);
        s.Q(System + 0x360, 123); s.Q(System + 0x3F8, Entity); s.Q(System + 0x400, Health);
        s.Q(Table, Buckets); s.Q(Table + 8, 24); s.Q(Table + 16, 1);
        s.Q(Buckets, 0); s.Q(Buckets + 8, 123); s.Q(Buckets + 16, Entity);
        s.Put(Entity, new byte[128]); s.Q(Entity + 0x78, Components);
        s.Put(Entity + 0x18 + 34, [2]); s.Put(Entity + 0x18 + 6, [1]);
        s.Put(Entity + 0x18 + 1, [255]); s.Put(Entity + 0x18 + 2, [4]);
        s.D(M + 0x2F588A0, 34); s.D(M + 0x2F57850, 6);
        s.D(M + 0x2F58270, 1); s.D(M + 0x2F582E0, 2);
        s.Q(Components + 8, Health); s.Q(Components + 16, Position);
        s.Put(Position, new byte[0x110]); s.Q(Position + 0x10, Entity); s.Put(Position + 0x48, BitConverter.GetBytes(1.5f));
        s.Put(Position + 0x4C, BitConverter.GetBytes(-2f)); s.Put(Position + 0x50, BitConverter.GetBytes(3f));
        s.Q(Health + 0x10, Entity); s.Q(Health + 0x40, Owner);
        s.Q(Owner, M + 0x2927448); s.Q(M + 0x2927488, M + 0x19D21E0);
        s.Q(M + 0x34731B0, M + 0x2929BD0); s.Q(M + 0x2929BD8, M + 0x19F4D60);
        s.Q(Owner + 0x20, 0); s.D(Owner + 0x100, 41); s.Put(Owner + 0x19D, [0]);
        s.D(Owner + 0x168, 3); s.D(Owner + 0x150, 1234); s.Q(M + 0x336EBF8, 0);
        return s;
    }

    private static void AddResidentZone(Fake s)
    {
        s.Q(M + 0x336EBF8, Provider); s.Put(Provider + 0x40, BitConverter.GetBytes((ushort)55));
        s.Q(M + 0x3372C18, Wrapper); s.Q(Wrapper, Registry); s.D(Registry + 0x274, 0);
        s.Q(Teb + 0x30, Teb); s.Q(Teb + 0x38, 0); s.Q(Teb + 0x40, 123); s.Q(Teb + 0x48, 77);
        s.Q(Teb + 0x1480, 0); s.Q(Registry + 0x220, Cache);
        s.Q(Registry + 0x228, 24); s.Q(Registry + 0x230, 1); s.Q(Registry + 0x238, 1);
        s.Put(Cache, new byte[24]); s.Put(Cache + 8, BitConverter.GetBytes((ushort)55));
        s.D(Cache + 12, 1234); s.Q(Cache + 16, Holder); s.Q(Holder + 0x18, Zone);
        s.Q(Zone, M + 0x2B254A8); s.Q(M + 0x2B254E8, M + 0x1E772C0);
        s.Q(M + 0x35109E0, M + 0x2B2FEE0); s.Q(M + 0x2B2FEE8, M + 0x1E9FD50);
        s.Q(Zone + 0x1F0, 0);
    }

    private sealed class Fake : IReadOnlyNativeMemorySession
    {
        private readonly Dictionary<ulong, byte> data = [];
        private readonly Dictionary<ulong, byte[]> changes = [];
        private readonly HashSet<ulong> seen = [];
        public NativeProcessIdentity Identity { get; set; } =
            new(123, 456, "rift_x64.exe", CurrentBuildPlayerLookup.GameSha256, M, 0x4000000);
        public Action<ulong, int>? OnRead { get; set; }
        public Action? OnRevalidate { get; set; }
        public string? Invalidation { get; set; }
        public int Reads { get; private set; }
        public int Revalidations { get; private set; }
        public void Put(ulong address, byte[] bytes)
        {
            for (var i = 0; i < bytes.Length; i++) data[address + (ulong)i] = bytes[i];
        }
        public void Q(ulong address, ulong value) => Put(address, BitConverter.GetBytes(value));
        public void D(ulong address, uint value) => Put(address, BitConverter.GetBytes(value));
        public void ChangeAfterFirst(ulong address, byte[] bytes) => changes[address] = bytes;
        public NativeReadResult Read(ulong address, int length)
        {
            Reads++; OnRead?.Invoke(address, length);
            if (!seen.Add(address) && changes.TryGetValue(address, out var changed)) Put(address, changed);
            var bytes = new byte[length];
            for (var i = 0; i < length; i++)
                if (!data.TryGetValue(address + (ulong)i, out bytes[i])) return new("unavailable", [], null, "missing");
            return new("success", bytes, null, null);
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken cancellationToken)
        {
            Revalidations++; cancellationToken.ThrowIfCancellationRequested(); OnRevalidate?.Invoke();
            return ValueTask.FromResult(Invalidation);
        }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
