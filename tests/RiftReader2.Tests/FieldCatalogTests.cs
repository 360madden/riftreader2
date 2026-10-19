using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Tests;

public sealed class FieldCatalogTests
{
    private const string BuildA = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
    private const string BuildB = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB";
    private static readonly DateTimeOffset EvaluatedAt = DateTimeOffset.Parse("2026-10-19T12:00:00Z");

    [Fact]
    public async Task LoadsPinnedAssessmentAndArtifactAndQualifiesExactContext()
    {
        using var fixture = new CatalogFixture();
        var field = Definition("addon", "addon-api", [new(BuildA, "session-a")], ["meaning", "locator"]);
        fixture.AddAssessment(field, "assessment-a", BuildA, "session-a", "rift-recording",
            new FieldAssessmentDeclarationDocument("meaning", "supports", "Observed API value tracks the declared meaning."),
            new FieldAssessmentDeclarationDocument("locator", "supports", "The named addon API method reproduced the value."));
        var catalogPath = fixture.WriteCatalog(field);

        var loaded = await FieldCatalogFile.LoadAsync(catalogPath);
        var result = new FieldQualificationEvaluator().Evaluate(loaded.Catalog, loaded.Assessments,
            new(BuildA, "session-a", EvaluatedAt));

        Assert.Equal(Hash(await File.ReadAllBytesAsync(catalogPath)), loaded.CatalogSha256);
        Assert.Equal(FieldDefinitionFingerprint.Compute(field), result.Fields.Single().FieldDefinitionSha256);
        Assert.Equal("supported-by-recorded-assessment", result.Fields.Single().Status);
        Assert.Equal("recorded-assertions-only", result.SemanticVerification);
        Assert.All(result.Fields.Single().Claims,
            claim =>
            {
                if (claim.Claim is "meaning" or "locator")
                    Assert.Equal("supported-by-recorded-assessment", claim.Status);
                else
                    Assert.Equal("unqualified", claim.Status);
            });
    }

    [Fact]
    public void RestartAndUpdateClaimsRequireExplicitDistinctContexts()
    {
        var applicability = new FieldApplicability[]
        {
            new(BuildA, "session-a"), new(BuildA, "session-b"), new(BuildB, "session-c")
        };
        var field = Definition("native", "signature-scan", applicability,
            ["meaning", "locator", "restart-survival", "update-survival"]);
        var hash = FieldDefinitionFingerprint.Compute(field);
        var assessments = new[]
        {
            Assessment("selected", field, hash, BuildA, "session-a", "meaning", "supports"),
            Assessment("locator", field, hash, BuildA, "session-a", "locator", "supports"),
            Assessment("restart-a", field, hash, BuildA, "session-a", "restart-survival", "supports"),
            Assessment("restart-b", field, hash, BuildA, "session-b", "restart-survival", "supports"),
            Assessment("update-a", field, hash, BuildA, "session-a", "update-survival", "supports"),
            Assessment("update-b", field, hash, BuildB, "session-c", "update-survival", "supports")
        };

        var result = Evaluate(field, assessments);

        Assert.Equal("supported-by-recorded-assessment", result.Fields.Single().Status);
        Assert.Equal(2, result.Fields.Single().Claims.Single(c => c.Claim == "restart-survival")
            .SupportingAssessmentIds.Count);
        Assert.Equal(2, result.Fields.Single().Claims.Single(c => c.Claim == "update-survival")
            .SupportingAssessmentIds.Count);
    }

    [Fact]
    public void CrossContextContradictionsOverrideRestartAndUpdateSupport()
    {
        var applicability = new FieldApplicability[]
        {
            new(BuildA, "session-a"), new(BuildA, "session-b"), new(BuildB, "session-c")
        };
        var field = Definition("native", "signature-scan", applicability,
            ["meaning", "locator", "restart-survival", "update-survival"]);
        var hash = FieldDefinitionFingerprint.Compute(field);
        var assessments = new[]
        {
            Assessment("meaning", field, hash, BuildA, "session-a", "meaning", "supports"),
            Assessment("locator", field, hash, BuildA, "session-a", "locator", "supports"),
            Assessment("restart-a", field, hash, BuildA, "session-a", "restart-survival", "supports"),
            Assessment("restart-b", field, hash, BuildA, "session-b", "restart-survival", "supports"),
            Assessment("restart-no", field, hash, BuildA, "session-b", "restart-survival", "contradicts"),
            Assessment("update-a", field, hash, BuildA, "session-a", "update-survival", "supports"),
            Assessment("update-b", field, hash, BuildB, "session-c", "update-survival", "supports"),
            Assessment("update-no", field, hash, BuildB, "session-c", "update-survival", "contradicts")
        };

        var result = Evaluate(field, assessments).Fields.Single();

        Assert.Equal("contradicted", result.Status);
        Assert.Equal("contradicted", result.Claims.Single(c => c.Claim == "restart-survival").Status);
        Assert.Equal("contradicted", result.Claims.Single(c => c.Claim == "update-survival").Status);
    }

