using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Tests;

public sealed class WallMotionReplayTests
{
    private static readonly DateTimeOffset Origin = DateTimeOffset.Parse("2026-10-18T20:00:00Z");
    private const string Sha256 = "0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF";

    [Fact]
    public async Task Analyzer_ReproducesFreeTravelAndTwoDecisiveWallDisagreements()
    {
        var trials = new[]
        {
            Trial("free", "free-travel", 1, 2),
            Trial("wall-a", "wall-contact", 3, 4),
            Trial("wall-b", "wall-contact", 5, 6)
        };
        var samples = new[]
        {
            Sample(1, 0.95, 0, 0, 2, 0), Sample(2, 1, 0, 0, 2, 0),
            Sample(3, 1.5, 1, 0, 2, 0), Sample(4, 2, 2, 0, 2, 0),
            Sample(5, 2.95, 2, 0, 1, 1), Sample(6, 3, 2, 0, 1, 1),
            Sample(7, 3.5, 2.5, -0.5, 1, 1), Sample(8, 4, 3, -1, 1, 1),
            Sample(9, 4.95, 3, -1, 1, 1), Sample(10, 5, 3, -1, 1, 1),
            Sample(11, 5.5, 3.5, -1.5, 1, 1), Sample(12, 6, 4, -2, 1, 1)
        };

        var result = await new WallMotionReplayAnalyzer().AnalyzeAsync(
            ToAsync(samples), trials, new(100, 500));

        Assert.True(result.ReproducedSavedConclusion);
        Assert.Equal("unknown-unconstrained-projection", result.ProjectionSemantic);
        Assert.Equal("rejected-as-realized-velocity", result.RealizedVelocity);
        Assert.Equal("free-travel-plausible", result.Trials[0].Classification);
        Assert.All(result.Trials.Skip(1), trial => Assert.Equal("decisive-wall-disagreement", trial.Classification));
        Assert.Equal([2.0, 0.0], result.Trials[0].ActualDeltaXz);
        Assert.Equal(0, result.Trials[0].ProjectedVectorErrorFractionOfActualDisplacement, 12);
        Assert.Equal(90, result.Trials[1].DirectionErrorDegrees, 10);
    }

    [Fact]
    public async Task Analyzer_HandlesLargeFiniteAlignedVectorsWithoutOverflow()
    {
        var result = await new WallMotionReplayAnalyzer().AnalyzeAsync(
            ToAsync(ExtremeFreeTravelSamples(0, 5e199, 1e200, 1e200)),
            StandardTrials(), new(100, 500));

        Assert.Equal("free-travel-plausible", result.Trials[0].Classification);
        Assert.Equal(0, result.Trials[0].DirectionErrorDegrees, 10);
        Assert.Equal(0, result.Trials[0].ProjectedVectorErrorFractionOfActualDisplacement, 10);
    }

    [Fact]
    public async Task Analyzer_RejectsFiniteCoordinatesWhoseDeltaOverflows()
    {
        var error = await Assert.ThrowsAsync<InvalidDataException>(() =>
            new WallMotionReplayAnalyzer().AnalyzeAsync(
                ToAsync(ExtremeFreeTravelSamples(-double.MaxValue, 0, double.MaxValue, 1)),
                StandardTrials(), new(100, 500)));

        Assert.Contains("nonfinite realized displacement", error.Message);
    }

    private static WallMotionTrial[] StandardTrials() =>
    [
        Trial("free", "free-travel", 1, 2),
        Trial("wall-a", "wall-contact", 3, 4),
        Trial("wall-b", "wall-contact", 5, 6)
    ];

    private static WallMotionSample[] ExtremeFreeTravelSamples(
        double beforeX, double middleX, double afterX, double projectedX) =>
    [
        Sample(1, 0.95, beforeX, 0, projectedX, 0),
        Sample(2, 1, beforeX, 0, projectedX, 0),
        Sample(3, 1.5, middleX, 0, projectedX, 0),
        Sample(4, 2, afterX, 0, projectedX, 0),
        Sample(5, 2.95, 2, 0, 1, 1),
        Sample(6, 3, 2, 0, 1, 1),
        Sample(7, 3.5, 2.5, -0.5, 1, 1),
        Sample(8, 4, 3, -1, 1, 1),
        Sample(9, 4.95, 3, -1, 1, 1),
        Sample(10, 5, 3, -1, 1, 1),
        Sample(11, 5.5, 3.5, -1.5, 1, 1),
        Sample(12, 6, 4, -2, 1, 1)
    ];

