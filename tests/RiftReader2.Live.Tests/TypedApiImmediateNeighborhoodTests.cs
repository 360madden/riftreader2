using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class TypedApiImmediateNeighborhoodTests
{
    private const ulong Base = 0x20000;
    private const int Page = TypedApiImmediateNeighborhood.PageBytes;
    private const ulong MarkerAddress = Base + 2 * Page + 100;
    private static readonly byte[] PrefixWithObject = Encoding.ASCII.GetBytes("RRAPIVAL2|{");

    [Fact]
    public void Capture_PlausiblePrefixCopiesExactlySevenHashBoundPages()
    {
        var memory = Memory();
        var readCalls = new List<(ulong Address, int Count)>();
        var result = TypedApiImmediateNeighborhood.Capture(TypedApiPrefixMatcher.MarkerText,
            MarkerAddress, Reader(memory, readCalls), () => false,
            utcNow: () => "2026-10-24T18:00:00.0000000Z");

        Assert.Equal("complete", result.Status);
        Assert.Null(result.Reason);
        Assert.Equal($"0x{MarkerAddress:X}", result.MarkerAddress);
        Assert.Equal($"0x{Base:X}", result.WindowStart);
        Assert.Equal(8, readCalls.Count);
        Assert.Equal((MarkerAddress, PrefixWithObject.Length), readCalls[0]);
        Assert.Equal(7, result.Chunks.Count);
        for (var index = 0; index < 7; index++)
        {
            var chunk = result.Chunks[index];
            Assert.Equal($"0x{Base + (ulong)(index * Page):X}", chunk.Address);
            Assert.Equal("success", chunk.Status);
            Assert.Equal(Page, chunk.RequestedByteLength);
            Assert.Equal(Page, chunk.BytesRead);
            Assert.NotNull(chunk.BytesBase64);
            Assert.NotNull(chunk.BytesSha256);
            Assert.Equal(Page, Convert.FromBase64String(chunk.BytesBase64).Length);
            Assert.Equal(64, chunk.BytesSha256.Length);
        }
        Assert.Equal(result.StartedAtUtc, result.CompletedAtUtc);
    }

    [Fact]
    public void Capture_PersistedBinaryMarkerIsRejectedWithoutCopyingPages()
    {
        var memory = Memory();
        memory[(int)(MarkerAddress - Base + (ulong)(PrefixWithObject.Length - 1))] = 0;
        var calls = new List<(ulong, int)>();
        var result = TypedApiImmediateNeighborhood.Capture(TypedApiPrefixMatcher.MarkerText, MarkerAddress, Reader(memory, calls), () => false);

        Assert.Equal("prefix-not-plausible", result.Status);
        Assert.Empty(result.Chunks);
        Assert.Single(calls);
        Assert.Throws<InvalidOperationException>(() => result.ToSnapshotFile(Source(), Identity()));
    }

    [Fact]
    public void Capture_MarkerRelocatedBetweenScanAndReadFailsClosed()
    {
        var memory = Memory();
        memory[(int)(MarkerAddress - Base)] = 0;
        var result = TypedApiImmediateNeighborhood.Capture(TypedApiPrefixMatcher.MarkerText, MarkerAddress, Reader(memory), () => false);

        Assert.Equal("prefix-not-plausible", result.Status);
        Assert.Empty(result.Chunks);
    }

    [Fact]
    public void Capture_CanRecheckPrefixAcrossFourKilobytePageBoundary()
    {
        var memory = Memory();
        Array.Clear(memory, (int)(MarkerAddress - Base), PrefixWithObject.Length);
        var crossing = Base + 3 * Page - 8UL;
        PrefixWithObject.CopyTo(memory.AsSpan((int)(crossing - Base)));
        var result = TypedApiImmediateNeighborhood.Capture(TypedApiPrefixMatcher.MarkerText, crossing, Reader(memory), () => false);

        Assert.Equal("complete", result.Status);
        Assert.Equal(7, result.Chunks.Count);
        Assert.Equal($"0x{Base:X}", result.WindowStart);
    }

    [Fact]
    public void Capture_OneUnreadablePageIsExplicitAndNeverZeroFilled()
    {
        var memory = Memory();
        var unreadable = Base + 3 * Page;
        NativeReadResult Read(ulong address, int count) =>
            address == unreadable && count == Page
                ? new("unavailable", [], 299, "ReadProcessMemory returned no bytes.")
                : Reader(memory)(address, count);

        var result = TypedApiImmediateNeighborhood.Capture(TypedApiPrefixMatcher.MarkerText, MarkerAddress, Read, () => false);
        Assert.Equal("partial", result.Status);
        Assert.Equal(7, result.Chunks.Count);
        var hole = result.Chunks[3];
        Assert.Equal("unavailable", hole.Status);
        Assert.Equal(0, hole.BytesRead);
        Assert.Null(hole.BytesBase64);
        Assert.Null(hole.BytesSha256);
        Assert.Equal(299, hole.Win32ErrorCode);
        Assert.Equal(6, result.Chunks.Count(chunk => chunk.Status == "success"));
        Assert.Equal("partial", result.ToSnapshotFile(Source(), Identity()).Status);
    }

    [Fact]
    public void Capture_TimeBudgetBeforeHeaderDoesNotReadAnything()
    {
        var calls = 0;
        var result = TypedApiImmediateNeighborhood.Capture(TypedApiPrefixMatcher.MarkerText, MarkerAddress,
            (_, _) => { calls++; throw new Exception("must not read"); }, () => true);
        Assert.Equal("time-budget-exceeded", result.Status);
        Assert.Empty(result.Chunks);
        Assert.Equal(0, calls);
        Assert.Throws<InvalidOperationException>(() => result.ToSnapshotFile(Source(), Identity()));
    }

    [Fact]
    public void Capture_ElapsedBudgetRetainsOnlyActuallyReadChunks()
    {
        var memory = Memory();
        var calls = 0;
        NativeReadResult Read(ulong address, int count)
        {
            calls++;
            return Reader(memory)(address, count);
        }
        var result = TypedApiImmediateNeighborhood.Capture(TypedApiPrefixMatcher.MarkerText,
            MarkerAddress, Read, () => calls >= 3);
        Assert.Equal("time-budget-exceeded", result.Status);
        Assert.Equal(3, calls); // one header and two pages
        Assert.Equal(2, result.Chunks.Count);
        Assert.All(result.Chunks, chunk => Assert.Equal("success", chunk.Status));
        Assert.Equal("time-budget-exceeded", result.ToSnapshotFile(Source(), Identity()).Status);
    }

    [Fact]
    public void Capture_RejectsUnsupportedLowAndHighAddresses()
    {
        var read = Reader(Memory());
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            TypedApiImmediateNeighborhood.Capture(TypedApiPrefixMatcher.MarkerText, 0x10000, read, () => false));
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            TypedApiImmediateNeighborhood.Capture(TypedApiPrefixMatcher.MarkerText, TypedApiPrefixScout.MaxUserEnd - 100, read, () => false));
    }

    [Fact]
    public void Capture_RejectsImpossibleReaderByteCounts()
    {
        var header = true;
        NativeReadResult Read(ulong _, int requested)
        {
            if (header)
            {
                header = false;
                return new("success", PrefixWithObject, null, null);
            }
            return new("success", new byte[requested + 1], null, null);
        }
        Assert.Throws<InvalidDataException>(() =>
            TypedApiImmediateNeighborhood.Capture(TypedApiPrefixMatcher.MarkerText, MarkerAddress, Read, () => false));
    }

    [Fact]
    public async Task Capture_ValidSnapshotRoundTripsThroughExistingStrictLoader()
    {
        var result = TypedApiImmediateNeighborhood.Capture(TypedApiPrefixMatcher.MarkerText, MarkerAddress, Reader(Memory()), () => false,
            utcNow: () => "2026-10-24T18:00:00.0000000Z");
        var snapshot = result.ToSnapshotFile(Source(), Identity());
        var path = Path.Combine(Path.GetTempPath(), $"rr2-inline-typed-{Guid.NewGuid():N}.json");
        try
        {
            var bytes = JsonSerializer.SerializeToUtf8Bytes(snapshot, JsonFormat.Options);
            await File.WriteAllBytesAsync(path, bytes);
            var loaded = await NativeMemorySnapshotFile.LoadAsync(path);
            Assert.Equal("complete", loaded.File.Status);
            Assert.Equal(7, loaded.File.Chunks.Count);
            Assert.Empty(loaded.CoverageWarnings);
            Assert.Equal(TypedApiImmediateNeighborhood.WindowBytes,
                Assert.Single(loaded.Snapshot.Segments).Bytes.Length);
        }
        finally
        {
            File.Delete(path);
        }
    }

    [Fact]
    public async Task WindowsSelfProcess_RealReadOnlyScoutCallbackCopiesOwnLiveNativeAllocation()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;

        var allocation = Marshal.AllocHGlobal(TypedApiImmediateNeighborhood.WindowBytes + 2 * Page);
        try
        {
            var baseAddress = checked(((ulong)allocation.ToInt64() + (ulong)(Page - 1)) & ~(ulong)(Page - 1));
            var marker = baseAddress + 2 * Page + 100;
            var bytes = new byte[TypedApiImmediateNeighborhood.WindowBytes];
            Array.Fill(bytes, (byte)0x5A);
            PrefixWithObject.CopyTo(bytes.AsSpan(2 * Page + 100));
            Marshal.Copy(bytes, 0, checked((nint)(long)baseAddress), bytes.Length);

            await using var session = await WindowsNativeMemorySession.OpenAsync(
                Environment.ProcessId, null, null, CancellationToken.None);
            TypedApiImmediateNeighborhoodResult? captured = null;
            var scopedRegions = new[]
            {
                new WindowsMemoryRegion(baseAddress, (ulong)bytes.Length, 4, 0x20000)
            };
            var scout = TypedApiPrefixScout.Scan(TypedApiPrefixMatcher.MarkerText, scopedRegions, baseAddress,
                TypedApiPrefixScout.ChunkBytes, 128, session.ReadScanChunk, () => false,
                onMatch: address => captured = TypedApiImmediateNeighborhood.Capture(TypedApiPrefixMatcher.MarkerText,
                    address, session.Read, () => false));

            Assert.Equal("complete", scout.Status);
            Assert.Equal(marker, Assert.Single(scout.PrefixAddresses));
            Assert.NotNull(captured);
            Assert.Equal("complete", captured.Status);
            var reassembled = captured.Chunks
                .SelectMany(chunk => Convert.FromBase64String(chunk.BytesBase64!))
                .ToArray();
            Assert.Equal(bytes, reassembled);
            Assert.Null(await session.RevalidateAsync(CancellationToken.None));
        }
        finally
        {
            Marshal.FreeHGlobal(allocation);
        }
    }

    private static byte[] Memory()
    {
        var data = new byte[TypedApiImmediateNeighborhood.WindowBytes];
        Array.Fill(data, (byte)0x55);
        PrefixWithObject.CopyTo(data.AsSpan((int)(MarkerAddress - Base)));
        return data;
    }

    private static Func<ulong, int, NativeReadResult> Reader(
        byte[] memory, List<(ulong Address, int Count)>? calls = null) =>
        (address, count) =>
        {
            calls?.Add((address, count));
            var start = checked((int)(address - Base));
            return new("success", memory.AsSpan(start, count).ToArray(), null, null);
        };

    private static NativeMemorySnapshotSource Source() =>
        new("native-memory-snapshot-request/1", new string('A', 64), "producer-declared",
            new("1.0.0.0", "single-file-bundle", null, "probe.exe", new string('B', 64)));

    private static NativeProcessIdentity Identity() =>
        new(42, 639284177321390013, @"C:\RIFT\rift_x64.exe", new string('C', 64), 0x100000, 0x200000);
}
