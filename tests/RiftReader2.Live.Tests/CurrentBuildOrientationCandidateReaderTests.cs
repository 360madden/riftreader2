using System.Buffers.Binary;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildOrientationCandidateReaderTests
{
    const ulong Component = 0x20060000;
    [Theory]
    [InlineData(1, 90)]
    [InlineData(-1, -90)]
    public void ReadsRawMatricesAndNumericDescriptorOnly(int sine, int degrees)
    {
        var s = new Fake();
        s.Matrix(0x60, [0, 0, -sine, 0, 1, 0, sine, 0, 0]);
        s.Matrix(0x94, [1, 0, 0, 0, 1, 0, 0, 0, 1]);
        BinaryPrimitives.WriteUInt64LittleEndian(s.Raw.AsSpan(0x100), 123);
        s.Raw[0x108] = 7;
        var verified = false;
        var o = CurrentBuildOrientationCandidateReader.Read(s, _ => new(42, 0x20040000, Component, () => verified = true));
        Assert.True(verified);
        Assert.Equal((ulong)123, o.RefreshHandleRaw);
        Assert.Equal((byte)7, o.RefreshFlagRaw);
        Assert.Equal(degrees, o.Primary.PlanarAngleDegreesCandidate!.Value, 8);
        Assert.Equal(0, o.Secondary.PlanarAngleRadiansCandidate!.Value, 8);
        Assert.Equal(9, o.Primary.RawBits.Length);
        Assert.Contains("body-facing/axis/sign/passive-freshness/restart-unverified", o.Qualification);
    }

    [Theory]
    [InlineData(0x60)]
    [InlineData(0x94)]
    [InlineData(0x100)]
    [InlineData(0x108)]
    public void RejectsChangedConsumedBytes(int offset)
    {
        var s = new Fake { ChangedOffset = offset };
        Assert.Throws<InvalidDataException>(() => Read(s));
    }

    [Fact]
    public void RejectsInvalidBuildBeforeMemoryOrOwnerResolution()
    {
        var s = new Fake();
        s.Identity = s.Identity with { ExecutableSha256 = new string('0', 64) };
        Assert.Throws<InvalidDataException>(() => CurrentBuildOrientationCandidateReader.Read(s,
            _ => throw new Exception("must not resolve")));
        Assert.Equal(0, s.Reads);
    }

    [Fact]
    public void RejectsOwnerAndEpochChange()
    {
        var s = new Fake();
        Assert.Throws<InvalidDataException>(() => CurrentBuildOrientationCandidateReader.Read(s,
            _ => new(42, 0x20040000, Component, () => throw new InvalidDataException("owner"))));
        Assert.Throws<InvalidDataException>(() => CurrentBuildOrientationCandidateReader.Read(s,
            _ => new(42, 0x20040000, Component, () => s.Identity = s.Identity with { ProcessStartUtcTicks = 789 })));
    }

    [Fact]
    public void RejectsMissingOwnerAndReadHole()
    {
        var s = new Fake();
        Assert.Throws<InvalidDataException>(() => CurrentBuildOrientationCandidateReader.Read(s,
            _ => new(0, 0x20040000, Component, () => { })));
        s.Hole = true;
        Assert.Throws<InvalidDataException>(() => Read(s));
        Assert.Throws<InvalidDataException>(() => CurrentBuildOrientationCandidateReader.Decode(new byte[35], 0x60));
    }

    [Fact]
    public void NonfiniteMatrixPreservesBitsWithoutUnserializableFloats()
    {
        var s = new Fake();
        s.Matrix(0x60, [float.NaN, 0, 0, 0, 1, 0, 0, 0, 1]);
        var o = Read(s);
        Assert.Equal("nonfinite-matrix", o.Primary.Status);
        Assert.Null(o.Primary.RowMajorF32);
        Assert.Null(o.Primary.PlanarAngleRadiansCandidate);
        Assert.Equal(BitConverter.SingleToUInt32Bits(float.NaN), o.Primary.RawBits[0]);
        Assert.NotEmpty(JsonSerializer.Serialize(o));
    }

    [Fact]
    public void ScaledAndNonPlanarMatricesWithholdAngle()
    {
        var s = new Fake();
        s.Matrix(0x60, [2, 0, 0, 0, 1, 0, 0, 0, 1]);
        s.Matrix(0x94, [1, 0, 0, 0, 0, -1, 0, 1, 0]);
        var o = Read(s);
        Assert.Equal("unqualified-matrix-shape", o.Primary.Status);
        Assert.Null(o.Primary.PlanarAngleDegreesCandidate);
        Assert.Null(o.Secondary.PlanarAngleDegreesCandidate);
        Assert.NotNull(o.Primary.RowMajorF32);
    }

    [Fact]
    public void SerializesMaximumUnitKeyAndOpaqueHandleLosslessly()
    {
        var s = new Fake();
        BinaryPrimitives.WriteUInt64LittleEndian(s.Raw.AsSpan(0x100), ulong.MaxValue);
        var o = CurrentBuildOrientationCandidateReader.Read(s,
            _ => new(ulong.MaxValue, 0x20040000, Component, () => { }));
        Assert.Equal(ulong.MaxValue, o.UnitKey);
        Assert.Equal(ulong.MaxValue, o.RefreshHandleRaw);
        using var json = JsonDocument.Parse(JsonSerializer.Serialize(o));
        Assert.Equal(JsonValueKind.String, json.RootElement.GetProperty("unitKey").ValueKind);
        Assert.Equal("18446744073709551615", json.RootElement.GetProperty("unitKey").GetString());
        Assert.Equal("0xFFFFFFFFFFFFFFFF", json.RootElement.GetProperty("refreshHandleRaw").GetString());
        Assert.False(json.RootElement.TryGetProperty("UnitKey", out _));
        Assert.False(json.RootElement.TryGetProperty("RefreshHandleRaw", out _));
    }

    static CurrentBuildOrientationCandidate Read(Fake s) =>
        CurrentBuildOrientationCandidateReader.Read(s, _ => new(42, 0x20040000, Component, () => { }));

    sealed class Fake : IReadOnlyNativeMemorySession
    {
        public byte[] Raw { get; } = new byte[0x110];
        public int? ChangedOffset { get; init; }
        public bool Hole { get; set; }
        public int Reads { get; private set; }
        public NativeProcessIdentity Identity { get; set; } = new(123, 456, "rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 64 * 1024 * 1024);
        public Fake()
        {
            Matrix(0x60, [1, 0, 0, 0, 1, 0, 0, 0, 1]);
            Matrix(0x94, [1, 0, 0, 0, 1, 0, 0, 0, 1]);
        }
        public void Matrix(int offset, float[] values)
        {
            for (int i = 0; i < 9; i++)
                BinaryPrimitives.WriteInt32LittleEndian(Raw.AsSpan(offset + i * 4), BitConverter.SingleToInt32Bits(values[i]));
        }
        public NativeReadResult Read(ulong address, int length)
        {
            Reads++;
            if (Hole || address < Component || address + (ulong)length > Component + (ulong)Raw.Length)
                return new("unavailable", [], null, "hole");
            var offset = checked((int)(address - Component));
            var value = Raw.AsSpan(offset, length).ToArray();
            if (address != Component && ChangedOffset is int changed && changed >= offset && changed < offset + length)
                value[changed - offset] ^= 1;
            return new("success", value, null, null);
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken _) => ValueTask.FromResult<string?>(null);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
