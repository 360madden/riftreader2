using System.Text.Json;
using System.Text.Json.Nodes;
using RiftReader2.Cli;

namespace RiftReader2.Tests;

public sealed class TargetedHealthChangeTests
{
    [Fact]
    public async Task TracksChangedTypedHealthAndPowerWithoutQualifyingAnyField()
    {
        using var pair = await Pair.CreateAsync();
        var result = await pair.CompareAsync();
        Assert.Equal(0, result.Code);
        using var report = JsonDocument.Parse(result.Stdout);
        var root = report.RootElement;
        Assert.Equal("targeted-health-change-comparison/1", root.GetProperty("evidenceKind").GetString());
        Assert.Equal("candidate-only", root.GetProperty("qualification").GetString());
        Assert.Equal(-1208, root.GetProperty("typed").GetProperty("deltas").GetProperty("currentHealth").GetInt32());
        Assert.Equal(-25, root.GetProperty("typed").GetProperty("deltas").GetProperty("rawPower").GetInt32());
        Assert.False(root.GetProperty("summary").GetProperty("currentHealthFieldQualified").GetBoolean());
        Assert.False(root.GetProperty("summary").GetProperty("resourceFieldQualified").GetBoolean());
        Assert.Equal(1, root.GetProperty("summary").GetProperty("groupsWithMatchingTypedChange").GetInt32());
        var sites = root.GetProperty("groups")[0].GetProperty("sites");
        Assert.Equal("tracks-one-typed-change", sites[1].GetProperty("status").GetString());
        Assert.Equal("currentHealth", sites[1].GetProperty("trackedTypedValues")[0].GetString());
        Assert.Equal("unchanged-or-cache", sites[2].GetProperty("status").GetString());
        Assert.Equal("rawPower", sites[4].GetProperty("trackedTypedValues")[0].GetString());
    }

    [Fact]
    public async Task UnchangedTypedValuesCannotExplainNativeDifferences()
    {
        using var pair = await Pair.CreateAsync(afterHealth: 18208, afterPower: 100);
        var result = await pair.CompareAsync();
        Assert.Equal(0, result.Code);
        using var json = JsonDocument.Parse(result.Stdout);
        Assert.False(json.RootElement.GetProperty("typed").GetProperty("changed").GetBoolean());
        Assert.Equal(0, json.RootElement.GetProperty("summary").GetProperty("groupsWithMatchingTypedChange").GetInt32());
        Assert.True(json.RootElement.GetProperty("summary").GetProperty("unexplainedMarkerChanges").GetInt32() > 0);
    }

    [Theory]
    [InlineData("epoch", "PID/start/build differs")]
    [InlineData("request", "requests differ")]
    [InlineData("observer", "observer, player")]
    [InlineData("sequence", "sequence changed")]
    [InlineData("stale", "near-capture Lua")]
    [InlineData("partial", "complete native acquisitions")]
    [InlineData("time", "overlap or run in reverse")]
    public async Task ContradictoryEvidenceIsRejected(string mutation, string expected)
    {
        using var pair = await Pair.CreateAsync();
        pair.EditAfter(root =>
        {
            switch (mutation)
            {
                case "epoch": root["identity"]!["processStartUtcTicks"] = 639279978665141458L + 1; break;
                case "request": root["source"]!["requestSha256"] = new string('F', 64); break;
                case "observer": root["typed"]!["observer"] = "unknown"; break;
                case "sequence": root["typed"]!["sequence"] = 9; break;
                case "stale": root["capture"]!["typedReferenceNearCapture"] = false; break;
                case "partial": root["capture"]!["status"] = "partial"; break;
                case "time": root["capture"]!["startedAtUtc"] = "2026-10-19T12:00:02Z"; break;
            }
        });
        var result = await pair.CompareAsync();
        Assert.Equal(2, result.Code);
        Assert.Contains(expected, result.Stderr);
    }

    [Fact]
    public async Task TamperedNativeSiteDoesNotMatchItsOwnTypedComparison()
    {
        using var pair = await Pair.CreateAsync();
        pair.EditAfter(root => root["results"]![0]!["sites"]![1]!["nativeInt32"] = 1111);
        var result = await pair.CompareAsync();
        Assert.Equal(2, result.Code);
        Assert.Contains("typed site comparison", result.Stderr);
    }

