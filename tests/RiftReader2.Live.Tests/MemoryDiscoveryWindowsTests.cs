using System.Runtime.InteropServices;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live.Tests;

public sealed class MemoryDiscoveryWindowsTests
{
    [Fact]
    public async Task SnapshotCommand_ReadsKnownAllocatedBytesInExplicitChunks()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;
        var memory = Marshal.AllocHGlobal(5000);
        var directory = CreateDirectory();
        try
        {
            for (var index = 0; index < 5000; index++)
                Marshal.WriteByte(memory, index, (byte)(index % 251));
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                Environment.ProcessId, null, null, CancellationToken.None);
            var requestPath = Path.Combine(directory, "request.json");
            var outputPath = Path.Combine(directory, "snapshot.json");
            await File.WriteAllTextAsync(requestPath, JsonSerializer.Serialize(new
            {
                schemaVersion = 1,
                evidenceKind = "native-memory-snapshot-request/1",
                target = Target(session.Identity),
                maxDurationMilliseconds = 5000,
                ranges = new[]
                {
                    new
                    {
                        addressKind = "absolute-session-address",
                        address = Hex(checked((ulong)memory.ToInt64())),
                        byteLength = 5000
                    }
                }
            }, JsonFormat.Options));

            var exit = await NativeCommandRunner.RunAsync(
                ["snapshot-native", "--request", requestPath, "--output", outputPath],
                TextWriter.Null, TextWriter.Null);

            Assert.Equal(0, exit);
            var loaded = await NativeMemorySnapshotFile.LoadAsync(outputPath);
            Assert.Equal("complete", loaded.File.Status);
            Assert.Equal(2, loaded.File.Chunks.Count);
            var segment = Assert.Single(loaded.Snapshot.Segments);
            Assert.Equal(5000, segment.Bytes.Length);
            Assert.Equal((byte)0, segment.Bytes[0]);
            Assert.Equal((byte)(4999 % 251), segment.Bytes[^1]);
        }
        finally
        {
            Marshal.FreeHGlobal(memory);
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public async Task PointerResolver_FollowsKnownAllocatedChainThroughWindowsReadHandle()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;
        var root = Marshal.AllocHGlobal(8);
        var middle = Marshal.AllocHGlobal(8);
        var terminal = Marshal.AllocHGlobal(16);
        try
        {
            Marshal.WriteInt64(root, middle.ToInt64());
            Marshal.WriteInt64(middle, terminal.ToInt64());
            Marshal.WriteInt32(terminal, 4, unchecked((int)0x78563412));
            await using var native = await WindowsNativeMemorySession.OpenAsync(
                Environment.ProcessId, null, null, CancellationToken.None);
            var rootAddress = checked((ulong)root.ToInt64());
            var expected = native.Identity with { ModuleBaseAddress = rootAddress, ModuleSize = 8 };
            await using var session = new IdentityViewSession(native, expected);

            var result = await MemoryDiscovery.ResolvePointerChainAsync(
                new(0, [0, 4]), expected, session, 4, CancellationToken.None);

            Assert.Equal("complete", result.Status);
            Assert.Equal(2, result.Hops.Count);
            Assert.Equal(checked((ulong)terminal.ToInt64() + 4), result.TerminalAddress);
            Assert.Equal([0x12, 0x34, 0x56, 0x78], result.TerminalRead!.Bytes);
        }
        finally
        {
            Marshal.FreeHGlobal(root);
            Marshal.FreeHGlobal(middle);
            Marshal.FreeHGlobal(terminal);
        }
    }

    [Fact]
    public async Task SnapshotCommand_RejectsWrongProcessEpochWithoutPublishing()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;
        var directory = CreateDirectory();
        try
        {
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                Environment.ProcessId, null, null, CancellationToken.None);
            var requestPath = Path.Combine(directory, "wrong-epoch.json");
            var outputPath = Path.Combine(directory, "snapshot.json");
            await File.WriteAllTextAsync(requestPath, JsonSerializer.Serialize(new
            {
                schemaVersion = 1,
                evidenceKind = "native-memory-snapshot-request/1",
                target = new
                {
                    processId = session.Identity.ProcessId,
                    processStartUtcTicks = session.Identity.ProcessStartUtcTicks + 1,
                    executableSha256 = session.Identity.ExecutableSha256
                },
                maxDurationMilliseconds = 5000,
                ranges = new[]
                {
                    new { addressKind = "module-relative-rva", address = "0x0", byteLength = 2 }
                }
            }, JsonFormat.Options));

            Assert.Equal(2, await NativeCommandRunner.RunAsync(
                ["snapshot-native", "--request", requestPath, "--output", outputPath],
                TextWriter.Null, TextWriter.Null));
            Assert.False(File.Exists(outputPath));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public async Task MapCommand_UsesExactSessionAndIncludesKnownAllocation()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;
        var memory = Marshal.AllocHGlobal(16);
        var directory = CreateDirectory();
        try
        {
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                Environment.ProcessId, null, null, CancellationToken.None);
            var requestPath = Path.Combine(directory, "map-request.json");
            var outputPath = Path.Combine(directory, "map.json");
            await File.WriteAllTextAsync(requestPath, JsonSerializer.Serialize(new
            {
                schemaVersion = 1,
                evidenceKind = "native-memory-map-request/1",
                target = Target(session.Identity),
                maxRegionCount = 32768,
                maxDurationMilliseconds = 5000
            }, JsonFormat.Options));
            var address = checked((ulong)memory.ToInt64());

            Assert.Equal(0, await NativeCommandRunner.RunAsync(
                ["map-native", "--request", requestPath, "--output", outputPath],
                TextWriter.Null, TextWriter.Null));
            using var report = JsonDocument.Parse(await File.ReadAllBytesAsync(outputPath));
            Assert.Equal("complete", report.RootElement.GetProperty("status").GetString());
            Assert.Contains(report.RootElement.GetProperty("regions").EnumerateArray(), region =>
            {
                var start = Convert.ToUInt64(region.GetProperty("baseAddress").GetString()![2..], 16);
                var size = region.GetProperty("regionSize").GetUInt64();
                return address >= start && address < checked(start + size);
            });
            var original = await File.ReadAllBytesAsync(outputPath);
            Assert.Equal(2, await NativeCommandRunner.RunAsync(
                ["map-native", "--request", requestPath, "--output", outputPath],
                TextWriter.Null, TextWriter.Null));
            Assert.Equal(original, await File.ReadAllBytesAsync(outputPath));
        }
        finally
        {
            Marshal.FreeHGlobal(memory);
            Directory.Delete(directory, recursive: true);
        }
    }

    private static object Target(NativeProcessIdentity identity) => new
    {
        processId = identity.ProcessId,
        processStartUtcTicks = identity.ProcessStartUtcTicks,
        executableSha256 = identity.ExecutableSha256
    };

    private static string Hex(ulong value) => $"0x{value:X}";

    private static string CreateDirectory()
    {
        var path = Path.Combine(Path.GetTempPath(), $"rr2-memory-{Guid.NewGuid():N}");
        Directory.CreateDirectory(path);
        return path;
    }

    private sealed class IdentityViewSession(
        WindowsNativeMemorySession inner,
        NativeProcessIdentity identity) : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; } = identity;

        public NativeReadResult Read(ulong address, int byteLength) => inner.Read(address, byteLength);

        public ValueTask<string?> RevalidateAsync(CancellationToken cancellationToken) =>
            inner.RevalidateAsync(cancellationToken);

        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
