using System.Buffers.Binary;
using System.Globalization;
using System.Text.Json.Serialization;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

/// <summary>Read-only branch-input evidence, not a refresh or position freshness claim.</summary>
internal sealed record PositionRefreshBranchCandidate(
    NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc,
    [property: JsonIgnore] ulong PlayerKey, ulong PlayerEntity, ulong PositionComponent,
    ulong? ReferencedHandle, byte? Flag, int? SourceSelector,
    string Status, ulong? SourceComponent,
    [property: JsonIgnore] ulong? ReferencedEntity = null,
    [property: JsonIgnore] ulong? SourceGuardContext = null,
    int? SourceGuardValue = null,
    bool? SourceProviderPresent = null,
    string SourceGuardStatus = "not-applicable")
{
    public string? ReferencedEntityHex => ReferencedEntity is ulong entity ? $"0x{entity:X16}" : null;
    public string? ReferencedHandleDecimal => ReferencedHandle?.ToString(CultureInfo.InvariantCulture);
    public string? ReferencedHandleHex => ReferencedHandle is ulong handle ? $"0x{handle:X16}" : null;
    public string? SourceGuardContextHex => SourceGuardContext is ulong context ? $"0x{context:X16}" : null;
    public bool? SourceGuardEligible => SourceGuardStatus switch
    {
        "eligible-candidate" => true,
        "ineligible-negative-context" or "ineligible-null-provider" => false,
        _ => null
    };
    public string PlayerKeyDecimal => PlayerKey.ToString(CultureInfo.InvariantCulture);
    public string PlayerUnitIdCandidate => $"u{PlayerKey:X16}";
    public string Qualification =>
        "branch-input-candidate; 0x6136B0 source predicate is sampled only on the flag branch; writer execution, source semantics and passive freshness unverified; raw address and handle uint64 values may lose precision in JSON consumers";
}

internal static class CurrentBuildPositionRefreshBranchCandidateReader
{
    internal const ulong SourceSelectorRva = 0x2F57918;
    internal const ulong PositionSelectorRva = 0x2F588A0;

    internal static PositionRefreshBranchCandidate Read(IReadOnlyNativeMemorySession session)
    {
        ArgumentNullException.ThrowIfNull(session);
        var started = DateTimeOffset.UtcNow;
        var lookup = CurrentBuildPlayerLookup.Resolve(session);
        var position = lookup.ResolveComponent(PositionSelectorRva);
        return ReadResolved(session, session.Identity, started, lookup.PlayerKey,
            lookup.EntityAddress, position, lookup.VerifyUnchanged,
            () => lookup.ResolveComponent(SourceSelectorRva),
            handle => lookup.ResolveReferencedComponent(handle, SourceSelectorRva));
    }

