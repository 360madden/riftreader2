using System.Buffers.Binary;
using System.Globalization;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

internal sealed record CurrentBuildSelectedPositionObservation(
    NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc,
    string SelfKey, string Status, string SelectionBranch, string RawFallbackKey,
    string? TargetKey, string? TargetUnitIdCandidate, string? TargetEntityDecimal,
    CurrentBuildXyz? TargetPositionCandidate, uint[]? TargetPositionRawBits,
    CurrentBuildOpticalCameraCandidate OpticalCameraCandidate,
    CurrentBuildOpticalCameraCandidate OpticalCameraAfterCandidate, bool CameraStableCandidate)
{
    public string Qualification =>
        "conditional raw selection and cached position candidate; selected-target semantics, freshness and restart unverified";
}

/// <summary>
/// Narrow position-only target observation. Does not depend on the historical
/// health/vitals record reader or call any game getter. The game's conditional
/// fallback-key branch is used ONLY when its native selection guard admits it.
/// </summary>
internal static class CurrentBuildSelectedPositionCandidateReader
{
    private const ulong HistoricalHealthSelectorRva = 0x2F57850;
    private const ulong UpdatedHealthSelectorRva = 0x2F68850;
    private const ulong HistoricalPresenceSelectorRva = 0x2F582E0;
    private const ulong UpdatedPresenceSelectorRva = 0x2F692E0;
    private const ulong HistoricalSelectionSelectorRva = 0x2F57260;
    private const ulong UpdatedSelectionSelectorRva = 0x2F68260;
    private const ulong HistoricalOwnerVptrRva = 0x2927448;
    private const ulong UpdatedOwnerVptrRva = 0x2933218;

