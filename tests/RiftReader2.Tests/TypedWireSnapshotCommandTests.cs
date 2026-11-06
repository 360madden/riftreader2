using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RiftReader2.Cli;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Tests;

public sealed class TypedWireSnapshotCommandTests
{
    private static readonly string[] NumberFields =
        ["coordX", "coordY", "coordZ", "health", "healthMax", "mana", "manaMax", "power", "combo", "planar", "planarMax"];
    private static readonly string[] BooleanFields = ["combat", "dead", "mounted"];

    [Fact]
    public async Task AdvancingFramesAcrossChunksAndHeapRelocationAreScopeLimited()
    {
        using var fixture = new Fixture();
        var firstWire = Wire(100, 20.5, "player-1", 123.25);
        var secondWire = Wire(103, 23.0, "player-1", 130.75);
        var before = await fixture.WriteAsync(
            [Chunk(0x10000, firstWire[..42]), Chunk(0x1002A, firstWire[42..])]);
        var after = await fixture.WriteAsync(
            [Chunk(0x25000, secondWire)], later: true);
        var (code, result, error) = await RunAsync(before, after);
        Assert.Equal(0, code);
        Assert.Empty(error);
        using var report = JsonDocument.Parse(result);
        var root = report.RootElement;
        Assert.Equal("advanced-in-covered-scope", root.GetProperty("status").GetString());
        Assert.Equal(3, root.GetProperty("advances").GetProperty("sequenceDelta").GetInt64());
        Assert.Equal(2.5, root.GetProperty("advances").GetProperty("frameTimeDelta").GetDouble());
        Assert.Equal("0x10000", root.GetProperty("selected").GetProperty("before").GetProperty("address").GetString());
        Assert.Equal("0x25000", root.GetProperty("selected").GetProperty("after").GetProperty("address").GetString());
        Assert.Equal(130.75, root.GetProperty("selected").GetProperty("after").GetProperty("xyz").GetProperty("x").GetDouble());
        Assert.Equal(1, root.GetProperty("source").GetProperty("before").GetProperty("completeCandidateCount").GetInt32());
        Assert.Equal(0, root.GetProperty("source").GetProperty("before").GetProperty("incompleteFragmentCount").GetInt32());
        Assert.Contains("scope-limited", root.GetProperty("limitations")[1].GetString());
    }

    [Fact]
    public async Task DuplicateJsonPropertyInCompleteFrameBlocksPublicationClaim()
    {
        using var fixture = new Fixture();
        var altered = Encoding.UTF8.GetString(Wire(100, 10, "player-1"))
            .Replace("\"sequence\":100", "\"sequence\":100,\"sequence\":101", StringComparison.Ordinal);
        var before = await fixture.WriteAsync([Chunk(0x10000, Encoding.UTF8.GetBytes(altered))]);
        var after = await fixture.WriteAsync([Chunk(0x10000, Wire(102, 12, "player-1"))], later: true);
        var (_, json, _) = await RunAsync(before, after);
        using var doc = JsonDocument.Parse(json);
        Assert.Equal("blocked", doc.RootElement.GetProperty("status").GetString());
        Assert.Equal("before:malformed-complete-frame", doc.RootElement.GetProperty("reason").GetString());
        Assert.Equal("json-duplicate-key",
            doc.RootElement.GetProperty("source").GetProperty("before").GetProperty("candidates")[0].GetProperty("reason").GetString());
    }

    [Fact]
    public async Task DifferentContentsAtLatestSameSequenceAndClockBlock()
    {
        using var fixture = new Fixture();
        var two = Wire(100, 10, "player-1", 111.5)
            .Concat(new byte[] { 0 })
            .Concat(Wire(100, 10, "player-1", 222.5))
            .ToArray();
        var before = await fixture.WriteAsync(Chunks(0x10000, two));
        var after = await fixture.WriteAsync([Chunk(0x30000, Wire(105, 15, "player-1"))], later: true);
        var (_, json, _) = await RunAsync(before, after);
        using var doc = JsonDocument.Parse(json);
        Assert.Equal("blocked", doc.RootElement.GetProperty("status").GetString());
        Assert.Equal("before:conflicting-latest-frames", doc.RootElement.GetProperty("reason").GetString());
    }