    // Separate resolvers prevent a handle-branch miss from falling back to SELF.
    internal static PositionRefreshBranchCandidate ReadResolved(
        IReadOnlyNativeMemorySession session, NativeProcessIdentity id, DateTimeOffset started,
        ulong key, ulong entity, ulong position, Action verifyOwner, Func<ulong> resolveSelfSource,
        Func<ulong, (ulong ReferencedEntityAddress, ulong SourceComponentAddress)>? resolveReferencedSource = null)
    {
        ArgumentNullException.ThrowIfNull(session);
        ArgumentNullException.ThrowIfNull(verifyOwner);
        ArgumentNullException.ThrowIfNull(resolveSelfSource);
        if (session.Identity != id || id.ProcessId <= 0 || id.ProcessStartUtcTicks <= 0 ||
            !string.Equals(id.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase) ||
            id.ModuleSize < SourceSelectorRva + 4 || key == 0)
            throw new InvalidDataException("Invalid current-build process or owner identity.");
        var owner = CurrentBuildPlayerLookup.Pointer(entity, 128);
        var component = CurrentBuildPlayerLookup.Pointer(position, 0x109);
        var anchors = new List<(ulong Address, byte[] Bytes)>();
        byte[] Take(ulong address, int count)
        {
            var bytes = CurrentBuildPlayerLookup.Exact(session, address, count);
            anchors.Add((address, bytes.ToArray()));
            return bytes;
        }

        ulong? handle = null;
        byte? flag = null;
        int? selector = null;
        ulong? source = null;
        ulong? referencedEntity = null;
        ulong? sourceGuardContext = null;
        int? sourceGuardValue = null;
        bool? sourceProviderPresent = null;
        var sourceGuardStatus = "not-applicable";
        var status = "unavailable";
        try
        {
            var componentOwner = BinaryPrimitives.ReadUInt64LittleEndian(Take(checked(component + 0x10), 8));
            if (componentOwner != owner)
                status = "position-owner-mismatch";
            else
            {
                handle = BinaryPrimitives.ReadUInt64LittleEndian(Take(checked(component + 0x100), 8));
                if (handle != 0)
                {
                    sourceGuardStatus = "not-applicable-handle-branch";
                    status = "handle-branch-referenced-entity-unavailable";
                    if (resolveReferencedSource is not null)
                    {
                        selector = BinaryPrimitives.ReadInt32LittleEndian(Take(checked(id.ModuleBaseAddress + SourceSelectorRva), 4));
                        if (selector is < 0 or >= 0x60)
                            status = "handle-branch-selector-unavailable";
                        else
                        {
                            var resolved = resolveReferencedSource(handle.Value);
                            var resolvedEntity = CurrentBuildPlayerLookup.Pointer(resolved.ReferencedEntityAddress, 128);
                            var resolvedSource = CurrentBuildPlayerLookup.Pointer(resolved.SourceComponentAddress);
                            referencedEntity = resolvedEntity;
                            source = resolvedSource;
                            status = "handle-branch-referenced-source-present-candidate";
                        }
                    }
                }
                else
                {
                    flag = Take(checked(component + 0x108), 1)[0];
                    if (flag == 0)
                    {
                        status = "guard-ineligible-candidate";
                        sourceGuardStatus = "not-evaluated-flag-zero";
                    }
                    else
                    {
                        selector = BinaryPrimitives.ReadInt32LittleEndian(Take(checked(id.ModuleBaseAddress + SourceSelectorRva), 4));
                        if (selector is < 0 or >= 0x60)
                        {
                            status = "flag-branch-selector-unavailable";
                            sourceGuardStatus = "unavailable-invalid-selector";
                        }
                        else
                        {
                            status = "flag-branch-self-source-unavailable";
                            sourceGuardStatus = "unavailable-source-component";
                            var candidateSource = CurrentBuildPlayerLookup.Pointer(resolveSelfSource());
                            status = "flag-branch-source-owner-unavailable";
                            sourceGuardStatus = "unavailable-source-owner";
                            var sourceOwner = BinaryPrimitives.ReadUInt64LittleEndian(Take(checked(candidateSource + 0x10), 8));
                            if (sourceOwner != owner)
                            {
                                status = "flag-branch-source-owner-mismatch";
                                sourceGuardStatus = "unavailable-source-owner-mismatch";
                            }
                            else
                            {
                                source = candidateSource;
                                status = "flag-branch-guard-unavailable";
                                sourceGuardStatus = "unavailable-context-pointer";
                                var contextRaw = BinaryPrimitives.ReadUInt64LittleEndian(Take(checked(candidateSource + 0x48), 8));
                                if (contextRaw == 0)
                                {
                                    sourceGuardStatus = "unavailable-null-context";
                                }
                                else
                                {
                                    sourceGuardContext = CurrentBuildPlayerLookup.Pointer(contextRaw, 0x28);
                                    sourceGuardStatus = "unavailable-nested-value";
                                    sourceGuardValue = BinaryPrimitives.ReadInt32LittleEndian(
                                        Take(checked(sourceGuardContext.Value + 0x24), 4));
                                    if (sourceGuardValue.Value < 0)
                                    {
                                        status = "flag-branch-guard-ineligible-candidate";
                                        sourceGuardStatus = "ineligible-negative-context";
                                    }
                                    else
                                    {
                                        sourceGuardStatus = "unavailable-provider-pointer";
                                        var provider = BinaryPrimitives.ReadUInt64LittleEndian(Take(checked(candidateSource + 0x58), 8));
                                        sourceProviderPresent = provider != 0;
                                        if (provider == 0)
                                        {
                                            status = "flag-branch-guard-ineligible-candidate";
                                            sourceGuardStatus = "ineligible-null-provider";
                                        }
                                        else
                                        {
                                            status = "flag-branch-guard-eligible-candidate";
                                            sourceGuardStatus = "eligible-candidate";
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        catch (InvalidDataException)
        {
            // Preserve branch-specific unavailable status and recheck all
            // successful inputs plus the lookup owner before publication.
        }
        foreach (var anchor in anchors)
            CurrentBuildPlayerLookup.RequireSame(CurrentBuildPlayerLookup.Exact(session, anchor.Address, anchor.Bytes.Length), anchor.Bytes);
        verifyOwner();
        if (session.Identity != id) throw new InvalidDataException("Process identity changed during branch capture.");
        return new(id, started, DateTimeOffset.UtcNow, key, owner, component, handle, flag,
            selector, status, source, referencedEntity, sourceGuardContext, sourceGuardValue,
            sourceProviderPresent, sourceGuardStatus);
    }
}
