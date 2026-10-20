using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using RiftReader2.Cli;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Tests;

public sealed class TargetedHealthAuditTests
{
    [Fact]
    public async Task ChangedHealthAndPowerAreReportedOnlyAsCandidates()
    {
        using var fixture = new Fixture();
        var result = await fixture.RunAsync();
        Assert.Equal(0, result.Code);
        using var report = JsonDocument.Parse(result.Stdout);
        var root = report.RootElement;
        Assert.Equal("targeted-health-snapshot-audit/1", root.GetProperty("evidenceKind").GetString());
        Assert.Equal("candidate-only", root.GetProperty("qualification").GetString());
        Assert.Equal(1, root.GetProperty("summary").GetProperty("successfulGroups").GetInt32());
        Assert.Equal(1, root.GetProperty("summary").GetProperty("currentTypedAnyMatches").GetInt32());
        Assert.Equal(0, root.GetProperty("summary").GetProperty("historicalBytesIdenticalGroups").GetInt32());
        Assert.False(root.GetProperty("summary").GetProperty("currentVsMaxHealthDisambiguated").GetBoolean());
        Assert.True(root.GetProperty("capture").GetProperty("typedReferenceNearCapture").GetBoolean());
        var item = root.GetProperty("results")[0];
        Assert.True(item.GetProperty("allSitesMatchAnyCurrentValue").GetBoolean());
        Assert.False(item.GetProperty("historicalBytesIdentical").GetBoolean());
        var markers = item.GetProperty("sites").EnumerateArray().ToArray();
        Assert.Equal(6, markers.Length);
        Assert.Equal(17_000, markers[1].GetProperty("nativeInt32").GetInt32());
        var comparisons = markers[1].GetProperty("comparisons").EnumerateArray().ToArray();
        Assert.True(comparisons[0].GetProperty("matches").GetBoolean());
        Assert.False(comparisons[1].GetProperty("matches").GetBoolean());
        Assert.Equal(JsonValueKind.Null, markers[0].GetProperty("comparisons")[0].GetProperty("matches").ValueKind);
    }

    [Fact]
    public async Task OldReceiptStillPermitsByteAuditButForbidsTypedMatchClaim()
    {
        using var fixture = new Fixture();
        fixture.RecreateSnapshot("2026-10-19T12:01:01Z");
        var result = await fixture.RunAsync();
        Assert.Equal(0, result.Code);
        using var report = JsonDocument.Parse(result.Stdout);
        Assert.False(report.RootElement.GetProperty("capture").GetProperty("typedReferenceNearCapture").GetBoolean());
        Assert.Equal(JsonValueKind.Null,
            report.RootElement.GetProperty("summary").GetProperty("currentTypedAnyMatches").ValueKind);
        Assert.Equal(JsonValueKind.Null,
            report.RootElement.GetProperty("results")[0].GetProperty("allSitesMatchAnyCurrentValue").ValueKind);
    }

    [Fact]
    public async Task UnavailableChunkCannotBeInterpretedAsZero()
    {
        using var fixture = new Fixture();
        fixture.RecreateSnapshot("2026-10-19T12:00:05Z", unavailable: true);
        var result = await fixture.RunAsync();
        Assert.Equal(0, result.Code);
        using var report = JsonDocument.Parse(result.Stdout);
        Assert.Equal(0, report.RootElement.GetProperty("summary").GetProperty("successfulGroups").GetInt32());
        Assert.Equal(1, report.RootElement.GetProperty("summary").GetProperty("unavailableOrUncapturedGroups").GetInt32());
        var item = report.RootElement.GetProperty("results")[0];
        Assert.Equal("unavailable", item.GetProperty("status").GetString());
        Assert.Empty(item.GetProperty("sites").EnumerateArray());
        Assert.Equal(JsonValueKind.Null, item.GetProperty("historicalBytesIdentical").ValueKind);
    }

    [Fact]
    public async Task ExactRequestHashIsPinnedToTheNativeProducer()
    {
        using var fixture = new Fixture();
        fixture.EditJson(fixture.Request, root => root["maxDurationMilliseconds"] = 4000);
        var result = await fixture.RunAsync();
        Assert.Equal(2, result.Code);
        Assert.Contains("request SHA-256 differs", result.Stderr);
    }

