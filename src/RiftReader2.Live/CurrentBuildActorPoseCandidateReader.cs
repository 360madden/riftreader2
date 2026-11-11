using System.Buffers.Binary;
using System.Globalization;
using System.Text.Json.Serialization;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

/// <summary>Read-only current-build actor/model matrix candidate, not qualified body facing.</summary>
internal sealed record CurrentBuildActorPoseCandidate(
    NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc,
    [property: JsonIgnore] ulong PlayerKey,
    [property: JsonIgnore] ulong PlayerEntity,
    [property: JsonIgnore] ulong ActorComponent,
    [property: JsonIgnore] ulong PositionComponent, uint ActorFlags,
    CurrentBuildMatrixDescriptorCandidate ActorMatrix,
    CurrentBuildMatrixDescriptorCandidate ModelMatrix,
    CurrentBuildMatrixDescriptorCandidate? RenderMatrix,
    string RenderStatus, double? RenderCompositionMaxAbsDelta)
{
    public string PlayerKeyDecimal => PlayerKey.ToString(CultureInfo.InvariantCulture);
    public string PlayerEntityDecimal => PlayerEntity.ToString(CultureInfo.InvariantCulture);
    public string ActorComponentDecimal => ActorComponent.ToString(CultureInfo.InvariantCulture);
    public string PositionComponentDecimal => PositionComponent.ToString(CultureInfo.InvariantCulture);
    public bool NormalRenderBranch => (ActorFlags & 1) == 0;
    public bool ActorHeadingQualified => false;
    // These translation triplets share the already bracketed matrix payloads.
    // They are not independently qualified as the live player world position.
    public CurrentBuildXyz? ActorWorldTranslationCandidate { get; init; }
    public CurrentBuildXyz? RenderWorldTranslationCandidate { get; init; }
    public double? RenderWorldTranslationMaxAbsDeltaCandidate { get; init; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public CurrentBuildActorPosePositionBracketCandidate? PositionBracketCandidate { get; init; }
    public string Qualification =>
        "actor/model/render-matrix/translation-candidate-only; body-facing, source freshness, input response and restart unverified";
}

internal sealed record CurrentBuildActorPosePositionBracketCandidate(
    string PlayerKeyDecimal, CurrentBuildXyz Before, CurrentBuildXyz After,
    double ElapsedMilliseconds)
{
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public CurrentBuildXyz? SecondaryBeforeCandidate { get; init; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public CurrentBuildXyz? SecondaryAfterCandidate { get; init; }
}

/// <summary>
/// Exact-build self-owned actor pose from the known component selectors. The actor
/// and model matrices are retained even when the normal renderer branch is absent.
/// No reads of alternate-branch renderer references are attempted.
/// </summary>
internal static class CurrentBuildActorPoseCandidateReader
{
    internal const ulong ActorSelectorRva = 0x2F58490;
    internal const ulong PositionSelectorRva = 0x2F588A0;

    internal static CurrentBuildActorPoseCandidate Read(IReadOnlyNativeMemorySession session)
    {
        ArgumentNullException.ThrowIfNull(session);
        var lookup = CurrentBuildPlayerLookup.Resolve(session);
        return ReadResolved(session, session.Identity, DateTimeOffset.UtcNow,
            lookup.PlayerKey, lookup.EntityAddress,
            lookup.ResolveComponent(ActorSelectorRva),
            lookup.ResolveComponent(PositionSelectorRva),
            lookup.VerifyUnchanged);
    }

    internal static CurrentBuildActorPoseCandidate ReadResolved(
        IReadOnlyNativeMemorySession session, NativeProcessIdentity identity,
        DateTimeOffset started, ulong playerKey, ulong playerEntity,
        ulong actorComponent, ulong positionComponent, Action verifyOwner)
    {
        ArgumentNullException.ThrowIfNull(session);
        ArgumentNullException.ThrowIfNull(verifyOwner);
        if (session.Identity != identity || identity.ProcessId <= 0
            || identity.ProcessStartUtcTicks <= 0 || playerKey == 0
            || !string.Equals(identity.ExecutableSha256,
                CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase)
            || identity.ModuleSize < PositionSelectorRva + 4)
            throw new InvalidDataException("Actor pose requires exact current-build process and owner.");
        CurrentBuildPlayerLookup.Pointer(playerEntity, 128);
        var actor = CurrentBuildPlayerLookup.Pointer(actorComponent, 0x418);
        var position = CurrentBuildPlayerLookup.Pointer(positionComponent);
        if (actor == position)
            throw new InvalidDataException("Actor and position components unexpectedly alias.");

        var flagsAddress = checked(actor + 0x1C0);
        var actorAddress = checked(actor + 0x398);
        var modelAddress = checked(actor + 0x3EC);
        var pointerAddress = checked(actor + 0x410);
        var flagsRaw = CurrentBuildPlayerLookup.Exact(session, flagsAddress, 4);
        var flags = BinaryPrimitives.ReadUInt32LittleEndian(flagsRaw);
        var actorRaw = CurrentBuildPlayerLookup.Exact(session, actorAddress, 0x30);
        var modelRaw = CurrentBuildPlayerLookup.Exact(session, modelAddress, 0x24);
        var actorMatrix = CurrentBuildOrientationCandidateReader.Decode(actorRaw.AsSpan(0, 0x24), 0x398);
        var modelMatrix = CurrentBuildOrientationCandidateReader.Decode(modelRaw, 0x3EC);

        CurrentBuildMatrixDescriptorCandidate? renderMatrix = null;
        byte[]? pointerRaw = null;
        byte[]? renderRaw = null;
        ulong renderAddress = 0;
        var renderStatus = "alternate-reference-branch-not-followed";
        if ((flags & 1) == 0)
        {
            pointerRaw = CurrentBuildPlayerLookup.Exact(session, pointerAddress, 8);
            var pointer = BinaryPrimitives.ReadUInt64LittleEndian(pointerRaw);
            if (pointer == 0)
            {
                renderStatus = "normal-render-pointer-absent";
            }
            else
            {
                var renderer = CurrentBuildPlayerLookup.Pointer(pointer, 0xD0);
                renderAddress = checked(renderer + 0xA0);
                renderRaw = CurrentBuildPlayerLookup.Exact(session, renderAddress, 0x30);
                renderMatrix = CurrentBuildOrientationCandidateReader.Decode(renderRaw.AsSpan(0, 0x24), 0xA0);
                renderStatus = "normal-render-matrix-candidate";
            }
        }

        verifyOwner();
        CurrentBuildPlayerLookup.RequireSame(CurrentBuildPlayerLookup.Exact(session, flagsAddress, 4), flagsRaw);
        CurrentBuildPlayerLookup.RequireSame(CurrentBuildPlayerLookup.Exact(session, actorAddress, 0x30), actorRaw);
        CurrentBuildPlayerLookup.RequireSame(CurrentBuildPlayerLookup.Exact(session, modelAddress, 0x24), modelRaw);
        if (pointerRaw is not null)
            CurrentBuildPlayerLookup.RequireSame(CurrentBuildPlayerLookup.Exact(session, pointerAddress, 8), pointerRaw);
        if (renderRaw is not null)
            CurrentBuildPlayerLookup.RequireSame(CurrentBuildPlayerLookup.Exact(session, renderAddress, 0x30), renderRaw);
        if (session.Identity != identity)
            throw new InvalidDataException("Actor pose process identity changed.");
        var delta = CompositionDelta(actorMatrix.RowMajorF32, modelMatrix.RowMajorF32,
            renderMatrix?.RowMajorF32);
        var actorTranslation = DecodeFiniteTranslation(actorRaw.AsSpan(0x24, 0x0C));
        var renderTranslation = renderRaw is null ? null : DecodeFiniteTranslation(renderRaw.AsSpan(0x24, 0x0C));
        return new(identity, started, DateTimeOffset.UtcNow, playerKey, playerEntity, actor, position,
            flags, actorMatrix, modelMatrix, renderMatrix, renderStatus, delta)
        {
            ActorWorldTranslationCandidate = actorTranslation,
            RenderWorldTranslationCandidate = renderTranslation,
            RenderWorldTranslationMaxAbsDeltaCandidate = TranslationDelta(actorTranslation, renderTranslation)
        };
    }

    private static CurrentBuildXyz? DecodeFiniteTranslation(ReadOnlySpan<byte> raw)
    {
        var x = BinaryPrimitives.ReadSingleLittleEndian(raw);
        var y = BinaryPrimitives.ReadSingleLittleEndian(raw.Slice(4));
        var z = BinaryPrimitives.ReadSingleLittleEndian(raw.Slice(8));
        return float.IsFinite(x) && float.IsFinite(y) && float.IsFinite(z)
            ? new CurrentBuildXyz(x, y, z) : null;
    }

    private static double? TranslationDelta(CurrentBuildXyz? actor, CurrentBuildXyz? render) =>
        actor is null || render is null ? null : Math.Max(
            Math.Max(Math.Abs((double)actor.X - render.X), Math.Abs((double)actor.Y - render.Y)),
            Math.Abs((double)actor.Z - render.Z));

    private static double? CompositionDelta(float[]? actor, float[]? model, float[]? render)
    {
        if (actor is null || model is null || render is null) return null;
        var maximum = 0d;
        for (var row = 0; row < 3; row++)
            for (var col = 0; col < 3; col++)
            {
                var value = 0d;
                for (var k = 0; k < 3; k++)
                    value += (double)actor[row * 3 + k] * model[k * 3 + col];
                maximum = Math.Max(maximum, Math.Abs(value - render[row * 3 + col]));
            }
        return maximum;
    }
}
