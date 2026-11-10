using System.Diagnostics;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Control;

internal sealed record ControlNativeOrientationResponse(
    int NativeOrientationVersion, string HashMode, DateTimeOffset ObservedAtUtc,
    CurrentBuildOrientationCandidate Report)
{
    public string InstanceId { get; init; } = "";
}

/// <summary>
/// One bounded read-only player-owned matrix candidate via the authenticated guest.
/// It never claims to be an actor-facing value until independent calibration.
/// </summary>
internal static class ControlNativeOrientation
{
    internal static Task<ControlNativeOrientationResponse> CaptureAsync(
        ControlAgentConfiguration configuration, ControlIdentityRequest expected,
        CancellationToken token) =>
        CaptureAsync(configuration, expected, ct => OpenSessionAsync(configuration, expected, ct),
            CurrentBuildOrientationCandidateReader.Read, token);

    private static async Task<IReadOnlyNativeMemorySession> OpenSessionAsync(
        ControlAgentConfiguration configuration, ControlIdentityRequest expected,
        CancellationToken token)
    {
        var processes = Process.GetProcessesByName(configuration.ProcessName);
        try
        {
            if (processes.Length != 1 || processes[0].Id != expected.ProcessId
                || processes[0].StartTime.ToUniversalTime().Ticks != expected.ProcessStartUtcTicks)
                throw new InvalidOperationException("Expected exactly one matching RIFT process epoch.");
        }
        finally
        {
            foreach (var process in processes) process.Dispose();
        }
        return await WindowsNativeMemorySession.OpenAsync(expected.ProcessId,
            expected.ProcessStartUtcTicks, expected.ExecutableSha256, token);
    }

    internal static async Task<ControlNativeOrientationResponse> CaptureAsync(
        ControlAgentConfiguration configuration, ControlIdentityRequest expected,
        Func<CancellationToken, Task<IReadOnlyNativeMemorySession>> openSession,
        Func<IReadOnlyNativeMemorySession, CurrentBuildOrientationCandidate> read,
        CancellationToken token)
    {
        expected.Validate();
        if (expected.MachineName != Environment.MachineName
            || !string.Equals(expected.MachineName, configuration.ExpectedMachineName, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(expected.ExecutableSha256, configuration.ExecutableSha256, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(expected.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Expected native orientation identity differs from configured machine/build.");
        token.ThrowIfCancellationRequested();
        await using var session = await openSession(token);
        var identity = session.Identity;
        if (expected.ProcessId != identity.ProcessId || expected.ProcessStartUtcTicks != identity.ProcessStartUtcTicks
            || !string.Equals(expected.ExecutableSha256, identity.ExecutableSha256, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(Path.GetFullPath(configuration.ExecutablePath), Path.GetFullPath(identity.ExecutablePath),
                StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Native orientation session does not match configured process/path/build.");
        var observation = read(session);
        token.ThrowIfCancellationRequested();
        if (observation.Identity != identity || observation.UnitKey == 0
            || session.Identity != identity)
            throw new InvalidDataException("Native orientation candidate identity invalid.");
        if (await session.RevalidateAsync(token) is not null || session.Identity != identity)
            throw new InvalidDataException("Native orientation identity invalidated; no report published.");
        token.ThrowIfCancellationRequested();
        return new(1, "fresh-bytes", DateTimeOffset.UtcNow, observation);
    }
}