    [Fact]
    public async Task Analyzer_RejectsAProjectionGapThatCouldHideMotion()
    {
        var trials = new[]
        {
            Trial("free", "free-travel", 1, 2),
            Trial("wall-a", "wall-contact", 3, 4),
            Trial("wall-b", "wall-contact", 5, 6)
        };
        var samples = new[]
        {
            Sample(1, 0.99, 0, 0, 1, 0), Sample(2, 1, 0, 0, 1, 0), Sample(3, 2, 1, 0, 1, 0),
            Sample(4, 3, 1, 0, 1, 1), Sample(5, 4, 2, -1, 1, 1),
            Sample(6, 5, 2, -1, 1, 1), Sample(7, 6, 3, -2, 1, 1)
        };

        var error = await Assert.ThrowsAsync<InvalidDataException>(() =>
            new WallMotionReplayAnalyzer().AnalyzeAsync(ToAsync(samples), trials, new(100, 100)));

        Assert.Contains("projection sample-gap", error.Message);
    }

    [Fact]
    public async Task Analyzer_RejectsRunTimingThatDisagreesWithObservedHold()
    {
        var trials = new[]
        {
            Trial("free", "free-travel", 1, 2) with { ObservedHoldMilliseconds = 900 },
            Trial("wall-a", "wall-contact", 3, 4),
            Trial("wall-b", "wall-contact", 5, 6)
        };

        var error = await Assert.ThrowsAsync<InvalidDataException>(() =>
            new WallMotionReplayAnalyzer().AnalyzeAsync(ToAsync([]), trials, new()));

        Assert.Contains("observed hold", error.Message);
    }

    [Fact]
    public async Task Reader_RejectsSourceHashMismatchBeforeParsingEvidence()
    {
        using var directory = new TemporaryDirectory();
        var source = Path.Combine(directory.Path, "samples.jsonl");
        await File.WriteAllTextAsync(source, "x", new UTF8Encoding(false));
        var manifest = CreateManifest(source, 1, new string('0', 64), directory.Path);

        var error = await Assert.ThrowsAsync<InvalidDataException>(() => WallMotionEvidenceReader.OpenAsync(manifest));

        Assert.Contains("SHA-256", error.Message);
    }

