using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RiftReader2.Infrastructure;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class TypedApiScoutCommandTests
{
    [Fact]
    public async Task ScoutCommand_ReadsExactOwnProcessAndPreservesNoOverwriteReport()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;
        var memory = Marshal.AllocHGlobal(128);
        var directory = NewDirectory();
        try
        {
            var marker = Encoding.ASCII.GetBytes(TypedApiPrefixMatcher.MarkerText);
            Marshal.Copy(marker, 0, memory, marker.Length);
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                Environment.ProcessId, null, null, CancellationToken.None);
            var address = checked((ulong)memory.ToInt64());
            var request = Path.Combine(directory, "scout-request.json");
            var output = Path.Combine(directory, "scout-report.json");
            var requestBytes = Request(session.Identity, Hex(address));
            await File.WriteAllBytesAsync(request, requestBytes);
            var stdout = new StringWriter();
            var stderr = new StringWriter();

            var exit = await NativeCommandRunner.RunAsync(
                ["scout-typed-native", "--request", request, "--output", output], stdout, stderr);

            Assert.True(exit is 0 or 3, stderr.ToString());
            using var report = JsonDocument.Parse(await File.ReadAllBytesAsync(output));
            var root = report.RootElement;
            Assert.Equal("native-typed-prefix-scout/1", root.GetProperty("evidenceKind").GetString());
            Assert.Equal(Hex(address), root.GetProperty("startAddress").GetString());
            Assert.Equal(TypedApiPrefixMatcher.MarkerText, root.GetProperty("marker").GetString());
            Assert.Equal(session.Identity.ProcessId, root.GetProperty("identity").GetProperty("processId").GetInt32());
            Assert.Equal(session.Identity.ProcessStartUtcTicks,
                root.GetProperty("identity").GetProperty("processStartUtcTicks").GetInt64());
            Assert.Equal(Convert.ToHexString(SHA256.HashData(requestBytes)),
                root.GetProperty("requestSha256").GetString());
            Assert.Equal(64, root.GetProperty("coverageContentSha256").GetString()!.Length);
            Assert.Contains(root.GetProperty("prefixAddresses").EnumerateArray(),
                prefix => prefix.GetString() == Hex(address));
            Assert.InRange(root.GetProperty("attemptedBytes").GetInt64(), 1, TypedApiPrefixScout.ChunkBytes);
            Assert.InRange(root.GetProperty("examinedBytes").GetInt64(), 1, TypedApiPrefixScout.ChunkBytes);
            Assert.Equal("committed-readable-nonguard-MEM_PRIVATE-at-or-after-startAddress",
                root.GetProperty("scope").GetString());
            Assert.True(root.GetProperty("coveredSpans").GetArrayLength() > 0);
            Assert.True(root.GetProperty("implementation").GetProperty("deploymentKind").GetString() is
                "assembly-files" or "single-file-bundle");

            var original = await File.ReadAllBytesAsync(output);
            Assert.Equal(2, await NativeCommandRunner.RunAsync(
                ["scout-typed-native", "--request", request, "--output", output],
                TextWriter.Null, TextWriter.Null));
            Assert.Equal(original, await File.ReadAllBytesAsync(output));
        }
        finally
        {
            Marshal.FreeHGlobal(memory);
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public async Task ScoutCommand_RejectsWrongEpochWithoutReadingOrPublishing()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;
        var directory = NewDirectory();
        try
        {
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                Environment.ProcessId, null, null, CancellationToken.None);
            var request = Path.Combine(directory, "wrong-epoch.json");
            var output = Path.Combine(directory, "unwritten.json");
            await File.WriteAllBytesAsync(request, Request(
                session.Identity with { ProcessStartUtcTicks = session.Identity.ProcessStartUtcTicks + 1 },
                "0x10000"));

            Assert.Equal(2, await NativeCommandRunner.RunAsync(
                ["scout-typed-native", "--request", request, "--output", output],
                TextWriter.Null, TextWriter.Null));
            Assert.False(File.Exists(output));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public async Task ScoutCommand_RejectsOutOfScopePlansBeforeOpeningProcess()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;
        var directory = NewDirectory();
        try
        {
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                Environment.ProcessId, null, null, CancellationToken.None);
            var badPlans = new[]
            {
                Request(session.Identity, "0xdeadbeef"),
                Request(session.Identity, "0x8000"),
                Request(session.Identity, "0x10000", maxBytes: 1),
                Request(session.Identity, "0x10000", maxBytes: TypedApiPrefixScout.MaxScanBytes + 1),
                Request(session.Identity, "0x10000", maxMatches: 129),
                Request(session.Identity, "0x10000", maxRegions: 32769),
                Request(session.Identity, "0x10000", maxMilliseconds: 30001),
                Request(session.Identity, "0x10000", evidenceKind: "native-memory-map-request/1")
            };
            for (var i = 0; i < badPlans.Length; i++)
            {
                var request = Path.Combine(directory, $"invalid-{i}.json");
                var output = Path.Combine(directory, $"should-not-exist-{i}.json");
                await File.WriteAllBytesAsync(request, badPlans[i]);

                Assert.Equal(2, await NativeCommandRunner.RunAsync(
                    ["scout-typed-native", "--request", request, "--output", output],
                    TextWriter.Null, TextWriter.Null));
                Assert.False(File.Exists(output));
            }
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public async Task Help_AdvertisesVersionedScoutCommand()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;
        var output = new StringWriter();

        Assert.Equal(0, await NativeCommandRunner.RunAsync(["help"], output, TextWriter.Null));
        Assert.Contains("scout-typed-native --request PATH --output PATH", output.ToString(),
            StringComparison.Ordinal);
    }

    private static byte[] Request(
        RiftReader2.Domain.NativeProcessIdentity identity,
        string startAddress,
        long maxBytes = TypedApiPrefixScout.ChunkBytes,
        int maxMilliseconds = 10_000,
        int maxRegions = 32_768,
        int maxMatches = 128,
        string evidenceKind = "native-typed-prefix-scout-request/1") =>
        JsonSerializer.SerializeToUtf8Bytes(new
        {
            schemaVersion = 1,
            evidenceKind,
            target = new
            {
                processId = identity.ProcessId,
                processStartUtcTicks = identity.ProcessStartUtcTicks,
                executableSha256 = identity.ExecutableSha256
            },
            startAddress,
            maxScanBytes = maxBytes,
            maxDurationMilliseconds = maxMilliseconds,
            maxRegionCount = maxRegions,
            maxMatchCount = maxMatches
        }, JsonFormat.Options);

    private static string Hex(ulong address) => $"0x{address:X}";

    private static string NewDirectory()
    {
        var directory = Path.Combine(Path.GetTempPath(), $"rr2-prefix-scout-{Guid.NewGuid():N}");
        Directory.CreateDirectory(directory);
        return directory;
    }
}
