using System.Text.Json;
using RiftReader2.Cli;

namespace RiftReader2.Tests;

public sealed class NativeStatsComparisonCliTests
{
    private static readonly (string Name, int Selector)[] Fields =
        [("armor", 37), ("powerAttack", 24), ("powerSpell", 32), ("critAttack", 26), ("critSpell", 33)];

    [Fact]
    public async Task CalculatesCandidateDeltasWithoutConvertingUnavailableToZero()
    {
        var dir = NewDirectory();
        try
        {
            var before = Save(dir, "before.json", Snapshot(100, "2026-11-07T21:00:00Z"));
            var after = Save(dir, "after.json", Snapshot(110, "2026-11-07T21:01:00Z"));
            var (code, json, error) = await Run(before, after);
            Assert.Equal(0, code);
            Assert.Empty(error);
            using var result = JsonDocument.Parse(json);
            var root = result.RootElement;
            Assert.Equal("candidate-only", root.GetProperty("status").GetString());
            Assert.True(root.GetProperty("identity").GetProperty("sameProcessEpoch").GetBoolean());
            Assert.Equal(5, root.GetProperty("summary").GetProperty("comparedSelectors").GetInt32());
            Assert.Equal(1, root.GetProperty("summary").GetProperty("changedSelectors").GetInt32());
            Assert.Equal(1, root.GetProperty("summary").GetProperty("changedValues").GetInt32());
            Assert.Equal(1, root.GetProperty("summary").GetProperty("changedSpreads").GetInt32());
            Assert.Equal(2, root.GetProperty("summary").GetProperty("unavailablePairs").GetInt32());
            var rows = root.GetProperty("stats");
            Assert.Equal(10, rows[0].GetProperty("ordinary").GetProperty("delta").GetInt32());
            Assert.Equal(0, rows[0].GetProperty("unbuffed").GetProperty("delta").GetInt32());
            var spread = rows[0].GetProperty("ordinaryMinusUnbuffed");
            Assert.Equal(0, spread.GetProperty("before").GetInt32());
            Assert.Equal(10, spread.GetProperty("after").GetInt32());
            Assert.Equal(10, spread.GetProperty("delta").GetInt32());
            Assert.Equal("unavailable", rows[1].GetProperty("ordinaryMinusUnbuffed").GetProperty("status").GetString());
            Assert.Equal("unavailable", rows[1].GetProperty("ordinary").GetProperty("status").GetString());
            Assert.Equal(JsonValueKind.Null, rows[1].GetProperty("ordinary").GetProperty("delta").ValueKind);
        }
        finally { Directory.Delete(dir, recursive: true); }
    }

    [Fact]
    public async Task ReportsCrossEpochWithoutClaimingRestartQualification()
    {
        var dir = NewDirectory();
        try
        {
            var before = Save(dir, "before.json", Snapshot(100, "2026-11-07T21:00:00Z"));
            var after = Save(dir, "after.json", Snapshot(110, "2026-11-08T21:00:00Z", pid: 456, ticks: 789));
            var (code, json, _) = await Run(before, after);
            Assert.Equal(0, code);
            using var result = JsonDocument.Parse(json);
            Assert.False(result.RootElement.GetProperty("identity").GetProperty("sameProcessEpoch").GetBoolean());
            Assert.Equal("candidate-only", result.RootElement.GetProperty("status").GetString());
        }
        finally { Directory.Delete(dir, recursive: true); }
    }

    [Fact]
    public async Task RejectsDifferentPlayerAndSameSourceFile()
    {
        var dir = NewDirectory();
        try
        {
            var before = Save(dir, "before.json", Snapshot(100, "2026-11-07T21:00:00Z"));
            var after = Save(dir, "after.json", Snapshot(110, "2026-11-07T21:01:00Z", unitKey: 999));
            var (code, json, error) = await Run(before, after);
            Assert.Equal(2, code);
            Assert.Empty(json);
            Assert.Contains("matching game build and player key", error);
            var same = await Run(before, before);
            Assert.Equal(2, same.Code);
        }
        finally { Directory.Delete(dir, recursive: true); }
    }

