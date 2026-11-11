using System.Text.Json;
using RiftReader2.Cli;

namespace RiftReader2.Tests;

public sealed class NativeVitalsComparisonCliTests
{
    [Fact]
    public async Task ComputesNetChangeNotRegenerationAndKeepsMissingNull()
    {
        var dir = MakeDir();
        try
        {
            var before = Write(dir, "before.json", Sample("2026-11-10T23:00:00Z", 100, 90));
            var after = Write(dir, "after.json", Sample("2026-11-10T23:00:10Z", 120, 70));
            var (code, output, error) = await Run(before, after);
            Assert.Equal(0, code);
            Assert.Empty(error);
            using var json = JsonDocument.Parse(output);
            var root = json.RootElement;
            Assert.Equal("candidate-only", root.GetProperty("status").GetString());
            Assert.True(root.GetProperty("identity").GetProperty("sameProcessEpoch").GetBoolean());
            Assert.Equal(JsonValueKind.Null, root.GetProperty("resourceKindCandidates").GetProperty("same").ValueKind);
            Assert.Equal(10, root.GetProperty("intervalSeconds").GetDecimal());
            Assert.Equal(2, root.GetProperty("summary").GetProperty("changedResources").GetInt32());
            var resources = root.GetProperty("resources");
            Assert.Equal(20, resources.GetProperty("health").GetProperty("netChange").GetInt64());
            Assert.Equal(2, resources.GetProperty("health").GetProperty("netChangePerSecondCandidate").GetDecimal());
            Assert.Equal(-20, resources.GetProperty("energy").GetProperty("netChange").GetInt64());
            Assert.Equal(-2, resources.GetProperty("energy").GetProperty("netChangePerSecondCandidate").GetDecimal());
            Assert.Equal("unavailable", resources.GetProperty("mana").GetProperty("status").GetString());
            Assert.Equal(JsonValueKind.Null, resources.GetProperty("mana").GetProperty("netChange").ValueKind);
        }
        finally { Directory.Delete(dir, true); }
    }

    [Fact]
    public async Task MissingResourceAfterwardDoesNotFabricateZero()
    {
        var dir = MakeDir();
        try
        {
            var before = Write(dir, "before.json", Sample("2026-11-10T23:00:00Z", 100, 90));
            var after = Write(dir, "after.json", Sample("2026-11-10T23:00:10Z", 100, null));
            var (code, output, _) = await Run(before, after);
            Assert.Equal(0, code);
            using var json = JsonDocument.Parse(output);
            var energy = json.RootElement.GetProperty("resources").GetProperty("energy");
            Assert.Equal("unavailable", energy.GetProperty("status").GetString());
            Assert.Equal(90, energy.GetProperty("beforeCurrent").GetInt64());
            Assert.Equal(JsonValueKind.Null, energy.GetProperty("afterCurrent").ValueKind);
            Assert.Equal(JsonValueKind.Null, energy.GetProperty("netChangePerSecondCandidate").ValueKind);
        }
        finally { Directory.Delete(dir, true); }
    }

    [Fact]
    public async Task UnavailableResourceMayCarryNativeDiagnosticInputs()
    {
        var dir = MakeDir();
        try
        {
            var before = Write(dir, "before.json", Sample("2026-11-10T23:00:00Z", 100, 90));
            var after = Write(dir, "after.json", Sample("2026-11-10T23:00:10Z", 100, null,
                diagnosticUnavailable: true));
            var (code, output, error) = await Run(before, after);
            Assert.Equal(0, code);
            Assert.Empty(error);
            using var json = JsonDocument.Parse(output);
            var energy = json.RootElement.GetProperty("resources").GetProperty("energy");
            Assert.Equal("unavailable", energy.GetProperty("status").GetString());
            Assert.Equal("revision-mismatch-needs-native-cache-write",
                energy.GetProperty("afterUnavailableReason").GetString());
            Assert.Equal(JsonValueKind.Null, energy.GetProperty("netChange").ValueKind);
        }
        finally { Directory.Delete(dir, true); }
    }

    [Fact]
    public async Task ComparesOptionalNativeResourceKindWithoutAssumingItsMeaning()
    {
        var dir = MakeDir();
        try
        {
            var before = Write(dir, "before.json", Sample("2026-11-10T23:00:00Z", 100, null, resourceKind: 2));
            var after = Write(dir, "after.json", Sample("2026-11-10T23:00:10Z", 100, null, resourceKind: 5));
            var (code, output, _) = await Run(before, after);
            Assert.Equal(0, code);
            using var json = JsonDocument.Parse(output);
            var kinds = json.RootElement.GetProperty("resourceKindCandidates");
            Assert.Equal(2, kinds.GetProperty("before").GetInt32());
            Assert.Equal(5, kinds.GetProperty("after").GetInt32());
            Assert.False(kinds.GetProperty("same").GetBoolean());
            Assert.Equal(0, json.RootElement.GetProperty("summary").GetProperty("changedResources").GetInt32());
        }
        finally { Directory.Delete(dir, true); }
    }

