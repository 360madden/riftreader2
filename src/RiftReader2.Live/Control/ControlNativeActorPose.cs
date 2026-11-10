using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Control;

internal sealed record ControlNativeActorPoseResponse(
    int NativeActorPoseVersion, string HashMode, DateTimeOffset ObservedAtUtc,
    CurrentBuildActorPoseCandidate Report)
{
    public string InstanceId { get; init; } = "";
}

/// <summary>One authenticated, disarmed, read-only actor/model pose candidate.</summary>
internal static class ControlNativeActorPose
{
    internal static Task<ControlNativeActorPoseResponse> CaptureAsync(
        ControlAgentConfiguration configuration, ControlIdentityRequest expected,
        CancellationToken token) =>
        CaptureAsync(configuration, expected, ct => OpenSessionAsync(configuration, expected, ct),
            CurrentBuildActorPoseCandidateReader.Read, token);

    private static async Task<IReadOnlyNativeMemorySession> OpenSessionAsync(
        ControlAgentConfiguration configuration, ControlIdentityRequest expected,
        CancellationToken token)
    {
        ControlNativeProcessGate.RequireExpectedProcessEpoch(configuration, expected);
        return await WindowsNativeMemorySession.OpenAsync(expected.ProcessId,
            expected.ProcessStartUtcTicks, expected.ExecutableSha256, token);
    }

    internal static async Task<ControlNativeActorPoseResponse> CaptureAsync(
        ControlAgentConfiguration configuration, ControlIdentityRequest expected,
        Func<CancellationToken, Task<IReadOnlyNativeMemorySession>> openSession,
        Func<IReadOnlyNativeMemorySession, CurrentBuildActorPoseCandidate> read,
        CancellationToken token)
    {
        expected.Validate();
        if (expected.MachineName != Environment.MachineName
            || !string.Equals(expected.MachineName, configuration.ExpectedMachineName, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(expected.ExecutableSha256, configuration.ExecutableSha256, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(expected.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Expected actor pose identity differs from configured machine/build.");
        token.ThrowIfCancellationRequested();
        await using var session = await openSession(token);
        var identity = session.Identity;
        if (expected.ProcessId != identity.ProcessId || expected.ProcessStartUtcTicks != identity.ProcessStartUtcTicks
            || !string.Equals(expected.ExecutableSha256, identity.ExecutableSha256, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(Path.GetFullPath(configuration.ExecutablePath), Path.GetFullPath(identity.ExecutablePath),
                StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Native actor pose session does not match configured process/path/build.");
        var observation = read(session);
        token.ThrowIfCancellationRequested();
        if (observation.Identity != identity || observation.PlayerKey == 0
            || session.Identity != identity)
            throw new InvalidDataException("Native actor pose candidate identity invalid.");
        if (await session.RevalidateAsync(token) is not null || session.Identity != identity)
            throw new InvalidDataException("Native actor pose identity invalidated; no report published.");
        token.ThrowIfCancellationRequested();
        return new(1, "fresh-bytes", DateTimeOffset.UtcNow, observation);
    }
}
