using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Cli;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Tests;

public sealed class DiscoveryExportTests
{
    private static readonly string FixtureRoot = Path.Combine(AppContext.BaseDirectory, "Fixtures");
    private static readonly string Fixture = Path.Combine(FixtureRoot, "discovery-sources.json");
    private static readonly string Build = new('A', 64);

    [Fact]
    public async Task SampleCatalogAndResearchCompileDeterministicallyWithoutPromotion()
    {
        using var folder = new TemporaryFolder();
        var first = Path.Combine(folder.Path, "one.json");
        var second = Path.Combine(folder.Path, "two.json");
        Assert.Equal(0, await Run(Fixture, first));
        Assert.Equal(0, await Run(Fixture, second));
        Assert.Equal(await File.ReadAllBytesAsync(first), await File.ReadAllBytesAsync(second));
        using var json = JsonDocument.Parse(await File.ReadAllTextAsync(first));
        var root = json.RootElement;
        Assert.Equal("discovery-compilation/1", root.GetProperty("contractVersion").GetString());
        Assert.Equal(6, root.GetProperty("totalRecords").GetInt32());
        Assert.Equal(6, root.GetProperty("selectedRecords").GetInt32());
        var rows = root.GetProperty("records").EnumerateArray().ToArray();
        Assert.Equal("supported-by-recorded-assessment",
            rows.Single(r => r.GetProperty("fieldId").GetString() == "demo.supported")
                .GetProperty("status").GetString());
        Assert.Equal("contradicted",
            rows.Single(r => r.GetProperty("fieldId").GetString() == "demo.disputed")
                .GetProperty("status").GetString());
        Assert.Equal("unqualified",
            rows.Single(r => r.GetProperty("fieldId").GetString() == "demo.address-only")
                .GetProperty("status").GetString());
        Assert.Equal("recorded-only",
            rows.Single(r => r.GetProperty("fieldId").GetString() == "player.heading.candidate")
                .GetProperty("qualification").GetString());
        Assert.Null(rows.Single(r => r.GetProperty("fieldId").GetString() == "target.position.unknown")
            .GetProperty("value").GetStringOrNull());
        Assert.All(rows, r => Assert.Equal(64,
            r.GetProperty("evidenceSha256").GetString()!.Length));
    }

    [Fact]
    public async Task SearchMultiFilterAndCsvExportAreScopedAndSpreadsheetSafe()
    {
        using var folder = new TemporaryFolder();
        var csv = Path.Combine(folder.Path, "combat.csv");
        Assert.Equal(0, await Run(Fixture, csv, "--format", "csv", "--source", "addon",
            "--category", "combat", "--search", "ability", "--columns", "fieldId,value,status"));
        var content = await File.ReadAllTextAsync(csv);
        Assert.Contains("\"fieldId\",\"value\",\"status\"", content);
        Assert.Contains("\"ability.name.example\",\"'=1+1\",\"observed\"", content);
        Assert.DoesNotContain("demo.supported", content);
        Assert.Equal(2, content.Split('\n', StringSplitOptions.RemoveEmptyEntries).Length);
        var before = await File.ReadAllBytesAsync(csv);
        Assert.Equal(2, await Run(Fixture, csv, "--format", "csv", "--source", "addon",
            "--category", "combat", "--search", "ability", "--columns", "fieldId,value,status"));
        Assert.Equal(before, await File.ReadAllBytesAsync(csv));

        var jsonl = Path.Combine(folder.Path, "records.jsonl");
        Assert.Equal(0, await Run(Fixture, jsonl, "--format", "jsonl", "--status", "contradicted,unqualified"));
        var lines = await File.ReadAllLinesAsync(jsonl);
        Assert.Equal(3, lines.Length);
        Assert.All(lines, line =>
        {
            using var parsed = JsonDocument.Parse(line);
            Assert.Contains(parsed.RootElement.GetProperty("status").GetString(),
                new[] { "contradicted", "unqualified" });
        });
    }

    [Fact]
    public void SortingIsStableAndMissingDatesRemainLastInEitherDirection()
    {
        var values = new[]
        {
            MakeRow("b", new DateTimeOffset(2026, 10, 21, 1, 0, 0, TimeSpan.Zero)),
            MakeRow("c", null),
            MakeRow("a", new DateTimeOffset(2026, 10, 21, 1, 0, 0, TimeSpan.Zero)),
            MakeRow("old", new DateTimeOffset(2026, 10, 19, 1, 0, 0, TimeSpan.Zero))
        };
        Assert.Equal(new[] { "old", "a", "b", "c" },
            DiscoveryQuery.Apply(values, new(null, null, null, null, "observedAtUtc:asc"))
                .Select(r => r.Id));
        Assert.Equal(new[] { "a", "b", "old", "c" },
            DiscoveryQuery.Apply(values, new(null, null, null, null, "observedAtUtc:desc"))
                .Select(r => r.Id));
        Assert.Throws<ArgumentException>(() => DiscoveryQuery.ParseSort("status:desc,status:asc"));
        Assert.Throws<ArgumentException>(() => DiscoveryQuery.ParseSort("unsupported:asc"));
    }