    [Fact]
    public void ContradictoryExpiredAndOtherContextAssessmentsRemainVisible()
    {
        var field = Definition("addon", "addon-api",
            [new(BuildA, "session-a"), new(BuildA, "session-b")], ["meaning", "locator"]);
        var hash = FieldDefinitionFingerprint.Compute(field);
        var assessments = new[]
        {
            Assessment("support", field, hash, BuildA, "session-a", "meaning", "supports"),
            Assessment("contradiction", field, hash, BuildA, "session-a", "meaning", "contradicts"),
            Assessment("expired", field, hash, BuildA, "session-a", "locator", "supports",
                EvaluatedAt.AddMinutes(-1)),
            Assessment("other", field, hash, BuildA, "session-b", "locator", "supports")
        };

        var result = Evaluate(field, assessments);

        Assert.Equal("contradicted", result.Fields.Single().Status);
        Assert.Contains(result.AssessmentDispositions, item =>
            item.AssessmentId == "contradiction" && item.Disposition == "applicable");
        Assert.Contains(result.AssessmentDispositions, item =>
            item.AssessmentId == "expired" && item.Disposition == "expired");
        Assert.Contains(result.AssessmentDispositions, item =>
            item.AssessmentId == "other" && item.Disposition == "other-context");
    }

    [Fact]
    public void SyntheticDeclarationsCannotQualifyOrContradictRecordedField()
    {
        var field = Definition("native", "module-relative-rva", [new(BuildA, "session-a")],
            ["meaning", "locator"]);
        var hash = FieldDefinitionFingerprint.Compute(field);
        var assessments = new[]
        {
            Assessment("synthetic-meaning", field, hash, BuildA, "session-a", "meaning", "supports",
                origin: "synthetic"),
            Assessment("synthetic-locator", field, hash, BuildA, "session-a", "locator", "supports",
                origin: "synthetic"),
            Assessment("synthetic-contradiction", field, hash, BuildA, "session-a", "meaning", "contradicts",
                origin: "synthetic")
        };

        var result = Evaluate(field, assessments);

        Assert.Equal("unqualified", result.Fields.Single().Status);
        Assert.All(result.AssessmentDispositions,
            item => Assert.Equal("synthetic-not-applicable", item.Disposition));
    }

