using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class TypedApiScoutCopyCommandTests
{
    [Theory]
    [InlineData("RRAPIVAL2|")]
    [InlineData("RR2R1|")]
    public async Task ScoutCopy_WindowsSelfProcessPublishesStrictSnapshotsAndRejectsOverwrite(string selectedMarker)
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;

        var bytes = new byte[TypedApiPrefixScout.ChunkBytes + 8192];
        Array.Fill(bytes, (byte)0x61);
        const int markerOffset = 2 * TypedApiImmediateNeighborhood.PageBytes + 100;
        var marker = Encoding.ASCII.GetBytes(selectedMarker + "{");
        marker.CopyTo(bytes.AsSpan(markerOffset));
        var allocation = Marshal.AllocHGlobal(bytes.Length + TypedApiImmediateNeighborhood.PageBytes);
        var root = Path.Combine(Path.GetTempPath(), $"rr2-copy-command-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        try
        {
            var aligned = checked(((ulong)allocation.ToInt64() +
                (ulong)(TypedApiImmediateNeighborhood.PageBytes - 1)) &
                ~(ulong)(TypedApiImmediateNeighborhood.PageBytes - 1));
            Marshal.Copy(bytes, 0, checked((nint)(long)aligned), bytes.Length);
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                Environment.ProcessId, null, null, CancellationToken.None);
            var target = new NativeCaptureTarget(
                session.Identity.ProcessId,
                session.Identity.ProcessStartUtcTicks,
                session.Identity.ExecutableSha256);
            var requestPath = Path.Combine(root, "scout-request.json");
            var request = new
            {
                schemaVersion = 1,
                evidenceKind = "native-typed-inline-capture-request/1",
                target,
                startAddress = $"0x{aligned:X}",
                maxScanBytes = TypedApiPrefixScout.ChunkBytes,
                maxDurationMilliseconds = 20_000,
                maxRegionCount = 32_768,
                maxMatchCount = 8,
                maxCopiedCandidates = 2
            };
            var requestNode = JsonSerializer.SerializeToNode(request, JsonFormat.Options)!;
            requestNode["marker"] = selectedMarker;
            await File.WriteAllTextAsync(requestPath, requestNode.ToJsonString(JsonFormat.Options));
            var outputDirectory = Path.Combine(root, "trial-01");
            var stdout = new StringWriter();
            var stderr = new StringWriter();

            var exit = await NativeCommandRunner.RunAsync(
                ["scout-copy-typed-native", "--request", requestPath, "--output", outputDirectory],
                stdout, stderr);

            Assert.True(exit is 0 or 3, stderr.ToString());
            Assert.True(Directory.Exists(outputDirectory));
            Assert.True(File.Exists(Path.Combine(outputDirectory, "index.json")));
            using var manifest = JsonDocument.Parse(await File.ReadAllBytesAsync(
                Path.Combine(outputDirectory, "index.json")));
            Assert.Equal(selectedMarker, manifest.RootElement.GetProperty("marker").GetString());
            var rootJson = manifest.RootElement;
            Assert.Equal("native-typed-inline-capture/1",
                rootJson.GetProperty("evidenceKind").GetString());
            Assert.Equal(session.Identity.ProcessId,
                rootJson.GetProperty("identity").GetProperty("processId").GetInt32());
            var candidate = rootJson.GetProperty("candidates").EnumerateArray()
                .First(entry => entry.GetProperty("markerAddress").GetString() ==
                    $"0x{aligned + markerOffset:X}");
            Assert.Equal("complete", candidate.GetProperty("status").GetString());
            Assert.True(rootJson.GetProperty("publishedSnapshots").GetInt32() >= 1);

            var snapshotName = candidate.GetProperty("snapshotFile").GetString()!;
            var sourceName = candidate.GetProperty("requestFile").GetString()!;
            var sourceFile = Path.Combine(outputDirectory, sourceName);
            var snapshotFile = Path.Combine(outputDirectory, snapshotName);
            var rawSource = await File.ReadAllBytesAsync(sourceFile);
            var rawSnapshot = await File.ReadAllBytesAsync(snapshotFile);
            Assert.Equal(Convert.ToHexString(SHA256.HashData(rawSource)),
                candidate.GetProperty("requestSha256").GetString());
            Assert.Equal(Convert.ToHexString(SHA256.HashData(rawSnapshot)),
                candidate.GetProperty("snapshotSha256").GetString());
            var loaded = await NativeMemorySnapshotFile.LoadAsync(snapshotFile);
            Assert.Equal("complete", loaded.File.Status);
            Assert.Equal(7, loaded.File.Chunks.Count);
            Assert.Equal(Convert.ToHexString(SHA256.HashData(rawSource)),
                loaded.File.Source.RequestSha256);
            var reconstructed = loaded.File.Chunks
                .SelectMany(chunk => Convert.FromBase64String(chunk.BytesBase64!)).ToArray();
            Assert.Equal(bytes.AsSpan(0, TypedApiImmediateNeighborhood.WindowBytes).ToArray(),
                reconstructed);

            // Files and directory remain byte-identical after an attempted replay.
            var originalIndex = await File.ReadAllBytesAsync(Path.Combine(outputDirectory, "index.json"));
            stdout.GetStringBuilder().Clear();
            stderr.GetStringBuilder().Clear();
            var replayExit = await NativeCommandRunner.RunAsync(
                ["scout-copy-typed-native", "--request", requestPath, "--output", outputDirectory],
                stdout, stderr);
            Assert.Equal(2, replayExit);
            Assert.Contains("already exists", stderr.ToString(), StringComparison.OrdinalIgnoreCase);
            Assert.Equal(originalIndex,
                await File.ReadAllBytesAsync(Path.Combine(outputDirectory, "index.json")));
            Assert.Equal(selectedMarker, manifest.RootElement.GetProperty("marker").GetString());
            Assert.Null(await session.RevalidateAsync(CancellationToken.None));
        }
        finally
        {
            Marshal.FreeHGlobal(allocation);
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task ScoutCopy_RejectsUnsupportedRequestBeforePublishingDirectory()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;
        var root = Path.Combine(Path.GetTempPath(), $"rr2-copy-invalid-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        try
        {
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                Environment.ProcessId, null, null, CancellationToken.None);
            var target = new NativeCaptureTarget(
                session.Identity.ProcessId,
                session.Identity.ProcessStartUtcTicks + 1,
                session.Identity.ExecutableSha256);
            var request = new
            {
                schemaVersion = 1,
                evidenceKind = "native-typed-inline-capture-request/1",
                target,
                startAddress = "0x10000",
                maxScanBytes = TypedApiPrefixScout.ChunkBytes,
                maxDurationMilliseconds = 5000,
                maxRegionCount = 32768,
                maxMatchCount = 8,
                maxCopiedCandidates = 1,
                marker = "RR2R1|"
            };
            var requestPath = Path.Combine(root, "invalid.json");
            var requestNode = JsonSerializer.SerializeToNode(request, JsonFormat.Options)!;
            await File.WriteAllTextAsync(requestPath, requestNode.ToJsonString(JsonFormat.Options));
            var outputDirectory = Path.Combine(root, "should-not-exist");
            var stdout = new StringWriter();
            var stderr = new StringWriter();

            var exit = await NativeCommandRunner.RunAsync(
                ["scout-copy-typed-native", "--request", requestPath, "--output", outputDirectory],
                stdout, stderr);

            Assert.Equal(2, exit);
            Assert.Contains("start identity", stderr.ToString(), StringComparison.OrdinalIgnoreCase);
            Assert.False(Directory.Exists(outputDirectory));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }
}
