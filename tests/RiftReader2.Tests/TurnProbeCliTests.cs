using System.Text.Json;
using RiftReader2.Cli;

namespace RiftReader2.Tests;

public sealed class TurnProbeCliTests : IDisposable
{
    private readonly string directory = Path.Combine(Path.GetTempPath(), "rr2-turn-" + Guid.NewGuid().ToString("N"));

    public TurnProbeCliTests() => Directory.CreateDirectory(directory);

    private async Task<(string Before, string After, string Receipt)> EvidenceAsync(
        double afterDegrees = 16, ulong afterComponent = 0x12345678, double observedHold = 120)
    {
        const string qualification = "matrix-descriptor-candidate-only; body-facing/axis/sign/passive-freshness/restart-unverified";
        object Sample(double angle, ulong component, string start, string end)
        {
            var radians = angle * Math.PI / 180;
            var cosine = (float)Math.Cos(radians);
            var sine = (float)Math.Sin(radians);
            float[] cells = [cosine, 0, -sine, 0, 1, 0, sine, 0, cosine];
            return new
            {
                identity = new
                {
                    processId = 1234,
                    processStartUtcTicks = 639298670575905950L,
                    executableSha256 = new string('A', 64),
                    moduleBaseAddress = 0x140000000UL,
                    moduleSize = 50_000_000L
                },
                startedAtUtc = start,
                completedAtUtc = end,
                unitKey = "123456",
                componentAddress = component,
                qualification,
                primary = new
                {
                    status = "structural-y-planar-matrix-candidate",
                    sourceOffset = 0x60,
                    planarAngleDegreesCandidate = angle,
                    rawBits = cells.Select(BitConverter.SingleToUInt32Bits).ToArray(),
                    rowMajorF32 = cells
                }
            };
        }
        var beforePath = Path.Combine(directory, "before.json");
        var afterPath = Path.Combine(directory, "after.json");
        var receiptPath = Path.Combine(directory, "action.json");
        await File.WriteAllTextAsync(beforePath, JsonSerializer.Serialize(
            Sample(10, 0x12345678, "2026-11-10T09:00:00Z", "2026-11-10T09:00:00.100Z")));
        await File.WriteAllTextAsync(afterPath, JsonSerializer.Serialize(
            Sample(afterDegrees, afterComponent, "2026-11-10T09:00:00.700Z", "2026-11-10T09:00:00.800Z")));
        var receipt = new
        {
            action = new { keys = new[] { "a" }, holdMilliseconds = 100 },
            target = new
            {
                processId = 1234,
                processStartUtcTicks = 639298670575905950L,
                executableSha256 = new string('A', 64)
            },
            result = new
            {
                deliverySucceeded = true,
                releaseSucceeded = true,
                cancelled = false,
                targetLost = false,
                stateUncertain = false,
                requiresCallerDisarm = false
            },
            inputEvents = new object[]
            {
                new { kind = "keyDownInserted", value = "a", elapsedMilliseconds = 11.3 },
                new { kind = "keyUpInserted", value = "a", elapsedMilliseconds = 11.3 + observedHold }
            },
            recoveryRequired = false,
            startedAtUtc = "2026-11-10T09:00:00.200Z",
            completedAtUtc = "2026-11-10T09:00:00.600Z"
        };
        await File.WriteAllTextAsync(receiptPath, JsonSerializer.Serialize(receipt));
        return (beforePath, afterPath, receiptPath);
    }

    private async Task<(string Before, string After, string Receipt)> ActorEvidenceAsync()
    {
        var paths = await EvidenceAsync();
        const string qualification = "actor/model/render-matrix-candidate-only; body-facing, source freshness, input response and restart unverified";
        object Matrix(double degrees, int offset)
        {
            var radians = degrees * Math.PI / 180;
            var cosine = (float)Math.Cos(radians);
            var sine = (float)Math.Sin(radians);
            float[] cells = [cosine, 0, -sine, 0, 1, 0, sine, 0, cosine];
            return new
            {
                status = "structural-y-planar-matrix-candidate",
                sourceOffset = offset,
                planarAngleDegreesCandidate = degrees,
                rawBits = cells.Select(BitConverter.SingleToUInt32Bits).ToArray(),
                rowMajorF32 = cells
            };
        }
        object Sample(double degrees, string start, string end) => new
        {
            identity = new
            {
                processId = 1234,
                processStartUtcTicks = 639298670575905950L,
                executableSha256 = new string('A', 64),
                moduleBaseAddress = 0x140000000UL,
                moduleSize = 50_000_000L
            },
            startedAtUtc = start, completedAtUtc = end,
            playerKeyDecimal = "123456",
            actorComponentDecimal = "305419896",
            actorHeadingQualified = false,
            qualification,
            actorMatrix = Matrix(degrees, 0x398),
            modelMatrix = Matrix(degrees, 0x3EC)
        };
        await File.WriteAllTextAsync(paths.Before, JsonSerializer.Serialize(
            Sample(10, "2026-11-10T09:00:00Z", "2026-11-10T09:00:00.100Z")));
        await File.WriteAllTextAsync(paths.After, JsonSerializer.Serialize(
            Sample(16, "2026-11-10T09:00:00.700Z", "2026-11-10T09:00:00.800Z")));
        return paths;
    }