    internal static CurrentBuildSelectedPositionObservation Read(IReadOnlyNativeMemorySession session)
    {
        ArgumentNullException.ThrowIfNull(session);
        var started = DateTimeOffset.UtcNow;
        var identity = session.Identity;
        if (!CurrentBuildPlayerLookup.IsCoreBuild(identity.ExecutableSha256) ||
            identity.ProcessId <= 0 || identity.ProcessStartUtcTicks <= 0)
            throw new InvalidDataException("Target position requires an exact qualified RIFT build and process epoch.");
        var updated = CurrentBuildPlayerLookup.IsUpdatedBuild(identity.ExecutableSha256);
        var lookup = CurrentBuildPlayerLookup.Resolve(session);
        var anchors = new List<(ulong Address, byte[] Bytes)>();
        var readBytes = 0;
        byte[] Take(ulong address, int length)
        {
            readBytes = checked(readBytes + length);
            if (readBytes > 64 * 1024)
                throw new InvalidDataException("Selected target read budget exceeded.");
            var bytes = CurrentBuildPlayerLookup.Exact(session, address, length);
            anchors.Add((address, bytes));
            return bytes;
        }
        ulong Q(ulong address) => BinaryPrimitives.ReadUInt64LittleEndian(Take(address, 8));
        ulong Ptr(ulong address, int length = 8) => CurrentBuildPlayerLookup.Pointer(address, length);
        byte Slot(ulong selectorRva)
        {
            var selector = BinaryPrimitives.ReadInt32LittleEndian(
                Take(checked(identity.ModuleBaseAddress + selectorRva), 4));
            if (selector is < 0 or >= 0x60)
                throw new InvalidDataException("Target selection component selector is invalid.");
            return Take(checked(lookup.EntityAddress + 0x18 + (ulong)selector), 1)[0];
        }
        ulong Component(byte slot)
        {
            if (slot == 0xFF) return 0;
            var table = Ptr(Q(checked(lookup.EntityAddress + 0x78)));
            return Ptr(Q(checked(table + (ulong)slot * 8)));
        }
        void Verify()
        {
            if (session.Identity != identity)
                throw new InvalidDataException("Target position process epoch changed.");
            foreach (var (address, bytes) in anchors)
                CurrentBuildPlayerLookup.RequireSame(
                    CurrentBuildPlayerLookup.Exact(session, address, bytes.Length), bytes);
            lookup.VerifyUnchanged();
            if (session.Identity != identity)
                throw new InvalidDataException("Target position process epoch changed.");
        }

        var healthSelector = updated ? UpdatedHealthSelectorRva : HistoricalHealthSelectorRva;
        var health = Ptr(lookup.ResolveComponent(healthSelector), 0x328);
        if (Q(checked(health + 0x10)) != lookup.EntityAddress)
            throw new InvalidDataException("Selected target health component owner changed.");
        var owner = Ptr(Q(checked(health + 0x40)), 0x28);
        var ownerData = Take(owner, 0x28);
        var expectedVptr = checked(identity.ModuleBaseAddress +
            (updated ? UpdatedOwnerVptrRva : HistoricalOwnerVptrRva));
        if (BinaryPrimitives.ReadUInt64LittleEndian(ownerData) != expectedVptr ||
            Q(checked(expectedVptr + 0x40)) != checked(identity.ModuleBaseAddress +
                (updated ? 0x19D2020UL : 0x19D21E0UL)))
            throw new InvalidDataException("Selected target player owner type fingerprint differs.");
        var rawFallback = BinaryPrimitives.ReadUInt64LittleEndian(ownerData.AsSpan(0x20));
        var cameraBefore = CurrentBuildOpticalCameraCandidateReader.TryRead(session, lookup.PlayerSystemAddress);
        var branch = "unavailable";
        var useFallback = false;

        var presenceSlot = Slot(updated ? UpdatedPresenceSelectorRva : HistoricalPresenceSelectorRva);
        if (presenceSlot != 0xFF)
        {
            branch = "presence-component-fallback";
            useFallback = true;
        }
        else
        {
            var selectionSlot = Slot(updated ? UpdatedSelectionSelectorRva : HistoricalSelectionSelectorRva);
            var selection = Component(selectionSlot);
            if (selection == 0)
            {
                branch = "selection-component-missing-fallback";
                useFallback = true;
            }
            else
            {
                Ptr(selection, 0x2B0);
                var first = Take(checked(selection + 0x280), 16);
                var second = Take(checked(selection + 0x290), 16);
                if (first.All(value => value == 0) && second.All(value => value == 0))
                {
                    var state = Ptr(Q(checked(health + 0x320)), 0x44);
                    var stateValue = BinaryPrimitives.ReadInt32LittleEndian(Take(checked(state + 0x40), 4));
                    if (stateValue is < 6 or > 11)
                    {
                        branch = "selection-state-fallback";
                        useFallback = true;
                    }
                    else if (Take(checked(selection + 0x2A0), 16).All(value => value == 0))
                    {
                        branch = "empty-selection-fallback";
                        useFallback = true;
                    }
                    else branch = "selection-override-active";
                }
                else branch = "selection-override-active";
            }
        }

        string status = useFallback ? (rawFallback == 0 ? "no-target" : "target-key-candidate")
            : "selection-override-unresolved";
        string? targetKey = useFallback && rawFallback != 0
            ? rawFallback.ToString(CultureInfo.InvariantCulture) : null;
        ulong targetEntity = 0;
        CurrentBuildXyz? xyz = null;
        uint[]? bits = null;
        if (targetKey is not null)
        {
            try
            {
                var resolved = lookup.ResolveReferencedComponent(rawFallback,
                    CurrentBuildPlayerLookup.PositionIndexRvaFor(identity.ExecutableSha256));
                targetEntity = resolved.ReferencedEntityAddress;
                var position = CurrentBuildPositionCandidateReader.ReadOwned(session,
                    _ => new(rawFallback, targetEntity, resolved.SourceComponentAddress, Verify));
                xyz = position.Position;
                bits = [BitConverter.SingleToUInt32Bits(xyz.X),
                    BitConverter.SingleToUInt32Bits(xyz.Y), BitConverter.SingleToUInt32Bits(xyz.Z)];
                status = "position-candidate";
            }
            catch (InvalidDataException)
            {
                // A selected key may refer to an entity without a loaded position.
                // Keep the key candidate, but never manufacture a coordinate.
                status = "position-unavailable";
                targetEntity = 0;
            }
        }
        var cameraAfter = CurrentBuildOpticalCameraCandidateReader.TryRead(session, lookup.PlayerSystemAddress);
        Verify();
        return new(identity, started, DateTimeOffset.UtcNow,
            lookup.PlayerKey.ToString(CultureInfo.InvariantCulture), status, branch,
            rawFallback.ToString(CultureInfo.InvariantCulture), targetKey,
            targetKey is null ? null : $"u{rawFallback:X16}",
            targetEntity == 0 ? null : targetEntity.ToString(CultureInfo.InvariantCulture),
            xyz, bits, cameraBefore, cameraAfter,
            CurrentBuildOpticalCameraCandidateReader.SameProjectionSnapshot(cameraBefore, cameraAfter));
    }
}
