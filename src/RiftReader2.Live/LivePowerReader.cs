using System.ComponentModel;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

/// <summary>Independent native observation; never fills or authenticates addon fields.</summary>
public sealed record LivePowerReport(
    string ContractVersion, string FieldId, string SourceKind, string Recipe,
    string Status, string? Reason, int? Value, int? Maximum,
    string? ObservedAtUtc, string? ExpiresAtUtc, double? AgeMilliseconds,
    double RemainingFreshMilliseconds, NativeProcessIdentity? Identity);

internal sealed record LivePowerRead(
    NativeProcessIdentity? Identity, PowerCandidateObservation? Observation,
    long StartedAtTimestamp, string? Failure)
{
    internal static LivePowerReport Unavailable(string reason) => new(
        "native-power-observation/1", "player.resource.power", "native", PowerCandidateReader.Recipe,
        "unavailable", reason, null, null, null, null, null, 0, null);

    internal LivePowerReport Present(TimeProvider timeProvider, TimeSpan timeout)
    {
        if (Failure is not null || Observation is null || Observation.Status != "complete")
            return Unavailable(Failure ?? Observation?.Reason ?? "native-power-unavailable");
        var age = timeProvider.GetElapsedTime(StartedAtTimestamp).TotalMilliseconds;
        var remaining = Math.Max(0, timeout.TotalMilliseconds - age);
        // Expire values again at publication (including after delivery), never renew their age.
        var fresh = age >= 0 && remaining > 0;
        return new("native-power-observation/1", "player.resource.power", "native", PowerCandidateReader.Recipe,
            fresh ? "fresh" : "expired", fresh ? null : "native-power-expired",
            fresh ? Observation.Power : null, fresh ? Observation.Maximum : null,
            Observation.StartedAtUtc,
            DateTimeOffset.Parse(Observation.StartedAtUtc, System.Globalization.CultureInfo.InvariantCulture).Add(timeout).ToString("O"),
            age >= 0 ? age : null, fresh ? remaining : 0, Identity);
    }
}

internal static class LivePowerReader
{
    internal static async Task<LivePowerRead> ReadAsync(
        DiscoveredTarget target, TimeProvider timeProvider, CancellationToken cancellationToken)
    {
        var started = timeProvider.GetTimestamp();
        if (target.Identity.ExecutableSha256 != PowerCandidateReader.ExecutableSha256)
            return new(null, null, started, "unsupported-native-power-build");
        try
        {
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                target.Identity.ProcessId, target.Identity.ProcessStartUtcTicks,
                PowerCandidateReader.ExecutableSha256, cancellationToken);
            return new(session.Identity,
                await PowerCandidateReader.ReadAsync(session, cancellationToken), started, null);
        }
        catch (Exception error) when (error is Win32Exception or IOException or InvalidDataException or
            ArgumentException or InvalidOperationException or UnauthorizedAccessException)
        {
            return new(null, null, started, $"native-power-read-failed:{error.GetType().Name}");
        }
    }
}
