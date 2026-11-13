using System.Diagnostics;
using System.Security.Cryptography;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class VerifiedNativeExecutablePinTests
{
    [Fact]
    public async Task Pin_DeniesWriteAndDelete_UntilDisposed()
    {
        var path = CreateTemporaryExecutable();
        try
        {
            var expected = await HashAsync(path);
            await using var pin = await VerifiedNativeExecutablePin.OpenAsync(path, expected, CancellationToken.None);

            Assert.Equal(expected, pin.GetVerifiedSha256(path, expected));
            Assert.Throws<IOException>(() =>
                new FileStream(path, FileMode.Open, FileAccess.Write, FileShare.ReadWrite | FileShare.Delete));
            Assert.Throws<IOException>(() => File.Delete(path));

            await pin.DisposeAsync();
            await File.WriteAllBytesAsync(path, [9, 8, 7]);
            File.Delete(path);
        }
        finally
        {
            File.Delete(path);
        }
    }

    [Fact]
    public async Task Pin_FailsClosed_ForDisposedPathAndHashMismatch()
    {
        var path = CreateTemporaryExecutable();
        var otherPath = CreateTemporaryExecutable();
        try
        {
            var expected = await HashAsync(path);
            await using var pin = await VerifiedNativeExecutablePin.OpenAsync(path, expected, CancellationToken.None);

            Assert.Throws<InvalidDataException>(() => pin.GetVerifiedSha256(otherPath, expected));
            Assert.Throws<InvalidDataException>(() => pin.GetVerifiedSha256(path, new string('0', 64)));
            await pin.DisposeAsync();
            Assert.Throws<ObjectDisposedException>(() => pin.GetVerifiedSha256(path, expected));

            await Assert.ThrowsAsync<InvalidDataException>(() =>
                VerifiedNativeExecutablePin.OpenAsync(path, new string('0', 64), CancellationToken.None));
            File.Delete(path); // A failed verification must not leak the denying handle.
        }
        finally
        {
            File.Delete(path);
            File.Delete(otherPath);
        }
    }

    [Fact]
    public async Task PinnedSession_StillValidatesEpoch_AndDisposedPinFailsRevalidation()
    {
        var path = Environment.ProcessPath ?? throw new InvalidOperationException("No current process path.");
        var expected = await HashAsync(path);
        await using var pin = await VerifiedNativeExecutablePin.OpenAsync(path, expected, CancellationToken.None);
        using var process = Process.GetCurrentProcess();
        var startTicks = process.StartTime.ToUniversalTime().Ticks;

        await Assert.ThrowsAsync<InvalidDataException>(() => WindowsNativeMemorySession.OpenAsync(
            Environment.ProcessId, startTicks + 1, expected, pin, CancellationToken.None));

        await using var session = await WindowsNativeMemorySession.OpenAsync(
            Environment.ProcessId, startTicks, expected, pin, CancellationToken.None);
        Assert.Null(await session.RevalidateAsync(CancellationToken.None));

        await pin.DisposeAsync();
        var failure = await session.RevalidateAsync(CancellationToken.None);
        Assert.Contains(nameof(ObjectDisposedException), failure, StringComparison.Ordinal);
    }

    private static string CreateTemporaryExecutable()
    {
        var path = Path.Combine(Path.GetTempPath(), $"rr2-pin-{Guid.NewGuid():N}.bin");
        File.WriteAllBytes(path, [1, 2, 3, 4, 5]);
        return path;
    }

    private static async Task<string> HashAsync(string path)
    {
        await using var stream = File.OpenRead(path);
        return Convert.ToHexString(await SHA256.HashDataAsync(stream));
    }
}
