using System.Security.Cryptography;
using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace RiftReader2.Live;

/// <summary>
/// Pins one verified executable file against writes, deletion, and replacement for a bounded operation.
/// </summary>
internal sealed class VerifiedNativeExecutablePin : IAsyncDisposable
{
    private readonly FileStream stream;
    private readonly FileIdentity fileIdentity;
    private bool disposed;

    private VerifiedNativeExecutablePin(
        FileStream stream, string executablePath, string sha256, FileIdentity fileIdentity)
    {
        this.stream = stream;
        this.fileIdentity = fileIdentity;
        ExecutablePath = executablePath;
        Sha256 = sha256;
    }

    internal string ExecutablePath { get; }
    internal string Sha256 { get; }

    internal static async Task<VerifiedNativeExecutablePin> OpenAsync(
        string executablePath,
        string expectedSha256,
        CancellationToken cancellationToken)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(executablePath);
        ArgumentException.ThrowIfNullOrWhiteSpace(expectedSha256);
        var fullPath = Path.GetFullPath(executablePath);
        var stream = new FileStream(
            fullPath, FileMode.Open, FileAccess.Read, FileShare.Read,
            128 * 1024, FileOptions.Asynchronous | FileOptions.SequentialScan);
        try
        {
            var sha256 = Convert.ToHexString(await SHA256.HashDataAsync(stream, cancellationToken));
            if (!string.Equals(sha256, expectedSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("The pinned executable SHA-256 does not match the expected build.");
            return new(stream, fullPath, sha256, GetIdentity(stream.SafeFileHandle));
        }
        catch
        {
            await stream.DisposeAsync();
            throw;
        }
    }

    internal string GetVerifiedSha256(string executablePath, string? expectedSha256)
    {
        ObjectDisposedException.ThrowIf(disposed, this);
        if (!string.Equals(Path.GetFullPath(executablePath), ExecutablePath, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("The process executable path does not match the pinned executable.");
        using var current = new FileStream(
            executablePath, FileMode.Open, FileAccess.Read, FileShare.Read, 1, FileOptions.None);
        if (GetIdentity(current.SafeFileHandle) != fileIdentity)
            throw new InvalidDataException("The process executable path no longer resolves to the pinned file.");
        if (expectedSha256 is null ||
            !string.Equals(expectedSha256, Sha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("The requested executable SHA-256 does not match the pinned executable.");
        return Sha256;
    }

    public async ValueTask DisposeAsync()
    {
        if (disposed)
            return;
        disposed = true;
        await stream.DisposeAsync();
    }

    private static FileIdentity GetIdentity(SafeFileHandle handle)
    {
        if (!GetFileInformationByHandle(handle, out var info))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not identify the pinned executable file.");
        return new(info.VolumeSerialNumber, info.FileIndexHigh, info.FileIndexLow);
    }

    private readonly record struct FileIdentity(uint Volume, uint IndexHigh, uint IndexLow);

    [StructLayout(LayoutKind.Sequential)]
    private struct ByHandleFileInformation
    {
        internal uint FileAttributes;
        internal System.Runtime.InteropServices.ComTypes.FILETIME CreationTime;
        internal System.Runtime.InteropServices.ComTypes.FILETIME LastAccessTime;
        internal System.Runtime.InteropServices.ComTypes.FILETIME LastWriteTime;
        internal uint VolumeSerialNumber;
        internal uint FileSizeHigh;
        internal uint FileSizeLow;
        internal uint NumberOfLinks;
        internal uint FileIndexHigh;
        internal uint FileIndexLow;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandle(
        SafeFileHandle handle, out ByHandleFileInformation information);
}
