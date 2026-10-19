using System.Text.Json;
using RiftReader2.Cli;

namespace RiftReader2.Tests;

public sealed class FieldCatalogCliTests
{
    private static string Fixture => Path.Combine(AppContext.BaseDirectory, "Fixtures", "catalog", "catalog.json");

    [Fact]
    public async Task RetainedBundleRebuildsDeterministicallyAndPreservesExistingOutput()
    {
        var directory = Path.Combine(Path.GetTempPath(), "rr2-catalog-cli-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            var destination = Path.Combine(directory, "report.json");
            using var first = new StringWriter();
            using var second = new StringWriter();
            using var errors = new StringWriter();
            Assert.Equal(0, await CliRunner.RunAsync(Arguments(Fixture, destination), first, errors));
            Assert.Equal(0, await CliRunner.RunAsync(Arguments(Fixture), second, errors));
            Assert.Equal(first.ToString(), second.ToString());
            Assert.Empty(errors.ToString());
            using var document = JsonDocument.Parse(first.ToString());
            var report = document.RootElement;
            Assert.Equal("declared-only", report.GetProperty("buildSessionIdentityVerification").GetString());
            var evaluation = report.GetProperty("evaluation");
            Assert.Equal("recorded-assertions-only", evaluation.GetProperty("semanticVerification").GetString());
            var fields = evaluation.GetProperty("fields").EnumerateArray().ToDictionary(
                field => field.GetProperty("fieldId").GetString()!, field => field.GetProperty("status").GetString());
            Assert.Equal("supported-by-recorded-assessment", fields["demo.supported"]);
            Assert.Equal("contradicted", fields["demo.disputed"]);
            Assert.Equal("unqualified", fields["demo.address-only"]);
            Assert.Contains(evaluation.GetProperty("assessmentDispositions").EnumerateArray(),
                item => item.GetProperty("disposition").GetString() == "expired");
            var retained = await File.ReadAllBytesAsync(destination);
            Assert.Equal(2, await CliRunner.RunAsync(Arguments(Fixture, destination), new StringWriter(), errors));
            Assert.Equal(retained, await File.ReadAllBytesAsync(destination));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Theory]
    [InlineData("2026-10-19")]
    [InlineData("2026-10-19T00:00:00")]
    [InlineData("2026-10-19T00:00:00-04:00")]
    public async Task EvaluationRequiresAnExplicitUtcInstant(string time)
    {
        var args = Arguments(Fixture);
        args[^1] = time;
        using var error = new StringWriter();
        Assert.Equal(2, await CliRunner.RunAsync(args, new StringWriter(), error));
        Assert.Contains("--as-of", error.ToString());
    }

    [Fact]
    public async Task ChangedArtifactFailsBeforePublishing()
    {
        var directory = Path.Combine(Path.GetTempPath(), "rr2-catalog-tamper-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            foreach (var file in Directory.GetFiles(Path.GetDirectoryName(Fixture)!, "*.json"))
                File.Copy(file, Path.Combine(directory, Path.GetFileName(file)));
            var artifact = Path.Combine(directory, "observation-1.json");
            var original = await File.ReadAllTextAsync(artifact);
            await File.WriteAllTextAsync(artifact, original.Replace("42", "43", StringComparison.Ordinal));
            var output = Path.Combine(directory, "report.json");
            using var error = new StringWriter();
            Assert.Equal(2, await CliRunner.RunAsync(Arguments(Path.Combine(directory, "catalog.json"), output),
                new StringWriter(), error));
            Assert.False(File.Exists(output));
            Assert.Contains("SHA-256", error.ToString());
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public async Task CancellationDoesNotPublish()
    {
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        using var output = new StringWriter();
        Assert.Equal(130, await CliRunner.RunAsync(Arguments(Fixture), output, new StringWriter(), cancellation.Token));
        Assert.Empty(output.ToString());
    }

    private static string[] Arguments(string catalog, string? output = null)
    {
        string[] args = ["qualify-fields", "--catalog", catalog, "--build-sha256", new string('A', 64),
            "--session-id", "synthetic-session-a", "--as-of", "2026-10-19T00:00:00Z"];
        return output is null ? args : [.. args, "--output", output];
    }
}