    [Fact]
    public async Task SnapshotGameBuildMismatchIsRejected()
    {
        using var fixture = new Fixture();
        fixture.EditJson(fixture.Snapshot, root => root["identity"]!["executableSha256"] = new string('B', 64));
        var result = await fixture.RunAsync();
        Assert.Equal(2, result.Code);
        Assert.Contains("PID/start/build differs", result.Stderr);
    }

    [Fact]
    public async Task SnapshotChunkHashTamperingIsRejectedBeforeOutput()
    {
        using var fixture = new Fixture();
        fixture.EditJson(fixture.Snapshot, root => root["chunks"]![0]!["bytesSha256"] = new string('A', 64));
        var destination = Path.Combine(fixture.DirectoryPath, "not-created.json");
        var result = await fixture.RunAsync(destination);
        Assert.Equal(2, result.Code);
        Assert.Contains("bytes SHA-256 does not match", result.Stderr);
        Assert.False(File.Exists(destination));
    }

    [Fact]
    public async Task SnapshotChunkAddressMustMatchTheExactPlannedRange()
    {
        using var fixture = new Fixture();
        fixture.EditJson(fixture.Snapshot, root => root["chunks"]![0]!["address"] = "0x21000");
        var result = await fixture.RunAsync();
        Assert.Equal(2, result.Code);
        Assert.Contains("not the requested range", result.Stderr);
    }

    [Fact]
    public async Task ReceiptMustMatchItsPinnedContentHash()
    {
        using var fixture = new Fixture();
        fixture.EditJson(fixture.Receipt,
            root => root["observation"]!["readback"]!["typedApi"]!["selectedSequence"] = 10);
        var result = await fixture.RunAsync();
        Assert.Equal(2, result.Code);
        Assert.Contains("receipt SHA-256 differs", result.Stderr);
    }

    [Fact]
    public async Task ReceiptGenerationMismatchIsRejectedEvenIfManifestHashUpdated()
    {
        using var fixture = new Fixture();
        fixture.EditJson(fixture.Receipt,
            root => root["observation"]!["readback"]!["typedApi"]!["generation"] = 3);
        fixture.RepinReceipt();
        var result = await fixture.RunAsync();
        Assert.Equal(2, result.Code);
        Assert.Contains("generation/sequence differs", result.Stderr);
    }

    [Fact]
    public async Task ReceiptStartTimeMismatchRejectsARecycledPid()
    {
        using var fixture = new Fixture();
        fixture.EditJson(fixture.Receipt,
            root => root["observation"]!["target"]!["processStartUtc"] = "2026-10-19T11:59:59Z");
        fixture.RepinReceipt();
        var result = await fixture.RunAsync();
        Assert.Equal(2, result.Code);
        Assert.Contains("receipt PID/start/build differs", result.Stderr);
    }

    [Fact]
    public async Task UnrelatedGameReceiptFailsEvenWhenManifestHashUpdated()
    {
        using var fixture = new Fixture();
        fixture.EditJson(fixture.Receipt,
            root => root["observation"]!["target"]!["processId"] = 9999);
        fixture.RepinReceipt();
        var result = await fixture.RunAsync();
        Assert.Equal(2, result.Code);
        Assert.Contains("receipt PID/start/build differs", result.Stderr);
    }

    [Fact]
    public async Task ManifestAndRequestRangeDisagreementIsRejected()
    {
        using var fixture = new Fixture();
        fixture.EditJson(fixture.Manifest,
            root => root["selections"]![0]!["rangeSessionAddress"] = "0x20100");
        var result = await fixture.RunAsync();
        Assert.Equal(2, result.Code);
        Assert.Contains("differs from the request", result.Stderr);
    }

    [Fact]
    public async Task BadMarkerOffsetOrTagIsRejected()
    {
        using var fixture = new Fixture();
        fixture.EditJson(fixture.Manifest,
            root => root["selections"]![0]!["markerPositions"]![0]!["byteOffset"] = 79);
        var result = await fixture.RunAsync();
        Assert.Equal(2, result.Code);
        Assert.Contains("marker byte offset", result.Stderr);
        fixture.EditJson(fixture.Manifest,
            root =>
            {
                root["selections"]![0]!["markerPositions"]![0]!["byteOffset"] = 8;
                root["selections"]![0]!["markerPositions"]![0]!["tags"] = new JsonArray("never-approved");
            });
        result = await fixture.RunAsync();
        Assert.Equal(2, result.Code);
        Assert.Contains("invalid typed marker tags", result.Stderr);
    }

