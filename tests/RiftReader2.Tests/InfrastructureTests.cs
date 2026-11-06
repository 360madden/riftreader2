using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Tests;

public sealed class InfrastructureTests
{
    private const string BuildSha256 = "0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF";
    private const string SessionId = "fixture-session";

    [Fact]
    public async Task CaptureReader_ReadsVerifiedFixtureAndReportsManifestIdentity()
    {
        using var directory = new TemporaryDirectory();
        var fixture = CreateFixture(directory.Path, ValidSampleLine + "\n");

        await using var reader = await CaptureReader.OpenAsync(fixture.ManifestPath, 1024 * 1024);
        var samples = await ReadAllAsync(reader);

        var expectedManifestHash = Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(fixture.ManifestPath)));
        Assert.Equal(expectedManifestHash, reader.ManifestSha256);
        Assert.Equal(fixture.SamplesSha256, reader.Manifest.SamplesSha256);
        Assert.Equal("synthetic", reader.Manifest.SourceKind);
        Assert.Equal("synthetic-units", reader.Manifest.PositionUnits);
        Assert.Equal("xz-horizontal-y-up", reader.Manifest.CoordinateFrame);
        Assert.Equal("session-monotonic-seconds", reader.Manifest.ClockBasis);
        Assert.Null(reader.Manifest.TimingUncertaintySeconds);
        var sample = Assert.Single(samples);
        Assert.Equal(SessionId, sample.SessionId);
        Assert.Equal(7, sample.Sequence);
        Assert.Equal(12.5, sample.TimestampSeconds);
        Assert.Equal(1.25, sample.X);
        Assert.Equal(-2.5, sample.Y);
        Assert.Equal(3.75, sample.Z);
        Assert.Equal(0.5, sample.YawRadians);
    }

    [Fact]
    public async Task CaptureReader_RejectsUnsupportedManifestSchema()
    {
        using var directory = new TemporaryDirectory();
        var fixture = CreateFixture(directory.Path, ValidSampleLine + "\n", schemaVersion: 2);

        var error = await Assert.ThrowsAsync<InvalidDataException>(
            () => CaptureReader.OpenAsync(fixture.ManifestPath, 1024 * 1024));

        Assert.Contains("schema", error.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData("{\"schemaVersion\":1,\"buildSha256\":\"0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF\",\"sessionId\":\"fixture-session\",\"samplesFile\":\"samples.ndjson\"}")]
    [InlineData("{\"schemaVersion\":1,\"buildSha256\":\"0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF\",\"sessionId\":\"fixture-session\",\"samplesFile\":\"samples.ndjson\",\"samplesSha256\":\"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\"}")]
    [InlineData("{\"schemaVersion\":1,\"buildSha256\":\"0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF\",\"sessionId\":\"fixture-session\",\"samplesFile\":\"samples.ndjson\",\"samplesSha256\":\"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\",\"sourceKind\":\"synthetic\",\"positionUnits\":\"synthetic-units\",\"coordinateFrame\":\"xz-horizontal-y-up\",\"clockBasis\":\"session-monotonic-seconds\"}")]
    [InlineData("{\"schemaVersion\":1,\"buildSha256\":\"0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF\",\"sessionId\":\"fixture-session\",\"samplesFile\":\"samples.ndjson\",\"samplesSha256\":\"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\",\"unexpected\":true}")]
    [InlineData("{\"schemaVersion\":1,\"schemaVersion\":1,\"buildSha256\":\"0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF\",\"sessionId\":\"fixture-session\",\"samplesFile\":\"samples.ndjson\",\"samplesSha256\":\"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\"}")]
    public async Task CaptureReader_RejectsMissingUnknownOrDuplicateManifestFields(string manifestJson)
    {
        using var directory = new TemporaryDirectory();
        var manifestPath = System.IO.Path.Combine(directory.Path, "manifest.json");
        await WriteUtf8Async(manifestPath, manifestJson);

        await Assert.ThrowsAsync<JsonException>(
            () => CaptureReader.OpenAsync(manifestPath, 1024 * 1024));
    }

    [Theory]
    [InlineData("unknown", "synthetic-units", "xz-horizontal-y-up", "session-monotonic-seconds", null)]
    [InlineData("synthetic", "", "xz-horizontal-y-up", "session-monotonic-seconds", null)]
    [InlineData("synthetic", "                                                                    ", "xz-horizontal-y-up", "session-monotonic-seconds", null)]
    [InlineData("synthetic", "synthetic-units", "xyz", "session-monotonic-seconds", null)]
    [InlineData("synthetic", "synthetic-units", "xz-horizontal-y-up", "wall-clock", null)]
    [InlineData("synthetic", "synthetic-units", "xz-horizontal-y-up", "session-monotonic-seconds", -0.001)]
    [InlineData("synthetic", "synthetic-units", "xz-horizontal-y-up", "session-monotonic-seconds", double.PositiveInfinity)]
    public void CaptureManifest_RejectsInvalidRequiredMetadata(
        string sourceKind,
        string positionUnits,
        string coordinateFrame,
        string clockBasis,
        double? timingUncertaintySeconds)
    {
        var manifest = new CaptureManifest(
            1,
            BuildSha256,
            SessionId,
            "samples.ndjson",
            new string('A', 64),
            sourceKind,
            positionUnits,
            coordinateFrame,
            clockBasis,
            timingUncertaintySeconds);

        Assert.Throws<InvalidDataException>(manifest.Validate);
    }

    [Fact]
    public void CaptureManifest_AcceptsKnownAndFiniteTimingUncertainty()
    {
        var manifest = new CaptureManifest(
            1,
            BuildSha256,
            SessionId,
            "samples.ndjson",
            new string('A', 64),
            "rift-recording",
            "synthetic-units",
            "xz-horizontal-y-up",
            "session-monotonic-seconds",
            0.002);

        manifest.Validate();
    }

    [Fact]
    public void CaptureManifest_RejectsPositionUnitsLongerThan64Characters()
    {
        var manifest = new CaptureManifest(
            1,
            BuildSha256,
            SessionId,
            "samples.ndjson",
            new string('A', 64),
            "synthetic",
            new string('u', 65),
            "xz-horizontal-y-up",
            "session-monotonic-seconds",
            null);

        Assert.Throws<InvalidDataException>(manifest.Validate);
    }

    [Fact]
    public async Task CaptureReader_RejectsCaptureHashMismatch()
    {
        using var directory = new TemporaryDirectory();
        var fixture = CreateFixture(directory.Path, ValidSampleLine + "\n", samplesSha256: new string('0', 64));

        var error = await Assert.ThrowsAsync<InvalidDataException>(
            () => CaptureReader.OpenAsync(fixture.ManifestPath, 1024 * 1024));

        Assert.Contains("SHA-256", error.Message);
    }

    [Theory]
    [InlineData("../samples.ndjson")]
    [InlineData("subdir/samples.ndjson")]
    [InlineData("C:\\samples.ndjson")]
    public async Task CaptureReader_RejectsSamplesPathTraversalOrDirectories(string samplesFile)
    {
        using var directory = new TemporaryDirectory();
        var fixture = CreateFixture(directory.Path, ValidSampleLine + "\n", samplesFile: samplesFile);

        var error = await Assert.ThrowsAsync<InvalidDataException>(
            () => CaptureReader.OpenAsync(fixture.ManifestPath, 1024 * 1024));

        Assert.Contains("plain filename", error.Message);
    }

    [Fact]
    public async Task CaptureReader_RejectsSampleFromAnotherSession()
    {
        using var directory = new TemporaryDirectory();
        var fixture = CreateFixture(directory.Path, ValidSampleLine.Replace(SessionId, "other-session") + "\n");
        await using var reader = await CaptureReader.OpenAsync(fixture.ManifestPath, 1024 * 1024);

        var error = await Assert.ThrowsAsync<InvalidDataException>(() => ReadAllAsync(reader));

        Assert.Contains("different session", error.Message);
    }

    [Fact]
    public async Task CaptureReader_RejectsCaptureLargerThanConfiguredLimit()
    {
        using var directory = new TemporaryDirectory();
        var fixture = CreateFixture(directory.Path, ValidSampleLine + "\n");
        var captureLength = new FileInfo(fixture.SamplesPath).Length;

        var error = await Assert.ThrowsAsync<InvalidDataException>(
            () => CaptureReader.OpenAsync(fixture.ManifestPath, captureLength - 1));

        Assert.Contains("exceeds", error.Message);
    }

    [Fact]
    public async Task CaptureReader_RejectsSampleLineLongerThanLimit()
    {
        using var directory = new TemporaryDirectory();
        var fixture = CreateFixture(directory.Path, ValidSampleLine + new string(' ', 17_000) + "\n");
        await using var reader = await CaptureReader.OpenAsync(fixture.ManifestPath, 1024 * 1024);

        var error = await Assert.ThrowsAsync<InvalidDataException>(() => ReadAllAsync(reader));

        Assert.Contains("exceeds 16384", error.Message);
    }

    [Fact]
    public async Task CaptureReader_RejectsInvalidUtf8()
    {
        using var directory = new TemporaryDirectory();
        var bytes = Encoding.UTF8.GetBytes(ValidSampleLine + "\n").Concat(new byte[] { 0xC3, 0x28 }).ToArray();
        var fixture = CreateFixture(directory.Path, bytes);
        await using var reader = await CaptureReader.OpenAsync(fixture.ManifestPath, 1024 * 1024);

        await Assert.ThrowsAsync<DecoderFallbackException>(() => ReadAllAsync(reader));
    }

    [Theory]
    [InlineData("{\"sessionId\":\"fixture-session\",\"sequence\":7,\"timestampSeconds\":12.5,\"x\":1.25,\"y\":-2.5,\"z\":3.75}")]
    [InlineData("{\"sessionId\":\"fixture-session\",\"sequence\":7,\"timestampSeconds\":12.5,\"x\":1.25,\"y\":-2.5,\"z\":3.75,\"yawRadians\":0.5,\"unexpected\":true}")]
    [InlineData("{\"sessionId\":\"fixture-session\",\"sequence\":7,\"sequence\":7,\"timestampSeconds\":12.5,\"x\":1.25,\"y\":-2.5,\"z\":3.75,\"yawRadians\":0.5}")]
    public async Task CaptureReader_RejectsMissingUnknownOrDuplicateSampleFields(string sampleJson)
    {
        using var directory = new TemporaryDirectory();
        var fixture = CreateFixture(directory.Path, sampleJson + "\n");
        await using var reader = await CaptureReader.OpenAsync(fixture.ManifestPath, 1024 * 1024);

        var error = await Assert.ThrowsAsync<InvalidDataException>(() => ReadAllAsync(reader));

        Assert.IsType<JsonException>(error.InnerException);
    }

    [Fact]
    public async Task JsonReportWriter_DoesNotOverwriteExistingEvidenceAndRemovesTemporaryFile()
    {
        using var directory = new TemporaryDirectory();
        var reportPath = System.IO.Path.Combine(directory.Path, "report.json");
        await WriteUtf8Async(reportPath, "original evidence");

        await Assert.ThrowsAsync<IOException>(
            () => JsonReportWriter.WriteNewAsync(reportPath, new { result = 42 }));

        Assert.Equal("original evidence", await File.ReadAllTextAsync(reportPath));
        Assert.Empty(Directory.EnumerateFiles(directory.Path, ".report.json.*.tmp"));
    }

    [Fact]
    public async Task JsonReportWriter_CancellationLeavesNoReportOrTemporaryFile()
    {
        using var directory = new TemporaryDirectory();
        var reportPath = System.IO.Path.Combine(directory.Path, "report.json");
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            () => JsonReportWriter.WriteNewAsync(reportPath, new { result = 42 }, cancellation.Token));

        Assert.False(File.Exists(reportPath));
        Assert.Empty(Directory.EnumerateFiles(directory.Path, ".report.json.*.tmp"));
    }

    [Fact]
    public async Task JsonReportWriter_PublishesCompleteJson()
    {
        using var directory = new TemporaryDirectory();
        var reportPath = System.IO.Path.Combine(directory.Path, "nested", "report.json");

        await JsonReportWriter.WriteNewAsync(reportPath, new AnalysisOptions(0.5, 123));

        using var document = JsonDocument.Parse(await File.ReadAllBytesAsync(reportPath));
        Assert.Equal(0.5, document.RootElement.GetProperty("maxGapSeconds").GetDouble());
        Assert.Equal(123, document.RootElement.GetProperty("maxSamples").GetInt32());
        Assert.Empty(Directory.EnumerateFiles(System.IO.Path.GetDirectoryName(reportPath)!, ".report.json.*.tmp"));
    }

    [Theory]
    [InlineData(0, 0.25, 100, 1024)]
    [InlineData(2, 0.25, 100, 1024)]
    [InlineData(1, 0.0, 100, 1024)]
    [InlineData(1, double.NaN, 100, 1024)]
    [InlineData(1, 0.25, 1, 1024)]
    [InlineData(1, 0.25, 100, 0)]
    [InlineData(1, 0.25, 100, 8589934593L)]
    public void ReaderConfiguration_RejectsInvalidBounds(
        int schemaVersion,
        double maxGapSeconds,
        int maxSamples,
        long maxCaptureBytes)
    {
        var configuration = new ReaderConfiguration(
            schemaVersion,
            new AnalysisOptions(maxGapSeconds, maxSamples),
            maxCaptureBytes);

        Assert.Throws<InvalidDataException>(configuration.Validate);
    }

    [Fact]
    public void ReaderConfiguration_AcceptsInclusiveCaptureBounds()
    {
        new ReaderConfiguration(1, new AnalysisOptions(), 1).Validate();
        new ReaderConfiguration(1, new AnalysisOptions(), 8L * 1024 * 1024 * 1024).Validate();
    }

    [Fact]
    public async Task ReaderConfiguration_LoadsStrictValidJson()
    {
        using var directory = new TemporaryDirectory();
        var path = System.IO.Path.Combine(directory.Path, "reader.json");
        await WriteUtf8Async(
            path,
            "{\"schemaVersion\":1,\"analysis\":{\"maxGapSeconds\":0.4,\"maxSamples\":250},\"maxCaptureBytes\":4096}");

        var configuration = await ReaderConfiguration.LoadAsync(path);

        Assert.Equal(0.4, configuration.Analysis.MaxGapSeconds);
        Assert.Equal(250, configuration.Analysis.MaxSamples);
        Assert.Equal(4096, configuration.MaxCaptureBytes);
    }

    private const string ValidSampleLine =
        "{\"sessionId\":\"fixture-session\",\"sequence\":7,\"timestampSeconds\":12.5,\"x\":1.25,\"y\":-2.5,\"z\":3.75,\"yawRadians\":0.5}";

    [Theory]
    [InlineData("{}")]
    [InlineData("{\"maxGapSeconds\":0.25}")]
    [InlineData("{\"maxSamples\":100}")]
    [InlineData("{\"maxGapSeconds\":0.25,\"maxSamples\":100,\"typo\":1}")]
    [InlineData("{\"maxGapSeconds\":0.25,\"maxSamples\":100,\"maxSamples\":200}")]
    [InlineData("null")]
    public async Task ConfigurationNeverSilentlyDefaultsMissingOrAmbiguousSettings(string analysis)
    {
        using var directory = new TemporaryDirectory();
        var path = System.IO.Path.Combine(directory.Path, "config.json");
        await WriteUtf8Async(path, "{\"schemaVersion\":1,\"analysis\":" + analysis + ",\"maxCaptureBytes\":1024}");
        await Assert.ThrowsAsync<JsonException>(() => ReaderConfiguration.LoadAsync(path));
    }

    private static CaptureFixture CreateFixture(
        string directory,
        string samples,
        int schemaVersion = 1,
        string samplesFile = "samples.ndjson",
        string? samplesSha256 = null,
        double? timingUncertaintySeconds = null) =>
        CreateFixture(
            directory,
            new UTF8Encoding(false).GetBytes(samples),
            schemaVersion,
            samplesFile,
            samplesSha256,
            timingUncertaintySeconds);

    private static CaptureFixture CreateFixture(
        string directory,
        byte[] samples,
        int schemaVersion = 1,
        string samplesFile = "samples.ndjson",
        string? samplesSha256 = null,
        double? timingUncertaintySeconds = null)
    {
        // Keep the actual fixture beside the manifest even when testing a rejected manifest path.
        var samplesPath = System.IO.Path.Combine(directory, "samples.ndjson");
        File.WriteAllBytes(samplesPath, samples);
        var actualSamplesHash = Convert.ToHexString(SHA256.HashData(samples));
        var manifestPath = System.IO.Path.Combine(directory, "manifest.json");
        var timingUncertaintyJson = timingUncertaintySeconds is null
            ? "null"
            : timingUncertaintySeconds.Value.ToString(System.Globalization.CultureInfo.InvariantCulture);
        var manifestJson =
            $"{{\"schemaVersion\":{schemaVersion},\"buildSha256\":\"{BuildSha256}\",\"sessionId\":\"{SessionId}\",\"samplesFile\":{JsonSerializer.Serialize(samplesFile)},\"samplesSha256\":\"{samplesSha256 ?? actualSamplesHash}\",\"sourceKind\":\"synthetic\",\"positionUnits\":\"synthetic-units\",\"coordinateFrame\":\"xz-horizontal-y-up\",\"clockBasis\":\"session-monotonic-seconds\",\"timingUncertaintySeconds\":{timingUncertaintyJson}}}";
        File.WriteAllText(manifestPath, manifestJson, new UTF8Encoding(false));
        return new CaptureFixture(manifestPath, samplesPath, actualSamplesHash);
    }

    private static async Task<List<MotionSample>> ReadAllAsync(CaptureReader reader)
    {
        var samples = new List<MotionSample>();
        await foreach (var sample in reader.ReadSamplesAsync())
            samples.Add(sample);
        return samples;
    }

    private static Task WriteUtf8Async(string path, string text) =>
        File.WriteAllTextAsync(path, text, new UTF8Encoding(false));

    private sealed record CaptureFixture(string ManifestPath, string SamplesPath, string SamplesSha256);

    private sealed class TemporaryDirectory : IDisposable
    {
        public TemporaryDirectory()
        {
            Path = System.IO.Path.Combine(System.IO.Path.GetTempPath(), $"riftreader2-tests-{Guid.NewGuid():N}");
            Directory.CreateDirectory(Path);
        }

        public string Path { get; }

        public void Dispose()
        {
            if (Directory.Exists(Path))
                Directory.Delete(Path, recursive: true);
        }
    }
}