    [Fact]
    public async Task Reader_RejectsRunBoundToAnotherObserver()
    {
        using var directory = new TemporaryDirectory();
        var source = Path.Combine(directory.Path, "samples.jsonl");
        await File.WriteAllTextAsync(source, "x", new UTF8Encoding(false));
        var sourceHash = Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(source)));
        var manifest = CreateManifest(source, 1, sourceHash, directory.Path, runObserver: "other-observer");

        var error = await Assert.ThrowsAsync<InvalidDataException>(() => WallMotionEvidenceReader.OpenAsync(manifest));

        Assert.Contains("observerInstanceId", error.Message);
    }

    [Fact]
    public async Task Reader_RejectsDifferentSubmicrosecondRunProcessIdentity()
    {
        using var directory = new TemporaryDirectory();
        var source = Path.Combine(directory.Path, "samples.jsonl");
        await File.WriteAllTextAsync(source, "x", new UTF8Encoding(false));
        var sourceHash = Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(source)));
        var expectedStart = Origin.AddTicks(7);
        var manifest = CreateManifest(
            source, 1, sourceHash, directory.Path,
            expectedProcessStart: expectedStart,
            runProcessStart: Origin.AddTicks(3));

        var error = await Assert.ThrowsAsync<InvalidDataException>(() => WallMotionEvidenceReader.OpenAsync(manifest));

        Assert.Contains("gameProcessStartUtc", error.Message);
    }

    [Fact]
    public async Task Reader_ParsesOneBoundedVerifiedSample()
    {
        using var directory = new TemporaryDirectory();
        var source = Path.Combine(directory.Path, "samples.jsonl");
        await File.WriteAllTextAsync(source, CreateSampleJson() + "\n", new UTF8Encoding(false));
        var sourceBytes = await File.ReadAllBytesAsync(source);
        var manifest = CreateManifest(source, sourceBytes.Length, Convert.ToHexString(SHA256.HashData(sourceBytes)), directory.Path);
        await using var reader = await WallMotionEvidenceReader.OpenAsync(manifest);

        var samples = new List<WallMotionSample>();
        await foreach (var sample in reader.ReadSamplesAsync())
            samples.Add(sample);

        var actual = Assert.Single(samples);
        Assert.Equal(1, actual.Sequence);
        Assert.Equal(2, actual.ProjectionX);
        Assert.Equal(3, actual.ProjectionZ);
    }

    [Theory]
    [InlineData("duplicate")]
    [InlineData("offset")]
    [InlineData("length")]
    public async Task Reader_RejectsDuplicateOrInconsistentSampleMetadata(string corruption)
    {
        using var directory = new TemporaryDirectory();
        var source = Path.Combine(directory.Path, "samples.jsonl");
        var sample = corruption switch
        {
            "duplicate" => "{\"instanceId\":\"expected-observer\"," + CreateSampleJson()[1..],
            "offset" => CreateSampleJson(offset: "0x1"),
            "length" => CreateSampleJson(byteLength: 227),
            _ => throw new InvalidOperationException()
        };
        await File.WriteAllTextAsync(source, sample + "\n", new UTF8Encoding(false));
        var sourceBytes = await File.ReadAllBytesAsync(source);
        var manifest = CreateManifest(source, sourceBytes.Length, Convert.ToHexString(SHA256.HashData(sourceBytes)), directory.Path);
        await using var reader = await WallMotionEvidenceReader.OpenAsync(manifest);

        var error = await Assert.ThrowsAsync<InvalidDataException>(async () =>
        {
            await foreach (var _ in reader.ReadSamplesAsync())
            {
            }
        });

        Assert.Contains("wall-motion", error.Message, StringComparison.OrdinalIgnoreCase);
    }

    private static WallMotionTrial Trial(string phase, string role, double down, double up) =>
        new(phase, role, Origin.AddSeconds(down), Origin.AddSeconds(up), (up - down) * 1000, false, Sha256);

    private static WallMotionSample Sample(long sequence, double seconds, double x, double z, double projectionX, double projectionZ) =>
        new(sequence, Origin.AddSeconds(seconds), seconds * 1000, x, z, projectionX, projectionZ);

    private static async IAsyncEnumerable<WallMotionSample> ToAsync(IEnumerable<WallMotionSample> samples)
    {
        foreach (var sample in samples)
        {
            await Task.Yield();
            yield return sample;
        }
    }

    private static string CreateManifest(
        string source,
        long sourceLength,
        string sourceHash,
        string directory,
        string runObserver = "expected-observer",
        DateTimeOffset? expectedProcessStart = null,
        DateTimeOffset? runProcessStart = null)
    {
        var expectedStart = expectedProcessStart ?? Origin;
        var identity = new WallMotionExpectedIdentity("expected-observer", 42, expectedStart, Sha256, "0x1234");
        var runJson = JsonSerializer.SerializeToUtf8Bytes(new
        {
            schemaVersion = 1,
            status = "passed",
            key = "w",
            inputSent = true,
            releaseSent = true,
            gameResponseVerified = false,
            guestBinding = new
            {
                observerInstanceId = runObserver,
                gameProcessId = 42,
                gameProcessStartUtc = runProcessStart ?? expectedStart,
                gameSha256 = Sha256
            },
            keyDownSentAtUtc = Origin.AddSeconds(1),
            keyUpSentAtUtc = Origin.AddSeconds(2),
            observedHoldMs = 1000.0
        }, JsonFormat.Options);
        var artifacts = new List<WallMotionRunArtifact>();
        foreach (var (phase, role) in new[] { ("free", "free-travel"), ("wall-a", "wall-contact"), ("wall-b", "wall-contact") })
        {
            var file = phase + ".json";
            File.WriteAllBytes(Path.Combine(directory, file), runJson);
            artifacts.Add(new(phase, role, file, runJson.Length, Convert.ToHexString(SHA256.HashData(runJson))));
        }
        var manifest = new WallMotionEvidenceManifest(
            1, "v1-wall-motion", source, sourceLength, sourceHash, 1, 4096, identity, 100, 100, artifacts);
        var path = Path.Combine(directory, "manifest.json");
        File.WriteAllText(path, JsonSerializer.Serialize(manifest, JsonFormat.Options), new UTF8Encoding(false));
        return path;
    }

    private static string CreateSampleJson(string offset = "0x0", int byteLength = 228)
    {
        var data = new byte[228];
        BitConverter.GetBytes(2f).CopyTo(data, 0xD8);
        BitConverter.GetBytes(3f).CopyTo(data, 0xE0);
        return JsonSerializer.Serialize(new
        {
            instanceId = "expected-observer",
            rootRva = "0x1234",
            target = new { processId = 42, processStartUtc = Origin, executableSha256 = Sha256 },
            buildIdentity = new { executableSha256 = Sha256 },
            sample = new
            {
                schemaVersion = 1,
                sequence = 1,
                capturedAtUtc = Origin.AddSeconds(1),
                monotonicMilliseconds = 1.0,
                status = "passed",
                blockers = Array.Empty<string>(),
                coordinate = new { x = 10.0, y = 20.0, z = 30.0 },
                windows = new[]
                {
                    new
                    {
                        pointerOffset = "0x3F8/0x78/0x30",
                        offset,
                        byteLength,
                        dataBase64 = Convert.ToBase64String(data)
                    }
                }
            }
        }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false });
    }

    private sealed class TemporaryDirectory : IDisposable
    {
        public TemporaryDirectory()
        {
            Path = System.IO.Path.Combine(System.IO.Path.GetTempPath(), $"riftreader2-wall-tests-{Guid.NewGuid():N}");
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