    [Fact]
    public async Task ChangedMarkerTagsAreNotSilentlyRetargeted()
    {
        using var pair = await Pair.CreateAsync();
        pair.EditAfter(root => root["results"]![0]!["sites"]![1]!["comparisons"]![0]!["tag"] = "rawPower");
        var result = await pair.CompareAsync();
        Assert.Equal(2, result.Code);
        Assert.NotEmpty(result.Stderr);
    }

    [Fact]
    public async Task SameSnapshotReplayedTwiceDoesNotCountAsChangedState()
    {
        using var pair = await Pair.CreateAsync();
        var result = await pair.CompareAsync(afterOverride: pair.Before);
        Assert.Equal(2, result.Code);
        Assert.Contains("independent native snapshots", result.Stderr);
    }

    [Fact]
    public async Task DuplicateJsonPropertiesAreRejected()
    {
        using var pair = await Pair.CreateAsync();
        File.WriteAllText(pair.After, "{\"schemaVersion\":1,\"schemaVersion\":1}");
        var result = await pair.CompareAsync();
        Assert.Equal(2, result.Code);
        Assert.Contains("Duplicate JSON property", result.Stderr);
    }

    [Fact]
    public async Task ExistingComparisonOutputIsNeverOverwritten()
    {
        using var pair = await Pair.CreateAsync();
        var output = Path.Combine(pair.Directory, "comparison.json");
        Assert.Equal(0, (await pair.CompareAsync(output)).Code);
        var initial = await File.ReadAllBytesAsync(output);
        Assert.Equal(2, (await pair.CompareAsync(output)).Code);
        Assert.Equal(initial, await File.ReadAllBytesAsync(output));
    }

    [Fact]
    public async Task MissingExpectedValueFailsWithAControlledError()
    {
        using var pair = await Pair.CreateAsync();
        pair.EditAfter(root =>
            root["results"]![0]!["sites"]![1]!["comparisons"]![0]!.AsObject().Remove("expected"));
        var result = await pair.CompareAsync();
        Assert.Equal(2, result.Code);
        Assert.Contains("Missing typed comparison property", result.Stderr);
    }

    [Fact]
    public async Task CompleteAuditCannotContradictItsOwnSuccessCoverage()
    {
        using var pair = await Pair.CreateAsync();
        pair.EditAfter(root => root["results"]![0]!["status"] = "unavailable");
        var result = await pair.CompareAsync();
        Assert.Equal(2, result.Code);
        Assert.Contains("complete snapshot cannot contain unavailable", result.Stderr);
    }

    private sealed class Pair : IDisposable
    {
        private readonly TargetedHealthAuditTests.Fixture _fixture = new();
        public string Directory => _fixture.DirectoryPath;
        public string Before => Path.Combine(Directory, "before-audit.json");
        public string After => Path.Combine(Directory, "after-audit.json");

        public static async Task<Pair> CreateAsync(int afterHealth = 17000, int afterPower = 75)
        {
            var pair = new Pair();
            try
            {
                pair._fixture.SetReferenceState(18208, 100, 9,
                    "2026-10-19T12:00:00.0000000+00:00");
                pair._fixture.RecreateSnapshot("2026-10-19T12:00:02Z",
                    baseline: true, completedUtc: "2026-10-19T12:00:03Z");
                var before = await pair._fixture.RunAsync(pair.Before);
                if (before.Code != 0)
                    throw new InvalidOperationException("Baseline audit failed: " + before.Stderr);

                pair._fixture.SetReferenceState(afterHealth, afterPower, 10,
                    "2026-10-19T12:00:10.0000000+00:00");
                pair._fixture.RecreateSnapshot("2026-10-19T12:00:12Z",
                    baseline: false, completedUtc: "2026-10-19T12:00:13Z");
                var after = await pair._fixture.RunAsync(pair.After);
                if (after.Code != 0)
                    throw new InvalidOperationException("Follow-up audit failed: " + after.Stderr);
                return pair;
            }
            catch
            {
                pair.Dispose();
                throw;
            }
        }

        public void EditAfter(Action<JsonNode> action) => _fixture.EditJson(After, action);

        public async Task<(int Code, string Stdout, string Stderr)> CompareAsync(
            string? output = null, string? afterOverride = null)
        {
            var args = new List<string> {
                "compare-targeted-health", "--before", Before, "--after", afterOverride ?? After
            };
            if (output != null)
            {
                args.Add("--output");
                args.Add(output);
            }
            using var stdout = new StringWriter();
            using var stderr = new StringWriter();
            var code = await CliRunner.RunAsync([.. args], stdout, stderr);
            return (code, stdout.ToString(), stderr.ToString());
        }

        public void Dispose() => _fixture.Dispose();
    }
}