    [Fact]
    public async Task HoleBetweenChunksNeverBecomesACompleteWire()
    {
        using var fixture = new Fixture();
        var wire = Wire(100, 10, "player-1");
        var firstHalf = wire.Length / 2;
        var first = Chunk(0x10000, wire[..firstHalf]);
        var gapAddress = 0x10000UL + (ulong)firstHalf;
        var gap = new NativeMemorySnapshotChunk($"0x{gapAddress:X}", 1, "unavailable", 0, null, null, 299, "gap");
        var last = Chunk(gapAddress + 1, wire[firstHalf..]);
        var before = await fixture.WriteAsync([first, gap, last], "partial", "one gap");
        var after = await fixture.WriteAsync([Chunk(0x10000, Wire(103, 13, "player-1"))], later: true);
        var (_, json, _) = await RunAsync(before, after);
        using var doc = JsonDocument.Parse(json);
        Assert.Equal("blocked", doc.RootElement.GetProperty("status").GetString());
        Assert.Equal("before:incomplete-typed-fragment-in-covered-scope", doc.RootElement.GetProperty("reason").GetString());
        Assert.True(doc.RootElement.GetProperty("source").GetProperty("before").GetProperty("incompleteFragmentCount").GetInt32() > 0);
        Assert.True(doc.RootElement.GetProperty("coverageWarnings").GetArrayLength() > 0);
    }

    [Fact]
    public async Task IncompleteFragmentAlongsideValidFrameStillBlocksClaim()
    {
        using var fixture = new Fixture();
        var truncated = Wire(110, 11, "player-1");
        var mixed = Wire(100, 10, "player-1")
            .Concat(truncated[..(truncated.Length / 3)]).ToArray();
        var before = await fixture.WriteAsync([Chunk(0x10000, mixed)]);
        var after = await fixture.WriteAsync([Chunk(0x25000, Wire(115, 16, "player-1"))], later: true);
        var (_, json, _) = await RunAsync(before, after);
        using var doc = JsonDocument.Parse(json);
        Assert.Equal("blocked", doc.RootElement.GetProperty("status").GetString());
        Assert.Equal("before:incomplete-typed-fragment-in-covered-scope",
            doc.RootElement.GetProperty("reason").GetString());
        Assert.Equal(1, doc.RootElement.GetProperty("source").GetProperty("before").GetProperty("completeCandidateCount").GetInt32());
    }

    [Theory]
    [InlineData(100, 10.0)]
    [InlineData(101, 10.0)]
    [InlineData(100, 11.0)]
    [InlineData(99, 9.0)]
    public async Task SourceRequiresBothSequenceAndFrameClockAdvance(long secondSeq, double secondClock)
    {
        using var fixture = new Fixture();
        var before = await fixture.WriteAsync([Chunk(0x10000, Wire(100, 10, "player-1"))]);
        var after = await fixture.WriteAsync([Chunk(0x25000, Wire(secondSeq, secondClock, "player-1"))], later: true);
        var (_, json, _) = await RunAsync(before, after);
        using var doc = JsonDocument.Parse(json);
        Assert.Equal("blocked", doc.RootElement.GetProperty("status").GetString());
        Assert.Equal("source-clock-or-sequence-not-advanced", doc.RootElement.GetProperty("reason").GetString());
    }

    [Fact]
    public async Task PlayerIdentityMustRemainSame()
    {
        using var fixture = new Fixture();
        var before = await fixture.WriteAsync([Chunk(0x10000, Wire(100, 10, "player-1"))]);
        var after = await fixture.WriteAsync([Chunk(0x25000, Wire(102, 12, "player-2"))], later: true);
        var (_, json, _) = await RunAsync(before, after);
        using var doc = JsonDocument.Parse(json);
        Assert.Equal("blocked", doc.RootElement.GetProperty("status").GetString());
        Assert.Equal("player-identity-changed", doc.RootElement.GetProperty("reason").GetString());
    }

    [Fact]
    public async Task WrongProcessEpochFailsBeforeReportPublication()
    {
        using var fixture = new Fixture();
        var before = await fixture.WriteAsync([Chunk(0x10000, Wire(100, 10, "player-1"))]);
        var after = await fixture.WriteAsync([Chunk(0x20000, Wire(102, 12, "player-1"))],
            later: true, identity: Fixture.Identity with { ProcessId = 43 });
        var dest = Path.Combine(fixture.DirectoryPath, "not-published.json");
        var (code, output, error) = await RunAsync(before, after, dest);
        Assert.Equal(2, code);
        Assert.Empty(output);
        Assert.Contains("same process", error, StringComparison.OrdinalIgnoreCase);
        Assert.False(File.Exists(dest));
    }