    [Fact]
    public async Task RejectsTypedEnergyThatContradictsDeclaredResourceKind()
    {
        var dir = MakeDir();
        try
        {
            var before = Write(dir, "before.json", Sample("2026-11-10T23:00:00Z", 100, 90,
                resourceKind: 3));
            var after = Write(dir, "after.json", Sample("2026-11-10T23:00:10Z", 100, 90,
                resourceKind: 3));
            var (code, _, error) = await Run(before, after);
            Assert.Equal(2, code);
            Assert.Contains("resource kind", error, StringComparison.OrdinalIgnoreCase);
        }
        finally { Directory.Delete(dir, true); }
    }

    [Fact]
    public async Task RejectsDifferentPlayerAndReversedObservation()
    {
        var dir = MakeDir();
        try
        {
            var before = Write(dir, "before.json", Sample("2026-11-10T23:00:00Z", 100, 90));
            var different = Write(dir, "different.json", Sample("2026-11-10T23:00:10Z", 120, 70, unitKey: 99));
            Assert.Equal(2, (await Run(before, different)).Code);
            var backward = Write(dir, "backward.json", Sample("2026-11-10T22:59:00Z", 120, 70));
            Assert.Equal(2, (await Run(before, backward)).Code);
            Assert.Equal(2, (await Run(before, before)).Code);
        }
        finally { Directory.Delete(dir, true); }
    }

    [Fact]
    public async Task OutputFileIsWriteOnce()
    {
        var dir = MakeDir();
        try
        {
            var before = Write(dir, "before.json", Sample("2026-11-10T23:00:00Z", 100, 90));
            var after = Write(dir, "after.json", Sample("2026-11-10T23:00:10Z", 120, 70));
            var output = Path.Combine(dir, "comparison.json");
            Assert.Equal(0, (await Run(before, after, output)).Code);
            var original = await File.ReadAllBytesAsync(output);
            Assert.Equal(2, (await Run(before, after, output)).Code);
            Assert.Equal(original, await File.ReadAllBytesAsync(output));
        }
        finally { Directory.Delete(dir, true); }
    }

    private static object Sample(string instant, long health, long? energy, ulong unitKey = 42,
        bool diagnosticUnavailable = false, int? resourceKind = null)
    {
        object present(long value, long maximum, string? type = null) =>
            new { status = "calculated-candidate", unavailableReason = (string?)null,
                current = (long?)value, maximum = (long?)maximum,
                inputs = type is null ? (object)new { baseRaw = value } :
                    new { verifiedTypeCode = type } };
        object missing(string reason) =>
            new { status = "unavailable", unavailableReason = (string?)reason,
                current = (long?)null, maximum = (long?)null, inputs = (object?)null };
        return new
        {
            schemaVersion = 1, contractVersion = "native-current-vitals-candidate-sample/2",
            status = "complete", sourceBuildSha256 = new string('A', 64),
            source = "native-process-memory",
            qualification = "candidate-only; semantics/passive-freshness/restart-unverified",
            observation = new
            {
                identity = new { processId = 123, processStartUtcTicks = 456L,
                    executableSha256 = new string('A', 64) },
                startedAtUtc = instant, completedAtUtc = instant, unitKey,
                resourceKindCandidate = resourceKind,
                source = "native-process-memory",
                qualification = "candidate-only; semantics/passive-freshness/restart-unverified",
                health = present(health, 150), mana = missing("not-mana-kind-three"),
                energy = energy.HasValue ? present(energy.Value, 100, "0x072B") :
                    diagnosticUnavailable ? new
                    {
                        status = "unavailable", unavailableReason = "revision-mismatch-needs-native-cache-write",
                        current = (long?)null, maximum = (long?)null,
                        inputs = (object?)new { baseRaw = 90, recordRevision = 1, wrapperRevision = 2 }
                    } : missing("not-energy-kind-four")
            }
        };
    }

    private static string MakeDir()
    {
        var path = Path.Combine(Path.GetTempPath(), "rr2-vitals-compare-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(path);
        return path;
    }
    private static string Write(string dir, string name, object payload)
    {
        var path = Path.Combine(dir, name);
        File.WriteAllText(path, JsonSerializer.Serialize(payload));
        return path;
    }
    private static async Task<(int Code, string Output, string Error)> Run(
        string before, string after, string? outputPath = null)
    {
        using var stdout = new StringWriter();
        using var stderr = new StringWriter();
        var args = new List<string> { "compare-native-vitals", "--before", before, "--after", after };
        if (outputPath is not null) { args.Add("--output"); args.Add(outputPath); }
        var code = await CliRunner.RunAsync([.. args], stdout, stderr);
        return (code, stdout.ToString(), stderr.ToString());
    }
}