    [Fact]
    public void AbsoluteSessionAddressCannotQualifyAsDurableLocator()
    {
        var field = Definition("native", "absolute-session-address", [new(BuildA, "session-a")],
            ["meaning", "locator"]);
        var hash = FieldDefinitionFingerprint.Compute(field);
        var assessments = new[]
        {
            Assessment("meaning", field, hash, BuildA, "session-a", "meaning", "supports"),
            Assessment("locator", field, hash, BuildA, "session-a", "locator", "supports")
        };

        var result = Evaluate(field, assessments);

        Assert.Equal("unqualified", result.Fields.Single().Status);
        Assert.Contains("absolute session address", result.Fields.Single().Claims
            .Single(c => c.Claim == "locator").Reasons.Single(), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void FutureAndOtherSessionContradictionsStayVisibleWithoutAffectingSelectedContext()
    {
        var field = Definition("addon", "addon-api",
            [new(BuildA, "session-a"), new(BuildA, "session-b")], ["meaning", "locator"]);
        var hash = FieldDefinitionFingerprint.Compute(field);
        var selected = Assessment("selected", field, hash, BuildA, "session-a", "meaning", "supports");
        var locator = Assessment("locator", field, hash, BuildA, "session-a", "locator", "supports");
        var other = Assessment("other-contradiction", field, hash, BuildA, "session-b", "meaning", "contradicts");
        var future = Assessment("future", field, hash, BuildA, "session-a", "meaning", "contradicts") with
        {
            AssessedAtUtc = EvaluatedAt.AddMinutes(1)
        };

        var result = Evaluate(field, [selected, locator, other, future]);

        Assert.Equal("supported-by-recorded-assessment", result.Fields.Single().Status);
        Assert.Contains(result.AssessmentDispositions, item =>
            item.AssessmentId == "other-contradiction" && item.Disposition == "other-context");
        Assert.Contains(result.AssessmentDispositions, item =>
            item.AssessmentId == "future" && item.Disposition == "future");
    }

    [Fact]
    public void FingerprintChangesWithLocatorOrApplicability()
    {
        var original = Definition("native", "signature-scan", [new(BuildA, "session-a")],
            ["meaning", "locator"]);
        var meaningChanged = original with { Meaning = "A different claimed meaning." };
        var locatorChanged = original with { Locator = new("signature-scan", "A different locating method.") };
        var scopeChanged = original with { Applicability = [new(BuildA, "session-b")] };

        Assert.NotEqual(FieldDefinitionFingerprint.Compute(original),
            FieldDefinitionFingerprint.Compute(meaningChanged));
        Assert.NotEqual(FieldDefinitionFingerprint.Compute(original),
            FieldDefinitionFingerprint.Compute(locatorChanged));
        Assert.NotEqual(FieldDefinitionFingerprint.Compute(original),
            FieldDefinitionFingerprint.Compute(scopeChanged));
    }

    [Fact]
    public async Task RejectsChangedArtifactBeforeEvaluation()
    {
        using var fixture = new CatalogFixture();
        var field = Definition("addon", "addon-api", [new(BuildA, "session-a")], ["meaning", "locator"]);
        fixture.AddAssessment(field, "assessment-a", BuildA, "session-a", "rift-recording",
            new FieldAssessmentDeclarationDocument("meaning", "supports", "Recorded claim."));
        var catalogPath = fixture.WriteCatalog(field);
        await File.AppendAllTextAsync(Path.Combine(fixture.Path, "observation-assessment-a.bin"), "changed");

        var error = await Assert.ThrowsAsync<InvalidDataException>(() => FieldCatalogFile.LoadAsync(catalogPath));

        Assert.Contains("byte length", error.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task RejectsHugeArtifactLengthAsInvalidData()
    {
        using var fixture = new CatalogFixture();
        var field = Definition("addon", "addon-api", [new(BuildA, "session-a")], ["meaning", "locator"]);
        var assessment = new FieldAssessmentDocument(1, "field-assessment/1", "huge", field.FieldId,
            FieldDefinitionFingerprint.Compute(field), "fixture-reviewer", "Fixture method.", "rift-recording",
            EvaluatedAt.AddHours(-1), null, new(BuildA, "session-a"),
            [new("meaning", "supports", "Fixture rationale.")],
            [new("observation", "huge.bin", long.MaxValue, new string('A', 64),
                "fixture-observation", BuildA, "session-a")]);
        var assessmentBytes = JsonSerializer.SerializeToUtf8Bytes(assessment, JsonFormat.Options);
        await File.WriteAllBytesAsync(Path.Combine(fixture.Path, "huge.json"), assessmentBytes);
        var definition = new FieldDefinitionDocument(field.FieldId, field.Meaning, field.Units,
            field.SourceKind, new(field.Locator.Kind, field.Locator.Method),
            [new(BuildA, "session-a")], field.InvalidationConditions, field.RequiredClaims);
        var catalog = new FieldCatalogDocument(1, "field-catalog/1", [definition],
            [new("huge.json", assessmentBytes.Length, Hash(assessmentBytes))]);
        var catalogPath = Path.Combine(fixture.Path, "catalog.json");
        await File.WriteAllBytesAsync(catalogPath, JsonSerializer.SerializeToUtf8Bytes(catalog, JsonFormat.Options));

        var error = await Assert.ThrowsAsync<InvalidDataException>(() => FieldCatalogFile.LoadAsync(catalogPath));

        Assert.Contains("byteLength", error.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData("unknown", "1")]
    [InlineData("fields", "null")]
    public async Task StrictlyRejectsUnknownOrNullCatalogMembers(string property, string value)
    {
        using var fixture = new CatalogFixture();
        var json = property == "fields"
            ? "{\"schemaVersion\":1,\"contractVersion\":\"field-catalog/1\",\"fields\":null,\"assessments\":[]}"
            : $"{{\"schemaVersion\":1,\"contractVersion\":\"field-catalog/1\",\"fields\":[],\"assessments\":[],\"{property}\":{value}}}";
        var path = System.IO.Path.Combine(fixture.Path, "catalog.json");
        await File.WriteAllTextAsync(path, json, new UTF8Encoding(false));

        await Assert.ThrowsAsync<InvalidDataException>(() => FieldCatalogFile.LoadAsync(path));
    }

    private static FieldQualificationEvaluation Evaluate(
        FieldDefinition field,
        IReadOnlyList<FieldAssessment> assessments) =>
        new FieldQualificationEvaluator().Evaluate(new(1, "field-catalog/1", [field]), assessments,
            new(BuildA, "session-a", EvaluatedAt));

    private static FieldDefinition Definition(
        string sourceKind,
        string locatorKind,
        IReadOnlyList<FieldApplicability> applicability,
        IReadOnlyList<string> requiredClaims) => new(
        "player.position.x", "Player horizontal X coordinate.", "game-units", sourceKind,
        new(locatorKind, "Resolve the documented source and read its bounded value."), applicability,
        ["Executable build changes.", "Source contract changes."], requiredClaims);

    private static FieldAssessment Assessment(
        string id,
        FieldDefinition field,
        string definitionHash,
        string build,
        string session,
        string claim,
        string outcome,
        DateTimeOffset? expiresAt = null,
        string origin = "rift-recording") => new(
        id, field.FieldId, definitionHash, "fixture-reviewer", "Fixture assessment method.", origin,
        EvaluatedAt.AddHours(-1), expiresAt, new(build, session),
        [new(claim, outcome, "Fixture declaration rationale.")],
        [new("observation", $"{id}.bin", 1, new string('C', 64), "fixture-observation", build, session)],
        Hash(Encoding.UTF8.GetBytes(id)));

    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes));

    private sealed class CatalogFixture : IDisposable
    {
        private readonly List<(FieldAssessmentDocument Document, string File, long Length, string Hash)> assessments = [];

        public CatalogFixture()
        {
            Path = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "rr2-field-catalog-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(Path);
        }

        public string Path { get; }

        public void AddAssessment(
            FieldDefinition field,
            string id,
            string build,
            string session,
            string origin,
            params FieldAssessmentDeclarationDocument[] declarations)
        {
            var artifactFile = $"observation-{id}.bin";
            var artifactBytes = Encoding.UTF8.GetBytes($"observation:{id}");
            File.WriteAllBytes(System.IO.Path.Combine(Path, artifactFile), artifactBytes);
            var document = new FieldAssessmentDocument(1, "field-assessment/1", id, field.FieldId,
                FieldDefinitionFingerprint.Compute(field), "fixture-reviewer", "Fixture assessment method.", origin,
                EvaluatedAt.AddHours(-1), EvaluatedAt.AddHours(1), new(build, session), declarations,
                [new("observation", artifactFile, artifactBytes.Length, Hash(artifactBytes),
                    "fixture-observation", build, session)]);
            var bytes = JsonSerializer.SerializeToUtf8Bytes(document, JsonFormat.Options);
            var file = $"{id}.json";
            File.WriteAllBytes(System.IO.Path.Combine(Path, file), bytes);
            assessments.Add((document, file, bytes.Length, Hash(bytes)));
        }

        public string WriteCatalog(FieldDefinition field)
        {
            var definition = new FieldDefinitionDocument(field.FieldId, field.Meaning, field.Units,
                field.SourceKind, new(field.Locator.Kind, field.Locator.Method),
                field.Applicability.Select(static item => new FieldApplicabilityDocument(
                    item.BuildSha256, item.SessionId)).ToArray(), field.InvalidationConditions,
                field.RequiredClaims);
            var document = new FieldCatalogDocument(1, "field-catalog/1", [definition],
                assessments.Select(static item => new FieldAssessmentReference(item.File, item.Length, item.Hash)).ToArray());
            var path = System.IO.Path.Combine(Path, "catalog.json");
            File.WriteAllBytes(path, JsonSerializer.SerializeToUtf8Bytes(document, JsonFormat.Options));
            return path;
        }

        public void Dispose()
        {
            if (Directory.Exists(Path))
                Directory.Delete(Path, recursive: true);
        }
    }
}
