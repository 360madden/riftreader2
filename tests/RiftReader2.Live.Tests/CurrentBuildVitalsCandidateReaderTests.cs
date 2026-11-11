using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildVitalsCandidateReaderTests
{
    private const ulong Module = 0x140000000, Component = 0x20000000, Owner = 0x20010000,
        Container = 0x20020000, Hp = 0x20030000, KindOwner = 0x20040000,
        Wrapper = 0x20050000, Reference = 0x20060000, Energy = 0x20070000, Clock = 0x20080000;

    [Fact]
    public void ReplaysRetainedLabTwoOrdinaryInputs()
    {
        var session = Fixture();
        var result = Read(session);
        Assert.Equal(10635, result.Health.Current);
        Assert.Equal(10635, result.Health.Maximum);
        Assert.Equal(100, result.Energy.Current);
        Assert.Equal(100, result.Energy.Maximum);
        Assert.Equal(4, result.ResourceKindCandidate);
        Assert.Contains("0x072B", System.Text.Json.JsonSerializer.Serialize(result.Energy.Inputs));
        Assert.Equal("not-mana-kind-three", result.Mana.UnavailableReason);
        Assert.Equal("native-process-memory", result.Source);
        Assert.Equal(123UL, result.UnitKey);
    }

    [Fact]
    public void ProductionLookupBracketsOriginalIntermediateAnchors()
    {
        const ulong manager = 0x20100000, system = 0x20110000, table = 0x20120000,
            buckets = 0x20130000, entity = 0x20140000, components = 0x20150000;
        var s = Fixture();
        s.Put(Module + 0x33624A8, Q(manager)); s.Put(Module + 0x33623E0, Q(system));
        s.Put(manager + 0x50, Q(table)); s.Put(system + 0x360, Q(123));
        var header = new byte[24]; Q(buckets).CopyTo(header, 0); Q(24).CopyTo(header, 8); Q(1).CopyTo(header, 16);
        s.Put(table, header);
        var node = new byte[24]; Q(123).CopyTo(node, 8); Q(entity).CopyTo(node, 16);
        s.Put(buckets, node);
        var entityRaw = new byte[128]; entityRaw[0x19] = 0; Q(components).CopyTo(entityRaw, 0x78);
        s.Put(entity, entityRaw); s.Put(components, Q(Component)); s.Put(Module + 0x2F57850, D(1));
        Assert.Equal(10635, CurrentBuildVitalsCandidateReader.Read(s).Health.Current);
        // A replacement manager can still resolve to exactly the same leaf/key.
        // The snapshot must reject the changed original intermediate link.
        s.ResetSeen();
        s.ChangeAfterFirst(manager + 0x50, Q(table + 0x1000));
        var failure = Assert.Throws<InvalidDataException>(() => CurrentBuildVitalsCandidateReader.Read(s));
        Assert.Contains("ownership", failure.Message);
    }

    [Fact]
    public void IntermediateOwnerChangeFailsEvenWithSameLeafAndKey()
    {
        var s = Fixture();
        const ulong intermediateAnchor = 0x20090000;
        s.Put(intermediateAnchor, Q(0x200A0000));
        s.ChangeAfterFirst(intermediateAnchor, Q(0x200B0000));
        var resolutions = 0;
        Assert.Throws<InvalidDataException>(() => CurrentBuildVitalsCandidateReader.Read(s, source =>
        {
            resolutions++;
            var original = source.Read(intermediateAnchor, 8).Bytes;
            // The leaf component and unit key stay identical, while an original
            // lookup-path anchor changes. Re-resolution alone would miss it.
            return new(123, Component, () =>
            {
                if (!source.Read(intermediateAnchor, 8).Bytes.AsSpan().SequenceEqual(original))
                    throw new InvalidDataException("Intermediate owner anchor changed.");
            });
        }));
        Assert.Equal(1, resolutions);
    }

    [Theory]
    [InlineData("type")]
    [InlineData("record")]
    [InlineData("wrapper")]
    [InlineData("clock-owner")]
    public void RejectsCorruptedTypeOrChangedInputs(string defect)
    {
        var s = Fixture();
        if (defect == "type") s.Put(Module + 0x2D1D428, Q(Module + 1));
        if (defect == "record") s.ChangeAfterFirst(Energy, s.Get(Energy).Select((v, i) => i == 0x20 ? (byte)99 : v).ToArray());
        if (defect == "wrapper") s.ChangeAfterFirst(Component + 0x30, new byte[8]);
        if (defect == "clock-owner") s.ChangeAfterFirst(Module + 0x33DC2B0, Q(Clock + 8));
        Assert.Throws<InvalidDataException>(() => Read(s));
    }

    [Fact]
    public void RevisionMismatchIsExplicitUnavailable()
    {
        var s = Fixture();
        s.Put(Wrapper + 0x18, Cache(58, 61610.41796875f));
        var result = Read(s);
        Assert.Equal("unavailable", result.Energy.Status);
        Assert.Equal("revision-mismatch-needs-native-cache-write", result.Energy.UnavailableReason);
        Assert.Null(result.Energy.Current);
    }

    [Fact]
    public void TypeCheckedManaUsesOnlyKindThreeLayout()
    {
        var s = Fixture();
        ConfigureMana(s);
        var result = Read(s);
        Assert.Equal(3, result.ResourceKindCandidate);
        Assert.Equal("calculated-candidate", result.Mana.Status);
        Assert.Equal(3980, result.Mana.Current);
        Assert.Equal(3980, result.Mana.Maximum);
        Assert.Equal("not-energy-kind-four", result.Energy.UnavailableReason);
    }

    [Fact]
    public void OtherResourceKindsRemainVisibleWithoutFalseManaOrEnergy()
    {
        var s = Fixture();
        s.Put(KindOwner + 0x168, D(2));
        var result = Read(s);
        Assert.Equal(2, result.ResourceKindCandidate);
        Assert.Equal("unavailable", result.Mana.Status);
        Assert.Equal("unavailable", result.Energy.Status);
    }

    [Fact]
    public void WrongBuildRejectsBeforeMemoryReads()
    {
        var s = Fixture();
        s.Identity = s.Identity with { ExecutableSha256 = new string('0', 64) };
        Assert.Throws<InvalidDataException>(() => Read(s));
        Assert.Equal(0, s.Reads);
    }

    [Fact]
    public void EnergyDepletionAndInvalidClocks()
    {
        var raw = EnergyRaw();
        BinaryPrimitives.WriteInt32LittleEndian(raw.AsSpan(0x28), -2000);
        Assert.Equal(80, CurrentBuildVitalsCandidateReader.CalculateEnergy(raw, Cache(59, 100), 101).Current);
        Assert.Equal("unavailable", CurrentBuildVitalsCandidateReader.CalculateEnergy(raw, Cache(59, 100), 99).Status);
        Assert.Equal("unavailable", CurrentBuildVitalsCandidateReader.CalculateEnergy(raw, Cache(59, 100), float.NaN).Status);
    }

    [Fact]
    public void HealthCapPrecedesAliveFloorAndDeadBaseStaysDead()
    {
        var raw = HealthRaw();
        BinaryPrimitives.WriteInt32LittleEndian(raw.AsSpan(0x6C), 0);
        Assert.Equal(0, CurrentBuildVitalsCandidateReader.CalculateHealth(raw, Cache(74, 10), 10).Current);
        BinaryPrimitives.WriteInt64LittleEndian(raw.AsSpan(0x48), 0);
        Assert.Equal(0, CurrentBuildVitalsCandidateReader.CalculateHealth(raw, Cache(74, 10), 100).Current);
    }

    [Fact]
    public void RejectsUnavailableRecordAndChangedProcessEpoch()
    {
        var s = Fixture();
        s.Put(Hp, new byte[4]);
        Assert.Throws<InvalidDataException>(() => Read(s));
        s = Fixture();
        Assert.Throws<InvalidDataException>(() => CurrentBuildVitalsCandidateReader.Read(s, _ =>
        {
            return new(123, Component, () => s.Identity = s.Identity with { ProcessStartUtcTicks = 457 });
        }));
    }

    [Fact]
    public void NonfiniteUnavailableResultCanBeSerialized()
    {
        var result = CurrentBuildVitalsCandidateReader.CalculateEnergy(EnergyRaw(), Cache(59, 100), float.NaN);
        Assert.NotNull(result.Inputs);
        Assert.Contains("unavailable", System.Text.Json.JsonSerializer.Serialize(result));
        Assert.Contains("baseRaw", System.Text.Json.JsonSerializer.Serialize(result.Inputs));
        result = CurrentBuildVitalsCandidateReader.CalculateHealth(HealthRaw(), Cache(74, float.NaN), 100);
        Assert.NotNull(result.Inputs);
        Assert.Contains("unavailable", System.Text.Json.JsonSerializer.Serialize(result));
        Assert.Contains("baseRaw", System.Text.Json.JsonSerializer.Serialize(result.Inputs));
    }

    [Fact]
    public void EnergyRejectsSignedSubtractionOverflow()
    {
        var raw = EnergyRaw();
        D(int.MaxValue).CopyTo(raw, 0x20);
        Assert.Equal("signed32-subtraction-overflow",
            CurrentBuildVitalsCandidateReader.CalculateEnergy(raw, Cache(59, 100), 101).UnavailableReason);
    }

    private static CurrentBuildVitalsObservation Read(FakeSession s) => CurrentBuildVitalsCandidateReader.Read(s, _ => new(123, Component, () => { }));
    private static FakeSession Fixture()
    {
        var s = new FakeSession();
        s.Put(Module + 0x33DC2B0, Q(Clock)); s.Put(Clock + 0x18, D(BitConverter.SingleToInt32Bits(61827.53515625f)));
        s.Put(Component + 0x28, Q(Owner)); s.Put(Owner + 0x40, Q(Container)); s.Put(Container + 0x640, Q(Hp));
        s.Put(Hp, HealthRaw()); s.Put(Component + 0x30, Cache(74, 61827.53515625f));
        s.Put(Module + 0x2C0EEC8, Q(Module + 0x20CCC60)); s.Put(Module + 0x355F430, Q(Module + 0x2C281B0));
        s.Put(Module + 0x2C281B8, Q(Module + 0x20F2480));
        s.Put(Component + 0x40, Q(KindOwner)); s.Put(KindOwner + 0x168, D(4));
        s.Put(Component + 0x38, Q(Wrapper)); s.Put(Wrapper + 0x10, Q(Reference)); s.Put(Reference, Q(Energy));
        s.Put(Energy, EnergyRaw()); s.Put(Wrapper + 0x18, Cache(59, 61610.41796875f));
        s.Put(Module + 0x2D194D8, Q(Module + 0x231BEB0)); s.Put(Module + 0x35AEB80, Q(Module + 0x2D1D420));
        s.Put(Module + 0x2D1D428, Q(Module + 0x233E9B0));
        return s;
    }
    private static byte[] HealthRaw()
    {
        var b = new byte[128]; Q(Module + 0x2C0EE88).CopyTo(b, 0);
        BinaryPrimitives.WriteInt64LittleEndian(b.AsSpan(0x48), 10635);
        BinaryPrimitives.WriteInt64LittleEndian(b.AsSpan(0x50), 10635);
        BinaryPrimitives.WriteInt64LittleEndian(b.AsSpan(0x60), 14250);
        D(74).CopyTo(b, 0x68); D(BitConverter.SingleToInt32Bits(1)).CopyTo(b, 0x6C); D(BitConverter.SingleToInt32Bits(1)).CopyTo(b, 0x70);
        return b;
    }
    private static byte[] EnergyRaw()
    {
        var b = new byte[64]; Q(Module + 0x2D19498).CopyTo(b, 0);
        D(100).CopyTo(b, 0x20); D(100).CopyTo(b, 0x24); D(2000).CopyTo(b, 0x28); D(59).CopyTo(b, 0x34);
        return b;
    }
    private static void ConfigureMana(FakeSession s)
    {
        s.Put(KindOwner + 0x168, D(3));
        var wrapper = new byte[48]; Q(Reference).CopyTo(wrapper, 0x10);
        D(8).CopyTo(wrapper, 0x1C); D(BitConverter.SingleToInt32Bits(61827.53515625f)).CopyTo(wrapper, 0x24);
        s.Put(Wrapper, wrapper);
        var record = new byte[64]; Q(Module + 0x2A6ACD8).CopyTo(record, 0);
        D(9807).CopyTo(record, 0x18); D(3980).CopyTo(record, 0x1C);
        D(8).CopyTo(record, 0x20); D(3980).CopyTo(record, 0x24);
        s.Put(Energy, record);
        s.Put(Module + 0x2A6AD18, Q(Module + 0x1CCB460));
        s.Put(Module + 0x34D8990, Q(Module + 0x2A7C418));
        s.Put(Module + 0x2A7C420, Q(Module + 0x1CF9F10));
    }
    private static byte[] Q(ulong v) { var b = new byte[8]; BinaryPrimitives.WriteUInt64LittleEndian(b, v); return b; }
    private static byte[] D(int v) { var b = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(b, v); return b; }
    private static byte[] Cache(int rev, float clock) { var b = new byte[8]; D(rev).CopyTo(b, 0); D(BitConverter.SingleToInt32Bits(clock)).CopyTo(b, 4); return b; }
    private sealed class FakeSession : IReadOnlyNativeMemorySession
    {
        private readonly Dictionary<ulong, byte[]> data = [];
        private readonly Dictionary<ulong, byte[]> changed = [];
        private readonly HashSet<ulong> seen = [];
        public int Reads { get; private set; }
        public NativeProcessIdentity Identity { get; set; } = new(123, 456, @"C:\RIFT\rift_x64.exe", CurrentBuildPositionSampleCommand.GameSha256, Module, 0x4000000);
        public void Put(ulong address, byte[] bytes) => data[address] = bytes;
        public byte[] Get(ulong address) => data[address].ToArray();
        public void ChangeAfterFirst(ulong address, byte[] bytes) => changed[address] = bytes;
        public void ResetSeen() => seen.Clear();
        public NativeReadResult Read(ulong address, int length)
        {
            Reads++;
            var b = !seen.Add(address) && changed.TryGetValue(address, out var c) ? c : data.GetValueOrDefault(address);
            return b is not null && b.Length == length ? new("success", b.ToArray(), null, null) : new("unavailable", [], null, null);
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken _) => ValueTask.FromResult<string?>(null);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
