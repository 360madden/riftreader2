using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildManaCandidateFieldTests
{
    private const ulong Module = 0x140000000, Component = 0x21000000,
        Wrapper = 0x21010000, Reference = 0x21020000, Record = 0x21030000,
        KindOwner = 0x21040000, ClockOwner = 0x21050000, HealthRecord = 0x21060000;

    [Fact]
    public void ReplaysRetainedTypeCheckedLabOneCandidate()
    {
        var session = Fixture();
        var result = Read(session);
        Assert.Equal("calculated-candidate", result.Status);
        Assert.Equal(3980, result.Current);
        Assert.Equal(3980, result.Maximum);
        Assert.Contains("0x072A", System.Text.Json.JsonSerializer.Serialize(result.Inputs));
    }

    [Theory]
    [InlineData("record-vtable")]
    [InlineData("record-getter")]
    [InlineData("descriptor")]
    [InlineData("type-getter")]
    public void RejectsAnyFingerprintMismatch(string defect)
    {
        var session = Fixture();
        if (defect == "record-vtable") session.Put(Record, ManaRecord(vtable: Module + 8));
        if (defect == "record-getter") session.Put(Module + 0x2A6AD18, Q(Module + 8));
        if (defect == "descriptor") session.Put(Module + 0x34D8990, Q(Module + 8));
        if (defect == "type-getter") session.Put(Module + 0x2A7C420, Q(Module + 8));
        Assert.Throws<InvalidDataException>(() => Read(session));
    }

    [Theory]
    [InlineData("wrapper")]
    [InlineData("record")]
    [InlineData("type")]
    public void RejectsChangedBracketedInput(string defect)
    {
        var session = Fixture();
        if (defect == "wrapper") session.ChangeAfterFirst(Wrapper, ManaWrapper(revision: 9));
        if (defect == "record") session.ChangeAfterFirst(Record, ManaRecord(baseline: 3979));
        if (defect == "type") session.ChangeAfterFirst(Module + 0x2A7C420, Q(Module + 8));
        Assert.Throws<InvalidDataException>(() => Read(session));
    }

    [Fact]
    public void RequiresExactBuildBeforeReadingMemory()
    {
        var session = Fixture();
        session.Identity = session.Identity with { ExecutableSha256 = new string('0', 64) };
        Assert.Throws<InvalidDataException>(() => Read(session));
        Assert.Equal(0, session.Reads);
    }

    [Fact]
    public void RejectsAnotherResourceKindBeforeFollowingItsRecord()
    {
        var session = Fixture();
        session.Put(KindOwner + 0x168, D(4));
        Assert.Throws<InvalidDataException>(() => Read(session));
    }

    [Fact]
    public void OwnerAndProcessEpochAreRechecked()
    {
        var session = Fixture();
        Assert.Throws<InvalidDataException>(() => CurrentBuildManaCandidateField.Read(
            session, session.Identity, Component, HealthRecord,
            () => throw new InvalidDataException("owner changed")));
        session = Fixture();
        var expected = session.Identity;
        Assert.Throws<InvalidDataException>(() => CurrentBuildManaCandidateField.Read(
            session, expected, Component, HealthRecord,
            () => session.Identity = session.Identity with { ProcessStartUtcTicks = 999 }));
    }

    [Fact]
    public void RejectsHealthRecordAlias()
    {
        var session = Fixture();
        Assert.Throws<InvalidDataException>(() => CurrentBuildManaCandidateField.Read(
            session, session.Identity, Component, Record, () => { }));
    }

    [Fact]
    public void ClockComesFromPinnedSessionAndItsOwnerIsBracketed()
    {
        var session = Fixture();
        session.Put(ClockOwner + 0x18, D(BitConverter.SingleToInt32Bits(float.NaN)));
        Assert.Equal("invalid-float-input", Read(session).UnavailableReason);

        session = Fixture();
        session.ChangeAfterFirst(Module + 0x33DC2B0, Q(ClockOwner + 8));
        Assert.Throws<InvalidDataException>(() => Read(session));
    }

    [Fact]
    public void RevisionAndClockFailuresRemainExplicitlyUnavailable()
    {
        var record = ManaRecord();
        Assert.Equal("revision-mismatch-needs-native-cache-write",
            CurrentBuildManaCandidateField.Calculate(record, ManaWrapper(revision: 9), 74292.7421875f).UnavailableReason);
        Assert.Equal("invalid-float-input",
            CurrentBuildManaCandidateField.Calculate(record, ManaWrapper(), float.NaN).UnavailableReason);
        Assert.Equal("clock-delta-outside-normal-domain",
            CurrentBuildManaCandidateField.Calculate(record, ManaWrapper(), 70000).UnavailableReason);
    }

    [Fact]
    public void OrdinaryRateArithmeticUsesSeparateFloat32StepsAndClamps()
    {
        var record = ManaRecord(baseline: 100, maximum: 200, rate: -2000);
        var wrapper = ManaWrapper(clock: 100);
        Assert.Equal(80, CurrentBuildManaCandidateField.Calculate(record, wrapper, 101).Current);
        record = ManaRecord(baseline: int.MaxValue, maximum: int.MaxValue, rate: int.MaxValue);
        Assert.Equal("signed32-subtraction-overflow",
            CurrentBuildManaCandidateField.Calculate(record, wrapper, 101).UnavailableReason);
    }

    private static CurrentBuildVitalCandidate Read(FakeSession session) =>
        CurrentBuildManaCandidateField.Read(session, session.Identity, Component, HealthRecord, () => { });

    private static FakeSession Fixture()
    {
        var session = new FakeSession();
        session.Put(Module + 0x33DC2B0, Q(ClockOwner));
        session.Put(ClockOwner + 0x18, D(BitConverter.SingleToInt32Bits(74292.7421875f)));
        session.Put(Component + 0x40, Q(KindOwner));
        session.Put(KindOwner + 0x168, D(3));
        session.Put(Component + 0x38, Q(Wrapper));
        session.Put(Wrapper, ManaWrapper());
        session.Put(Reference, Q(Record));
        session.Put(Record, ManaRecord());
        session.Put(Module + 0x2A6AD18, Q(Module + 0x1CCB460));
        session.Put(Module + 0x34D8990, Q(Module + 0x2A7C418));
        session.Put(Module + 0x2A7C420, Q(Module + 0x1CF9F10));
        return session;
    }

    private static byte[] ManaRecord(ulong? vtable = null, int baseline = 3980,
        int maximum = 3980, int rate = 9807, int revision = 8)
    {
        var bytes = new byte[64];
        Q(vtable ?? Module + 0x2A6ACD8).CopyTo(bytes, 0);
        D(rate).CopyTo(bytes, 0x18); D(baseline).CopyTo(bytes, 0x1C);
        D(revision).CopyTo(bytes, 0x20); D(maximum).CopyTo(bytes, 0x24);
        return bytes;
    }

    private static byte[] ManaWrapper(int revision = 8, float clock = 74064.5703125f)
    {
        var bytes = new byte[48]; Q(Reference).CopyTo(bytes, 0x10);
        D(revision).CopyTo(bytes, 0x1C); D(BitConverter.SingleToInt32Bits(clock)).CopyTo(bytes, 0x24);
        return bytes;
    }

    private static byte[] Q(ulong value) { var bytes = new byte[8]; BinaryPrimitives.WriteUInt64LittleEndian(bytes, value); return bytes; }
    private static byte[] D(int value) { var bytes = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(bytes, value); return bytes; }

    private sealed class FakeSession : IReadOnlyNativeMemorySession
    {
        private readonly Dictionary<ulong, byte[]> data = [];
        private readonly Dictionary<ulong, byte[]> changed = [];
        private readonly HashSet<ulong> seen = [];
        public int Reads { get; private set; }
        public NativeProcessIdentity Identity { get; set; } = new(7164, 639294897866244204,
            @"C:\RIFT\rift_x64.exe", CurrentBuildPlayerLookup.GameSha256, Module, 0x4000000);
        public void Put(ulong address, byte[] bytes) => data[address] = bytes;
        public void ChangeAfterFirst(ulong address, byte[] bytes) => changed[address] = bytes;
        public NativeReadResult Read(ulong address, int length)
        {
            Reads++;
            var bytes = !seen.Add(address) && changed.TryGetValue(address, out var replacement)
                ? replacement : data.GetValueOrDefault(address);
            return bytes is not null && bytes.Length == length
                ? new("success", bytes.ToArray(), null, null)
                : new("unavailable", [], null, null);
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken _) => ValueTask.FromResult<string?>(null);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
