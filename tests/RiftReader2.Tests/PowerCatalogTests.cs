using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Cli;
using RiftReader2.Infrastructure;

namespace RiftReader2.Tests;

public sealed class PowerCatalogTests
{
    private static string DirectoryPath => Path.Combine(AppContext.BaseDirectory, "Fixtures", "power");
    private const string Build = PowerCandidateReader.ExecutableSha256;

    [Theory]
    [InlineData("rift-1224-639285359295548343")]
    [InlineData("rift-12076-639285736860316715")]
    public async Task RetainedEvidenceSupportsOnlyMeaningLocatorAndObservedRestart(string session)
    {
        var loaded = await FieldCatalogFile.LoadAsync(Path.Combine(DirectoryPath, "catalog.json"));
        var result = new FieldQualificationEvaluator().Evaluate(loaded.Catalog, loaded.Assessments,
            new(Build, session, DateTimeOffset.Parse("2026-10-27T00:00:00Z")));
        var field = Assert.Single(result.Fields);
        Assert.Equal("player.resource.power", field.FieldId);
        Assert.Equal("supported-by-recorded-assessment", field.Status);
        Assert.Equal("unqualified", field.Claims.Single(c => c.Claim == "update-survival").Status);
        Assert.Equal(2, field.Claims.Single(c => c.Claim == "restart-survival").SupportingAssessmentIds.Count);
        Assert.Equal("recorded-assertions-only", result.SemanticVerification);
    }

    [Theory]
    [InlineData("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "rift-12076-639285736860316715")]
    [InlineData(Build, "unobserved-future-session")]
    public async Task CatalogDoesNotExtendEvidenceToAnotherBuildOrUnobservedSession(string build, string session)
    {
        var loaded = await FieldCatalogFile.LoadAsync(Path.Combine(DirectoryPath, "catalog.json"));
        var result = new FieldQualificationEvaluator().Evaluate(loaded.Catalog, loaded.Assessments,
            new(build, session, DateTimeOffset.Parse("2026-10-27T00:00:00Z")));
        Assert.NotEqual("supported-by-recorded-assessment", result.Fields.Single().Status);
    }

    [Fact]
    public async Task NormalDiscoveryExportIncludesPowerWithoutInventingLiveValue()
    {
        var output = Path.Combine(Path.GetTempPath(), "rr2-power-export-" + Guid.NewGuid().ToString("N") + ".json");
        try
        {
            using var errors = new StringWriter();
            var code = await CliRunner.RunAsync(["export-discoveries", "--manifest",
                Path.Combine(DirectoryPath, "discovery-sources.json"), "--build-sha256", Build,
                "--session-id", "rift-12076-639285736860316715", "--as-of", "2026-10-27T00:00:00Z",
                "--format", "json", "--output", output], new StringWriter(), errors);
            Assert.Equal(0, code);
            Assert.Empty(errors.ToString());
            using var json = JsonDocument.Parse(await File.ReadAllTextAsync(output));
            var row = Assert.Single(json.RootElement.GetProperty("records").EnumerateArray());
            Assert.Equal("player.resource.power", row.GetProperty("fieldId").GetString());
            Assert.Equal("native", row.GetProperty("sourceKind").GetString());
            Assert.Equal("supported-by-recorded-assessment", row.GetProperty("status").GetString());
            Assert.Equal(JsonValueKind.Null, row.GetProperty("value").ValueKind);
        }
        finally { File.Delete(output); }
    }
}
