using System.Security.AccessControl;
using System.Security.Principal;
using Xunit.Abstractions;

namespace RiftReader2.Live.Tests;

/// <summary>Isolated filesystem tests only; no game, VM, production lease directory or process reads.</summary>
public sealed class NativeReadFileLeaseAdversarialTests(ITestOutputHelper output)
{
    const string Sha = "ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789";
    static Task<NativeReadFileLease> Open(string path, int pid = 123, long start = 456,
        string sha = Sha, TimeSpan? timeout = null, CancellationToken token = default) =>
        NativeReadFileLease.AcquireAsync(pid, start, sha, timeout ?? TimeSpan.Zero, token, path);

    [Fact]
    public async Task LowercaseBuildCannotBypassHeldIdentityAndCreatesNoSecondFile()
    {
        using var dir = new IsolatedDirectory();
        await using var held = await Open(dir.Path);
        await Assert.ThrowsAsync<ArgumentException>(() => Open(dir.Path, sha: Sha.ToLowerInvariant()));
        await Assert.ThrowsAsync<TimeoutException>(() => Open(dir.Path));
        Assert.Single(Directory.GetFiles(dir.Path, "*.lock"));
    }

    [Fact]
    public async Task WindowsDirectoryCasingStillContendsForSameIdentity()
    {
        if (!OperatingSystem.IsWindows()) { output.WriteLine("Windows path casing case not exercised."); return; }
        using var dir = new IsolatedDirectory();
        await using var held = await Open(dir.Path);
        await Assert.ThrowsAsync<TimeoutException>(() => Open(dir.Path.ToUpperInvariant()));
        Assert.Single(Directory.GetFiles(dir.Path, "*.lock"));
    }

    [Fact]
    public async Task WrongPidStartOrBuildIsDistinctRatherThanFalseCoordination()
    {
        using var dir = new IsolatedDirectory();
        await using var first = await Open(dir.Path);
        await using var pid = await Open(dir.Path, pid: 124);
        await using var start = await Open(dir.Path, start: 457);
        await using var build = await Open(dir.Path, sha: new string('B', 64));
        Assert.Equal(4, Directory.GetFiles(dir.Path, "*.lock").Length);
        await Assert.ThrowsAsync<TimeoutException>(() => Open(dir.Path));
        await Assert.ThrowsAsync<TimeoutException>(() => Open(dir.Path, pid: 124));
        await Assert.ThrowsAsync<TimeoutException>(() => Open(dir.Path, start: 457));
        await Assert.ThrowsAsync<TimeoutException>(() => Open(dir.Path, sha: new string('B', 64)));
    }

