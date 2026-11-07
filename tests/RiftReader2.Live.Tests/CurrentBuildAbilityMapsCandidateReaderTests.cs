using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildAbilityMapsCandidateReaderTests
{
    const ulong Module = 0x140000000, SystemAddress = 0x20000000, Context = 0x20010000, Clock = 0x20020000, Buckets = 0x20030000, Entity = 0x20040000;
    [Fact] public void ReadsObservedLayoutAndAdvancingClock()
    {
        var s = Fixture(); s.Change(Clock + 0x18, F(101));
        var result = Read(s);
        Assert.Equal(202UL, result.Maps[0].BucketCount); Assert.Equal(122, result.Maps[0].Entries.Count);
        Assert.Empty(result.Maps[1].Entries); Assert.Equal(100, result.ClockBefore); Assert.Equal(101, result.ClockAfter);
        Assert.Equal("0000803f", result.Maps[0].Entries[0].ValueRawHex);
    }
    [Theory]
    [InlineData("owner")][InlineData("stride")][InlineData("count")][InlineData("clock")][InlineData("bytes")][InlineData("root")]
    public void RejectsChangedOrInvalidSnapshot(string defect)
    {
        var s = Fixture();
        if (defect == "owner") s.Put(SystemAddress + 0x3F8, Q(Entity + 8));
        if (defect == "stride") s.Put(Context + 0x1C0, Header(Buckets, 24, 202, 122));
        if (defect == "count") s.Put(Context + 0x1C0, Header(Buckets, 40, 202, 123));
        if (defect == "clock") s.Change(Clock + 0x18, F(99));
        if (defect == "bytes") s.Change(Buckets, Node(999));
        if (defect == "root") s.Change(Module + 0x33623E0, Q(SystemAddress + 8));
        Assert.Throws<InvalidDataException>(() => Read(s));
    }
    [Fact] public void RejectsCyclicChain()
    {
        var s = Fixture(); var node = Node(0); Q(Buckets).CopyTo(node, 0); s.Put(Buckets, node);
        Assert.Throws<InvalidDataException>(() => Read(s));
    }
    [Fact] public void VerifiesOriginalOwner()
    {
        var s = Fixture();
        Assert.Throws<InvalidDataException>(() => CurrentBuildAbilityMapsCandidateReader.ReadResolved(s, s.Identity, DateTimeOffset.UtcNow, 123, Entity, Context, () => throw new InvalidDataException("owner changed")));
    }
    static CurrentBuildAbilityMapsObservation Read(Fake s) => CurrentBuildAbilityMapsCandidateReader.ReadResolved(s, s.Identity, DateTimeOffset.UtcNow, 123, Entity, Context, () => { });
    static Fake Fixture()
    {
        var s = new Fake(); s.Put(Module + 0x33623E0, Q(SystemAddress)); s.Put(SystemAddress + 0x3F8, Q(Entity));
        s.Put(Module + 0x33DC2B0, Q(Clock)); s.Put(Clock + 0x18, F(100));
        s.Put(Context + 0x1C0, Header(Buckets, 40, 202, 122)); s.Put(Context + 0x240, Header(0, 24, 0, 0));
        for (ulong i = 0; i < 202; i++) s.Put(Buckets + i * 40, i < 122 ? Node((uint)i) : Empty());
        return s;
    }
    static byte[] Header(ulong b, ulong stride, ulong buckets, ulong count) { var x = new byte[32]; Q(b).CopyTo(x, 0); Q(stride).CopyTo(x, 8); Q(buckets).CopyTo(x, 16); Q(count).CopyTo(x, 24); return x; }
    static byte[] Node(uint key) { var x = new byte[24]; BinaryPrimitives.WriteUInt32LittleEndian(x.AsSpan(8), key); F(1).CopyTo(x, 16); return x; }
    static byte[] Empty() { var x = new byte[24]; x[0] = 1; return x; }
    static byte[] Q(ulong value) { var x = new byte[8]; BinaryPrimitives.WriteUInt64LittleEndian(x, value); return x; }
    static byte[] F(float value) => BitConverter.GetBytes(value);
    sealed class Fake : IReadOnlyNativeMemorySession
    {
        readonly Dictionary<ulong, byte[]> data = []; readonly Dictionary<ulong, byte[]> changed = []; readonly HashSet<ulong> seen = [];
        public NativeProcessIdentity Identity { get; } = new(123, 456, @"C:\RIFT\rift_x64.exe", CurrentBuildPlayerLookup.GameSha256, Module, 0x4000000);
        public void Put(ulong address, byte[] value) => data[address] = value;
        public void Change(ulong address, byte[] value) => changed[address] = value;
        public NativeReadResult Read(ulong address, int length)
        {
            var value = !seen.Add(address) && changed.TryGetValue(address, out var c) ? c : data.GetValueOrDefault(address);
            return value is not null && value.Length == length ? new("success", value.ToArray(), null, null) : new("unavailable", [], null, null);
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken _) => ValueTask.FromResult<string?>(null);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
