using RiftReader2.Domain;

namespace RiftReader2.Application;

public sealed class FieldQualificationEvaluator
{
    private static readonly string[] ClaimOrder =
        ["meaning", "locator", "restart-survival", "update-survival"];

    public FieldQualificationEvaluation Evaluate(
        FieldCatalog catalog,
        IReadOnlyList<FieldAssessment> assessments,
        FieldQualificationContext context)
    {
        ArgumentNullException.ThrowIfNull(catalog);
        ArgumentNullException.ThrowIfNull(assessments);
        ArgumentNullException.ThrowIfNull(context);
        ValidateContext(context);

        var fieldIds = catalog.Fields.Select(static field => field.FieldId).ToHashSet(StringComparer.Ordinal);
        var definitionHashes = catalog.Fields.ToDictionary(
            static field => field.FieldId,
            FieldDefinitionFingerprint.Compute,
            StringComparer.Ordinal);
        var dispositions = BuildDispositions(catalog, assessments, context, fieldIds, definitionHashes);
        var results = catalog.Fields.Select(field => EvaluateField(
            field, definitionHashes[field.FieldId], assessments, context, dispositions)).ToArray();
        return new("recorded-assertions-only", context, results, dispositions);
    }

    private static FieldQualificationResult EvaluateField(
        FieldDefinition field,
        string definitionSha256,
        IReadOnlyList<FieldAssessment> assessments,
        FieldQualificationContext context,
        IReadOnlyList<FieldAssessmentDisposition> dispositions)
    {
        if (!field.Applicability.Any(item => Matches(item, context.BuildSha256, context.SessionId)))
        {
            var inapplicableClaims = ClaimOrder.Select(claim => new FieldClaimResult(
                claim, "unqualified", ["Selected build/session is outside the field definition applicability."], [], [])).ToArray();
            return new(field.FieldId, definitionSha256, field.RequiredClaims, "unqualified",
                ["Selected build/session is outside the field definition applicability."], inapplicableClaims);
        }

        var claims = ClaimOrder
            .Select(claim => EvaluateClaim(field, definitionSha256, claim, assessments, context, dispositions))
            .ToArray();
        var required = claims.Where(claim => field.RequiredClaims.Contains(claim.Claim, StringComparer.Ordinal)).ToArray();
        var status = required.Any(static claim => claim.Status == "contradicted")
            ? "contradicted"
            : required.All(static claim => claim.Status == "supported-by-recorded-assessment")
                ? "supported-by-recorded-assessment"
                : "unqualified";
        var reasons = required.Where(claim => claim.Status != "supported-by-recorded-assessment")
            .SelectMany(claim => claim.Reasons.Select(reason => $"{claim.Claim}: {reason}"))
            .ToArray();
        if (reasons.Length == 0)
            reasons = ["Every required claim is supported by active recorded assessments in the declared scope."];
        return new(field.FieldId, definitionSha256, field.RequiredClaims, status, reasons, claims);
    }

    private static FieldClaimResult EvaluateClaim(
        FieldDefinition field,
        string definitionSha256,
        string claim,
        IReadOnlyList<FieldAssessment> assessments,
        FieldQualificationContext context,
        IReadOnlyList<FieldAssessmentDisposition> dispositions)
    {
        if (field.Locator.Kind == "absolute-session-address" &&
            claim is ("locator" or "restart-survival" or "update-survival"))
            return new(claim, "unqualified", ["An absolute session address is session state, not a durable locator method."], [], []);

        var applicable = dispositions.Where(item =>
            item.FieldId == field.FieldId && item.Claim == claim && item.Disposition == "applicable").ToArray();
        var contradicting = applicable.Where(static item => item.Outcome == "contradicts")
            .Select(static item => item.AssessmentId).Distinct(StringComparer.Ordinal).Order().ToArray();
        if (contradicting.Length != 0)
            return new(claim, "contradicted", ["One or more active applicable assessments contradict this claim."],
                [], contradicting);

        var supporting = applicable.Where(static item => item.Outcome == "supports")
            .Select(static item => item.AssessmentId).Distinct(StringComparer.Ordinal).Order().ToArray();
        if (claim is "meaning" or "locator")
        {
            return supporting.Length != 0
                ? new(claim, "supported-by-recorded-assessment",
                    ["An active assessment records support for the selected exact build/session."], supporting, [])
                : new(claim, "unqualified",
                    ["No active supporting assessment applies to the selected exact build/session."], [], []);
        }

        var supportingAssessments = assessments.Where(assessment => supporting.Contains(assessment.AssessmentId,
            StringComparer.Ordinal)).ToArray();
        if (claim == "restart-survival")
        {
            var sessions = supportingAssessments.Select(static item => item.Applicability.SessionId)
                .Distinct(StringComparer.Ordinal).Count();
            var includesSelected = supportingAssessments.Any(item => Matches(item.Applicability,
                context.BuildSha256, context.SessionId));
            return sessions >= 2 && includesSelected
                ? new(claim, "supported-by-recorded-assessment",
                    ["Explicit restart-survival assessments cover the selected session and another session of the same build."],
                    supporting, [])
                : new(claim, "unqualified",
                    ["Restart survival requires explicit active support across two distinct sessions of the selected build, including the selected session."],
                    supporting, []);
        }

        var builds = supportingAssessments.Select(static item => item.Applicability.BuildSha256)
            .Distinct(StringComparer.OrdinalIgnoreCase).Count();
        var includesSelectedContext = supportingAssessments.Any(item => Matches(item.Applicability,
            context.BuildSha256, context.SessionId));
        return builds >= 2 && includesSelectedContext
            ? new(claim, "supported-by-recorded-assessment",
                ["Explicit update-survival assessments cover the selected context and another declared build."], supporting, [])
            : new(claim, "unqualified",
                ["Update survival requires explicit active support across two distinct declared builds, including the selected exact context."],
                supporting, []);
    }

