using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildBuffSeedCandidateReaderTests
{
    const ulong Module = 0x140000000, SystemOwner = 0x20000000, Entity = 0x20010000,
        Health = 0x20020000, Context = 0x20030000, Node1 = 0x20040000, Node2 = 0x20050000,
        Object1 = 0x20060000, Descriptor = 0x20070000;
    const ulong Sentinel = Context + 0x310;

    [Fact] public void EmptyList() { var s = Fixture(); Assert.Empty(Read(s).Nodes); }
    [Fact] public void TwoNodesPreserveRawObjectAndUnreadableObject()
    {
        var s = Fixture(); s.Q(Sentinel, Node1); s.Node(Node1, Node2, Object1, 0x23000000); s.Node(Node2, Sentinel, 0x24000000, 0);
        s.Q(Object1, Module + 0x2000); s.D(Object1 + 8, 17); s.Q(Object1 + 0x10, Descriptor);
        s.Q(Object1 + 0x20, 21); s.Q(Object1 + 0x28, 22); s.D(Object1 + 0x3C, 23); s.Q(Object1 + 0x48, 24);
        s.Q(Descriptor, Module + 0x3000); s.D(Descriptor + 0x38, 1);
        s.Q(Object1 + 0x20, 0x20080000); s.D(0x20080088, 5);
        s.Q(Object1 + 0x68, 0x20090000); s.Q(0x20090000, Module + 0x4000);
        s.Q(Module + 0x4030, Module + 0x5000); s.Q(Module + 0x4038, Module + 0x5100); s.Q(Module + 0x4048, Module + 0x5200);
        var result = Read(s); Assert.Equal(2, result.Nodes.Count); Assert.Equal(17U, result.Nodes[0].RawObject.Dword08);
        Assert.Equal(0x2000UL, result.Nodes[0].RawObject.VtableRva); Assert.Equal(1U, result.Nodes[0].RawObject.DescriptorDword38);
        Assert.Equal(5U, result.Nodes[0].RawObject.StateDword88);
        Assert.Equal(0x5000UL, result.Nodes[0].RawObject.ClockSlot30Rva);
        Assert.Equal(0x5100UL, result.Nodes[0].RawObject.ClockSlot38Rva);
        Assert.Equal(0x5200UL, result.Nodes[0].RawObject.ClockSlot48Rva);
        Assert.Equal("unavailable", result.Nodes[1].RawObject.Status); Assert.Equal(0x24000000UL, result.Nodes[1].Object);
    }
    [Fact] public void RejectsCycleAndChangedNode()
    {
        var s = Fixture(); s.Q(Sentinel, Node1); s.Node(Node1, Node1, 0, 0);
        Assert.Throws<InvalidDataException>(() => Read(s));
        s = Fixture(); s.Q(Sentinel, Node1); s.Node(Node1, Sentinel, 0, 0); s.Changed = (Node1, 8);
        Assert.Throws<InvalidDataException>(() => Read(s));
    }
    [Theory]
    [InlineData(12345678L, 1.234f)]
    [InlineData(-12345678L, -1.234f)]
    public void TypedTimerUsesSignedTruncatedTicks(long ticks, float expected)
    {
        var s = TimingFixture(ticks, 0);
        var result = ReadTiming(s); var timing = result.Nodes[0].Timing!;
        Assert.Equal("raw-timing-candidate", timing.Status);
        Assert.Equal(ticks, timing.DurationTicks);
        Assert.Equal(expected, timing.Duration!.Value, 5);
        Assert.Equal(expected - 5f, timing.Remaining!.Value, 5);
        Assert.Equal(0x2220UL, timing.ReferenceSlot48Rva);
    }
    [Fact] public void SentinelAndChangedTimerAreNotNumeric()
    {
        var s = TimingFixture(12345678, 5);
        var timing = ReadTiming(s).Nodes[0].Timing!;
        Assert.Equal("state-sentinel", timing.Status); Assert.Null(timing.Duration);
        Assert.Equal(0x200A0000UL, timing.TimerReference);
        s = TimingFixture(12345678, 0); s.Changed = (0x200A0018, 8);
        Assert.Throws<InvalidDataException>(() => ReadTiming(s));
    }
    [Fact] public void DynamicFloatRequiresExactPropertyMetadata()
    {
        var s = DynamicFixture(); var timing = ReadTiming(s).Nodes[0].Timing!;
        Assert.Equal("raw-timing-candidate", timing.Status);
        Assert.Equal((uint)BitConverter.SingleToInt32Bits(12.5f), timing.DurationInputRawBits);
        Assert.Equal(12.5f, timing.Duration); Assert.Equal(7.5f, timing.Remaining); Assert.Null(timing.DurationTicks);
        s = DynamicFixture(); s.Bytes(Module + 0x345DE38, "!6b50761x\0"u8.ToArray());
        Assert.Equal("dynamic-type-or-property-unavailable", ReadTiming(s).Nodes[0].Timing!.Status);
        s = DynamicFixture(); s.Q(0x200A0000, Module + 0x286CDC8);
        Assert.Equal("dynamic-type-or-property-unavailable", ReadTiming(s).Nodes[0].Timing!.Status);
        s = DynamicFixture(); s.FieldTable(0x303E860, 0x303E720, 0x303E790, 0x303E828, 0x303E828);
        Assert.Equal("dynamic-type-or-property-unavailable", ReadTiming(s).Nodes[0].Timing!.Status);
    }
    static Fake DynamicFixture()
    {
        var s = TimingFixture(0, 0);
        s.Q(0x20090000, Module + 0x26BCE50); s.Q(Module + 0x26BCE80, Module + 0x72B040);
        s.Q(Module + 0x26BCE88, Module + 0x72B3C0); s.Q(Module + 0x26BCE98, Module + 0x09D680);
        s.Q(0x200A0000, Module + 0x28EC200); s.Q(Module + 0x28EC240, Module + 0x194CCE0);
        s.Q(Module + 0x28EC248, Module + 0x04F180); s.Q(Module + 0x3462A70, Module + 0x28F5968);
        s.Q(Module + 0x28F5970, Module + 0x1978670); s.Q(Module + 0x28F5990, Module + 0x197A330);
        s.Q(Module + 0x28F59A0, Module + 0x197D520);
        s.FieldTable(0x303E860, 0x303E720, 0x303E790, 0x303E7E0, 0x303E828);
        s.Q(Module + 0x303E7E0, Module + 0x28ED1E8); s.Q(Module + 0x28ED240, Module + 0x194DCC0);
        s.Q(Module + 0x28ED250, Module + 0x194DD00); s.Q(Module + 0x28ED260, Module + 0x194DD40);
        s.Bytes(Module + 0x345DE18, "!8dca2bf7\0"u8.ToArray()); s.Bytes(Module + 0x345DE48, "!8f2b42db\0"u8.ToArray());
        s.Bytes(Module + 0x345DE28, "!a0843f13\0"u8.ToArray()); s.Bytes(Module + 0x345DE58, "!1381549c\0"u8.ToArray());
        s.Bytes(Module + 0x345DE38, "!6b50761c\0"u8.ToArray()); s.D(0x200A0024, (uint)BitConverter.SingleToInt32Bits(12.5f));
        return s;
    }
    static CurrentBuildBuffSeedObservation ReadTiming(Fake s) => CurrentBuildBuffSeedCandidateReader.ReadResolved(s,
        s.Identity, DateTimeOffset.UtcNow, 123, Entity, Health, Context, () => { }, true);
    static Fake TimingFixture(long ticks, uint state)
    {
        var s = Fixture(); s.Q(Sentinel, Node1); s.Node(Node1, Sentinel, Object1, 0);
        s.Q(Module + 0x33DC2B0, 0x200B0000); s.D(0x200B0018, (uint)BitConverter.SingleToInt32Bits(15f));
        s.Q(Object1, Module + 0x2000); s.D(Object1 + 8, 17); s.Q(Object1 + 0x10, 0);
        s.Q(Object1 + 0x20, 0x20080000); s.D(0x20080088, state); s.Q(Object1 + 0x28, 0);
        s.D(Object1 + 0x3C, 3); s.Q(Object1 + 0x48, 0); s.Q(Object1 + 0x68, 0x20090000);
        s.Q(0x20090000, Module + 0x26BC950); s.Q(Module + 0x26BC980, Module + 0x72AE00);
        s.Q(Module + 0x26BC988, Module + 0x72B3C0); s.Q(Module + 0x26BC998, Module + 0x09D680);
        s.Q(0x20090010, 0x200A0000); s.D(0x20090018, (uint)BitConverter.SingleToInt32Bits(10f));
        s.Q(0x200A0000, Module + 0x286CDC8); s.Q(Module + 0x286CE08, Module + 0x18254A0);
        s.Q(Module + 0x286CE10, Module + 0x2220); s.Q(Module + 0x343B3C0, Module + 0x2876CA8);
        s.Q(Module + 0x2876CB0, Module + 0x184B530); s.Q(0x200A0018, unchecked((ulong)ticks));
        return s;
    }
    static CurrentBuildBuffSeedObservation Read(Fake s) => CurrentBuildBuffSeedCandidateReader.ReadResolved(s,
        s.Identity, DateTimeOffset.UtcNow, 123, Entity, Health, Context, () => { });
    static Fake Fixture()
    {
        var s = new Fake(); s.Q(Module + 0x33623E0, SystemOwner); s.Q(SystemOwner + 0x3F8, Entity);
        s.Q(Health + 0x10, Entity); s.Q(Context + 0x10, Entity); s.Q(Sentinel, Sentinel); return s;
    }
    sealed class Fake : IReadOnlyNativeMemorySession
    {
        readonly Dictionary<(ulong, int), byte[]> data = []; readonly Dictionary<(ulong, int), int> reads = [];
        public (ulong, int)? Changed { get; set; }
        public NativeProcessIdentity Identity { get; } = new(1, 2, "rift_x64.exe", CurrentBuildPlayerLookup.GameSha256, Module, 64 * 1024 * 1024);
        public void FieldTable(params ulong[] values)
        {
            var b = new byte[48];
            for (int i = 0; i < values.Length; i++) BinaryPrimitives.WriteUInt64LittleEndian(b.AsSpan(i * 8), Module + values[i]);
            Bytes(Module + 0x303E8A8, b);
        }
        public void Bytes(ulong a, byte[] b) => data[(a,b.Length)] = b.ToArray();
        public void Q(ulong a, ulong v) { var b = new byte[8]; BinaryPrimitives.WriteUInt64LittleEndian(b, v); data[(a,8)] = b; }
        public void D(ulong a, uint v) { var b = new byte[4]; BinaryPrimitives.WriteUInt32LittleEndian(b, v); data[(a,4)] = b; }
        public void Node(ulong a, ulong next, ulong obj, ulong control) { Q(a,next); Q(a+0x10,obj); Q(a+0x18,control); }
        public NativeReadResult Read(ulong a, int n)
        {
            var k=(a,n); var seen=reads.GetValueOrDefault(k); reads[k]=seen+1;
            if (!data.TryGetValue(k,out var b)) return new("unavailable", [], null, "missing");
            var copy=b.ToArray(); if (Changed == k && seen > 0) copy[0]^=1;
            return new("success",copy,null,null);
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken _) => ValueTask.FromResult<string?>(null);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
