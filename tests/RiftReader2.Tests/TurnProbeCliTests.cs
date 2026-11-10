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

    public void Dispose()
    {
        if (Directory.Exists(directory))
            Directory.Delete(directory, recursive: true);
    }
}
