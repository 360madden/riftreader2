using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using RiftReader2.Application;
using RiftReader2.Cli;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Tests;

public sealed class AddonGuidanceTests : IDisposable
{
    private const string Nonce = "0123456789abcdef0123456789abcdef";
    private readonly string directory = Path.Combine(Path.GetTempPath(), "rr2-guidance-" + Guid.NewGuid().ToString("N"));

    public AddonGuidanceTests() => Directory.CreateDirectory(directory);

    [Fact]
    public void CalculatesSignedVectorDistanceAndCoordinateAxisBearing()
    {
        var report = AddonGuidanceCalculator.Calculate(
            Frame(x: 10, y: 2, z: 20), "input.wire", "lab1", Nonce, 7,
            destinationX: 7, destinationY: 6, destinationZ: 24);

        Assert.Equal(-3, report.Calculation.DeltaX);
        Assert.Equal(4, report.Calculation.DeltaY);
        Assert.Equal(4, report.Calculation.VerticalDelta);
        Assert.Equal(4, report.Calculation.DeltaZ);
        Assert.Equal(5, report.Calculation.PlanarDistance);
        Assert.Equal(126.86989764584402, report.Calculation.CoordinateAxisBearingDegrees);
        Assert.Contains("not player facing", report.Calculation.BearingMeaning);
        Assert.Equal("unverified-until-addon-receipt", report.FreshnessStatus);
        Assert.Equal(
            "/rr2guide result lab1 0123456789abcdef0123456789abcdef 7 3 12 123.5 u123_ABC 10 2 20 5 -3 4 4",
            report.SlashCommand);
        Assert.True(report.SlashCommand.Length <= AddonGuidanceCalculator.MaxSlashCommandLength);
    }

    [Fact]
    public void ZeroPlanarDistanceKeepsVerticalDeltaAndHasNoBearing()
    {
        var report = AddonGuidanceCalculator.Calculate(
            Frame(x: 10, y: 2, z: 20), "input.wire", "lab2", Nonce, 1,
            destinationX: 10, destinationY: -3, destinationZ: 20);

        Assert.Equal(0, report.Calculation.PlanarDistance);
        Assert.Equal(-5, report.Calculation.DeltaY);
        Assert.Null(report.Calculation.CoordinateAxisBearingDegrees);
        Assert.EndsWith(" 0 0 0 -5", report.SlashCommand);
    }

    [Theory]
    [InlineData("other", Nonce)]
    [InlineData("lab1", "1123456789abcdef0123456789abcdef")]
    [InlineData("lab1", "not-hex")]
    public void RejectsWrongLabOrSession(string lab, string session)
    {
        Assert.ThrowsAny<ArgumentException>(() => AddonGuidanceCalculator.Calculate(
            Frame(), "input.wire", lab, session, 1, 0, 0, 0));
    }

    [Theory]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    [InlineData(10000001)]
    public void RejectsInvalidDestination(double destination)
    {
        Assert.ThrowsAny<ArgumentException>(() => AddonGuidanceCalculator.Calculate(
            Frame(), "input.wire", "lab1", Nonce, 1, destination, 0, 0));
    }

    [Fact]
    public void RejectsUnavailableSourceCoordinate()
    {
        var observation = Observation() with
        {
            Fields = Observation().Fields with { CoordX = new(AddonFieldStatus.Unavailable, null) }
        };
        Assert.Throws<InvalidDataException>(() => AddonGuidanceCalculator.Calculate(
            Frame(observation: observation), "input.wire", "lab1", Nonce, 1, 0, 0, 0));
    }

    [Fact]
    public void RejectsSourceClockAboveLuaExactIntegerRange()
    {
        var observation = Observation() with
        {
            Clock = new(AddonFieldStatus.Ok, AddonGuidanceCalculator.MaxExactInteger + 1d)
        };
        Assert.Throws<InvalidDataException>(() => AddonGuidanceCalculator.Calculate(
            Frame(observation: observation), "input.wire", "lab1", Nonce, 1, 0, 0, 0));
    }

