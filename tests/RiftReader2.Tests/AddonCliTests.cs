using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RiftReader2.Cli;

namespace RiftReader2.Tests;

public sealed class AddonCliTests : IDisposable
{
    private readonly string directory = Path.Combine(Path.GetTempPath(), "rr2-addon-" + Guid.NewGuid().ToString("N"));

    public AddonCliTests() => Directory.CreateDirectory(directory);

    [Fact]
    public async Task SavedFrameProducesUnboundReportWithExactByteIdentityAndNoOverwrite()
    {
        using var cases = JsonDocument.Parse(await File.ReadAllTextAsync(Path.Combine(AppContext.BaseDirectory, "Fixtures", "addon", "cases.json")));
        var expected = cases.RootElement[0].GetProperty("expected");
        var frame = Encoding.ASCII.GetBytes("RR2A1|" + expected.GetRawText() + "|ENDRR2A1");
        var source = Path.Combine(directory, "input.wire");
        var destination = Path.Combine(directory, "result.json");
        await File.WriteAllBytesAsync(source, frame);
        using var output = new StringWriter();
        using var error = new StringWriter();
        string[] args = ["decode-addon", "--frame", source, "--output", destination];
        Assert.Equal(0, await CliRunner.RunAsync(args, output, error));
        Assert.Empty(error.ToString());
        using var json = JsonDocument.Parse(await File.ReadAllTextAsync(destination));
        Assert.Equal("unbound", json.RootElement.GetProperty("bindingStatus").GetString());
        Assert.Equal("unverified", json.RootElement.GetProperty("freshnessStatus").GetString());
        Assert.Equal(Convert.ToHexString(SHA256.HashData(frame)), json.RootElement.GetProperty("frameSha256").GetString()!.ToUpperInvariant());
        Assert.Equal(0, json.RootElement.GetProperty("observation").GetProperty("fields").GetProperty("coordX").GetProperty("value").GetDouble());
        Assert.False(json.RootElement.GetProperty("observation").GetProperty("fields").GetProperty("combat").GetProperty("value").GetBoolean());
        var saved = await File.ReadAllBytesAsync(destination);
        Assert.Equal(2, await CliRunner.RunAsync(args, TextWriter.Null, error));
        Assert.Equal(saved, await File.ReadAllBytesAsync(destination));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(4097)]
    [InlineData(100000)]
    public async Task InvalidOrOversizedFramesNeverPublishReports(int length)
    {
        var source = Path.Combine(directory, "input.wire");
        var destination = Path.Combine(directory, "result.json");
        await File.WriteAllBytesAsync(source, new byte[length]);
        using var error = new StringWriter();
        Assert.Equal(2, await CliRunner.RunAsync(["decode-addon", "--frame", source, "--output", destination], TextWriter.Null, error));
        Assert.False(File.Exists(destination));
        Assert.Contains("error", error.ToString());
    }

    [Fact]
    public async Task CancellationDoesNotPublishReport()
    {
        var source = Path.Combine(directory, "input.wire");
        await File.WriteAllTextAsync(source, "irrelevant");
        var destination = Path.Combine(directory, "result.json");
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        using var error = new StringWriter();
        Assert.Equal(130, await CliRunner.RunAsync(["decode-addon", "--frame", source, "--output", destination], TextWriter.Null, error, cancellation.Token));
        Assert.False(File.Exists(destination));
    }

    [Theory]
    [InlineData("decode-addon")]
    [InlineData("decode-addon", "--frame")]
    [InlineData("decode-addon", "--frame", "one", "--frame", "two")]
    [InlineData("decode-addon", "--manifest", "capture.json")]
    [InlineData("decode-addon", "--config", "config.json")]
    public async Task CommandRejectsMissingDuplicateAndForeignOptions(params string[] args)
    {
        using var error = new StringWriter();
        Assert.Equal(2, await CliRunner.RunAsync(args, TextWriter.Null, error));
        Assert.Contains("error", error.ToString());
    }

    public void Dispose() => Directory.Delete(directory, recursive: true);
}
