using System.Diagnostics;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Control;

internal sealed record ControlNativeVitalsResponse(
    int NativeVitalsVersion, string HashMode, DateTimeOffset ObservedAtUtc, CurrentBuildVitalsReport Report)
{
    public string InstanceId { get; init; } = "";
}

/// <summary>One bounded candidate acquisition over the authenticated guest channel.</summary>
internal static class ControlNativeVitals
{
    internal static Task<ControlNativeVitalsResponse> CaptureAsync(
        ControlAgentConfiguration configuration, ControlIdentityRequest expected,
        CancellationToken cancellationToken) => CaptureAsync(configuration, expected,
            token => OpenSessionAsync(configuration, expected, token),
            CurrentBuildVitalsCandidateReader.Read, cancellationToken);

    private static async Task<IReadOnlyNativeMemorySession> OpenSessionAsync(
        ControlAgentConfiguration configuration, ControlIdentityRequest expected, CancellationToken token)
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
            foreach (var process in processes)
                process.Dispose();
        }
        // OpenAsync and RevalidateAsync independently hash the executable bytes;
        // sessions and player/component addresses are never reused across calls.
        return await WindowsNativeMemorySession.OpenAsync(expected.ProcessId,
            expected.ProcessStartUtcTicks, expected.ExecutableSha256, token);
    }

    internal static async Task<ControlNativeVitalsResponse> CaptureAsync(
        ControlAgentConfiguration configuration, ControlIdentityRequest expected,
        Func<CancellationToken, Task<IReadOnlyNativeMemorySession>> openSession,
        Func<IReadOnlyNativeMemorySession, CurrentBuildVitalsObservation> read,
        CancellationToken cancellationToken)
    {
        expected.Validate();
        if (expected.MachineName != Environment.MachineName
            || !string.Equals(expected.MachineName, configuration.ExpectedMachineName, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(expected.ExecutableSha256, configuration.ExecutableSha256, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(expected.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Expected native vitals identity differs from the configured machine/build.");
        cancellationToken.ThrowIfCancellationRequested();
        await using var session = await openSession(cancellationToken);
        RequireIdentity(configuration, expected, session.Identity);
        var report = await CurrentBuildVitalsSampleCommand.CaptureAsync(session, read, cancellationToken);
        RequireIdentity(configuration, expected, session.Identity);
        if (report.Observation.Identity != session.Identity)
            throw new InvalidDataException("Native vitals observation belongs to another process identity.");
        cancellationToken.ThrowIfCancellationRequested();
        return new(1, "fresh-bytes", DateTimeOffset.UtcNow, report);
    }

    private static void RequireIdentity(ControlAgentConfiguration configuration,
        ControlIdentityRequest expected, NativeProcessIdentity actual)
    {
        if (expected.ProcessId != actual.ProcessId || expected.ProcessStartUtcTicks != actual.ProcessStartUtcTicks
            || !string.Equals(expected.ExecutableSha256, actual.ExecutableSha256, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(Path.GetFullPath(configuration.ExecutablePath), Path.GetFullPath(actual.ExecutablePath),
                StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Native vitals session does not match the configured process/path/build.");
    }
}
