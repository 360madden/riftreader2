using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Cli;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Tests;

public sealed class MemoryDiscoveryCliTests
{
    [Fact]
    public async Task PatternSearchJoinsAdjacentSuccessesButNeverBridgesAHole()
    {
        using var fixture = new SnapshotFixture();
        var snapshot = await fixture.WriteAsync("partial", "one range was unavailable",
            Chunk(0x10000, [0xAA]),
            Chunk(0x10001, [0xBB]),
            new("0x10002", 1, "unavailable", 0, null, null, 299, "unmapped"),
            Chunk(0x10003, [0xCC]));

        using var adjacentOutput = new StringWriter();
        Assert.Equal(0, await CliRunner.RunAsync(
            ["find-pattern", "--snapshot", snapshot, "--pattern", "AA BB"], adjacentOutput, new StringWriter()));
        using var adjacent = JsonDocument.Parse(adjacentOutput.ToString());
        var root = adjacent.RootElement;
        Assert.Equal("0x10000", root.GetProperty("result").GetProperty("matches")[0].GetProperty("address").GetString());
        Assert.Contains("did not complete", root.GetProperty("coverageWarnings")[0].GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.Equal(Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(snapshot))),
            root.GetProperty("inputs")[0].GetProperty("snapshotSha256").GetString());

