using System.Diagnostics;
using System.Text.Json;

namespace RiftReader2.Live.Control;

/// <summary>Local launcher shutdown request; acknowledgement follows action cleanup.</summary>
public static class ControlAgentLifetime
{
    public static async Task RunAsync(string outputDirectory, Func<CancellationToken, Task> run,
        CancellationToken cancellationToken)
    {
        var request = Path.Combine(outputDirectory, "shutdown.request");
        if (File.Exists(request))
            throw new InvalidOperationException("Stale shutdown request; use a fresh agent run directory.");
        using var stopping = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        var requested = false;
        var watcher = WatchAsync();
        var completed = false;
        try
        {
            try { await run(stopping.Token); }
            catch (OperationCanceledException) when (stopping.IsCancellationRequested) { }
            completed = true;
        }
        finally
        {
            await stopping.CancelAsync();
            await watcher;
            if (requested && completed)
            {
                using var process = Process.GetCurrentProcess();
                var receipt = JsonSerializer.Serialize(new
                {
                    processId = process.Id,
                    processStartUtcTicks = process.StartTime.ToUniversalTime().Ticks,
                    clean = !File.Exists(Path.Combine(outputDirectory, "pending.json")),
                    completedAtUtc = DateTimeOffset.UtcNow
                });
                var path = Path.Combine(outputDirectory, "shutdown-complete.json");
                await File.WriteAllTextAsync(path + ".tmp", receipt, CancellationToken.None);
                File.Move(path + ".tmp", path, false);
            }
        }

        async Task WatchAsync()
        {
            try
            {
                while (!stopping.IsCancellationRequested)
                {
                    if (File.Exists(request))
                    {
                        requested = true;
                        await stopping.CancelAsync();
                        return;
                    }
                    await Task.Delay(100, stopping.Token);
                }
            }
            catch (OperationCanceledException) when (stopping.IsCancellationRequested) { }
        }
    }
}
