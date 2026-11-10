using System.Diagnostics;

namespace RiftReader2.Live.Control;

/// <summary>
/// Preserve legacy one-process admission when unbound, but allow exact physical
/// PID/start-epoch reads when the control agent has an explicit multibox binding.
/// </summary>
internal static class ControlNativeProcessGate
{
    internal static int SelectExpectedProcessIndex(
        IReadOnlyList<int> processIds,
        ControlAgentConfiguration configuration,
        ControlIdentityRequest expected)
    {
        ArgumentNullException.ThrowIfNull(processIds);
        ArgumentNullException.ThrowIfNull(configuration);
        ArgumentNullException.ThrowIfNull(expected);
        expected.Validate();
        if (configuration.BoundProcessId.HasValue != configuration.BoundProcessStartUtcTicks.HasValue)
            throw new InvalidOperationException("Incomplete native process binding.");
        if (configuration.BoundProcessId is int boundPid
            && (boundPid != expected.ProcessId
                || configuration.BoundProcessStartUtcTicks != expected.ProcessStartUtcTicks))
            throw new InvalidOperationException("Native request differs from the configured bound process epoch.");

        var selected = WindowsControlDesktop.SelectProcessIndex(
            processIds, configuration.BoundProcessId, configuration.ProcessName);
        if (processIds[selected] != expected.ProcessId)
            throw new InvalidOperationException("Native process selection differs from the expected PID.");
        return selected;
    }

    internal static void RequireExpectedProcessEpoch(
        ControlAgentConfiguration configuration,
        ControlIdentityRequest expected)
    {
        var processes = Process.GetProcessesByName(configuration.ProcessName);
        try
        {
            var selected = SelectExpectedProcessIndex(
                processes.Select(process => process.Id).ToArray(), configuration, expected);
            var process = processes[selected];
            process.Refresh();
            if (process.HasExited
                || process.StartTime.ToUniversalTime().Ticks != expected.ProcessStartUtcTicks)
                throw new InvalidOperationException("Native process epoch changed during preflight.");
        }
        finally
        {
            foreach (var process in processes)
                process.Dispose();
        }
    }
}
