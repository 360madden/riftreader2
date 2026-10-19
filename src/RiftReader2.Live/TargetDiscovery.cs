using System.Diagnostics;
using System.Security.Cryptography;
using RiftReader2.Domain;

namespace RiftReader2.Live;

public sealed record DiscoveredTarget(
    LiveAttachmentIdentity Identity,
    string ExecutablePath,
    string ProcessName);

public sealed record TargetDiscoveryResult(
    string Status,
    int ProcessCount,
    DiscoveredTarget? Target,
    string? Reason);

public static class TargetDiscovery
{
    public static async Task<TargetDiscoveryResult> DiscoverAsync(
        string processName,
        string readerSessionNonce,
        CancellationToken cancellationToken)
    {
        var processes = Process.GetProcessesByName(processName);
        try
        {
            if (processes.Length == 0)
                return new("not-found", 0, null, "No rift_x64 process is running.");
            if (processes.Length != 1)
                return new("ambiguous", processes.Length, null, "More than one rift_x64 process is running.");

            var process = processes[0];
            process.Refresh();
            if (process.HasExited)
                return new("not-found", 0, null, "The discovered rift_x64 process exited.");
            var startTicks = process.StartTime.ToUniversalTime().Ticks;
            var path = process.MainModule?.FileName;
            if (string.IsNullOrWhiteSpace(path))
                return new("identity-unavailable", 1, null, "The executable path is unavailable.");
            await using var stream = new FileStream(
                path,
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read,
                128 * 1024,
                FileOptions.Asynchronous | FileOptions.SequentialScan);
            var hash = Convert.ToHexString(await SHA256.HashDataAsync(stream, cancellationToken));
            process.Refresh();
            if (process.HasExited || process.StartTime.ToUniversalTime().Ticks != startTicks)
                return new("identity-changed", 1, null, "The process identity changed during executable hashing.");
            var pathAfterHash = process.MainModule?.FileName;
            if (string.IsNullOrWhiteSpace(pathAfterHash) ||
                !string.Equals(Path.GetFullPath(path), Path.GetFullPath(pathAfterHash), StringComparison.OrdinalIgnoreCase))
                return new("identity-changed", 1, null, "The process executable path changed during executable hashing.");
            var identity = new LiveAttachmentIdentity(process.Id, startTicks, hash, readerSessionNonce);
            return new("single-target", 1, new(identity, Path.GetFullPath(path), process.ProcessName), null);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            return new("identity-unavailable", processes.Length, null, exception.Message);
        }
        finally
        {
            foreach (var process in processes)
                process.Dispose();
        }
    }
}