        using var holeOutput = new StringWriter();
        Assert.Equal(0, await CliRunner.RunAsync(
            ["find-pattern", "--snapshot", snapshot, "--pattern", "BB CC"], holeOutput, new StringWriter()));
        using var hole = JsonDocument.Parse(holeOutput.ToString());
        Assert.Empty(hole.RootElement.GetProperty("result").GetProperty("matches").EnumerateArray());
    }

    [Fact]
    public async Task TamperedChunkHashFailsBeforePublishing()
    {
        using var fixture = new SnapshotFixture();
        var snapshot = await fixture.WriteAsync("complete", null, Chunk(0x10000, [1, 2, 3, 4]));
        var json = await File.ReadAllTextAsync(snapshot);
        await File.WriteAllTextAsync(snapshot, json.Replace("AQIDBA==", "AQIDBQ==", StringComparison.Ordinal));
        var report = Path.Combine(fixture.DirectoryPath, "report.json");
        using var error = new StringWriter();

        Assert.Equal(2, await CliRunner.RunAsync(
            ["search-memory", "--snapshot", snapshot, "--type", "int32", "--value", "67305985", "--output", report],
            new StringWriter(), error));
        Assert.False(File.Exists(report));
        Assert.Contains("SHA-256", error.ToString());
    }

    [Fact]
    public async Task IdentityInvalidatedBytesAreRetainedButCannotBeSearched()
    {
        using var fixture = new SnapshotFixture();
        var snapshot = await fixture.WriteAsync("identity-invalidated", "process restarted", Chunk(0x10000, [1, 2, 3, 4]));
        var loaded = await NativeMemorySnapshotFile.LoadAsync(snapshot);
        Assert.Empty(loaded.Snapshot.Segments);
        Assert.Contains(loaded.CoverageWarnings, warning => warning.Contains("No bytes are analyzable", StringComparison.Ordinal));
        using var error = new StringWriter();

        Assert.Equal(2, await CliRunner.RunAsync(
            ["search-memory", "--snapshot", snapshot, "--type", "int32", "--value", "67305985"],
            new StringWriter(), error));
        Assert.Contains("identity was invalidated", error.ToString());
    }

    [Theory]
    [InlineData("partial")]
    [InlineData("unavailable")]
    public async Task SingleIncompleteContextSnapshotIsFailedWithoutAnalyzableBytes(string chunkStatus)
    {
        using var fixture = new SnapshotFixture();
        var partialBytes = new byte[] { 0xAA };
        var chunk = chunkStatus == "partial"
            ? new NativeMemorySnapshotChunk("0x10000", 4, "partial", 1,
                Convert.ToBase64String(partialBytes),
                Convert.ToHexString(SHA256.HashData(partialBytes)), 299, "short read")
            : new NativeMemorySnapshotChunk("0x10000", 4, "unavailable", 0,
                null, null, 299, "not readable");
        var snapshot = await fixture.WriteAsync("failed", "No complete context chunk", chunk);
        var loaded = await NativeMemorySnapshotFile.LoadAsync(snapshot);
        Assert.Equal("failed", loaded.File.Status);
        Assert.Equal(chunkStatus, Assert.Single(loaded.File.Chunks).Status);
        if (chunkStatus == "partial")
            Assert.Equal(Convert.ToBase64String(partialBytes), loaded.File.Chunks[0].BytesBase64);
        Assert.Empty(loaded.Snapshot.Segments);
        Assert.Contains(loaded.CoverageWarnings,
            warning => warning.Contains("overall status is 'failed'", StringComparison.Ordinal));
    }

    [Fact]
    public async Task PointerCandidatesUseModuleRvaAndExistingOutputIsPreserved()
    {
        using var fixture = new SnapshotFixture();
        var bytes = BitConverter.GetBytes(0x20000UL);
        var snapshot = await fixture.WriteAsync("complete", null, Chunk(0x10000, bytes));
        var report = Path.Combine(fixture.DirectoryPath, "pointers.json");
        using var first = new StringWriter();
        Assert.Equal(0, await CliRunner.RunAsync(
            ["find-pointers", "--snapshot", snapshot, "--target", "0x20000", "--max-depth", "1", "--max-offset", "0", "--output", report],
            first, new StringWriter()));
        using var parsed = JsonDocument.Parse(first.ToString());
        var chain = parsed.RootElement.GetProperty("result").GetProperty("chains")[0];
        Assert.Equal("0x0", chain.GetProperty("rootRva").GetString());
        Assert.Equal("0x0", chain.GetProperty("offsets")[0].GetString());
        var retained = await File.ReadAllBytesAsync(report);

        Assert.Equal(2, await CliRunner.RunAsync(
            ["find-pointers", "--snapshot", snapshot, "--target", "0x20000", "--max-depth", "1", "--max-offset", "0", "--output", report],
            new StringWriter(), new StringWriter()));
        Assert.Equal(retained, await File.ReadAllBytesAsync(report));
    }

    private static NativeMemorySnapshotChunk Chunk(ulong address, byte[] bytes) => new(
        $"0x{address:X}", bytes.Length, "success", bytes.Length, Convert.ToBase64String(bytes),
        Convert.ToHexString(SHA256.HashData(bytes)), null, null);

    private sealed class SnapshotFixture : IDisposable
    {
        public string DirectoryPath { get; } = Path.Combine(Path.GetTempPath(), "rr2-memory-cli-" + Guid.NewGuid().ToString("N"));

        public SnapshotFixture() => Directory.CreateDirectory(DirectoryPath);

        public async Task<string> WriteAsync(string status, string? reason, params NativeMemorySnapshotChunk[] chunks)
        {
            var file = new NativeMemorySnapshotFile(
                1, "native-memory-snapshot/1",
                new("native-memory-snapshot-request/1", new string('A', 64), "producer-declared",
                    new("test", "assembly-files", new Dictionary<string, string> { ["test"] = new string('B', 64) }, null, null)),
                new(42, 638964000000000000, @"C:\RIFT\rift_x64.exe", new string('C', 64), 0x10000, 0x1000),
                "2026-10-19T12:00:00Z", "2026-10-19T12:00:01Z", status, reason, chunks, ["test fixture"]);
            var path = Path.Combine(DirectoryPath, "snapshot-" + Guid.NewGuid().ToString("N") + ".json");
            await File.WriteAllTextAsync(path, JsonSerializer.Serialize(file, JsonFormat.Options));
            return path;
        }

        public void Dispose() => Directory.Delete(DirectoryPath, recursive: true);
    }
}