    [Fact]
    public async Task DuplicateManifestPropertiesAreRejected()
    {
        using var fixture = new Fixture();
        File.WriteAllText(fixture.Manifest, "{\"schemaVersion\":1,\"schemaVersion\":1}");
        var result = await fixture.RunAsync();
        Assert.Equal(2, result.Code);
        Assert.Contains("Duplicate JSON property", result.Stderr);
    }

    [Fact]
    public async Task OutputReportIsNeverOverwritten()
    {
        using var fixture = new Fixture();
        var output = Path.Combine(fixture.DirectoryPath, "audit.json");
        Assert.Equal(0, (await fixture.RunAsync(output)).Code);
        var previous = await File.ReadAllBytesAsync(output);
        var rejected = await fixture.RunAsync(output);
        Assert.Equal(2, rejected.Code);
        Assert.Equal(previous, await File.ReadAllBytesAsync(output));
    }

    internal sealed class Fixture : IDisposable
    {
        public const int Pid = 8356;
        public const string GameBuild = "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD";
        private const string StartUtc = "2026-10-19T12:00:00.0000000Z";
        private const string Observer = "fixture-typed-observer-20261019";
        public string DirectoryPath { get; } =
            Path.Combine(Path.GetTempPath(), "rr2-targeted-audit-" + Guid.NewGuid().ToString("N"));
        public string Request => Path.Combine(DirectoryPath, "request.json");
        public string Manifest => Path.Combine(DirectoryPath, "manifest.json");
        public string Receipt => Path.Combine(DirectoryPath, "receipt.json");
        public string Snapshot => Path.Combine(DirectoryPath, "snapshot.json");
        private static readonly long Ticks = DateTimeOffset.Parse(StartUtc).UtcTicks;
        private const ulong RangeAddress = 0x20000;

        public Fixture()
        {
            Directory.CreateDirectory(DirectoryPath);
            Write(Request, new
            {
                schemaVersion = 1,
                evidenceKind = "native-memory-snapshot-request/1",
                target = Target(),
                maxDurationMilliseconds = 5000,
                ranges = new[] { new {
                    addressKind = "absolute-session-address",
                    address = "0x20000", byteLength = 80
                }}
            });
            Write(Receipt, new
            {
                schemaVersion = 1,
                receivedAtUtc = "2026-10-19T12:00:00.0000000+00:00",
                observation = new
                {
                    instanceId = Observer,
                    riftProcessCount = 1,
                    target = new
                    {
                        processId = Pid,
                        processStartUtc = StartUtc,
                        executableSha256 = GameBuild
                    },
                    readback = new
                    {
                        status = "fresh",
                        typedApi = new
                        {
                            status = "fresh",
                            generation = 2,
                            selectedSequence = 9,
                            sequenceAdvanced = true,
                            frameTimeAdvanced = true,
                            snapshot = new
                            {
                                player = new
                                {
                                    unitId = "fixture-player",
                                    fields = new
                                    {
                                        health = new { status = "ok", value = 17000 },
                                        healthMax = new { status = "ok", value = 18208 },
                                        power = new { status = "ok", value = 75 }
                                    }
                                }
                            }
                        }
                    }
                }
            });
            var original = new byte[80];
            foreach (var (offset, value) in new (int, int)[] {
                         (8,45), (16,18208), (24,18208), (32,18208), (56,100), (60,100) })
                BitConverter.GetBytes(value).CopyTo(original, offset);
            Write(Manifest, new
            {
                schemaVersion = 1,
                evidenceKind = "native-health-targeted-snapshot-plan/1",
                qualification = "candidate-only",
                selectedPatternSha256 = new string('A', 64),
                selectedCount = 1,
                totalRequestedBytes = 80,
                source = new
                {
                    healthReportSha256 = new string('B', 64),
                    crossEpochReviewSha256 = new string('C', 64),
                    liveReceiptSha256 = Sha(Receipt)
                },
                target = Target(),
                typed = new
                {
                    observer = Observer,
                    generation = 2,
                    selectedSequence = 9,
                    unitId = "fixture-player",
                    sourceHealthValues = new
                    {
                        health = 18208,
                        healthMax = 18208,
                        power = 100
                    },
                    currentValues = new
                    {
                        health = 17000,
                        healthMax = 18208,
                        power = 75
                    }
                },
                selections = new[] { new {
                    firstHealthHitSessionAddress = "0x20010",
                    rangeSessionAddress = "0x20000", byteLength = 80,
                    sourceWindowSha256 = Convert.ToHexString(SHA256.HashData(original)),
                    markerPositions = new[] {
                        Marker(8, "visualLevelHint"),
                        Marker(16, "currentHealth", "maximumHealth"),
                        Marker(24, "currentHealth", "maximumHealth"),
                        Marker(32, "currentHealth", "maximumHealth"),
                        Marker(56, "rawPower"),
                        Marker(60, "rawPower")
                    }
                }}
            });
            RecreateSnapshot("2026-10-19T12:00:05Z");
        }

