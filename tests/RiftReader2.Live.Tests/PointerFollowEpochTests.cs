using System.ComponentModel;
using System.Diagnostics;
using System.Text.Json;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live.Tests;

public sealed class PointerFollowEpochTests
{
    [Fact]
    public async Task FollowPointer_RejectsStaleProcessStartBeforePublishing()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;

        var directory = CreateDirectory();
        try
        {
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                Environment.ProcessId, null, null, CancellationToken.None);
            var request = Path.Combine(directory, "old-epoch.json");
            var output = Path.Combine(directory, "should-not-exist.json");
            await File.WriteAllTextAsync(request, RequestJson(
                session.Identity.ProcessId,
                checked(session.Identity.ProcessStartUtcTicks - 1),
                session.Identity.ExecutableSha256));

            var result = await RunAsync(request, output);

            Assert.Equal(2, result.ExitCode);
            Assert.Empty(result.Stdout);
            Assert.Contains("process start identity", result.Stderr, StringComparison.OrdinalIgnoreCase);
            Assert.False(File.Exists(output));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public async Task FollowPointer_RejectsStaleStartBeforeCheckingIncorrectBuild()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;

        var directory = CreateDirectory();
        try
        {
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                Environment.ProcessId, null, null, CancellationToken.None);
            var request = Path.Combine(directory, "wrong-epoch-and-build.json");
            var output = Path.Combine(directory, "should-not-exist.json");
            await File.WriteAllTextAsync(request, RequestJson(
                session.Identity.ProcessId,
                checked(session.Identity.ProcessStartUtcTicks - 1),
                new string('0', 64)));

            var result = await RunAsync(request, output);

            Assert.Equal(2, result.ExitCode);
            Assert.Contains("process start identity", result.Stderr, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("executable SHA-256", result.Stderr, StringComparison.OrdinalIgnoreCase);
            Assert.False(File.Exists(output));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public async Task FollowPointer_RejectsIncorrectBuildWithoutOverwritingOutput()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;

        var directory = CreateDirectory();
        try
        {
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                Environment.ProcessId, null, null, CancellationToken.None);
            var request = Path.Combine(directory, "wrong-build.json");
            var output = Path.Combine(directory, "existing.json");
            await File.WriteAllTextAsync(request, RequestJson(
                session.Identity.ProcessId,
                session.Identity.ProcessStartUtcTicks,
                new string('0', 64)));
            var sentinel = "pre-existing report must remain intact";
            await File.WriteAllTextAsync(output, sentinel);

            var result = await RunAsync(request, output);

            Assert.Equal(2, result.ExitCode);
            Assert.Empty(result.Stdout);
            Assert.Contains("executable SHA-256", result.Stderr, StringComparison.OrdinalIgnoreCase);
            Assert.Equal(sentinel, await File.ReadAllTextAsync(output));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public async Task FollowPointer_RejectsExitedDisposableProcessEpoch()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;

        var directory = CreateDirectory();
        var launch = new ProcessStartInfo("powershell.exe")
        {
            UseShellExecute = false,
            CreateNoWindow = true
        };
        launch.ArgumentList.Add("-NoProfile");
        launch.ArgumentList.Add("-NonInteractive");
        launch.ArgumentList.Add("-Command");
        launch.ArgumentList.Add("Start-Sleep -Seconds 30");

        try
        {
            using var child = Process.Start(launch)
                ?? throw new InvalidOperationException("Could not start disposable test process.");
            try
            {
                await using var session = await OpenDisposableProcessAsync(child);
                var request = Path.Combine(directory, "exited-epoch.json");
                var output = Path.Combine(directory, "should-not-exist.json");
                await File.WriteAllTextAsync(request, RequestJson(
                    session.Identity.ProcessId,
                    session.Identity.ProcessStartUtcTicks,
                    session.Identity.ExecutableSha256));

                child.Kill(entireProcessTree: true);
                await child.WaitForExitAsync();

                var result = await RunAsync(request, output);

                Assert.Equal(2, result.ExitCode);
                Assert.Empty(result.Stdout);
                Assert.NotEmpty(result.Stderr);
                Assert.False(File.Exists(output));
            }
            finally
            {
                if (!child.HasExited)
                {
                    child.Kill(entireProcessTree: true);
                    await child.WaitForExitAsync();
                }
            }
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    private static async Task<WindowsNativeMemorySession> OpenDisposableProcessAsync(Process process)
    {
        var started = Stopwatch.GetTimestamp();
        while (true)
        {
            try
            {
                return await WindowsNativeMemorySession.OpenAsync(
                    process.Id, null, null, CancellationToken.None);
            }
            catch (Win32Exception exception) when (
                exception.NativeErrorCode == 18 &&
                !process.HasExited &&
                Stopwatch.GetElapsedTime(started) < TimeSpan.FromSeconds(5))
            {
                // A newly created process can exist briefly before Toolhelp exposes
                // its first module. Production epoch opening remains fail-fast; only
                // this disposable test fixture waits for process initialization.
                await Task.Delay(20);
            }
        }
    }

    private static async Task<(int ExitCode, string Stdout, string Stderr)> RunAsync(
        string requestPath, string outputPath)
    {
        using var stdout = new StringWriter();
        using var stderr = new StringWriter();
        var result = await NativeCommandRunner.RunAsync(
            ["follow-pointer", "--request", requestPath, "--output", outputPath],
            stdout, stderr);
        return (result, stdout.ToString(), stderr.ToString());
    }

    private static string RequestJson(int processId, long startUtcTicks, string buildSha256) =>
        JsonSerializer.Serialize(new
        {
            schemaVersion = 1,
            evidenceKind = "native-pointer-follow-request/1",
            target = new
            {
                processId,
                processStartUtcTicks = startUtcTicks,
                executableSha256 = buildSha256
            },
            rootRva = "0x1B8",
            offsets = new[] { "0x0" },
            terminalByteLength = 2,
            maxDurationMilliseconds = 5000
        }, JsonFormat.Options);

    private static string CreateDirectory()
    {
        var directory = Path.Combine(
            Path.GetTempPath(), $"rr2-pointer-epoch-{Guid.NewGuid():N}");
        Directory.CreateDirectory(directory);
        return directory;
    }
}
