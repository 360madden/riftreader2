using System.Text.Json;
using RiftReader2.Infrastructure;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class ControlAgentConfigurationTests
{
    [Fact]
    public void Validate_AcceptsBoundPrivateIpv4Configuration()
    {
        ValidConfiguration().Validate();
    }

    [Fact]
    public void Validate_RejectsInvalidBindingsAndBounds()
    {
        var valid = ValidConfiguration();
        var invalid = new ControlAgentConfiguration[]
        {
            valid with { SchemaVersion = 2 },
            valid with { HostAddress = "127.0.0.1" },
            valid with { HostAddress = "8.8.8.8" },
            valid with { HostAddress = "::1" },
            valid with { Port = 1023 },
            valid with { Port = 65536 },
            valid with { Token = new string('a', 31) },
            valid with { Token = new string('a', 257) },
            valid with { ExpectedMachineName = "another-machine" },
            valid with { ProcessName = "not-rift" },
            valid with { ExecutablePath = "rift_x64.exe" },
            valid with { ExecutableSha256 = new string('g', 64) },
            valid with { OutputDirectory = "relative-output" }
        };

        foreach (var configuration in invalid)
            Assert.Throws<InvalidDataException>(configuration.Validate);
    }

    [Fact]
    public void StrictJson_RejectsUnknownProperty()
    {
        var json = SerializeValid();
        var invalid = json.Insert(json.LastIndexOf('}'), ",\"unexpected\":true");

        Assert.Throws<JsonException>(() => Deserialize(invalid));
    }

    [Fact]
    public void StrictJson_RejectsMissingRequiredProperty()
    {
        var json = SerializeValid();
        using var document = JsonDocument.Parse(json);
        var properties = document.RootElement.EnumerateObject()
            .Where(property => property.Name != "token")
            .Select(property => $"{JsonSerializer.Serialize(property.Name)}:{property.Value.GetRawText()}");
        var invalid = "{" + string.Join(',', properties) + "}";

        Assert.Throws<JsonException>(() => Deserialize(invalid));
    }

    [Fact]
    public void StrictJson_RejectsDuplicateProperty()
    {
        var json = SerializeValid();
        var invalid = json.Insert(json.IndexOf('{') + 1, "\"schemaVersion\":1,");

        Assert.Throws<JsonException>(() => Deserialize(invalid));
    }

    [Fact]
    public void StrictJson_RejectsNullForNonNullableProperty()
    {
        var json = SerializeValid();
        var token = JsonSerializer.Serialize(ValidConfiguration().Token);
        var invalid = json.Replace(token, "null", StringComparison.Ordinal);

        Assert.Throws<JsonException>(() => Deserialize(invalid));
    }

    [Theory]
    [InlineData("")]
    [InlineData("null")]
    [InlineData("{")]
    [InlineData("[]")]
    public void StrictJson_RejectsInvalidConfigurationDocuments(string json)
    {
        Assert.ThrowsAny<Exception>(() =>
        {
            var configuration = Deserialize(json)
                ?? throw new InvalidDataException("Null control configuration.");
            configuration.Validate();
        });
    }

    private static ControlAgentConfiguration ValidConfiguration() => new(
        1,
        "192.168.56.1",
        32123,
        new string('a', 32),
        Environment.MachineName,
        "rift_x64",
        @"C:\Program Files\RIFT Game\rift_x64.exe",
        new string('A', 64),
        @"C:\RiftReader2\control");

    private static string SerializeValid() =>
        JsonSerializer.Serialize(ValidConfiguration(), JsonFormat.Options);

    private static ControlAgentConfiguration? Deserialize(string json) =>
        JsonSerializer.Deserialize<ControlAgentConfiguration>(json, JsonFormat.Options);
}
