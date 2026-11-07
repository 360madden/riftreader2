using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;
using RiftReader2.Infrastructure;
using RiftReader2.Live.Control;
using Xunit.Abstractions;

namespace RiftReader2.Live.Tests;

public sealed class ControlCaptureRetentionTests(ITestOutputHelper output)
{
    private static readonly JsonSerializerOptions Wire = new(JsonFormat.Options) { WriteIndented = false };

    [Fact]
    public void TypedCapturePreservesExactWirePropertiesAndRetainsAllMetadata()
    {
        var capture = Capture("aW1hZ2U=");
        var original = new
        {
            captureId = capture.CaptureId,
            target = capture.Target,
            imageFormat = capture.ImageFormat,
            imageBase64 = capture.ImageBase64,
            sha256 = capture.Sha256,
            capturedAtUtc = capture.CapturedAtUtc,
            reviewExpiresInSeconds = capture.ReviewExpiresInSeconds,
            captureBackend = capture.CaptureBackend
        };
        Assert.Equal(JsonSerializer.Serialize(original, Wire), JsonSerializer.Serialize(capture, Wire));
        var expected = JsonSerializer.SerializeToNode(original, Wire)!.AsObject();
        expected.Remove("imageBase64");
        var retained = ControlAgent.RetainResponsePayload(capture);
        Assert.True(JsonNode.DeepEquals(expected, retained));
        Assert.Equal(JsonSerializer.Serialize(capture.Target, Wire), retained!["target"]!.ToJsonString(Wire));
    }

    [Fact]
    public void GenericPayloadStillStripsArmTokenAndImageWithoutChangingOtherMetadata()
    {
        var payload = new { armToken = "private", imageBase64 = "private-image", captureId = "review", target = Capture("").Target };
        var retained = ControlAgent.RetainResponsePayload(payload)!.AsObject();
        Assert.False(retained.ContainsKey("armToken"));
        Assert.False(retained.ContainsKey("imageBase64"));
        Assert.Equal("review", retained["captureId"]!.GetValue<string>());
        Assert.Equal(JsonSerializer.Serialize(payload.target, Wire), retained["target"]!.ToJsonString(Wire));
    }

    [Fact]
    public void LargeCaptureRetentionBenchmarkReportsEquivalentMetadataAndAllocations()
    {
        // Offline microbenchmark of journal preparation only; excludes capture,
        // disk and wire serialization. No timing threshold makes CI flaky.
        var capture = Capture(new string('A', 5 * 1024 * 1024));
        JsonNode Legacy()
        {
            var node = JsonNode.Parse(JsonSerializer.Serialize(capture, Wire))!.AsObject();
            node.Remove("armToken");
            node.Remove("imageBase64");
            return node;
        }
        Assert.True(JsonNode.DeepEquals(Legacy(), ControlAgent.RetainResponsePayload(capture)));
        Measure("legacy serialize/parse/remove", () => Legacy());
        Measure("metadata serialize-to-node", () => ControlAgent.RetainResponsePayload(capture));
    }

    private void Measure(string label, Func<JsonNode?> operation)
    {
        const int iterations = 5;
        operation();
        var allocated = GC.GetAllocatedBytesForCurrentThread();
        var started = Stopwatch.GetTimestamp();
        for (var index = 0; index < iterations; index++)
            Assert.False(operation()!.AsObject().ContainsKey("imageBase64"));
        var milliseconds = Stopwatch.GetElapsedTime(started).TotalMilliseconds;
        allocated = GC.GetAllocatedBytesForCurrentThread() - allocated;
        output.WriteLine($"{label}: {iterations} iterations; {milliseconds / iterations:F3} ms/op; {allocated / iterations:N0} allocated bytes/op");
    }

    private static ControlCaptureResponse Capture(string image) => new("capture-id",
        new("RIFT-LAB-2", 123, 456, "0x123", @"C:\RIFT\rift_x64.exe", new string('F', 64), true, 1, 2, 1280, 720),
        "bmp", image, new string('A', 64), new DateTimeOffset(2026, 11, 7, 1, 2, 3, TimeSpan.Zero),
        45, "window-client-gdi-unqualified-until-visual-review");
}
