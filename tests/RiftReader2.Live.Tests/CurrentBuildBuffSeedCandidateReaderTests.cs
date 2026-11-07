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
