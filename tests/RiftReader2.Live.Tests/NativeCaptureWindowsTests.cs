using System.Text.Json;
using System.Diagnostics;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class NativeCaptureWindowsTests
{
    [Fact]
    public async Task WindowsSession_ReadsCurrentProcessModuleHeaderWithHandleBoundIdentity()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;
        await using var session = await WindowsNativeMemorySession.OpenAsync(
            Environment.ProcessId, null, null, CancellationToken.None);
        var plan = new NativeCapturePlan(
            session.Identity.ProcessId,
            session.Identity.ProcessStartUtcTicks,
            session.Identity.ExecutableSha256,
            [new("module-header", NativeAddressKind.ModuleRelative, 0, 2)],
            1, 0, 5_000);

        var result = await new NativeCaptureRunner().CaptureAsync(plan, session, CancellationToken.None);

        Assert.Equal("complete", result.Status);
        var bytes = Convert.FromBase64String(Assert.Single(Assert.Single(result.Samples).Ranges).BytesBase64!);
        Assert.Equal((byte)'M', bytes[0]);
        Assert.Equal((byte)'Z', bytes[1]);
    }

    [Fact]
    public async Task CaptureCommand_DoesNotPublishOnIdentityMismatchOrOverwriteExistingOutput()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;
        var directory = CreateDirectory();
        try
        {
            await using var session = await WindowsNativeMemorySession.OpenAsync(Environment.ProcessId, null, null, CancellationToken.None);
            var request = Path.Combine(directory, "request.json");
            var output = Path.Combine(directory, "capture.json");
            await File.WriteAllTextAsync(request, RequestJson(session.Identity, startDelta: 1));
            Assert.Equal(2, await NativeCommandRunner.RunAsync(
                ["capture-native", "--request", request, "--output", output], TextWriter.Null, TextWriter.Null));
            Assert.False(File.Exists(output));

            await File.WriteAllTextAsync(request, RequestJson(session.Identity));
            Assert.Equal(0, await NativeCommandRunner.RunAsync(
                ["capture-native", "--request", request, "--output", output], TextWriter.Null, TextWriter.Null));
            var first = await File.ReadAllBytesAsync(output);
            using (var report = JsonDocument.Parse(first))
            {
                var implementation = report.RootElement.GetProperty("implementation");
                Assert.Equal("assembly-files", implementation.GetProperty("deploymentKind").GetString());
                Assert.Equal(JsonValueKind.Object, implementation.GetProperty("assemblySha256").ValueKind);
                Assert.Equal(JsonValueKind.Null, implementation.GetProperty("bundleFileName").ValueKind);
                Assert.Equal(JsonValueKind.Null, implementation.GetProperty("bundleSha256").ValueKind);
            }
            Assert.Equal(2, await NativeCommandRunner.RunAsync(
                ["capture-native", "--request", request, "--output", output], TextWriter.Null, TextWriter.Null));
            Assert.Equal(first, await File.ReadAllBytesAsync(output));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public async Task WindowsSession_RevalidationDetectsActualProcessExit()
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
            return;
        var start = new ProcessStartInfo
        {
            FileName = "powershell.exe",
            UseShellExecute = false,
            CreateNoWindow = true
        };
        start.ArgumentList.Add("-NoProfile");
        start.ArgumentList.Add("-Command");
        start.ArgumentList.Add("Start-Sleep -Seconds 30");
        using var process = Process.Start(start) ?? throw new InvalidOperationException("Could not start exit-test process.");
        try
        {
            await Task.Delay(250);
            await using var session = await WindowsNativeMemorySession.OpenAsync(process.Id, null, null, CancellationToken.None);
            process.Kill(entireProcessTree: true);
            await process.WaitForExitAsync();
            Assert.True(process.HasExited);

            var failure = await session.RevalidateAsync(CancellationToken.None);

            Assert.NotNull(failure);
            Assert.Contains("validation failed", failure, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            if (!process.HasExited)
                process.Kill(entireProcessTree: true);
        }
    }

    private static string RequestJson(NativeProcessIdentity identity, long startDelta = 0) =>
        JsonSerializer.Serialize(new
        {
            schemaVersion = 1,
            evidenceKind = "native-memory-read-request/1",
            target = new
            {
                processId = identity.ProcessId,
                processStartUtcTicks = identity.ProcessStartUtcTicks + startDelta,
                executableSha256 = identity.ExecutableSha256
            },
            sampling = new { sampleCount = 1, intervalMilliseconds = 0, maxDurationMilliseconds = 5000 },
            ranges = new[] { new { id = "header", addressKind = "module-relative-rva", address = "0x0", byteLength = 2 } }
        }, JsonFormat.Options);

    private static string CreateDirectory()
    {
        var path = Path.Combine(Path.GetTempPath(), $"rr2-native-{Guid.NewGuid():N}");
        Directory.CreateDirectory(path);
        return path;
    }
}
