using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace RiftReader2.Live.Tests;

// These fixtures depend on real process startup, kernel signals and short
// real-time watchdog intervals. Keep them out of competing test collections
// without changing the production timeouts or removing any assertions.
[CollectionDefinition(Name, DisableParallelization = true)]
public sealed class WindowsTimingFixtureCollection
{
    public const string Name = "Windows timing and disposable process fixtures";
}

internal static class DisposableProcessExit
{
    // Process.HasExited is not the independent kernel-signaled observation
    // required by the epoch tests. Hold the exact child handle across Kill.
    public static async Task KillAndWaitAsync(Process child)
    {
        var handle = child.SafeHandle;
        child.Kill(entireProcessTree: true);
        var result = WaitForSingleObject(handle, 10_000);
        Assert.True(result == 0, $"Disposable child {child.Id} did not signal exit (wait result 0x{result:X8}).");
        await child.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(10));
        Assert.True(child.HasExited);
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern uint WaitForSingleObject(SafeProcessHandle handle, uint milliseconds);
}
