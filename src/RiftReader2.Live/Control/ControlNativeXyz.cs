using System.Diagnostics;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Control;

internal sealed record ControlNativeXyzReport(
    NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc,
    string UnitKey, string UnitIdCandidate, float X, float Y, float Z)
{
    public int SchemaVersion => 1;
    public string ContractVersion => "native-current-position-candidate-sample/1";
    public string Qualification => "candidate-only-not-passive-fresh-or-player-semantic-qualified";
    public string OwnerIdentityStatus => "player-component-chain-anchored";
}

internal sealed record ControlNativeXyzResponse(
    int NativeXyzVersion, string HashMode, DateTimeOffset ObservedAtUtc, ControlNativeXyzReport Report)
{
    public string InstanceId { get; init; } = "";
}

/// <summary>One bounded read-only candidate, with no retained session or coordinate fallback.</summary>
internal static class ControlNativeXyz
{
    internal static Task<ControlNativeXyzResponse> CaptureAsync(
        ControlAgentConfiguration configuration, ControlIdentityRequest expected, CancellationToken token) =>
        CaptureAsync(configuration, expected, ct => OpenSessionAsync(configuration, expected, ct),
            CurrentBuildPositionCandidateReader.ReadOwned, token);

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
            foreach (var process in processes) process.Dispose();
        }
        return await WindowsNativeMemorySession.OpenAsync(expected.ProcessId,
            expected.ProcessStartUtcTicks, expected.ExecutableSha256, token);
    }

    internal static async Task<ControlNativeXyzResponse> CaptureAsync(
        ControlAgentConfiguration configuration, ControlIdentityRequest expected,
        Func<CancellationToken, Task<IReadOnlyNativeMemorySession>> openSession,
        Func<IReadOnlyNativeMemorySession, CurrentBuildOwnedPosition> read, CancellationToken token)
    {
        expected.Validate();
        if (expected.MachineName != Environment.MachineName
            || !string.Equals(expected.MachineName, configuration.ExpectedMachineName, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(expected.ExecutableSha256, configuration.ExecutableSha256, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(expected.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Expected native XYZ identity differs from configured machine/build.");
        token.ThrowIfCancellationRequested();
        await using var session = await openSession(token);
        RequireIdentity(configuration, expected, session.Identity);
        var identity = session.Identity;
        var started = DateTimeOffset.UtcNow;
        var value = read(session);
        token.ThrowIfCancellationRequested();
        if (value.UnitKey == 0 || !float.IsFinite(value.Position.X)
            || !float.IsFinite(value.Position.Y) || !float.IsFinite(value.Position.Z))
            throw new InvalidDataException("Native XYZ candidate is invalid.");
        var invalidation = await session.RevalidateAsync(token);
        if (invalidation is not null)
            throw new InvalidDataException("Native XYZ process identity invalidated.");
        RequireIdentity(configuration, expected, session.Identity);
        if (identity != session.Identity)
            throw new InvalidDataException("Native XYZ process identity changed.");
        token.ThrowIfCancellationRequested();
        var report = new ControlNativeXyzReport(identity, started, DateTimeOffset.UtcNow,
            value.UnitKeyText, value.UnitIdCandidate, value.Position.X, value.Position.Y, value.Position.Z);
        return new(1, "fresh-bytes", DateTimeOffset.UtcNow, report);
    }

    private static void RequireIdentity(ControlAgentConfiguration configuration,
        ControlIdentityRequest expected, NativeProcessIdentity actual)
    {
        if (expected.ProcessId != actual.ProcessId || expected.ProcessStartUtcTicks != actual.ProcessStartUtcTicks
            || !string.Equals(expected.ExecutableSha256, actual.ExecutableSha256, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(Path.GetFullPath(configuration.ExecutablePath), Path.GetFullPath(actual.ExecutablePath),
                StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Native XYZ session does not match configured process/path/build.");
    }
}
