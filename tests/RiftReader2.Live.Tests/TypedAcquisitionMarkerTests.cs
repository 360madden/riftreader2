using System.Text.Json;
using RiftReader2.Infrastructure;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class TypedAcquisitionMarkerTests
{
    [Theory]
    [InlineData(false, "")]
    [InlineData(true, "")]
    [InlineData(false, ",\"marker\":null")]
    [InlineData(true, ",\"marker\":null")]
    [InlineData(false, ",\"marker\":\"unknown\"")]
    [InlineData(true, ",\"marker\":\"unknown\"")]
    public async Task MissingOrInvalidMarkerFailsBeforeOpeningProcess(bool copy, string markerProperty)
    {
        var directory = Path.Combine(Path.GetTempPath(), $"rr2-marker-{Guid.NewGuid():N}");
        Directory.CreateDirectory(directory);
        try
        {
            var request = Path.Combine(directory, "request.json");
            var output = Path.Combine(directory, "unpublished");
            // An invalid PID ensures the marker error precedes process validation/open.
            await File.WriteAllTextAsync(request, Request(copy, markerProperty));
            var options = new Dictionary<string, string> { ["--request"] = request, ["--output"] = output };
            var error = await Record.ExceptionAsync(() => copy
                ? MemoryDiscoveryCommand.ScoutCopyTypedAsync(options, TextWriter.Null, CancellationToken.None)
                : MemoryDiscoveryCommand.ScoutTypedAsync(options, TextWriter.Null, CancellationToken.None));

            Assert.NotNull(error);
            Assert.True(error is JsonException or ArgumentException, error.ToString());
            Assert.Contains("marker", error.Message, StringComparison.OrdinalIgnoreCase);
            Assert.False(File.Exists(output));
            Assert.False(Directory.Exists(output));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Theory]
    [InlineData("RR2R1|")]
    [InlineData("RRAPIVAL2|")]
    public void ExplicitProtocolSelectionSurvivesRequestDeserialization(string marker)
    {
        var markerProperty = ",\"marker\":" + JsonSerializer.Serialize(marker);
        var scout = JsonSerializer.Deserialize<TypedPrefixScoutRequest>(Request(false, markerProperty), JsonFormat.Options)!;
        var copy = JsonSerializer.Deserialize<TypedInlineCaptureRequest>(Request(true, markerProperty), JsonFormat.Options)!;

        Assert.Equal(marker, TypedApiPrefixMatcher.ValidateMarker(scout.Marker));
        Assert.Equal(marker, TypedApiPrefixMatcher.ValidateMarker(copy.Marker));
    }

    private static string Request(bool copy, string markerProperty) =>
        "{\"schemaVersion\":1,\"evidenceKind\":\"native-typed-" +
        (copy ? "inline-capture" : "prefix-scout") + "-request/1\",\"target\":{" +
        "\"processId\":0,\"processStartUtcTicks\":1,\"executableSha256\":\"" + new string('A', 64) +
        "\"},\"startAddress\":\"0x10000\",\"maxScanBytes\":65536,\"maxDurationMilliseconds\":1000," +
        "\"maxRegionCount\":128,\"maxMatchCount\":8" + (copy ? ",\"maxCopiedCandidates\":1" : "") +
        markerProperty + "}";
}
