using System.Buffers.Binary;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildPoseCacheHitCandidateTests
{
    private const ulong Actor = 0x10000, Bucket = 0x20000, Entry = 0x30000, Pose = 0x40000;
    private const ulong Key = 0x1234567800000001;

    [Theory]
    [InlineData(1UL, 0)]
    [InlineData(0xffffffffUL, 1)]
    public void UsesSignedLowWordHashAndStride(ulong key, int index)
    {
        var m = new Memory();
        m.Setup();
        m.Put(Actor + 0x5b8, 32);
        m.Put(Actor + 0x5c0, 7);
        m.Node(Bucket + (ulong)index * 32, 0, key, Entry);
        Assert.NotNull(CurrentBuildPoseCacheHitCandidate.TryRead(m.Read, Actor, key));
    }

    [Fact]
    public void StableHitReturnsOpaquePayload()
    {
        var m = new Memory();
        m.Setup();
        var hit = CurrentBuildPoseCacheHitCandidate.TryRead(m.Read, Actor, Key);
        Assert.NotNull(hit);
        Assert.Equal(Pose, hit.PoseAddress);
        Assert.Equal(Enumerable.Range(1, 12).Select(x => (byte)x), hit.RawPosePayload);
    }

    [Fact]
    public void TaggedHeadSkipsHeadKeyAndFindsLinkedNode()
    {
        var m = new Memory();
        m.Setup();
        m.Node(Bucket, 0x50001, Key, Entry);
        m.Node(0x50000, 1, Key, Entry);
        Assert.NotNull(CurrentBuildPoseCacheHitCandidate.TryRead(m.Read, Actor, Key));
        m.Node(0x50000, 1, Key + (1UL << 32), Entry);
        Assert.Null(CurrentBuildPoseCacheHitCandidate.TryRead(m.Read, Actor, Key));
    }

    [Fact]
    public void CyclesAndNinthNodeFailClosed()
    {
        var m = new Memory();
        m.Setup();
        m.Node(Bucket, 0x50001, 0, 0);
        for (int i = 0; i < 8; i++)
        {
            ulong address = 0x50000UL + (ulong)i * 0x100;
            m.Node(address, i == 7 ? 0UL : address + 0x100, i == 7 ? Key : 0, Entry);
        }
        Assert.Null(CurrentBuildPoseCacheHitCandidate.TryRead(m.Read, Actor, Key));
        m.Node(0x50000, 0x50000, 0, 0);
        Assert.Null(CurrentBuildPoseCacheHitCandidate.TryRead(m.Read, Actor, Key));
    }

    [Fact]
    public void MissingInvalidAndChangedDataFailClosed()
    {
        var m = new Memory();
        m.Setup();
        m.Put(Entry + 0x18, 0);
        Assert.Null(CurrentBuildPoseCacheHitCandidate.TryRead(m.Read, Actor, Key));
        m.Setup();
        int reads = 0;
        byte[]? Changing(ulong address, int length)
        {
            var result = m.Read(address, length);
            if (++reads == 5 && result is not null) result[0] ^= 1;
            return result;
        }
        Assert.Null(CurrentBuildPoseCacheHitCandidate.TryRead(Changing, Actor, Key));
        Assert.Null(CurrentBuildPoseCacheHitCandidate.TryRead((_, _) => null, Actor, Key));
        Assert.Null(CurrentBuildPoseCacheHitCandidate.TryRead(m.Read, 0, Key));
    }

    [Theory]
    [InlineData(0L, 0L)]
    [InlineData(24L, 0L)]
    [InlineData(8L, 1L)]
    public void InvalidHeaderFailsClosed(long stride, long count)
    {
        var m = new Memory();
        m.Setup();
        m.Put(Actor + 0x5b8, (ulong)stride);
        m.Put(Actor + 0x5c0, (ulong)count);
        Assert.Null(CurrentBuildPoseCacheHitCandidate.TryRead(m.Read, Actor, Key));
    }

    private sealed class Memory
    {
        private readonly Dictionary<ulong, byte> bytes = new();
        public void Setup()
        {
            Put(Actor + 0x5b0, Bucket);
            Put(Actor + 0x5b8, 24);
            Put(Actor + 0x5c0, 1);
            Node(Bucket, 0, Key, Entry);
            Put(Entry + 0x18, Pose);
            for (int i = 0; i < 12; i++) bytes[Pose + 0xf8 + (ulong)i] = (byte)(i + 1);
        }
        public void Node(ulong address, ulong next, ulong key, ulong entry)
        {
            Put(address, next);
            Put(address + 8, key);
            Put(address + 16, entry);
        }
        public void Put(ulong address, ulong value)
        {
            var b = new byte[8];
            BinaryPrimitives.WriteUInt64LittleEndian(b, value);
            for (int i = 0; i < b.Length; i++) bytes[address + (ulong)i] = b[i];
        }
        public byte[]? Read(ulong address, int length)
        {
            var result = new byte[length];
            for (int i = 0; i < length; i++)
                if (!bytes.TryGetValue(address + (ulong)i, out result[i])) return null;
            return result;
        }
    }
}
