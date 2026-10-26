using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Tests;

public sealed class PowerCandidateTests
{
    [Theory]
    [InlineData(80, 1200, 100.5f, 86)]
    [InlineData(80, 1200, 100.49f, 85)]
    [InlineData(80, 1200, 103, 100)]
    [InlineData(80, -1200, 110, 0)]
    public async Task ReconstructsTruncatedFloat32RegenerationAndClamps(int raw, int rate, float now, int expected)
    {
        var session = new Fixture();
        session.Int(0x600018, raw);
        session.Int(0x60002C, rate);
        session.Float(0x700018, now);
        var read = await PowerCandidateReader.ReadAsync(session, CancellationToken.None);
        Assert.Equal("complete", read.Status);
        Assert.Equal(expected, read.Power);
        Assert.Equal(raw, read.BaseValue);
        Assert.Equal(2, session.Validations);
        Assert.NotNull(read.RecordBytesBase64);
    }

    [Theory]
    [InlineData("build")]
    [InlineData("stale-before")]
    [InlineData("stale-after")]
    [InlineData("short-read")]
    [InlineData("null-owner")]
    [InlineData("wrong-type")]
    [InlineData("wrong-resource")]
    [InlineData("sequence")]
    [InlineData("change")]
    [InlineData("clock")]
    [InlineData("clock-backward")]
    [InlineData("overflow")]
    [InlineData("maximum")]
    public async Task InvalidOrChangingSourcesNeverReturnCachedPower(string fault)
    {
        var session = new Fixture { Fault = fault };
        if (fault == "null-owner") session.Pointer(0x1432E0200, 0);
        if (fault == "wrong-type") session.Pointer(0x600000, 0x140000000);
        if (fault == "wrong-resource") session.Int(0x800168, 2);
        if (fault == "sequence") session.Int(0x60001C, 9);
        if (fault == "clock") session.Float(0x700018, float.NaN);
        if (fault == "clock-backward") session.Float(0x700018, 99);
        if (fault == "overflow") session.Float(0x700018, float.MaxValue);
        if (fault == "maximum") session.Int(0x600020, 0);
        var read = await PowerCandidateReader.ReadAsync(session, CancellationToken.None);
        Assert.Equal("unavailable", read.Status);
        Assert.Null(read.Power);
        Assert.Null(read.RecordBytesBase64);
        if (fault == "build") Assert.Equal(0, session.Reads);
    }

    [Fact]
    public async Task NextObservationResolvesReplacementRecordWithoutCachedAddress()
    {
        var session = new Fixture();
        var first = await PowerCandidateReader.ReadAsync(session, CancellationToken.None);
        for (ulong i = 0; i < 48; i++) session.Memory[0x900000 + i] = session.Memory[0x600000 + i];
        session.Int(0x900018, 70);
        session.Pointer(0x500000, 0x900000);
        var second = await PowerCandidateReader.ReadAsync(session, CancellationToken.None);
        Assert.Equal(100, first.Power);
        Assert.Equal(76, second.Power);
        Assert.NotEqual(first.PointerChain![4], second.PointerChain![4]);
    }

    private sealed class Fixture : IReadOnlyNativeMemorySession
    {
        public Dictionary<ulong, byte> Memory { get; } = [];
        public string? Fault { get; init; }
        public int Validations { get; private set; }
        public int Reads { get; private set; }
        private int recordReads;
        public NativeProcessIdentity Identity => new(42, 12345, "rift_x64.exe",
            Fault == "build" ? new string('0', 64) : PowerCandidateReader.ExecutableSha256, 0x140000000, 0x4000000);
        public Fixture()
        {
            foreach (ulong address in new ulong[] { 0x300000, 0x400000, 0x600000 })
                for (ulong i = 0; i < 64; i++) Memory[address + i] = 0;
            Pointer(0x1432E0200, 0x200000);
            Pointer(0x200400, 0x300000);
            Pointer(0x300000, 0x142648E90);
            Pointer(0x300038, 0x400000);
            Pointer(0x300040, 0x800000);
            Int(0x800168, 1);
            Pointer(0x400000, 0x1427184F0);
            Pointer(0x400010, 0x500000);
            Pointer(0x500000, 0x600000);
            Pointer(0x600000, 0x142B378D8);
            Int(0x400018, 8); Float(0x40001C, 100);
            Int(0x600018, 100); Int(0x60001C, 8); Int(0x600020, 100); Int(0x60002C, 1200);
            Pointer(0x14335A0E0, 0x700000);
            Float(0x700018, 100.5f); Int(0x142649B94, unchecked((int)0xBC23D70A));
        }
        private void Put(ulong address, byte[] value)
        {
            for (var i = 0; i < value.Length; i++) Memory[address + (ulong)i] = value[i];
        }
        public void Pointer(ulong address, ulong value) => Put(address, BitConverter.GetBytes(value));
        public void Int(ulong address, int value) => Put(address, BitConverter.GetBytes(value));
        public void Float(ulong address, float value) => Put(address, BitConverter.GetBytes(value));
        public NativeReadResult Read(ulong address, int byteLength)
        {
            Reads++;
            if (Fault == "short-read") return new("success", new byte[byteLength - 1], null, null);
            var bytes = Enumerable.Range(0, byteLength).Select(i => Memory[address + (ulong)i]).ToArray();
            if (address == 0x600000 && byteLength == 48 && ++recordReads == 2 && Fault == "change")
                BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(0x18), 80);
            return new("success", bytes, null, null);
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken cancellationToken)
        {
            Validations++;
            return ValueTask.FromResult<string?>(Fault == "stale-before" || Fault == "stale-after" && Validations == 2 ? "stale-process" : null);
        }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