    [Fact]
    public async Task IdentityInvalidatedSnapshotRefusesAllBytes()
    {
        using var fixture = new Fixture();
        var before = await fixture.WriteAsync([Chunk(0x10000, Wire(100, 10, "player-1"))],
            "identity-invalidated", "process changed");
        var after = await fixture.WriteAsync([Chunk(0x20000, Wire(102, 12, "player-1"))], later: true);
        var (code, _, error) = await RunAsync(before, after);
        Assert.Equal(2, code);
        Assert.Contains("Identity-invalidated", error);
    }

    [Fact]
    public async Task NativeChunkChecksumMustBeAuthentic()
    {
        using var fixture = new Fixture();
        var before = await fixture.WriteAsync([Chunk(0x10000, Wire(100, 10, "player-1"))]);
        var validBytes = Wire(102, 12, "player-1");
        var after = await fixture.WriteAsync([Chunk(0x20000, validBytes)], later: true);
        var corruptedBytes = validBytes.ToArray();
        corruptedBytes[0] ^= 1;
        var snapshot = await File.ReadAllTextAsync(after);
        var tampered = snapshot.Replace(Convert.ToBase64String(validBytes), Convert.ToBase64String(corruptedBytes), StringComparison.Ordinal);
        Assert.NotEqual(snapshot, tampered);
        await File.WriteAllTextAsync(after, tampered);
        var (code, _, error) = await RunAsync(before, after);
        Assert.Equal(2, code);
        Assert.Contains("SHA-256", error);
    }