    [Fact]
    public async Task CommandReadsStrictEnvelopeAndWritesNoOverwriteReport()
    {
        var source = Path.Combine(directory, "source.wire");
        var outputPath = Path.Combine(directory, "guidance.json");
        await File.WriteAllTextAsync(source, Envelope(), new UTF8Encoding(false));
        var options = new Dictionary<string, string>
        {
            ["--frame"] = source,
            ["--lab"] = "lab1",
            ["--session-id"] = Nonce,
            ["--result-sequence"] = "9",
            ["--destination-x"] = "13",
            ["--destination-y"] = "2",
            ["--destination-z"] = "24",
            ["--output"] = outputPath
        };
        using var output = new StringWriter();

        Assert.Equal(0, await AddonGuidanceCommand.RunAsync(options, output));
        using var json = JsonDocument.Parse(output.ToString());
        Assert.Equal("calculated-addon-guidance/1", json.RootElement.GetProperty("evidenceKind").GetString());
        Assert.Equal(5, json.RootElement.GetProperty("calculation").GetProperty("planarDistance").GetDouble());
        var saved = await File.ReadAllBytesAsync(outputPath);
        await Assert.ThrowsAsync<IOException>(() => AddonGuidanceCommand.RunAsync(options, TextWriter.Null));
        Assert.Equal(saved, await File.ReadAllBytesAsync(outputPath));
    }

    [Fact]
    public async Task CliDispatchesGuideAddonAndRejectsForeignOption()
    {
        var source = Path.Combine(directory, "cli-source.wire");
        await File.WriteAllTextAsync(source, Envelope(), new UTF8Encoding(false));
        string[] args =
        [
            "guide-addon", "--frame", source, "--lab", "lab2", "--session-id", Nonce,
            "--result-sequence", "2", "--destination-x", "13", "--destination-y", "2",
            "--destination-z", "24"
        ];
        using var output = new StringWriter();
        using var error = new StringWriter();

        Assert.Equal(0, await CliRunner.RunAsync(args, output, error));
        Assert.Empty(error.ToString());
        using var json = JsonDocument.Parse(output.ToString());
        Assert.Equal("lab2", json.RootElement.GetProperty("lab").GetString());
        Assert.StartsWith("/rr2guide result lab2 ", json.RootElement.GetProperty("slashCommand").GetString());

        output.GetStringBuilder().Clear();
        error.GetStringBuilder().Clear();
        Assert.Equal(2, await CliRunner.RunAsync([.. args, "--bogus", "value"], output, error));
        using var errorJson = JsonDocument.Parse(error.ToString());
        Assert.Equal("Unknown option '--bogus'.", errorJson.RootElement.GetProperty("error").GetString());
    }

    [Fact]
    public async Task LiveSnapshotProducesBoundProvenanceAndNoOverwriteReport()
    {
        var now = DateTimeOffset.UtcNow;
        var source = Path.Combine(directory, "latest.json");
        var destination = Path.Combine(directory, "snapshot-guidance.json");
        await File.WriteAllTextAsync(source, Snapshot(now).ToJsonString(JsonFormat.Options));
        string[] args =
        [
            "guide-addon", "--snapshot", source, "--lab", "lab1", "--session-id", Nonce,
            "--result-sequence", "4", "--destination-x", "13", "--destination-y", "2",
            "--destination-z", "24", "--output", destination
        ];
        using var output = new StringWriter();
        using var error = new StringWriter();

        Assert.Equal(0, await CliRunner.RunAsync(args, output, error));
        using var json = JsonDocument.Parse(output.ToString());
        var origin = json.RootElement.GetProperty("origin");
        Assert.Equal("live-reader-snapshot", origin.GetProperty("sourceKind").GetString());
        Assert.Equal("conditionally-fresh-at-load", origin.GetProperty("freshnessStatus").GetString());
        Assert.Equal(64, origin.GetProperty("snapshotFileSha256").GetString()!.Length);
        Assert.Equal(42, origin.GetProperty("snapshot").GetProperty("target").GetProperty("processId").GetInt32());
        Assert.Contains("does not independently prove clock synchronization",
            origin.GetProperty("snapshot").GetProperty("clockAssumption").GetString());
        var saved = await File.ReadAllBytesAsync(destination);

        Assert.Equal(2, await CliRunner.RunAsync(args, TextWriter.Null, error));
        Assert.Equal(saved, await File.ReadAllBytesAsync(destination));
    }

