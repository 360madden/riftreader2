using System.Diagnostics;

namespace RiftReader2.Live.Tests;

public sealed class NativeReadFileLeaseTests
{
    const string Sha = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
    static readonly TimeSpan Short = TimeSpan.FromMilliseconds(100);

    [Fact] public async Task SameEpochContendsAndDifferentEpochDoesNot()
    {
        using var dir = new TestDirectory();
        await using var first = await Open(dir.Path, 123, 456);
        await Assert.ThrowsAsync<TimeoutException>(() => Open(dir.Path, 123, 456, Short));
        await using var other = await Open(dir.Path, 123, 457);
        await using var third = await Open(dir.Path, 124, 456);
    }

    [Fact] public async Task AsyncDisposeReleasesWithoutDeletingAndIsIdempotent()
    {
        using var dir = new TestDirectory();
        var first = await Open(dir.Path, 1, 2);
        await Task.Run(async () => await first.DisposeAsync());
        first.Dispose();
        Assert.Single(Directory.GetFiles(dir.Path, "*.lock"));
        await using var second = await Open(dir.Path, 1, 2);
    }

    [Fact] public async Task WaitingCancellationDoesNotReleaseCurrentOwner()
    {
        using var dir = new TestDirectory();
        await using var first = await Open(dir.Path, 1, 2);
        using var cancelled = new CancellationTokenSource(100);
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            NativeReadFileLease.AcquireAsync(1, 2, Sha, TimeSpan.FromSeconds(5), cancelled.Token, dir.Path));
        await Assert.ThrowsAsync<TimeoutException>(() => Open(dir.Path, 1, 2, Short));
    }

    [Fact] public async Task InvalidIdentityAndBoundsFailBeforeAcquisition()
    {
        using var dir = new TestDirectory();
        await Assert.ThrowsAsync<ArgumentException>(() => NativeReadFileLease.AcquireAsync(0, 2, Sha, Short, default, dir.Path));
        await Assert.ThrowsAsync<ArgumentException>(() => NativeReadFileLease.AcquireAsync(1, 2, Sha.ToLowerInvariant(), Short, default, dir.Path));
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => NativeReadFileLease.AcquireAsync(1, 2, Sha, TimeSpan.FromSeconds(31), default, dir.Path));
        Assert.Empty(Directory.GetFiles(dir.Path));
    }

    [Fact] public async Task StableLockFileSymlinkIsRejectedWhenSupported()
    {
        if (!OperatingSystem.IsWindows()) return;
        using var dir = new TestDirectory();
        var seed = await Open(dir.Path, 1, 2);
        seed.Dispose();
        var path = Assert.Single(Directory.GetFiles(dir.Path, "*.lock"));
        File.Delete(path);
        var target = System.IO.Path.Combine(dir.Path, "target");
        await File.WriteAllTextAsync(target, "untouched");
        try { File.CreateSymbolicLink(path, target); }
        catch (Exception e) when (e is UnauthorizedAccessException or PlatformNotSupportedException
            || e is IOException io && (io.HResult & 0xFFFF) == 1314) { return; }
        await Assert.ThrowsAsync<IOException>(() => Open(dir.Path, 1, 2));
        Assert.Equal("untouched", await File.ReadAllTextAsync(target));
    }

    [Fact] public async Task OtherProcessCrashReleasesKernelHandle()
    {
        if (!OperatingSystem.IsWindows()) return;
        using var dir = new TestDirectory();
        var seed = await Open(dir.Path, 1, 2);
        seed.Dispose();
        var path = Assert.Single(Directory.GetFiles(dir.Path, "*.lock"));
        var ps = new ProcessStartInfo("powershell.exe") { UseShellExecute = false,
            RedirectStandardOutput = true, RedirectStandardInput = true, CreateNoWindow = true };
        ps.ArgumentList.Add("-NoProfile"); ps.ArgumentList.Add("-NonInteractive"); ps.ArgumentList.Add("-Command");
        var literal = path.Replace("'", "''");
        ps.ArgumentList.Add("$f=[IO.File]::Open('" + literal + "',[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None);[Console]::WriteLine('HELD');[Console]::In.ReadLine()|Out-Null;$f.Dispose()");
        using var child = Process.Start(ps) ?? throw new InvalidOperationException("Cannot start test child.");
        try
        {
            var line = await child.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(10));
            Assert.Equal("HELD", line);
            await Assert.ThrowsAsync<TimeoutException>(() => Open(dir.Path, 1, 2, Short));
            child.Kill();
            await child.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(10));
            await using var recovered = await Open(dir.Path, 1, 2, TimeSpan.FromSeconds(3));
        }
        finally
        {
            if (!child.HasExited) { child.Kill(); await child.WaitForExitAsync(); }
        }
    }

    static Task<NativeReadFileLease> Open(string directory, int pid, long ticks, TimeSpan? timeout = null) =>
        NativeReadFileLease.AcquireAsync(pid, ticks, Sha, timeout ?? TimeSpan.FromSeconds(2), default, directory);

    sealed class TestDirectory : IDisposable
    {
        public string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "rr2-lease-test-" + Guid.NewGuid().ToString("N"));
        public TestDirectory() => Directory.CreateDirectory(Path);
        public void Dispose() => Directory.Delete(Path, recursive: true);
    }
}
