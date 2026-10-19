using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Tests;

public sealed class AddonDecoderTests
{
    public static IEnumerable<object[]> AcceptedCases()
    {
        using var document = JsonDocument.Parse(File.ReadAllBytes(FixturePath("cases.json")));
        foreach (var testCase in document.RootElement.EnumerateArray())
        {
            yield return
            [
                testCase.GetProperty("name").GetString()!,
                testCase.GetProperty("expected").GetRawText()
            ];
        }
    }

    public static IEnumerable<object[]> RejectedCases()
    {
        using var document = JsonDocument.Parse(File.ReadAllBytes(FixturePath("rejected.json")));
        foreach (var testCase in document.RootElement.EnumerateArray())
        {
            yield return
            [
                testCase.GetProperty("name").GetString()!,
                testCase.GetProperty("wire").GetString()!
            ];
        }
    }

    [Theory]
    [MemberData(nameof(AcceptedCases))]
    public void Decode_AcceptsSharedObservationCases(string name, string expectedJson)
    {
        _ = name;
        var frame = Frame(expectedJson);

        var report = AddonDecodedReport.FromFrame(frame);

        Assert.Equal(1, report.SchemaVersion);
        Assert.Equal("addon-api-reference", report.EvidenceKind);
        Assert.Equal("unbound", report.BindingStatus);
        Assert.Equal("unverified", report.FreshnessStatus);
        Assert.Equal(Convert.ToHexString(SHA256.HashData(frame)), report.FrameSha256);
        using var expected = JsonDocument.Parse(expectedJson);
        var actual = JsonSerializer.SerializeToElement(report.Observation, JsonFormat.Options);
        Assert.True(JsonElement.DeepEquals(expected.RootElement, actual));
    }

    [Theory]
    [MemberData(nameof(RejectedCases))]
    public void Decode_RejectsSharedMalformedFrames(string name, string wire)
    {
        _ = name;
        var bytes = Encoding.UTF8.GetBytes(wire);

        Assert.Throws<InvalidDataException>(() => AddonFrameDecoder.Decode(bytes));
    }

    [Fact]
    public void Decode_PreservesTypedSuccessfulAndUnavailableValues()
    {
        var frame = Frame(
            "{\"schemaVersion\":1,\"addonVersion\":\"0.1.0\",\"sequence\":9007199254740991," +
            "\"epoch\":9007199254740991,\"clock\":{\"status\":\"ok\",\"value\":0}," +
            "\"player\":{\"status\":\"ok\",\"value\":\"player-1\"},\"fields\":{" +
            "\"coordX\":{\"status\":\"ok\",\"value\":-1.5},\"coordY\":{\"status\":\"unavailable\"}," +
            "\"coordZ\":{\"status\":\"invalid\"},\"health\":{\"status\":\"ok\",\"value\":0}," +
            "\"healthMax\":{\"status\":\"ok\",\"value\":100},\"combat\":{\"status\":\"ok\",\"value\":false}}}");

        var observation = AddonFrameDecoder.Decode(frame);

        Assert.Equal(9_007_199_254_740_991, observation.Sequence);
        Assert.Equal(9_007_199_254_740_991, observation.Epoch);
        Assert.Equal(AddonFieldStatus.Ok, observation.Clock.Status);
        Assert.Equal(0, observation.Clock.Value);
        Assert.Equal(AddonFieldStatus.Unavailable, observation.Fields.CoordY.Status);
        Assert.Null(observation.Fields.CoordY.Value);
        Assert.Equal(AddonFieldStatus.Invalid, observation.Fields.CoordZ.Status);
        Assert.Null(observation.Fields.CoordZ.Value);
        Assert.False(observation.Fields.Combat.Value);
    }

    [Fact]
    public void Decode_Accepts128CharacterPrintablePlayerId()
    {
        var playerId = new string('p', 128);
        var frame = Frame(ValidObservationJson(playerId));

        var observation = AddonFrameDecoder.Decode(frame);

        Assert.Equal(playerId, observation.Player.Value);
    }

    [Fact]
    public void Decode_Rejects129CharacterPlayerId()
    {
        var frame = Frame(ValidObservationJson(new string('p', 129)));

        Assert.Throws<InvalidDataException>(() => AddonFrameDecoder.Decode(frame));
    }

    [Fact]
    public void Decode_RejectsEscapedNonAsciiPlayerId()
    {
        var frame = Frame(ValidObservationJson("\\u00e9", playerValueAlreadyEscaped: true));

        Assert.Throws<InvalidDataException>(() => AddonFrameDecoder.Decode(frame));
    }

    [Fact]
    public void Decode_RejectsFrameLargerThan4096BytesBeforeParsing()
    {
        var oversized = new byte[AddonFrameDecoder.MaxFrameBytes + 1];
        Array.Fill(oversized, (byte)' ');

        Assert.Throws<InvalidDataException>(() => AddonFrameDecoder.Decode(oversized));
    }

    [Fact]
    public void Decode_RejectsOverlappingMarkersAsInvalidData()
    {
        var overlappingMarkers = Encoding.ASCII.GetBytes("RR2A1|ENDRR2A1");

        Assert.Throws<InvalidDataException>(() => AddonFrameDecoder.Decode(overlappingMarkers));
    }

    private static byte[] Frame(string json) =>
        Encoding.ASCII.GetBytes($"RR2A1|{json}|ENDRR2A1");

    private static string ValidObservationJson(string playerId, bool playerValueAlreadyEscaped = false)
    {
        var encodedPlayer = playerValueAlreadyEscaped
            ? $"\"{playerId}\""
            : JsonSerializer.Serialize(playerId);
        return
            "{\"schemaVersion\":1,\"addonVersion\":\"0.1.0\",\"sequence\":1,\"epoch\":1," +
            "\"clock\":{\"status\":\"ok\",\"value\":10},\"player\":{\"status\":\"ok\",\"value\":" + encodedPlayer + "}," +
            "\"fields\":{\"coordX\":{\"status\":\"unavailable\"},\"coordY\":{\"status\":\"unavailable\"}," +
            "\"coordZ\":{\"status\":\"unavailable\"},\"health\":{\"status\":\"unavailable\"}," +
            "\"healthMax\":{\"status\":\"unavailable\"},\"combat\":{\"status\":\"unavailable\"}}}";
    }

    private static string FixturePath(string fileName) =>
        System.IO.Path.Combine(AppContext.BaseDirectory, "Fixtures", "addon", fileName);
}