    private static IReadOnlyList<FieldAssessmentDisposition> BuildDispositions(
        FieldCatalog catalog,
        IReadOnlyList<FieldAssessment> assessments,
        FieldQualificationContext context,
        IReadOnlySet<string> fieldIds,
        IReadOnlyDictionary<string, string> definitionHashes)
    {
        var result = new List<FieldAssessmentDisposition>();
        foreach (var assessment in assessments.OrderBy(static item => item.AssessmentId, StringComparer.Ordinal))
        {
            foreach (var declaration in assessment.Declarations.OrderBy(
                static item => Array.IndexOf(ClaimOrder, item.Claim)))
            {
                var (disposition, reason) = Disposition(catalog, assessment, declaration, context,
                    fieldIds, definitionHashes);
                result.Add(new(assessment.AssessmentId, assessment.AssessmentSha256, assessment.FieldId,
                    declaration.Claim, declaration.Outcome, disposition, reason,
                    assessment.Reviewer, assessment.Method, assessment.EvidenceOrigin, declaration.Rationale,
                    "content-hash-verified-identity-declared", assessment.Artifacts,
                    assessment.Applicability.BuildSha256, assessment.Applicability.SessionId,
                    assessment.AssessedAtUtc, assessment.ExpiresAtUtc));
            }
        }
        return result;
    }

    private static (string Disposition, string Reason) Disposition(
        FieldCatalog catalog,
        FieldAssessment assessment,
        FieldAssessmentDeclaration declaration,
        FieldQualificationContext context,
        IReadOnlySet<string> fieldIds,
        IReadOnlyDictionary<string, string> definitionHashes)
    {
        if (!fieldIds.Contains(assessment.FieldId))
            return ("unknown-field", "Assessment fieldId is absent from the catalog.");
        if (!assessment.FieldDefinitionSha256.Equals(definitionHashes[assessment.FieldId], StringComparison.OrdinalIgnoreCase))
            return ("definition-mismatch", "Assessment does not bind the current canonical field definition.");
        var field = catalog.Fields.Single(item => item.FieldId == assessment.FieldId);
        if (assessment.EvidenceOrigin == "synthetic" && field.SourceKind != "synthetic")
            return ("synthetic-not-applicable", "Synthetic evidence cannot support or contradict a non-synthetic field.");
        if (assessment.AssessedAtUtc > context.EvaluatedAtUtc)
            return ("future", "Assessment occurs after the explicit evaluation time.");
        if (assessment.ExpiresAtUtc is { } expires && expires <= context.EvaluatedAtUtc)
            return ("expired", "Assessment expired at or before the explicit evaluation time.");
        if (!field.Applicability.Any(item => Matches(item, assessment.Applicability.BuildSha256,
                assessment.Applicability.SessionId)))
            return ("outside-definition-applicability", "Assessment context is absent from the field definition applicability.");

        var contextMatches = Matches(assessment.Applicability, context.BuildSha256, context.SessionId);
        if (declaration.Claim is "meaning" or "locator")
            return contextMatches
                ? ("applicable", "Assessment applies to the selected exact build/session.")
                : ("other-context", "Assessment is retained but applies to another build/session.");
        if (declaration.Claim == "restart-survival")
            return assessment.Applicability.BuildSha256.Equals(context.BuildSha256, StringComparison.OrdinalIgnoreCase)
                ? ("applicable", "Assessment is an explicit restart-survival declaration for the selected build.")
                : ("other-context", "Restart-survival assessment applies to another build.");
        return ("applicable", "Assessment is an explicit update-survival declaration for a declared build/session.");
    }

    private static bool Matches(FieldApplicability applicability, string buildSha256, string sessionId) =>
        applicability.BuildSha256.Equals(buildSha256, StringComparison.OrdinalIgnoreCase) &&
        applicability.SessionId == sessionId;

    private static void ValidateContext(FieldQualificationContext context)
    {
        if (context.BuildSha256 is not { Length: 64 } || !context.BuildSha256.All(char.IsAsciiHexDigit))
            throw new InvalidDataException("Qualification buildSha256 must be a SHA-256 hexadecimal string.");
        if (string.IsNullOrWhiteSpace(context.SessionId) || context.SessionId.Length > 256)
            throw new InvalidDataException("Qualification sessionId must contain 1 to 256 characters.");
        if (context.EvaluatedAtUtc.Offset != TimeSpan.Zero)
            throw new InvalidDataException("Qualification evaluatedAtUtc must use UTC offset Z.");
    }

}
