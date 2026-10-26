using System.Text.Json;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class ControlAgentLifetimeTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Shutdown_AcknowledgesOnlyAfterCleanupAndRetainsUncertainRelease(bool pending)
    {
        var root = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            if (pending) File.WriteAllText(Path.Combine(root, "pending.json"), "{}");
            var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            var cleaned = false;
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            var run = ControlAgentLifetime.RunAsync(root, async token =>
            {
                entered.SetResult();
                try { await Task.Delay(Timeout.Infinite, token); }
                finally
                {
                    Assert.False(File.Exists(Path.Combine(root, "shutdown-complete.json")));
                    cleaned = true;
                }
            }, timeout.Token);
            await entered.Task;
            File.WriteAllText(Path.Combine(root, "shutdown.request"), "stop");
            await run;
            Assert.True(cleaned);
            using var result = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "shutdown-complete.json")));
            Assert.Equal(!pending, result.RootElement.GetProperty("clean").GetBoolean());
        }
        finally { Directory.Delete(root, true); }
    }

    [Fact]
    public async Task StaleRequest_DoesNotStartAgent()
    {
        var root = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            File.WriteAllText(Path.Combine(root, "shutdown.request"), "old");
            await Assert.ThrowsAsync<InvalidOperationException>(() => ControlAgentLifetime.RunAsync(root,
                _ => throw new Exception("must not start"), CancellationToken.None));
        }
        finally { Directory.Delete(root, true); }
    }
}