    private static string[] Args((string Before, string After, string Receipt) paths, string uncontaminated = "true") =>
        ["analyze-turn-probe", "--before", paths.Before, "--after", paths.After,
         "--receipt", paths.Receipt, "--matrix", "primary", "--uncontaminated", uncontaminated];

    [Fact]
    public async Task ProducesMeasuredHoldCandidateRateWithoutClaimingActorHeading()
    {
        var paths = await EvidenceAsync();
        using var output = new StringWriter();
        using var error = new StringWriter();
        Assert.Equal(0, await CliRunner.RunAsync(Args(paths), output, error));
        Assert.Empty(error.ToString());
        using var report = JsonDocument.Parse(output.ToString());
        var root = report.RootElement;
        Assert.Equal("candidate-rate-observed", root.GetProperty("status").GetString());
        Assert.Equal(120.0, root.GetProperty("observedKeyHoldMilliseconds").GetDouble(), 8);
        Assert.Equal(50, root.GetProperty("calibration").GetProperty("candidateDegreesPerSecond").GetDouble(), 8);
        Assert.False(root.GetProperty("actorHeadingQualified").GetBoolean());
    }

    [Fact]
    public async Task RefusesCalibrationWhenOperatorReportsContaminationOrTimingDrifts()
    {
        var paths = await EvidenceAsync();
        using var contaminated = new StringWriter();
        Assert.Equal(0, await CliRunner.RunAsync(Args(paths, "false"), contaminated, TextWriter.Null));
        using var first = JsonDocument.Parse(contaminated.ToString());
        Assert.Equal("contaminated-input-window", first.RootElement.GetProperty("status").GetString());
        Assert.Equal(JsonValueKind.Null, first.RootElement.GetProperty("calibration").ValueKind);

        var drift = await EvidenceAsync(observedHold: 180);
        using var invalid = new StringWriter();
        Assert.Equal(0, await CliRunner.RunAsync(Args(drift), invalid, TextWriter.Null));
        using var second = JsonDocument.Parse(invalid.ToString());
        Assert.Equal("observed-key-hold-invalid", second.RootElement.GetProperty("status").GetString());
    }

    [Fact]
    public async Task CandidateCalibrationPlansOneBoundedPulseWithoutExecutingIt()
    {
        var paths = await EvidenceAsync();
        using var output = new StringWriter();
        Assert.Equal(0, await CliRunner.RunAsync(
            [.. Args(paths), "--target-degrees", "30"], output, TextWriter.Null));
        using var report = JsonDocument.Parse(output.ToString());
        var next = report.RootElement.GetProperty("nextCandidatePulse");
        Assert.Equal("one-bounded-pulse-candidate", next.GetProperty("status").GetString());
        Assert.Equal("a", next.GetProperty("key").GetString());
        Assert.Equal(125, next.GetProperty("holdMilliseconds").GetInt32());
        Assert.False(report.RootElement.GetProperty("actorHeadingQualified").GetBoolean());

        using var contaminated = new StringWriter();
        Assert.Equal(0, await CliRunner.RunAsync(
            [.. Args(paths, "false"), "--target-degrees", "30"], contaminated, TextWriter.Null));
        using var blocked = JsonDocument.Parse(contaminated.ToString());
        Assert.Equal(JsonValueKind.Null, blocked.RootElement.GetProperty("nextCandidatePulse").ValueKind);

        Assert.Equal(2, await CliRunner.RunAsync(
            [.. Args(paths), "--target-degrees", "NaN"], TextWriter.Null, TextWriter.Null));
    }

    [Fact]
    public async Task RejectsInputEventsOutsideTheActionReceiptWindow()
    {
        var paths = await EvidenceAsync();
        var receipt = await File.ReadAllTextAsync(paths.Receipt);
        var impossible = receipt.Replace("\"completedAtUtc\":\"2026-11-10T09:00:00.600Z\"",
            "\"completedAtUtc\":\"2026-11-10T09:00:00.250Z\"", StringComparison.Ordinal);
        Assert.NotEqual(receipt, impossible);
        await File.WriteAllTextAsync(paths.Receipt, impossible);
        using var error = new StringWriter();
        Assert.Equal(2, await CliRunner.RunAsync(Args(paths), TextWriter.Null, error));
        Assert.Contains("action receipt duration", error.ToString());
    }