    [Fact]
    public async Task OutputIsNoOverwriteEvenWhenFramesAdvance()
    {
        using var fixture = new Fixture();
        var before = await fixture.WriteAsync([Chunk(0x10000, Wire(100, 10, "player-1"))]);
        var after = await fixture.WriteAsync([Chunk(0x20000, Wire(102, 12, "player-1"))], later: true);
        var destination = Path.Combine(fixture.DirectoryPath, "protected.json");
        await File.WriteAllTextAsync(destination, "preserve-me");
        var (code, _, error) = await RunAsync(before, after, destination);
        Assert.Equal(2, code);
        Assert.Contains("exist", error, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("preserve-me", await File.ReadAllTextAsync(destination));
    }

    [Fact]
    public async Task CandidateLimitFailsClosed()
    {
        using var fixture = new Fixture();
        var repeated = Enumerable.Repeat(Wire(100, 10, "player-1"), 130).SelectMany(bytes => bytes).ToArray();
        var before = await fixture.WriteAsync(Chunks(0x10000, repeated));
        var after = await fixture.WriteAsync([Chunk(0x30000, Wire(102, 12, "player-1"))], later: true);
        var (_, json, _) = await RunAsync(before, after);
        using var doc = JsonDocument.Parse(json);
        Assert.Equal("blocked", doc.RootElement.GetProperty("status").GetString());
        Assert.Equal("before:candidate-limit-exceeded", doc.RootElement.GetProperty("reason").GetString());
    }

    [Fact]
    public async Task NoFrameInCoveredScopeIsUnavailableWithNoCoordinates()
    {
        using var fixture = new Fixture();
        var before = await fixture.WriteAsync([Chunk(0x10000, "ordinary memory"u8.ToArray())]);
        var after = await fixture.WriteAsync([Chunk(0x25000, Wire(103, 13, "player-1"))], later: true);
        var (_, json, _) = await RunAsync(before, after);
        using var doc = JsonDocument.Parse(json);
        Assert.Equal("unavailable", doc.RootElement.GetProperty("status").GetString());
        Assert.Equal(JsonValueKind.Null, doc.RootElement.GetProperty("selected").GetProperty("before").ValueKind);
        Assert.Equal(JsonValueKind.Null, doc.RootElement.GetProperty("advances").ValueKind);
    }

    [Fact]
    public async Task DuplicateNestedFieldKeyFailsClosed()
    {
        using var fixture = new Fixture();
        var altered = Encoding.UTF8.GetString(Wire(100, 10, "player-1"))
            .Replace("\"coordX\":{\"status\":\"ok\"", "\"coordX\":{\"status\":\"ok\",\"status\":\"ok\"", StringComparison.Ordinal);
        var before = await fixture.WriteAsync([Chunk(0x10000, Encoding.UTF8.GetBytes(altered))]);
        var after = await fixture.WriteAsync([Chunk(0x25000, Wire(103, 13, "player-1"))], later: true);
        var (_, json, _) = await RunAsync(before, after);
        using var doc = JsonDocument.Parse(json);
        Assert.Equal("blocked", doc.RootElement.GetProperty("status").GetString());
        Assert.Equal("json-duplicate-key",
            doc.RootElement.GetProperty("source").GetProperty("before").GetProperty("candidates")[0].GetProperty("reason").GetString());
    }

    [Fact]
    public async Task WrongWireVersionFailsClosed()
    {
        using var fixture = new Fixture();
        var bad = Encoding.UTF8.GetString(Wire(100, 10, "player-1"))
            .Replace("\"addonVersion\":\"0.6.0\"", "\"addonVersion\":\"9.9.9\"", StringComparison.Ordinal);
        var before = await fixture.WriteAsync([Chunk(0x10000, Encoding.UTF8.GetBytes(bad))]);
        var after = await fixture.WriteAsync([Chunk(0x20000, Wire(102, 12, "player-1"))], later: true);
        var (_, json, _) = await RunAsync(before, after);
        using var doc = JsonDocument.Parse(json);
        Assert.Equal("blocked", doc.RootElement.GetProperty("status").GetString());
        Assert.Equal("before:malformed-complete-frame", doc.RootElement.GetProperty("reason").GetString());
    }

    [Fact]
    public async Task OverlappingAcquisitionWindowsAreRejected()
    {
        using var fixture = new Fixture();
        var before = await fixture.WriteAsync([Chunk(0x10000, Wire(100, 10, "player-1"))], later: true);
        var after = await fixture.WriteAsync([Chunk(0x20000, Wire(102, 12, "player-1"))]);
        var (code, _, error) = await RunAsync(before, after);
        Assert.Equal(2, code);
        Assert.Contains("chronological", error);
    }

    [Fact]
    public async Task SharedLuaReferenceFixtureDecodesEveryFieldIncludingZeroAndFalse()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null && !File.Exists(Path.Combine(directory.FullName, "contracts", "addon", "fixtures", "reference-v1.json")))
            directory = directory.Parent;
        Assert.NotNull(directory);
        using var shared = JsonDocument.Parse(await File.ReadAllTextAsync(Path.Combine(directory.FullName, "contracts", "addon", "fixtures", "reference-v1.json")));
        using var fixture = new Fixture();
        var before = await fixture.WriteAsync(Chunks(0x10000, Encoding.ASCII.GetBytes(shared.RootElement.GetProperty("beforeFrame").GetString()!)));
        var after = await fixture.WriteAsync(Chunks(0x20000, Encoding.ASCII.GetBytes(shared.RootElement.GetProperty("afterFrame").GetString()!)), later: true);
        var (code, json, error) = await RunAsync(before, after, sessionId: shared.RootElement.GetProperty("nonce").GetString());
        Assert.Equal(0, code);
        Assert.Empty(error);
        using var report = JsonDocument.Parse(json);
        Assert.Equal("advanced-in-covered-scope", report.RootElement.GetProperty("status").GetString());
        foreach (var side in new[] { "before", "after" })
        {
            var selected = report.RootElement.GetProperty("selected").GetProperty(side);
            var expected = shared.RootElement.GetProperty(side).GetProperty("fields");
            foreach (var field in expected.EnumerateObject())
                Assert.True(JsonElement.DeepEquals(field.Value, selected.GetProperty("fields").GetProperty(field.Name)), field.Name);
        }
    }

    private const string ReferenceSession = "0123456789abcdef0123456789abcdef";

    private static byte[] ReferenceWire(long sequence, double clock, long epoch = 1, string? nonce = null,
        string player = "player-1", string? fieldUnavailable = null, bool clockFailed = false)
    {
        using var legacy = JsonDocument.Parse(Wire(sequence, clock, player).AsMemory(10, Wire(sequence, clock, player).Length - 22));
        var fields = legacy.RootElement.GetProperty("player").GetProperty("fields").EnumerateObject()
            .ToDictionary(p => p.Name, p => (object)p.Value.Clone());
        if (fieldUnavailable is not null) fields[fieldUnavailable] = new { status = "unavailable" };
        if (clockFailed)
            foreach (var key in fields.Keys.ToArray()) fields[key] = new { status = "unavailable" };
        var payload = new
        {
            schemaVersion = 1,
            addon = "RiftReader2",
            addonVersion = "0.2.0",
            source = "rift-api",
            sessionId = nonce ?? ReferenceSession,
            sequence,
            epoch,
            clock = clockFailed ? (object)new { status = "unavailable" } : new { status = "ok", value = clock },
            player = clockFailed ? (object)new { status = "unavailable" } : new { status = "ok", value = player },
            fields
        };
        return Encoding.ASCII.GetBytes("RR2R1|" + JsonSerializer.Serialize(payload) + "|ENDRR2R1");
    }

    [Fact]
    public async Task ReferenceFramesPublishOwnedIdentityAndUnavailableResourceStatus()
    {
        using var fixture = new Fixture();
        var before = await fixture.WriteAsync(Chunks(0x10000, ReferenceWire(100, 10)));
        var after = await fixture.WriteAsync(Chunks(0x20000, ReferenceWire(102, 12, fieldUnavailable: "mana")), later: true);
        var (code, json, error) = await RunAsync(before, after, sessionId: ReferenceSession);
        Assert.Equal(0, code);
        Assert.Empty(error);
        using var doc = JsonDocument.Parse(json);
        Assert.Equal("advanced-in-covered-scope", doc.RootElement.GetProperty("status").GetString());
        var selected = doc.RootElement.GetProperty("selected").GetProperty("after");
        Assert.Equal("RR2R1", selected.GetProperty("protocol").GetString());
        Assert.Equal("RiftReader2", selected.GetProperty("addon").GetString());
        Assert.Equal(ReferenceSession, selected.GetProperty("sessionId").GetString());
        Assert.Equal(1, selected.GetProperty("epoch").GetInt64());
        Assert.Equal("unavailable", selected.GetProperty("fields").GetProperty("mana").GetProperty("status").GetString());
    }

    [Theory]
    [InlineData("foreign")]
    [InlineData("epoch")]
    [InlineData("mixed-epoch")]
    [InlineData("mixed-player")]
    [InlineData("clock-failed")]
    [InlineData("conflict")]
    [InlineData("sequence-clock-conflict")]
    public async Task ReferenceIdentityAndClearingFailuresBlock(string scenario)
    {
        using var fixture = new Fixture();
        var second = scenario switch
        {
            "foreign" => ReferenceWire(102, 12, nonce: new string('a', 32)),
            "epoch" => ReferenceWire(102, 12, epoch: 2),
            "mixed-epoch" => ReferenceWire(101, 11, epoch: 2).Concat(ReferenceWire(102, 12)).ToArray(),
            "mixed-player" => ReferenceWire(101, 11, player: "other").Concat(ReferenceWire(102, 12)).ToArray(),
            "clock-failed" => ReferenceWire(102, 12, clockFailed: true).Concat(ReferenceWire(101, 11)).ToArray(),
            "sequence-clock-conflict" => ReferenceWire(102, 12).Concat(ReferenceWire(102, 13)).ToArray(),
            _ => ReferenceWire(102, 12).Concat(ReferenceWire(102, 12, fieldUnavailable: "mana")).ToArray()
        };
        var before = await fixture.WriteAsync(Chunks(0x10000, ReferenceWire(100, 10)));
        var after = await fixture.WriteAsync(Chunks(0x20000, second), later: true);
        var (code, json, error) = await RunAsync(before, after, sessionId: ReferenceSession);
        Assert.Equal(0, code);
        Assert.Empty(error);
        using var doc = JsonDocument.Parse(json);
        Assert.Equal("blocked", doc.RootElement.GetProperty("status").GetString());
    }

    [Theory]
    [InlineData(8192, "advanced-in-covered-scope")]
    [InlineData(8193, "blocked")]
    public async Task ReferenceFrameLimitIncludesBothMarkers(int frameBytes, string expected)
    {
        using var fixture = new Fixture();
        var wire = ReferenceWire(102, 12);
        var text = Encoding.ASCII.GetString(wire);
        var padded = Encoding.ASCII.GetBytes(text.Insert(7, new string(' ', frameBytes - wire.Length)));
        var before = await fixture.WriteAsync(Chunks(0x10000, ReferenceWire(100, 10)));
        var after = await fixture.WriteAsync(Chunks(0x20000, padded), later: true);
        var (_, json, _) = await RunAsync(before, after, sessionId: ReferenceSession);
        using var doc = JsonDocument.Parse(json);
        Assert.Equal(expected, doc.RootElement.GetProperty("status").GetString());
    }

    private static async Task<(int Code, string Output, string Error)> RunAsync(
        string before, string after, string? outputFile = null, string? sessionId = null)
    {
        using var output = new StringWriter();
        using var error = new StringWriter();
        var args = new List<string> { "inspect-typed-wire", "--before", before, "--after", after };
        if (outputFile is not null) args.AddRange(["--output", outputFile]);
        if (sessionId is not null) args.AddRange(["--session-id", sessionId]);
        var code = await CliRunner.RunAsync([.. args], output, error);
        return (code, output.ToString(), error.ToString());
    }

    private static byte[] Wire(long sequence, double frame, string player, double x = 123.25)
    {
        static Dictionary<string, object> Fields(bool ok, double xValue)
        {
            var fields = new Dictionary<string, object>(StringComparer.Ordinal);
            foreach (var key in NumberFields)
            {
                fields[key] = ok ? new { status = "ok", value = key == "coordX" ? xValue : 55.0 }
                                 : new { status = "unavailable" };
            }
            foreach (var key in BooleanFields)
                fields[key] = ok ? new { status = "ok", value = false } : new { status = "unavailable" };
            fields["zone"] = ok ? new { status = "ok", value = "RIFT zone" } : new { status = "unavailable" };
            return fields;
        }
        var document = new
        {
            schemaVersion = 2,
            addon = "RiftReaderApiProbe",
            addonVersion = "0.6.0",
            source = "rift-api",
            sequence,
            clock = new { status = "ok", domain = "Inspect.Time.Frame", value = frame },
            player = new { status = "ok", fields = Fields(true, x), unitId = player },
            target = new { status = "absent", fields = Fields(false, x) },
            nativeTextEntryState = "unknown",
            autonomousInputReady = false
        };
        return Encoding.UTF8.GetBytes("RRAPIVAL2|" + JsonSerializer.Serialize(document) + "|RRAPIVALEND");
    }

    private static NativeMemorySnapshotChunk Chunk(ulong address, byte[] bytes) => new(
        $"0x{address:X}", bytes.Length, "success", bytes.Length,
        Convert.ToBase64String(bytes), Convert.ToHexString(SHA256.HashData(bytes)), null, null);

    private static NativeMemorySnapshotChunk[] Chunks(ulong start, byte[] bytes) =>
        Enumerable.Range(0, (bytes.Length + 4095) / 4096)
            .Select(i => Chunk(start + (ulong)(i * 4096), bytes.AsSpan(i * 4096, Math.Min(4096, bytes.Length - i * 4096)).ToArray()))
            .ToArray();

    private sealed class Fixture : IDisposable
    {
        internal static NativeProcessIdentity Identity { get; } =
            new(42, 638964000000000000, @"C:\RIFT\rift_x64.exe", new string('C', 64), 0x10000, 0x1000);
        internal string DirectoryPath { get; } =
            Path.Combine(Path.GetTempPath(), "rr2-typed-wire-" + Guid.NewGuid().ToString("N"));

        internal Fixture() => Directory.CreateDirectory(DirectoryPath);

        internal async Task<string> WriteAsync(
            IReadOnlyList<NativeMemorySnapshotChunk> chunks,
            string status = "complete",
            string? reason = null,
            bool later = false,
            NativeProcessIdentity? identity = null)
        {
            var snapshot = new NativeMemorySnapshotFile(
                1, "native-memory-snapshot/1",
                new("native-memory-snapshot-request/1", new string('A', 64), "producer-declared",
                    new("test", "assembly-files", new Dictionary<string, string> { ["test"] = new string('B', 64) }, null, null)),
                identity ?? Identity,
                later ? "2026-10-24T12:00:03Z" : "2026-10-24T12:00:00Z",
                later ? "2026-10-24T12:00:04Z" : "2026-10-24T12:00:01Z",
                status, reason, chunks, ["bounded synthetic fixture"]);
            var file = Path.Combine(DirectoryPath, Guid.NewGuid().ToString("N") + ".json");
            await File.WriteAllTextAsync(file, JsonSerializer.Serialize(snapshot, JsonFormat.Options));
            return file;
        }

        public void Dispose() => Directory.Delete(DirectoryPath, recursive: true);
    }
}