    [Fact]
    public void SearchFindsRetainedProvenanceLimitationsAndUtcObservationTime()
    {
        var one = MakeRow("one", new DateTimeOffset(2026, 10, 25, 0, 2, 0, TimeSpan.Zero)) with
        {
            SourceId = "first-report",
            SourcePath = "saved/native-a.json",
            EvidenceSha256 = new string('F', 64),
            Units = "degrees",
            Limitations = ["No verified control"]
        };
        var two = MakeRow("two", null) with
        {
            SourceId = "second-report",
            SourcePath = "saved/lua-b.json",
            EvidenceSha256 = new string('D', 64),
            Units = "metres",
            Limitations = ["Historical only"]
        };
        var rows = new[] { one, two };
        foreach (var (query, expected) in new[]
                 {
                     ("native-a.json", "one"), ("second-report", "two"),
                     ("No verified control", "one"), ("FFFFFFFF", "one"),
                     ("2026-10-25T00:02:00", "one"), ("degrees", "one")
                 })
            Assert.Equal(expected, Assert.Single(DiscoveryQuery.Apply(rows,
                new(null, null, null, query, "id:asc"))).Id);
    }

    [Fact]
    public async Task BadSourceHashAndTraversalDoNotPublish()
    {
        using var folder = new TemporaryFolder();
        var location = CopySamples(folder.Path);
        var rowsPath = Path.Combine(folder.Path, "discoveries-records.json");
        await File.AppendAllTextAsync(rowsPath, " ");
        var destination = Path.Combine(folder.Path, "failure.json");
        Assert.Equal(2, await Run(location, destination));
        Assert.False(File.Exists(destination));

        var manifest = new
        {
            schemaVersion = 1,
            contractVersion = "discovery-sources/1",
            sources = new[] { new {
                sourceId = "escape", kind = "record-set", path = "../discovery.json",
                byteLength = 1, sha256 = Build
            } }
        };
        var malicious = Path.Combine(folder.Path, "traversal.json");
        await File.WriteAllTextAsync(malicious, JsonSerializer.Serialize(manifest));
        Assert.Equal(2, await Run(malicious, destination));
        Assert.False(File.Exists(destination));
    }

    [Fact]
    public async Task CancellationLeavesNoOutputAndBadOptionsFailClosed()
    {
        using var folder = new TemporaryFolder();
        var output = Path.Combine(folder.Path, "never.json");
        using var token = new CancellationTokenSource();
        token.Cancel();
        using var stderr = new StringWriter();
        Assert.Equal(130, await CliRunner.RunAsync(Args(Fixture, output), new StringWriter(), stderr, token.Token));
        Assert.False(File.Exists(output));
        Assert.Equal(2, await Run(Fixture, output, "--sort", "status:sideways"));
        Assert.False(File.Exists(output));
        Assert.Equal(2, await Run(Fixture, output, "--format", "json", "--columns", "fieldId"));
    }

    [Fact]
    public void NativeAndTypedAdaptersKeepSeparateEvidenceAndCandidateStatus()
    {
        var native = new
        {
            schemaVersion = 1,
            evidenceKind = "native-motion-pair-review/1",
            status = "candidate-motion-consistent",
            qualification = "candidate-only-no-stimulus-or-clock-skew-proof",
            target = Identity(),
            rootRva = "0x32E0200",
            nativeSamples = new
            {
                before = new { completedAtUtc = "2026-10-25T00:00:00+00:00", xyz = new { x = 1.0, y = 2.0, z = 3.0 } },
                after = new { completedAtUtc = "2026-10-25T00:01:00+00:00", xyz = new { x = 2.0, y = 3.0, z = 4.0 } }
            },
            limitations = new[] { "No verified control stimulus." }
        };
        var typed = new
        {
            schemaVersion = 1,
            evidenceKind = "typed-wire-snapshot-inspection/1",
            status = "advanced-in-covered-scope",
            reason = "advancing producer",
            identity = Identity(),
            source = new { after = new { completedAtUtc = "2026-10-25T00:01:00Z" } },
            selected = new
            {
                before = new { playerUnitId = "u1", sequence = 10, frameTime = 1.0 },
                after = new
                {
                    playerUnitId = "u1",
                    sequence = 11,
                    frameTime = 2.0,
                    xyz = new { x = 2.0, y = 3.0, z = 4.0 }
                }
            },
            limitations = new[] { "Scoped Lua producer only." }
        };
        var nativeRow = DiscoveryReportAdapter.Parse(SampleSource("native-motion-review", "native", native)).Single();
        var typedRow = DiscoveryReportAdapter.Parse(SampleSource("typed-wire", "lua", typed)).Single();
        Assert.Equal(nativeRow.FieldId, typedRow.FieldId);
        Assert.NotEqual(nativeRow.Id, typedRow.Id);
        Assert.Equal("native", nativeRow.SourceKind);
        Assert.Equal("addon", typedRow.SourceKind);
        Assert.StartsWith("candidate-only", nativeRow.Qualification);
        Assert.Equal("source-advancement-only-not-native-qualified", typedRow.Qualification);
        Assert.Equal(4.0, nativeRow.Value!.Components!["z"]);
        Assert.Throws<InvalidDataException>(() => DiscoveryReportAdapter.Parse(
            SampleSource("native-position-review", "wrong-kind", native)));
    }