    [Fact]
    public async Task ReportsSelectorMappingDriftSeparatelyFromRawValueChanges()
    {
        var dir = NewDirectory();
        try
        {
            var before = Save(dir, "before.json", Snapshot(100, "2026-11-07T21:00:00Z"));
            var after = Save(dir, "after.json",
                Snapshot(100, "2026-11-07T21:01:00Z", armorMappedIndex: 17));
            var (code, json, error) = await Run(before, after);
            Assert.Equal(0, code);
            Assert.Empty(error);
            using var result = JsonDocument.Parse(json);
            Assert.Equal(1, result.RootElement.GetProperty("summary").GetProperty("changedMappings").GetInt32());
            Assert.Equal(0, result.RootElement.GetProperty("summary").GetProperty("changedValues").GetInt32());
            Assert.True(result.RootElement.GetProperty("stats")[0].GetProperty("mappedIndexChanged").GetBoolean());
            Assert.False(result.RootElement.GetProperty("stats")[2].GetProperty("mappedIndexChanged").GetBoolean());
        }
        finally { Directory.Delete(dir, recursive: true); }
    }

    [Fact]
    public async Task RejectsOverlappingAcquisitionIntervals()
    {
        var dir = NewDirectory();
        try
        {
            var before = Save(dir, "before.json", Snapshot(100, "2026-11-07T21:00:00Z",
                completedAt: "2026-11-07T21:02:00Z"));
            var after = Save(dir, "after.json", Snapshot(101, "2026-11-07T21:01:00Z"));
            var (code, json, error) = await Run(before, after);
            Assert.Equal(2, code);
            Assert.Empty(json);
            Assert.Contains("nonoverlapping chronological order", error);
        }
        finally { Directory.Delete(dir, recursive: true); }
    }

    [Fact]
    public async Task SavedOutputIsNeverOverwritten()
    {
        var dir = NewDirectory();
        try
        {
            var before = Save(dir, "before.json", Snapshot(100, "2026-11-07T21:00:00Z"));
            var after = Save(dir, "after.json", Snapshot(110, "2026-11-07T21:01:00Z"));
            var destination = Path.Combine(dir, "comparison.json");
            var first = await Run(before, after, destination);
            Assert.Equal(0, first.Code);
            var bytes = await File.ReadAllBytesAsync(destination);
            var second = await Run(before, after, destination);
            Assert.Equal(2, second.Code);
            Assert.Equal(bytes, await File.ReadAllBytesAsync(destination));
        }
        finally { Directory.Delete(dir, recursive: true); }
    }

    private static object Snapshot(long armor, string observedAt, int pid = 123, long ticks = 456,
        ulong unitKey = 42, int? armorMappedIndex = null, string? completedAt = null)
    {
        var rows = Fields.Select((f, i) => new
        {
            name = f.Name, selector = f.Selector,
            mappedIndex = i == 1 ? -1 : i == 0 && armorMappedIndex.HasValue ? armorMappedIndex.Value : i,
            ordinary = new
            {
                status = i == 1 ? "index-unavailable" : "raw-candidate",
                rawSigned64 = i == 1 ? (long?)null : i == 0 ? armor : 10L
            },
            unbuffed = new
            {
                status = i == 1 ? "index-unavailable" : "raw-candidate",
                rawSigned64 = i == 1 ? (long?)null : 100L
            }
        }).ToArray();
        return new
        {
            schemaVersion = 1, contractVersion = "native-current-stats-candidate/1", status = "complete",
            observation = new
            {
                identity = new { processId = pid, processStartUtcTicks = ticks,
                    executableSha256 = new string('A', 64) },
                startedAtUtc = observedAt, completedAtUtc = completedAt ?? observedAt, unitKey, stats = rows
            }
        };
    }

    private static string NewDirectory()
    {
        var dir = Path.Combine(Path.GetTempPath(), "rr2-stats-comparison-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        return dir;
    }

    private static string Save(string dir, string name, object content)
    {
        var path = Path.Combine(dir, name);
        File.WriteAllText(path, JsonSerializer.Serialize(content));
        return path;
    }

    private static async Task<(int Code, string Json, string Error)> Run(string before, string after, string? destination = null)
    {
        using var output = new StringWriter();
        using var error = new StringWriter();
        var args = new List<string> { "compare-native-stats", "--before", before, "--after", after };
        if (destination is not null) { args.Add("--output"); args.Add(destination); }
        var code = await CliRunner.RunAsync([.. args], output, error);
        return (code, output.ToString(), error.ToString());
    }
}