    [Fact]
    public async Task HeldWaitCancellationNeverReleasesOrDeletesOwner()
    {
        using var dir = new IsolatedDirectory();
        var held = await Open(dir.Path);
        try
        {
            var file = Assert.Single(Directory.GetFiles(dir.Path, "*.lock"));
            using var cancel = new CancellationTokenSource();
            var waiting = Open(dir.Path, timeout: TimeSpan.FromSeconds(5), token: cancel.Token);
            Assert.False(waiting.IsCompleted);
            cancel.Cancel();
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => waiting);
            Assert.True(File.Exists(file));
            await Assert.ThrowsAsync<TimeoutException>(() => Open(dir.Path));
        }
        finally { held.Dispose(); }
        await using var acquired = await Open(dir.Path);
        Assert.Single(Directory.GetFiles(dir.Path, "*.lock"));
    }

    [Fact]
    public async Task PrecancelledAttemptDoesNotEvenCreateDirectory()
    {
        using var dir = new IsolatedDirectory();
        var child = System.IO.Path.Combine(dir.Path, "not-created");
        using var cancel = new CancellationTokenSource();
        cancel.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Open(child, token: cancel.Token));
        Assert.False(Directory.Exists(child));
        Assert.Empty(Directory.GetFiles(dir.Path));
    }

    [Fact]
    public async Task ZeroTimeoutIsImmediateAttemptNotAnUnconditionalFailure()
    {
        using var dir = new IsolatedDirectory();
        var lease = await Open(dir.Path, timeout: TimeSpan.Zero);
        await Assert.ThrowsAsync<TimeoutException>(() => Open(dir.Path, timeout: TimeSpan.Zero));
        lease.Dispose();
        await using var recovered = await Open(dir.Path, timeout: TimeSpan.Zero);
    }

    [Fact]
    public async Task ConcurrentRepeatedDisposeAcrossThreadsRetainsExistingLockBytes()
    {
        using var dir = new IsolatedDirectory();
        var first = await Task.Run(() => Open(dir.Path));
        var file = Assert.Single(Directory.GetFiles(dir.Path, "*.lock"));
        await Task.WhenAll(Enumerable.Range(0, 12).Select(index => Task.Run(async () =>
        {
            if (index % 2 == 0) first.Dispose();
            else await first.DisposeAsync();
        })));
        Assert.True(File.Exists(file));
        var marker = new byte[] { 7, 11, 13, 17 };
        await File.WriteAllBytesAsync(file, marker);
        var second = await Task.Run(() => Open(dir.Path));
        await Task.Run(() => second.Dispose());
        await second.DisposeAsync();
        first.Dispose();
        Assert.Equal(file, Assert.Single(Directory.GetFiles(dir.Path, "*.lock")));
        Assert.Equal(marker, await File.ReadAllBytesAsync(file));
        await using var third = await Open(dir.Path);
    }

    [Fact]
    public async Task ReparseDirectoryOrAncestorIsRejectedWhenSymlinkCreationIsAvailable()
    {
        using var dir = new IsolatedDirectory();
        var target = System.IO.Path.Combine(dir.Path, "target");
        var link = System.IO.Path.Combine(dir.Path, "link");
        Directory.CreateDirectory(target);
        try { Directory.CreateSymbolicLink(link, target); }
        catch (Exception error) when (error is UnauthorizedAccessException or IOException or PlatformNotSupportedException)
        {
            output.WriteLine("NOT EXERCISED: directory symlink creation unavailable: " + error.GetType().Name);
            return;
        }
        Assert.True((File.GetAttributes(link) & FileAttributes.ReparsePoint) != 0);
        await Assert.ThrowsAsync<IOException>(() => Open(link));
        await Assert.ThrowsAsync<IOException>(() => Open(System.IO.Path.Combine(link, "nested")));
        Assert.Empty(Directory.GetFiles(target, "*.lock", SearchOption.AllDirectories));
        output.WriteLine("EXERCISED: both direct and ancestor reparse rejection.");
    }

    [Fact]
    public async Task ExistingFileInsteadOfDirectoryFailsWithoutDeletingFile()
    {
        using var dir = new IsolatedDirectory();
        var path = System.IO.Path.Combine(dir.Path, "not-a-directory");
        await File.WriteAllTextAsync(path, "retain");
        await Assert.ThrowsAnyAsync<IOException>(() => Open(path));
        Assert.Equal("retain", await File.ReadAllTextAsync(path));
        Assert.Empty(Directory.GetFiles(dir.Path, "*.lock"));
    }

    [Fact]
    public async Task DeniedCreateFilePermissionFailsClosedWithoutChangingAclOrUnlinking()
    {
        if (!OperatingSystem.IsWindows()) { output.WriteLine("Windows ACL case not exercised."); return; }
        using var dir = new IsolatedDirectory();
        var info = new DirectoryInfo(dir.Path);
        var original = info.GetAccessControl();
        var originalAccessSddl = original.GetSecurityDescriptorSddlForm(AccessControlSections.Access);
        var denied = info.GetAccessControl();
        var sid = WindowsIdentity.GetCurrent().User ?? throw new InvalidOperationException("No test user SID.");
        denied.AddAccessRule(new FileSystemAccessRule(sid, FileSystemRights.CreateFiles, AccessControlType.Deny));
        info.SetAccessControl(denied);
        try
        {
            var error = await Record.ExceptionAsync(() => Open(dir.Path));
            Assert.NotNull(error);
            Assert.True(error is UnauthorizedAccessException or IOException, error.GetType().FullName);
            Assert.IsNotType<TimeoutException>(error);
            Assert.True(Directory.Exists(dir.Path));
            Assert.Empty(Directory.GetFiles(dir.Path, "*.lock"));
            output.WriteLine("EXERCISED: denied-create-file ACL rejected.");
        }
        finally
        {
            // A freshly read descriptor has no modified sections; explicitly mark Access for persistence.
            var restoredAcl = new DirectorySecurity();
            restoredAcl.SetSecurityDescriptorSddlForm(originalAccessSddl, AccessControlSections.Access);
            info.SetAccessControl(restoredAcl);
        }
        await using var restored = await Open(dir.Path);
    }

    sealed class IsolatedDirectory : IDisposable
    {
        public string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(),
            "rr2-lease-adversarial-" + Guid.NewGuid().ToString("N"));
        public IsolatedDirectory() => Directory.CreateDirectory(Path);
        // Only this test's unique tree is removed; lease operations never unlink lock files.
        public void Dispose() => Directory.Delete(Path, recursive: true);
    }
}