    [Fact]
    public async Task DuplicateJsonKeysAreRejectedBeforeAnyExport()
    {
        using var folder = new TemporaryFolder();
        var bytes = Encoding.UTF8.GetBytes(
            "{\"schemaVersion\":1,\"schemaVersion\":1,\"contractVersion\":\"discovery-record-set/1\",\"records\":[]}");
        var path = Path.Combine(folder.Path, "duplicate.json");
        await File.WriteAllBytesAsync(path, bytes);
        var entry = new DiscoverySourceStamp("dupe", "record-set", "duplicate.json",
            bytes.Length, Convert.ToHexString(SHA256.HashData(bytes)));
        var manifest = Path.Combine(folder.Path, "manifest.json");
        await File.WriteAllTextAsync(manifest, JsonSerializer.Serialize(new
        {
            schemaVersion = 1,
            contractVersion = "discovery-sources/1",
            sources = new[] { entry }
        }, JsonFormat.Options));
        var output = Path.Combine(folder.Path, "not-created.csv");
        Assert.Equal(2, await Run(manifest, output, "--format", "csv"));
        Assert.False(File.Exists(output));
    }

    private static object Identity() => new
    {
        processId = 6940,
        processStartUtcTicks = 639284177321390013L,
        executableSha256 = new string('B', 64)
    };

    private static VerifiedDiscoverySource SampleSource(string kind, string id, object value)
    {
        var bytes = JsonSerializer.SerializeToUtf8Bytes(value, JsonFormat.Options);
        return new(new(id, kind, id + ".json", bytes.Length,
            Convert.ToHexString(SHA256.HashData(bytes))), id + ".json", bytes);
    }

    private static DiscoveryRecord MakeRow(string id, DateTimeOffset? time) =>
        new(id, "same.field", "movement", "native", "hypothesis", "recorded-only",
            "Synthetic", "unit", null, null, Build, "session", time, null,
            "fixture", Build, "fixture", "fixture.json", ["Synthetic"]);

    private static string CopySamples(string dest)
    {
        Directory.CreateDirectory(Path.Combine(dest, "catalog"));
        foreach (var file in Directory.GetFiles(Path.Combine(FixtureRoot, "catalog"), "*.json"))
            File.Copy(file, Path.Combine(dest, "catalog", Path.GetFileName(file)));
        File.Copy(Fixture, Path.Combine(dest, "discovery-sources.json"));
        File.Copy(Path.Combine(FixtureRoot, "discoveries-records.json"),
            Path.Combine(dest, "discoveries-records.json"));
        return Path.Combine(dest, "discovery-sources.json");
    }

    private static string[] Args(string manifest, string output, params string[] extra) =>
    [
        "export-discoveries", "--manifest", manifest, "--build-sha256", Build,
        "--session-id", "synthetic-session-a", "--as-of", "2026-10-21T00:00:00Z",
        "--format", "json", "--output", output, .. extra
    ];

    private static async Task<int> Run(string manifest, string output, params string[] extra)
    {
        var args = Args(manifest, output);
        var list = args.ToList();
        for (var i = 0; i < extra.Length; i += 2)
        {
            if (extra[i] == "--format")
            {
                list[list.IndexOf("--format") + 1] = extra[i + 1];
            }
            else list.AddRange(extra[i..(i + 2)]);
        }
        return await CliRunner.RunAsync(list.ToArray(), new StringWriter(), new StringWriter());
    }

    private sealed class TemporaryFolder : IDisposable
    {
        public string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(),
            "rr2-discovery-tests-" + Guid.NewGuid().ToString("N"));
        public TemporaryFolder() => Directory.CreateDirectory(Path);
        public void Dispose() => Directory.Delete(Path, recursive: true);
    }
}

internal static class JsonElementTestExtensions
{
    public static string? GetStringOrNull(this JsonElement value) =>
        value.ValueKind == JsonValueKind.Null ? null : value.GetString();
}
