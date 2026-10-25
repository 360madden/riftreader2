using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Tests;

public sealed class NativeValueScoutTests
{
    private const ulong Base = 0x20000;

    [Fact]
    public void Scan_FindsAlignedTypedValuesAcrossChunkBoundaryAndExcludesNonprivateMemory()
    {
        var privateBytes = Memory(NativeValueScout.ChunkBytes + 16);
        var boundary = NativeValueScout.ChunkBytes - 4;
        BinaryPrimitives.WriteInt32LittleEndian(privateBytes.AsSpan(boundary), 18208);
        BinaryPrimitives.WriteDoubleLittleEndian(privateBytes.AsSpan(boundary + 4), 18208d);
        var mappedBytes = Memory(NativeValueScout.ChunkBytes);
        BinaryPrimitives.WriteInt32LittleEndian(mappedBytes, 18208);
        var regions = new[]
        {
            new NativeValueScanRegion(Base, (ulong)privateBytes.Length, 0x20000),
            new NativeValueScanRegion(0x40000, (ulong)mappedBytes.Length, 0x40000)
        };

        var result = NativeValueScout.Scan(
            regions, Base,
            [new("health", MemoryValueKind.Int32, "18208", 0),
             new("health-double", MemoryValueKind.Float64, "18208", 0)],
            privateBytes.Length, 10,
            (address, buffer, count) => Read(address, buffer, count, privateBytes),
            () => false);

        Assert.Equal("complete", result.Status);
        Assert.Collection(result.Matches,
            match =>
            {
                Assert.Equal(Base + (ulong)boundary, match.Address);
                Assert.Equal("health", Assert.Single(match.ReferenceNames));
            },
            match =>
            {
                Assert.Equal(Base + (ulong)boundary + 4, match.Address);
                Assert.Equal("health-double", Assert.Single(match.ReferenceNames));
            });
        Assert.Equal(privateBytes.Length, result.ExaminedBytes);
        Assert.Equal(1, result.EligiblePrivateRegionCount);
        Assert.Empty(result.Holes);
    }

    [Fact]
    public void Scan_RetainsEarlyReadHoleButResumeCursorAdvancesPastIt()
    {
        var bytes = Memory(NativeValueScout.ChunkBytes * 2);
        var calls = 0;
        var result = NativeValueScout.Scan(
            [new(Base, (ulong)bytes.Length, 0x20000)], Base,
            [new("health", MemoryValueKind.Int32, "18208", 0)],
            bytes.Length, 10,
            (address, buffer, count) =>
            {
                calls++;
                if (calls == 2)
                    return new(false, 0, 299);
                return Read(address, buffer, count, bytes);
            },
            () => false);

        Assert.Equal("partial", result.Status);
        Assert.Equal("read-holes", result.Reason);
        var hole = Assert.Single(result.Holes);
        Assert.Equal(Base + NativeValueScout.ChunkBytes, hole.BaseAddress);
        Assert.Equal(299, hole.Win32Error);
        Assert.Equal(Base + (ulong)bytes.Length - 7, result.NextAddress);

        var resumedReads = 0;
        var resumed = NativeValueScout.Scan(
            [new(Base, (ulong)bytes.Length, 0x20000)], result.NextAddress!.Value,
            [new("health", MemoryValueKind.Int32, "18208", 0)],
            NativeValueScout.ChunkBytes, 10,
            (address, buffer, count) =>
            {
                resumedReads++;
                return Read(address, buffer, count, bytes);
            },
            () => false);
        Assert.Equal("complete", resumed.Status);
        Assert.Null(resumed.NextAddress);
        Assert.Equal(1, resumedReads);
    }

    [Fact]
    public void Scan_StopsAtCandidateLimitAndReturnsFirstUnretainedAddress()
    {
        var bytes = Memory(NativeValueScout.ChunkBytes);
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(0), 100);
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(4), 100);
        var result = NativeValueScout.Scan(
            [new(Base, (ulong)bytes.Length, 0x20000)], Base,
            [new("power", MemoryValueKind.Int32, "100", 0)],
            bytes.Length, 1,
            (address, buffer, count) => Read(address, buffer, count, bytes),
            () => false);

        Assert.Equal("partial", result.Status);
        Assert.Equal("candidate-budget-exceeded", result.Reason);
        Assert.Equal(Base + 4, result.NextAddress);
        Assert.Single(result.Matches);
    }

    [Fact]
    public async Task RequestLoaderRetainsTheExactBytesItHashed()
    {
        var path = Path.Combine(Path.GetTempPath(), $"rr2-value-request-{Guid.NewGuid():N}.json");
        try
        {
            var original = JsonSerializer.SerializeToUtf8Bytes(new
            {
                schemaVersion = 1,
                evidenceKind = "native-value-scout-request/1",
                target = new
                {
                    processId = 42,
                    processStartUtcTicks = 638000000000000000L,
                    executableSha256 = new string('A', 64)
                },
                startAddress = "0x10000",
                references = new[] { new { name = "health", type = "int32", value = "18208" } },
                contextBeforeBytes = 16,
                contextAfterBytes = 64,
                maxScanBytes = 65536,
                maxDurationMilliseconds = 1000,
                maxRegionCount = 10,
                maxMatchCount = 10
            }, JsonFormat.Options);
            await File.WriteAllBytesAsync(path, original);
            var loaded = await NativeValueScoutRequestFile.LoadAsync(path);
            await File.WriteAllTextAsync(path, "replaced after load");

            Assert.Equal(original, loaded.RawBytes);
            Assert.Equal(Convert.ToHexString(SHA256.HashData(loaded.RawBytes)), loaded.RequestSha256);
        }
        finally
        {
            File.Delete(path);
        }
    }

    private static byte[] Memory(int length)
    {
        var bytes = new byte[length];
        Array.Fill(bytes, (byte)0xA5);
        return bytes;
    }

    private static NativeValueScanReadResult Read(
        ulong address, byte[] destination, int count, byte[] source)
    {
        source.AsSpan(checked((int)(address - Base)), count).CopyTo(destination);
        return new(true, count, null);
    }
}