    [Fact]
    public async Task RefusesTurnReceiptFromAnotherGameProcessOrBuild()
    {
        var paths = await EvidenceAsync();
        var original = await File.ReadAllTextAsync(paths.Receipt);
        foreach (var (expected, replacement) in new[]
        {
            ("\"processId\":1234", "\"processId\":1235"),
            ("\"processStartUtcTicks\":639298670575905950", "\"processStartUtcTicks\":639298670575905951"),
            ("\"executableSha256\":\"" + new string('A', 64) + "\"",
                "\"executableSha256\":\"" + new string('B', 64) + "\"")
        })
        {
            var changed = original.Replace(expected, replacement, StringComparison.Ordinal);
            Assert.NotEqual(original, changed);
            await File.WriteAllTextAsync(paths.Receipt, changed);
            using var error = new StringWriter();
            Assert.Equal(2, await CliRunner.RunAsync(Args(paths), TextWriter.Null, error));
            Assert.Contains("receipt target", error.ToString());
        }
    }

    [Fact]
    public async Task RejectsChangedComponentIdentity()
    {
        var paths = await EvidenceAsync(afterComponent: 0x87654321);
        using var error = new StringWriter();
        Assert.Equal(2, await CliRunner.RunAsync(Args(paths), TextWriter.Null, error));
        Assert.Contains("candidate-component", error.ToString());
    }

    [Fact]
    public async Task RejectsStoredAngleThatContradictsRawMatrixBits()
    {
        var paths = await EvidenceAsync();
        var raw = await File.ReadAllTextAsync(paths.After);
        var tampered = raw.Replace("\"planarAngleDegreesCandidate\":16",
            "\"planarAngleDegreesCandidate\":17", StringComparison.Ordinal);
        Assert.NotEqual(raw, tampered);
        await File.WriteAllTextAsync(paths.After, tampered);
        using var error = new StringWriter();
        Assert.Equal(2, await CliRunner.RunAsync(Args(paths), TextWriter.Null, error));
        Assert.Contains("raw matrix", error.ToString());
    }

    [Theory]
    [InlineData("actor")]
    [InlineData("model")]
    public async Task ConsumesCurrentActorPoseBeforeAfterWithReleaseReceipt(string matrix)
    {
        var paths = await ActorEvidenceAsync();
        var args = Args(paths).Select(value => value == "primary" ? matrix : value).ToArray();
        using var output = new StringWriter();
        using var error = new StringWriter();
        Assert.Equal(0, await CliRunner.RunAsync(args, output, error));
        Assert.Empty(error.ToString());
        using var report = JsonDocument.Parse(output.ToString());
        var root = report.RootElement;
        Assert.Equal(matrix, root.GetProperty("matrix").GetString());
        Assert.Equal("candidate-rate-observed", root.GetProperty("status").GetString());
        Assert.Equal(6, root.GetProperty("signedCandidateDeltaDegrees").GetDouble(), 6);
        Assert.Equal(50, root.GetProperty("calibration").GetProperty("candidateDegreesPerSecond").GetDouble(), 6);
        Assert.False(root.GetProperty("actorHeadingQualified").GetBoolean());
    }

    [Fact]
    public async Task RejectsActorPoseOwnerDriftOrClaimedQualifiedHeading()
    {
        var paths = await ActorEvidenceAsync();
        var args = Args(paths).Select(value => value == "primary" ? "actor" : value).ToArray();
        var before = await File.ReadAllTextAsync(paths.Before);
        var after = await File.ReadAllTextAsync(paths.After);
        await File.WriteAllTextAsync(paths.After,
            after.Replace("\"actorComponentDecimal\":\"305419896\"",
                          "\"actorComponentDecimal\":\"305419904\"", StringComparison.Ordinal));
        using (var changedOwnerError = new StringWriter())
        {
            Assert.Equal(2, await CliRunner.RunAsync(args, TextWriter.Null, changedOwnerError));
            Assert.Contains("candidate-component", changedOwnerError.ToString());
        }

        await File.WriteAllTextAsync(paths.After, after);
        await File.WriteAllTextAsync(paths.Before,
            before.Replace("\"actorHeadingQualified\":false",
                           "\"actorHeadingQualified\":true", StringComparison.Ordinal));
        using var falselyQualifiedError = new StringWriter();
        Assert.Equal(2, await CliRunner.RunAsync(args, TextWriter.Null, falselyQualifiedError));
        Assert.Contains("unqualified current-build actor-pose", falselyQualifiedError.ToString());
    }

    public void Dispose()
    {
        if (Directory.Exists(directory))
            Directory.Delete(directory, recursive: true);
    }
}
