using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildFastManaPinnedSamplerTests
{
    private const ulong Module = 0x140000000, Manager = 0x22000000, PlayerSystem = 0x22010000,
        Table = 0x22020000, Buckets = 0x22030000, Entity = 0x22040000,
        ComponentTable = 0x22050000, Component = 0x22060000, HealthOwner = 0x22070000,
        HealthContainer = 0x22080000, HealthRecord = 0x22090000, Wrapper = 0x220A0000,
        Reference = Wrapper + 0x10, Record = 0x220B0000, KindOwner = 0x220C0000,
        ClockOwner = 0x220D0000, Anchor = 0x220E0000, PlayerKey = 123;

    [Fact]
    public async Task SamplesTwoStatesInsideFullPreAndPostVerification()
    {
        var session = Fixture();
        var times = Times();
        var result = await CurrentBuildFastManaPinnedSampler.SampleAsync(
            session, Request(), utcNow: () => times.Dequeue());
        Assert.Equal("native-mana-fast-sample/1", result.EvidenceKind);
        Assert.Equal("unchanged", result.TransitionStatus);
        Assert.Equal(3980, result.Mana.Current);
        Assert.Equal("0x072A", System.Text.Json.JsonDocument.Parse(
            System.Text.Json.JsonSerializer.Serialize(result.Mana.Inputs)).RootElement
            .GetProperty("verifiedTypeCode").GetString());
        Assert.True(result.VerificationStartedAtUtc <= result.StateA.StartedAtUtc);
        Assert.True(result.StateB.CompletedAtUtc <= result.VerificationCompletedAtUtc);
        Assert.True(session.Revalidated);
    }

    [Fact]
    public async Task AcceptsOneCoherentCacheTransitionAndCalculatesFromStateB()
    {
        var session = Fixture();
        session.Sequence(Wrapper, 48, WrapperBytes(8, 20, 100, 100),
            WrapperBytes(9, 21, 101, 101));
        session.Sequence(Record, 64, RecordBytes(3980, 8, 20),
            RecordBytes(3979, 9, 21));
        session.Sequence(ClockOwner + 0x18, 4, F(100), F(101));
        var result = await CurrentBuildFastManaPinnedSampler.SampleAsync(
            session, Request(), utcNow: Clock());
        Assert.Equal("coherent-cache-transition", result.TransitionStatus);
        Assert.Equal(3979, result.Mana.Current);
        Assert.Equal(9, result.StateB.RecordRevision);
        Assert.Equal(21, result.StateB.SecondaryRevision);
    }

    [Fact]
    public async Task GameClockOnlyAdvanceDoesNotClaimCacheTransition()
    {
        var session = Fixture();
        session.Sequence(ClockOwner + 0x18, 4, F(100), F(101));
        var result = await CurrentBuildFastManaPinnedSampler.SampleAsync(
            session, Request(), utcNow: Clock());
        Assert.Equal("unchanged", result.TransitionStatus);
        Assert.Equal(8, result.StateB.RecordRevision);
        Assert.Equal(3980, result.Mana.Current);
    }

    [Theory]
    [InlineData("mixed-primary")]
    [InlineData("mixed-secondary")]
    [InlineData("backward-clock")]
    [InlineData("immutable-record")]
    public async Task RejectsTornOrBackwardMutableState(string defect)
    {
        var session = Fixture();
        var secondWrapper = WrapperBytes(defect == "mixed-primary" ? 9 : 8,
            defect == "mixed-secondary" ? 21 : 20,
            defect == "backward-clock" ? 99 : 100, 100);
        var secondRecord = RecordBytes(3980, 8, 20);
        if (defect == "immutable-record") secondRecord[0x38] = 1;
        session.Sequence(Wrapper, 48, WrapperBytes(), secondWrapper);
        session.Sequence(Record, 64, RecordBytes(), secondRecord);
        await Assert.ThrowsAsync<InvalidDataException>(async () =>
            await CurrentBuildFastManaPinnedSampler.SampleAsync(
                session, Request(), utcNow: Clock()));
    }

    [Theory]
    [InlineData("rate")]
    [InlineData("base")]
    [InlineData("maximum")]
    public async Task RejectsArithmeticPayloadChangeWithoutForwardRevisionEpoch(string field)
    {
        var session = Fixture();
        var changed = RecordBytes();
        if (field == "rate") D(9808).CopyTo(changed, 0x18);
        if (field == "base") D(3979).CopyTo(changed, 0x1C);
        if (field == "maximum") D(3981).CopyTo(changed, 0x24);
        session.Sequence(Record, 64, RecordBytes(), changed);
        var failure = await Assert.ThrowsAsync<InvalidDataException>(async () =>
            await CurrentBuildFastManaPinnedSampler.SampleAsync(
                session, Request(), utcNow: Clock()));
        Assert.Contains("without a forward primary revision", failure.Message);
    }

    [Theory]
    [InlineData("primary-clock")]
    [InlineData("secondary-clock")]
    public async Task CacheClockChangeRequiresItsMatchingRevisionToAdvance(string field)
    {
        var session = Fixture();
        var changed = field == "primary-clock"
            ? WrapperBytes(clockB: 101)
            : WrapperBytes(clockA: 101);
        session.Sequence(Wrapper, 48, WrapperBytes(), changed);
        var failure = await Assert.ThrowsAsync<InvalidDataException>(async () =>
            await CurrentBuildFastManaPinnedSampler.SampleAsync(
                session, Request(), utcNow: Clock()));
        Assert.Contains(field == "primary-clock" ? "forward primary revision" :
            "forward secondary revision", failure.Message);
    }

    [Fact]
    public async Task PrimaryAndSecondaryEpochsMayAdvanceIndependently()
    {
        var primary = Fixture();
        primary.Sequence(Wrapper, 48, WrapperBytes(),
            WrapperBytes(primary: 9, secondary: 20, clockB: 101));
        primary.Sequence(Record, 64, RecordBytes(),
            RecordBytes(baseline: 3979, primary: 9, secondary: 20));
        primary.Sequence(ClockOwner + 0x18, 4, F(100), F(101));
        Assert.Equal("coherent-cache-transition",
            (await CurrentBuildFastManaPinnedSampler.SampleAsync(
                primary, Request(), utcNow: Clock())).TransitionStatus);

        var secondary = Fixture();
        secondary.Sequence(Wrapper, 48, WrapperBytes(),
            WrapperBytes(primary: 8, secondary: 21, clockA: 101));
        secondary.Sequence(Record, 64, RecordBytes(),
            RecordBytes(primary: 8, secondary: 21));
        Assert.Equal("coherent-cache-transition",
            (await CurrentBuildFastManaPinnedSampler.SampleAsync(
                secondary, Request(), utcNow: Clock())).TransitionStatus);
    }

    [Fact]
    public async Task RejectsFullChainOrRouteDriftAfterFinalValue()
    {
        var session = Fixture();
        session.Sequence(Module + 0x33624A8, 8, Q(Manager), Q(Manager + 8));
        await Assert.ThrowsAsync<InvalidDataException>(async () =>
            await CurrentBuildFastManaPinnedSampler.SampleAsync(session, Request(), utcNow: Clock()));

        session = Fixture();
        session.Sequence(Component + 0x38, 8, Q(Wrapper), Q(Wrapper + 8));
        await Assert.ThrowsAsync<InvalidDataException>(async () =>
            await CurrentBuildFastManaPinnedSampler.SampleAsync(session, Request(), utcNow: Clock()));
    }

    [Fact]
    public async Task RejectsCachedAnchorDriftAndProcessPostflightFailure()
    {
        var session = Fixture();
        session.Sequence(Anchor, 8, Q(0x12345678), Q(0x12345679));
        await Assert.ThrowsAsync<InvalidDataException>(async () =>
            await CurrentBuildFastManaPinnedSampler.SampleAsync(session, Request(), utcNow: Clock()));

        session = Fixture();
        session.Invalidation = "process-epoch-changed";
        await Assert.ThrowsAsync<InvalidDataException>(async () =>
            await CurrentBuildFastManaPinnedSampler.SampleAsync(session, Request(), utcNow: Clock()));
    }

    [Fact]
    public async Task InvalidBuildProvenanceOrOverlappingAnchorsFailsBeforeReads()
    {
        var session = Fixture();
        var wrong = Request() with { Identity = session.Identity with { ExecutableSha256 = "0".PadLeft(64, '0') } };
        await Assert.ThrowsAsync<InvalidDataException>(async () =>
            await CurrentBuildFastManaPinnedSampler.SampleAsync(session, wrong, utcNow: Clock()));
        Assert.Equal(0, session.Reads);

        session = Fixture();
        var badProvenance = Request() with { Provenance = Provenance() with { SamplerSourceSha256 = "bad" } };
        await Assert.ThrowsAsync<InvalidDataException>(async () =>
            await CurrentBuildFastManaPinnedSampler.SampleAsync(session, badProvenance, utcNow: Clock()));
        Assert.Equal(0, session.Reads);

        session = Fixture();
        var overlap = Request() with
        {
            CachedImmutableAnchors =
            [new(Anchor, Q(1)), new(Anchor + 4, Q(2))]
        };
        await Assert.ThrowsAsync<InvalidDataException>(async () =>
            await CurrentBuildFastManaPinnedSampler.SampleAsync(session, overlap, utcNow: Clock()));
        Assert.Equal(0, session.Reads);
    }

    [Fact]
    public async Task AcceptsBoundedUnalignedSelectorAnchor()
    {
        var session = Fixture();
        session.Put(Anchor + 1, [0x2A]);
        var request = Request() with
        {
            CachedImmutableAnchors = [new(Anchor + 1, [0x2A])]
        };
        var result = await CurrentBuildFastManaPinnedSampler.SampleAsync(
            session, request, utcNow: Clock());
        Assert.Equal(3980, result.Mana.Current);
    }

    private static CurrentBuildFastManaPinnedRequest Request() => new(
        new(7164, 639294897866244204, @"C:\RIFT\rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256, Module, 0x4000000),
        PlayerKey, Component, HealthRecord, Wrapper, Reference, Record, ClockOwner,
        [new(Anchor, Q(0x12345678))], Provenance());

    private static CurrentBuildFastManaProvenance Provenance() => new(
        H('A'), H('B'), H('C'), H('D'), H('E'), H('F'), H('1'), H('2'), H('3'));
    private static string H(char value) => new(value, 64);
    private static Func<DateTimeOffset> Clock()
    {
        var times = Times();
        return () => times.Dequeue();
    }
    private static Queue<DateTimeOffset> Times()
    {
        var start = new DateTimeOffset(2026, 11, 6, 12, 0, 0, TimeSpan.Zero);
        return new(Enumerable.Range(0, 6).Select(index => start.AddMilliseconds(index)));
    }

    private static FakeSession Fixture()
    {
        var session = new FakeSession();
        session.Put(Module + 0x33624A8, Q(Manager));
        session.Put(Module + 0x33623E0, Q(PlayerSystem));
        session.Put(Manager + 0x50, Q(Table));
        session.Put(PlayerSystem + 0x360, Q(PlayerKey));
        var header = new byte[24]; Q(Buckets).CopyTo(header, 0); Q(24).CopyTo(header, 8); Q(1).CopyTo(header, 16);
        session.Put(Table, header);
        var node = new byte[24]; Q(PlayerKey).CopyTo(node, 8); Q(Entity).CopyTo(node, 16);
        session.Put(Buckets, node);
        var entity = new byte[128]; Q(ComponentTable).CopyTo(entity, 0x78); entity[0x18] = 0;
        session.Put(Entity, entity); session.Put(Module + 0x2F57850, D(0)); session.Put(ComponentTable, Q(Component));
        session.Put(Component + 0x28, Q(HealthOwner)); session.Put(HealthOwner + 0x40, Q(HealthContainer));
        session.Put(HealthContainer + 0x640, Q(HealthRecord));
        session.Put(Component + 0x38, Q(Wrapper)); session.Put(Component + 0x40, Q(KindOwner));
        session.Put(KindOwner + 0x168, D(3)); session.Put(Reference, Q(Record));
        session.Put(Module + 0x33DC2B0, Q(ClockOwner));
        session.Put(Record, 8, Q(Module + 0x2A6ACD8));
        session.Put(Module + 0x2A6AD18, Q(Module + 0x1CCB460));
        session.Put(Module + 0x34D8990, Q(Module + 0x2A7C418));
        session.Put(Module + 0x2A7C420, Q(Module + 0x1CF9F10));
        session.Put(Wrapper, 48, WrapperBytes()); session.Put(Record, 64, RecordBytes());
        session.Put(ClockOwner + 0x18, 4, F(100)); session.Put(Anchor, Q(0x12345678));
        return session;
    }

    private static byte[] WrapperBytes(int primary = 8, int secondary = 20,
        float clockA = 100, float clockB = 100)
    {
        var value = new byte[48]; Q(Reference).CopyTo(value, 0x10); D(secondary).CopyTo(value, 0x18);
        D(primary).CopyTo(value, 0x1C); F(clockA).CopyTo(value, 0x20); F(clockB).CopyTo(value, 0x24);
        return value;
    }
    private static byte[] RecordBytes(int baseline = 3980, int primary = 8, int secondary = 20)
    {
        var value = new byte[64]; Q(Module + 0x2A6ACD8).CopyTo(value, 0);
        D(9807).CopyTo(value, 0x18); D(baseline).CopyTo(value, 0x1C); D(primary).CopyTo(value, 0x20);
        D(3980).CopyTo(value, 0x24); D(secondary).CopyTo(value, 0x28); return value;
    }
    private static byte[] Q(ulong value) { var bytes = new byte[8]; BinaryPrimitives.WriteUInt64LittleEndian(bytes, value); return bytes; }
    private static byte[] D(int value) { var bytes = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(bytes, value); return bytes; }
    private static byte[] F(float value) => D(BitConverter.SingleToInt32Bits(value));

    private sealed class FakeSession : IReadOnlyNativeMemorySession
    {
        private readonly Dictionary<(ulong, int), byte[]> data = [];
        private readonly Dictionary<(ulong, int), Queue<byte[]>> sequences = [];
        public int Reads { get; private set; }
        public bool Revalidated { get; private set; }
        public string? Invalidation { get; set; }
        public NativeProcessIdentity Identity { get; set; } = Request().Identity;
        public void Put(ulong address, byte[] value) => Put(address, value.Length, value);
        public void Put(ulong address, int length, byte[] value) => data[(address, length)] = value;
        public void Sequence(ulong address, int length, params byte[][] values) =>
            sequences[(address, length)] = new(values);
        public NativeReadResult Read(ulong address, int length)
        {
            Reads++;
            if (sequences.TryGetValue((address, length), out var queue) && queue.Count > 0)
            {
                var value = queue.Count > 1 ? queue.Dequeue() : queue.Peek();
                return new("success", value.ToArray(), null, null);
            }
            return data.TryGetValue((address, length), out var bytes)
                ? new("success", bytes.ToArray(), null, null) : new("unavailable", [], null, null);
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested(); Revalidated = true;
            return ValueTask.FromResult(Invalidation);
        }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
