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
    string Status, ulong? SourceComponent)
{
    public string PlayerKeyDecimal => PlayerKey.ToString(CultureInfo.InvariantCulture);
    public string PlayerUnitIdCandidate => $"u{PlayerKey:X16}";
    public string Qualification =>
        "branch-input-candidate; execution, source semantics and passive freshness unverified; raw address and handle uint64 values may lose precision in JSON consumers";
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
            () => lookup.ResolveComponent(SourceSelectorRva));
    }

    // Injected resolver is the SELF entity's component selector, never the handle
    // branch's referenced-entity lookup. Kept separate for offline synthetic tests.
    internal static PositionRefreshBranchCandidate ReadResolved(
        IReadOnlyNativeMemorySession session, NativeProcessIdentity id, DateTimeOffset started,
        ulong key, ulong entity, ulong position, Action verifyOwner, Func<ulong> resolveSelfSource)
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
                    status = "handle-branch-referenced-entity-unavailable";
                else
                {
                    flag = Take(checked(component + 0x108), 1)[0];
                    if (flag == 0)
                        status = "guard-ineligible-candidate";
                    else
                    {
                        selector = BinaryPrimitives.ReadInt32LittleEndian(Take(checked(id.ModuleBaseAddress + SourceSelectorRva), 4));
                        if (selector is < 0 or >= 0x60)
                            status = "flag-branch-selector-unavailable";
                        else
                        {
                            status = "flag-branch-self-source-unavailable";
                            source = CurrentBuildPlayerLookup.Pointer(resolveSelfSource());
                            status = "flag-branch-self-source-present-candidate";
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
        return new(id, started, DateTimeOffset.UtcNow, key, owner, component, handle, flag, selector, status, source);
    }
}
