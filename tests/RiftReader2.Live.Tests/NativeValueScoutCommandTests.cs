using System.Buffers.Binary;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class NativeValueScoutCommandTests
{
    [Fact]
    public async Task ScoutValues_WindowsSelfProcessPublishesContextAndRejectsOverwrite()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;
        var memory = new byte[NativeValueScout.ChunkBytes];
        Array.Fill(memory, (byte)0xA5);
        BinaryPrimitives.WriteInt32LittleEndian(memory, 18208);
        var allocation = Marshal.AllocHGlobal(memory.Length);
        var directory = NewDirectory("rr2-value-scout");
        try
        {
            Marshal.Copy(memory, 0, allocation, memory.Length);
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                Environment.ProcessId, null, null, CancellationToken.None);
            var address = checked((ulong)allocation.ToInt64());
            Assert.Equal(0UL, address % 4);
            var requestPath = Path.Combine(directory, "request.json");
            var outputDirectory = Path.Combine(directory, "result");
            var requestBytes = Request(session.Identity, Hex(address));
            await File.WriteAllBytesAsync(requestPath, requestBytes);
            var stdout = new StringWriter();
            var stderr = new StringWriter();

            var exit = await NativeCommandRunner.RunAsync(
                ["scout-values-native", "--request", requestPath, "--output", outputDirectory],
                stdout, stderr);

            Assert.True(exit is 0 or 3, stderr.ToString());
            var indexPath = Path.Combine(outputDirectory, "index.json");
            Assert.True(File.Exists(indexPath));
            using var index = JsonDocument.Parse(await File.ReadAllBytesAsync(indexPath));
            var root = index.RootElement;
            Assert.Equal("native-value-scout/1", root.GetProperty("evidenceKind").GetString());
            Assert.Equal(Convert.ToHexString(SHA256.HashData(requestBytes)),
                root.GetProperty("requestSha256").GetString());
            Assert.Equal(session.Identity.ProcessStartUtcTicks,
                root.GetProperty("identity").GetProperty("processStartUtcTicks").GetInt64());
            Assert.Equal("aligned-4-byte-values-in-committed-readable-nonguard-MEM_PRIVATE-at-or-after-startAddress",
                root.GetProperty("scope").GetString());
            var candidate = root.GetProperty("candidates").EnumerateArray()
                .First(item => item.GetProperty("address").GetString() == Hex(address));
            Assert.Contains(candidate.GetProperty("referenceNames").EnumerateArray(),
                item => item.GetString() == "health");
            var snapshotPath = Path.Combine(outputDirectory,
                candidate.GetProperty("snapshotFile").GetString()!);
            var loaded = await NativeMemorySnapshotFile.LoadAsync(snapshotPath);
            Assert.Equal("complete", loaded.File.Status);
            Assert.Equal(36, Assert.Single(loaded.File.Chunks).RequestedByteLength);
            var bytes = Convert.FromBase64String(loaded.File.Chunks[0].BytesBase64!);
            Assert.Equal(18208, BinaryPrimitives.ReadInt32LittleEndian(bytes));
            Assert.Equal(Convert.ToHexString(SHA256.HashData(requestBytes)),
                Convert.ToHexString(SHA256.HashData(
                    await File.ReadAllBytesAsync(Path.Combine(outputDirectory, "source-request.json")))));

            var originalIndex = await File.ReadAllBytesAsync(indexPath);
            Assert.Equal(2, await NativeCommandRunner.RunAsync(
                ["scout-values-native", "--request", requestPath, "--output", outputDirectory],
                TextWriter.Null, TextWriter.Null));
            Assert.Equal(originalIndex, await File.ReadAllBytesAsync(indexPath));
            Assert.Null(await session.RevalidateAsync(CancellationToken.None));
        }
        finally
        {
            Marshal.FreeHGlobal(allocation);
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public async Task ScoutValues_RejectsStaleIdentityAndInvalidBoundsWithoutPublishing()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;
        var directory = NewDirectory("rr2-value-scout-invalid");
        try
        {
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                Environment.ProcessId, null, null, CancellationToken.None);
            var staleRequest = Path.Combine(directory, "stale.json");
            await File.WriteAllBytesAsync(staleRequest, Request(
                session.Identity with { ProcessStartUtcTicks = session.Identity.ProcessStartUtcTicks + 1 },
                "0x10000"));
            var staleOutput = Path.Combine(directory, "stale-output");
            Assert.Equal(2, await NativeCommandRunner.RunAsync(
                ["scout-values-native", "--request", staleRequest, "--output", staleOutput],
                TextWriter.Null, TextWriter.Null));
            Assert.False(Directory.Exists(staleOutput));

            var invalidRequest = Path.Combine(directory, "invalid.json");
            await File.WriteAllBytesAsync(invalidRequest, Request(
                session.Identity, "0x10000", maxScanBytes: NativeValueScout.MaxScanBytes + 1));
            var invalidOutput = Path.Combine(directory, "invalid-output");
            Assert.Equal(2, await NativeCommandRunner.RunAsync(
                ["scout-values-native", "--request", invalidRequest, "--output", invalidOutput],
                TextWriter.Null, TextWriter.Null));
            Assert.False(Directory.Exists(invalidOutput));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public async Task Help_AdvertisesNativeValueScout()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;
        var output = new StringWriter();
        Assert.Equal(0, await NativeCommandRunner.RunAsync(["help"], output, TextWriter.Null));
        Assert.Contains("scout-values-native --request PATH --output NEW_DIRECTORY",
            output.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public void PrivateRegionCapIsAppliedAfterTypeFilter()
    {
        const uint memPrivate = 0x20000;
        const uint memMapped = 0x40000;
        const uint memImage = 0x1000000;
        var collector = new WindowsMemoryRegionCollector(maxRegionCount: 2, requiredType: memPrivate);
        for (var index = 0; index < 40_000; index++)
        {
            var type = index % 2 == 0 ? memMapped : memImage;
            collector.Add(new((ulong)(0x10000 + index * 0x1000L), 0x1000, 4, type));
        }
        collector.Add(new(0x100000000, 0x1000, 4, memPrivate));
        collector.Add(new(0x100001000, 0x1000, 4, memPrivate));

        Assert.Equal(2, collector.Regions.Count);
        Assert.All(collector.Regions, region => Assert.Equal(memPrivate, region.Type));
        Assert.Throws<InvalidDataException>(() =>
            collector.Add(new(0x100002000, 0x1000, 4, memPrivate)));
    }

    private static byte[] Request(
        NativeProcessIdentity identity,
        string startAddress,
        long maxScanBytes = NativeValueScout.ChunkBytes) =>
        JsonSerializer.SerializeToUtf8Bytes(new
        {
            schemaVersion = 1,
            evidenceKind = "native-value-scout-request/1",
            target = new
            {
                processId = identity.ProcessId,
                processStartUtcTicks = identity.ProcessStartUtcTicks,
                executableSha256 = identity.ExecutableSha256
            },
            startAddress,
            references = new[] { new { name = "health", type = "int32", value = "18208" } },
            contextBeforeBytes = 0,
            contextAfterBytes = 32,
            maxScanBytes,
            maxDurationMilliseconds = 20_000,
            maxRegionCount = 32_768,
            maxMatchCount = 8
        }, JsonFormat.Options);

    private static string Hex(ulong value) => $"0x{value:X}";

    private static string NewDirectory(string prefix)
    {
        var path = Path.Combine(Path.GetTempPath(), $"{prefix}-{Guid.NewGuid():N}");
        Directory.CreateDirectory(path);
        return path;
    }
}