        public void RecreateSnapshot(string startUtc, bool unavailable = false,
            bool baseline = false, string? completedUtc = null)
        {
            var current = new byte[80];
            foreach (var (offset, value) in new (int, int)[] {
                         (8,45), (16,baseline ? 18208 : 17000),
                         (24,18208), (32,18208),
                         (56,baseline ? 100 : 75), (60,baseline ? 100 : 75) })
                BitConverter.GetBytes(value).CopyTo(current, offset);
            var chunk = unavailable
                ? new NativeMemorySnapshotChunk("0x20000", 80, "unavailable", 0, null, null, 299, "unmapped")
                : new NativeMemorySnapshotChunk("0x20000", 80, "success", 80,
                    Convert.ToBase64String(current),
                    Convert.ToHexString(SHA256.HashData(current)), null, null);
            var snapshot = new NativeMemorySnapshotFile(
                1, "native-memory-snapshot/1",
                new("native-memory-snapshot-request/1", Sha(Request), "producer-declared",
                    new("fixture", "assembly-files",
                        new Dictionary<string, string> { ["fixture"] = new string('D', 64) },
                        null, null)),
                new NativeProcessIdentity(Pid, Ticks, @"C:\RIFT\rift_x64.exe",
                    GameBuild, 0x10000, 0x100000),
                startUtc, completedUtc ?? "2026-10-19T12:01:05Z",
                unavailable ? "failed" : "complete",
                unavailable ? "no readable target data" : null,
                [chunk], ["synthetic fixture; no game access"]);
            Write(Snapshot, snapshot);
        }

        private static object Target() => new
        {
            processId = Pid,
            processStartUtcTicks = Ticks,
            executableSha256 = GameBuild
        };

        private static object Marker(int offset, params string[] tags) =>
            new { byteOffset = offset, tags };

        private static string Sha(string path) =>
            Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path)));

        public void SetReferenceState(int health, int power, int sequence, string receivedAtUtc)
        {
            EditJson(Receipt, root =>
            {
                root["receivedAtUtc"] = receivedAtUtc;
                var typed = root["observation"]!["readback"]!["typedApi"]!;
                typed["selectedSequence"] = sequence;
                var fields = typed["snapshot"]!["player"]!["fields"]!;
                fields["health"]!["value"] = health;
                fields["power"]!["value"] = power;
            });
            EditJson(Manifest, root =>
            {
                root["typed"]!["selectedSequence"] = sequence;
                root["typed"]!["currentValues"]!["health"] = health;
                root["typed"]!["currentValues"]!["power"] = power;
            });
            RepinReceipt();
        }

        public void RepinReceipt() =>
            EditJson(Manifest, root => root["source"]!["liveReceiptSha256"] = Sha(Receipt));

        public void EditJson(string path, Action<JsonNode> mutation)
        {
            var root = JsonNode.Parse(File.ReadAllText(path))!;
            mutation(root);
            File.WriteAllText(path, root.ToJsonString(JsonFormat.Options));
        }

        public async Task<(int Code, string Stdout, string Stderr)> RunAsync(string? outputPath = null)
        {
            var options = new List<string> {
                "audit-targeted-health",
                "--request", Request, "--manifest", Manifest,
                "--receipt", Receipt, "--snapshot", Snapshot
            };
            if (outputPath is not null)
            {
                options.Add("--output");
                options.Add(outputPath);
            }
            using var stdout = new StringWriter();
            using var stderr = new StringWriter();
            var code = await CliRunner.RunAsync([.. options], stdout, stderr);
            return (code, stdout.ToString(), stderr.ToString());
        }

        private static void Write(string path, object obj) =>
            File.WriteAllText(path, JsonSerializer.Serialize(obj, JsonFormat.Options));

        public void Dispose() =>
            Directory.Delete(DirectoryPath, recursive: true);
    }
}