    [Fact]
    public async Task SnapshotGateRejectsStaleOrStoppedReader()
    {
        var now = DateTimeOffset.UtcNow;
        var source = Path.Combine(directory, "snapshot-status.json");
        await File.WriteAllTextAsync(source, Snapshot(now.AddSeconds(-3)).ToJsonString(JsonFormat.Options));
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            GuidanceSnapshotFile.ReadAsync(source, Nonce, now));

        var stopped = Snapshot(now);
        stopped["readerStatus"] = "stopped";
        await File.WriteAllTextAsync(source, stopped.ToJsonString(JsonFormat.Options));
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            GuidanceSnapshotFile.ReadAsync(source, Nonce, now));
    }

    [Fact]
    public async Task SnapshotGateRejectsWrongNonceAndIncompleteScan()
    {
        var now = DateTimeOffset.UtcNow;
        var source = Path.Combine(directory, "snapshot-nonce.json");
        var wrongNonce = Snapshot(now);
        wrongNonce["nonce"] = "1123456789abcdef0123456789abcdef";
        await File.WriteAllTextAsync(source, wrongNonce.ToJsonString(JsonFormat.Options));
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            GuidanceSnapshotFile.ReadAsync(source, Nonce, now));

        var incomplete = Snapshot(now);
        incomplete["riftReader2"]!["scan"]!["completed"] = false;
        incomplete["riftReader2"]!["scan"]!["status"] = "budget-exhausted";
        await File.WriteAllTextAsync(source, incomplete.ToJsonString(JsonFormat.Options));
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            GuidanceSnapshotFile.ReadAsync(source, Nonce, now));
    }

    [Theory]
    [InlineData("incomplete-scan")]
    [InlineData("conflict")]
    [InlineData("no-matching-candidate")]
    public async Task SnapshotGateRejectsNonSelectedStatus(string selectionStatus)
    {
        var now = DateTimeOffset.UtcNow;
        var source = Path.Combine(directory, "snapshot-selection.json");
        var value = Snapshot(now);
        value["riftReader2"]!["selectionStatus"] = selectionStatus;
        await File.WriteAllTextAsync(source, value.ToJsonString(JsonFormat.Options));

        await Assert.ThrowsAsync<InvalidDataException>(() =>
            GuidanceSnapshotFile.ReadAsync(source, Nonce, now));
    }

    [Theory]
    [InlineData("candidateSequence", 13)]
    [InlineData("candidateEpoch", 4)]
    public async Task SnapshotGateRejectsCandidateIdentityMismatch(string property, long value)
    {
        var now = DateTimeOffset.UtcNow;
        var source = Path.Combine(directory, "snapshot-candidate.json");
        var snapshot = Snapshot(now);
        snapshot["riftReader2"]![property] = value;
        await File.WriteAllTextAsync(source, snapshot.ToJsonString(JsonFormat.Options));

        await Assert.ThrowsAsync<InvalidDataException>(() =>
            GuidanceSnapshotFile.ReadAsync(source, Nonce, now));
    }

    private static LiveAddonFrame Frame(double x = 1, double y = 2, double z = 3, AddonObservation? observation = null) =>
        new(Nonce, observation ?? Observation(x, y, z), new string('A', 64), new string('B', 64));

    private static AddonObservation Observation(double x = 1, double y = 2, double z = 3) =>
        new(1, "0.1.0", 12, 3,
            new(AddonFieldStatus.Ok, 123.5),
            new(AddonFieldStatus.Ok, "u123_ABC"),
            new(
                new(AddonFieldStatus.Ok, x),
                new(AddonFieldStatus.Ok, y),
                new(AddonFieldStatus.Ok, z),
                new(AddonFieldStatus.Ok, 100),
                new(AddonFieldStatus.Ok, 100),
                new(AddonFieldStatus.Ok, false)));

    private static string Envelope()
    {
        const string inner = "{\"schemaVersion\":1,\"addonVersion\":\"0.1.0\",\"sequence\":12,\"epoch\":3,\"clock\":{\"status\":\"ok\",\"value\":123.5},\"player\":{\"status\":\"ok\",\"value\":\"u123_ABC\"},\"fields\":{\"coordX\":{\"status\":\"ok\",\"value\":10},\"coordY\":{\"status\":\"ok\",\"value\":2},\"coordZ\":{\"status\":\"ok\",\"value\":20},\"health\":{\"status\":\"ok\",\"value\":100},\"healthMax\":{\"status\":\"ok\",\"value\":100},\"combat\":{\"status\":\"ok\",\"value\":false}}}";
        return $"RR2L1|{Nonce}|RR2A1|{inner}|ENDRR2A1|ENDRR2L1";
    }

    private static JsonObject Snapshot(DateTimeOffset capturedAtUtc)
    {
        var json = $$"""
            {
              "schemaVersion": 1,
              "instanceId": "8b857427-a064-4a67-a75b-3867b65d19cd",
              "nonce": "{{Nonce}}",
              "sequence": 55,
              "capturedAtUtc": "{{capturedAtUtc.ToUniversalTime():O}}",
              "monotonicMilliseconds": 12345.5,
              "readerStatus": "running",
              "readerReason": null,
              "target": {
                "processId": 42,
                "processStartUtcTicks": 638000000000000000,
                "executablePath": "C:\\RIFT\\rift_x64.exe",
                "executableSha256": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                "readerSessionNonce": "{{Nonce}}"
              },
              "riftReader2": {
                "schemaVersion": 1,
                "bindingStatus": "bound",
                "freshnessStatus": "fresh",
                "reason": null,
                "scanStartedAtTimestamp": 100,
                "publishedAtTimestamp": 200,
                "lastAdvanceAtTimestamp": 190,
                "lastAdvanceAgeMilliseconds": 100,
                "freshnessTimeoutMilliseconds": 5000,
                "remainingFreshMilliseconds": 4900,
                "selectionStatus": "selected",
                "envelopeSha256": "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
                "addonFrameSha256": "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
                "candidateSequence": 12,
                "candidateEpoch": 3,
                "observation": {
                  "schemaVersion": 1,
                  "addonVersion": "0.1.0",
                  "sequence": 12,
                  "epoch": 3,
                  "clock": { "status": "ok", "value": 123.5 },
                  "player": { "status": "ok", "value": "u123_ABC" },
                  "fields": {
                    "coordX": { "status": "ok", "value": 10 },
                    "coordY": { "status": "ok", "value": 2 },
                    "coordZ": { "status": "ok", "value": 20 },
                    "health": { "status": "ok", "value": 100 },
                    "healthMax": { "status": "ok", "value": 100 },
                    "combat": { "status": "ok", "value": false }
                  }
                },
                "scan": {
                  "status": "complete",
                  "completed": true,
                  "plannedBytes": 1000,
                  "scannedBytes": 1000,
                  "regionCount": 3,
                  "elapsedMilliseconds": 25,
                  "endpointCandidateCount": 2,
                  "malformedCandidateCount": 0,
                  "matchingCandidateCount": 1,
                  "identicalCopyCount": 1,
                  "reason": null
                }
              },
              "delivery": { "enabled": false, "status": "disabled", "endpoint": null, "lastSuccessUtc": null, "error": null },
              "nativePower": { "status": "unavailable", "value": null }
            }
            """;
        return JsonNode.Parse(json)!.AsObject();
    }

    public void Dispose() => Directory.Delete(directory, recursive: true);
}
