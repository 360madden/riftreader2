using System.Diagnostics;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace RiftReader2.Live;

/// <summary>
/// Cooperative machine-local exclusion for bounded native-read operations.
/// Only participating processes are excluded. Keep the returned handle until
/// reads, identity revalidation, and session disposal are actually complete.
/// Never unlink or rename lock files; filename presence is not lock ownership.
/// </summary>
internal sealed class NativeReadFileLease : IDisposable, IAsyncDisposable
{
    private FileStream? stream;
    private NativeReadFileLease(FileStream stream) => this.stream = stream;

    internal static Task<NativeReadFileLease> AcquireAsync(
        int pid, long startUtcTicks, string buildSha256, TimeSpan timeout, CancellationToken token) =>
        AcquireAsync(pid, startUtcTicks, buildSha256, timeout, token,
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                "RiftReader2", "NativeReadLeases"));

    // Explicit directory exists only to allow isolated offline tests.
    internal static async Task<NativeReadFileLease> AcquireAsync(
        int pid, long startUtcTicks, string buildSha256, TimeSpan timeout, CancellationToken token,
        string directory)
    {
        if (pid <= 0 || startUtcTicks <= 0 || buildSha256 is null || buildSha256.Length != 64 ||
            buildSha256.Any(c => !((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F'))))
            throw new ArgumentException("Exact process epoch and uppercase executable SHA256 are required.");
        if (timeout < TimeSpan.Zero || timeout > TimeSpan.FromSeconds(30))
            throw new ArgumentOutOfRangeException(nameof(timeout));
        if (string.IsNullOrWhiteSpace(directory) || !Path.IsPathFullyQualified(directory))
            throw new ArgumentException("A stable absolute local lease directory is required.", nameof(directory));
        token.ThrowIfCancellationRequested();
        var root = Path.GetFullPath(directory);
        if (new Uri(root).IsUnc) throw new ArgumentException("Network lease directories are not supported.", nameof(directory));
        Directory.CreateDirectory(root);
        // Reject redirected directories; normal ACL provisioning is the deployer's
        // responsibility. This is not a security boundary against privileged actors.
        for (var item = new DirectoryInfo(root); item is not null; item = item.Parent)
            if ((item.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new IOException("Lease directory cannot contain a reparse point.");
        var identity = string.Join(":", "RR2-NATIVE-READ-1",
            pid.ToString(CultureInfo.InvariantCulture),
            startUtcTicks.ToString(CultureInfo.InvariantCulture), buildSha256);
        var name = Convert.ToHexString(SHA256.HashData(Encoding.ASCII.GetBytes(identity))) + ".lock";
        var path = Path.Combine(root, name);
        var timer = Stopwatch.StartNew();
        while (true)
        {
            token.ThrowIfCancellationRequested();
            try
            {
                // A stable preexisting link must not redirect this process to a different lock.
                // This check is not atomic against a hostile directory writer: trusted ACLs remain required.
                RejectLockReparsePoint(path, allowMissing: true);
                var file = new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
                try
                {
                    token.ThrowIfCancellationRequested();
                    RejectLockReparsePoint(path, allowMissing: false);
                    return new NativeReadFileLease(file);
                }
                catch { file.Dispose(); throw; }
            }
            catch (IOException error) when ((error.HResult & 0xFFFF) is 32 or 33)
            {
                var remaining = timeout - timer.Elapsed;
                if (remaining <= TimeSpan.Zero)
                    throw new TimeoutException("Native read lease is already held.", error);
                await Task.Delay(remaining < TimeSpan.FromMilliseconds(50) ? remaining : TimeSpan.FromMilliseconds(50), token)
                    .ConfigureAwait(false);
                if (timer.Elapsed >= timeout)
                    throw new TimeoutException("Native read lease is already held.", error);
            }
        }
    }

    private static void RejectLockReparsePoint(string path, bool allowMissing)
    {
        try
        {
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("Native read lock file cannot be a reparse point.");
        }
        catch (FileNotFoundException) when (allowMissing) { }
    }

    public void Dispose() => Interlocked.Exchange(ref stream, null)?.Dispose();

    public ValueTask DisposeAsync()
    {
        Dispose();
        return ValueTask.CompletedTask;
    }
}
