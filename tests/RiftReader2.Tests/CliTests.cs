using RiftReader2.Cli;
using System.Text.Json;

namespace RiftReader2.Tests;

public sealed class CliTests
{
    [Fact]
    public async Task SuccessfulReportPreservesVersionOneContractAndImplementationIdentity()
    {
        using var output = new StringWriter();
        using var error = new StringWriter();
        var manifest = Path.Combine(AppContext.BaseDirectory, "Fixtures", "demo", "capture.json");
        Assert.Equal(0, await CliRunner.RunAsync(["analyze", "--manifest", manifest], output, error));
        Assert.Empty(error.ToString());
        using var json = JsonDocument.Parse(output.ToString());
        var report = json.RootElement;
        Assert.Equal(["schemaVersion", "analyzerVersion", "evidenceKind", "implementation", "input", "configuration", "summary"],
            report.EnumerateObject().Select(x => x.Name).ToArray());
        Assert.Equal(1, report.GetProperty("schemaVersion").GetInt32());
        Assert.Equal("motion-derived/1", report.GetProperty("analyzerVersion").GetString());
        Assert.Equal("derived-motion", report.GetProperty("evidenceKind").GetString());
        var identity = report.GetProperty("implementation").GetProperty("assemblySha256");
        Assert.Equal(["RiftReader2.Application", "RiftReader2.Cli", "RiftReader2.Domain", "RiftReader2.Infrastructure"],
            identity.EnumerateObject().Select(x => x.Name).ToArray());
        Assert.All(identity.EnumerateObject(), item => Assert.Matches("^[A-F0-9]{64}$", item.Value.GetString()!));
        var input = report.GetProperty("input");
        Assert.Equal(["manifestSha256", "samplesSha256", "samplesHashVerification", "declaredBuildSha256", "buildIdentityVerification", "sessionId", "sourceKind", "positionUnits", "coordinateFrame", "clockBasis", "timingUncertaintySeconds"],
            input.EnumerateObject().Select(x => x.Name).ToArray());
        Assert.Equal(["maxGapSeconds", "maxSamples", "maxCaptureBytes"],
            report.GetProperty("configuration").EnumerateObject().Select(x => x.Name).ToArray());
        Assert.Equal(["sessionId", "sampleCount", "firstSequence", "lastSequence", "startTimestampSeconds", "endTimestampSeconds", "durationSeconds", "missingSequenceCount", "sequenceGapCount", "timingGapCount", "derivedIntervalCount", "skippedDerivativeIntervalCount", "maxHorizontalDerivedSpeed", "maxAbsoluteDerivedYawRate"],
            report.GetProperty("summary").EnumerateObject().Select(x => x.Name).ToArray());
        Assert.Equal("declared-only", input.GetProperty("buildIdentityVerification").GetString());
        Assert.Equal("verified", input.GetProperty("samplesHashVerification").GetString());
        Assert.Equal("synthetic", input.GetProperty("sourceKind").GetString());
        Assert.Equal(5, report.GetProperty("summary").GetProperty("sampleCount").GetInt32());
    }

    [Theory]
    [InlineData("unknown")]
    [InlineData("analyze")]
    [InlineData("analyze", "--manifest")]
    [InlineData("analyze", "--typo", "capture.json")]
    [InlineData("analyze", "--manifest", "one", "--manifest", "two")]
    [InlineData("validate-capture", "--output", "result.json")]
    public async Task InvalidArgumentsFailWithoutOutput(params string[] args)
    {
        using var output = new StringWriter();
        using var error = new StringWriter();
        Assert.Equal(2, await CliRunner.RunAsync(args, output, error));
        Assert.Empty(output.ToString());
        Assert.Contains("error", error.ToString());
    }

    [Fact]
    public async Task HelpDoesNotRequireConfigurationOrCapture()
    {
        using var output = new StringWriter();
        using var error = new StringWriter();
        Assert.Equal(0, await CliRunner.RunAsync(["--help"], output, error));
        Assert.Contains("validate-capture", output.ToString());
        Assert.Empty(error.ToString());
    }
}
