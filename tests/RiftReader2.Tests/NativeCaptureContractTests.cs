using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Tests;

public sealed class NativeCaptureContractTests
{
    private static readonly NativeProcessIdentity Identity = new(
        42, 638000000000000000, @"C:\RIFT\rift_x64.exe", new string('A', 64), 0x140000000, 0x4000000);

    [Fact]
    public async Task Capture_RecordsExactAddressesHashesSequenceAndPartialFailure()
    {
        var session = new FakeSession(Identity,
            new("success", [1, 2, 3, 4], null, null),
            new("partial", [8, 9], 299, "ReadProcessMemory returned 2 of 4 requested bytes."));
        var plan = Plan([
            new("header", NativeAddressKind.ModuleRelative, 0x10, 4),
            new("session", NativeAddressKind.Absolute, 0x20000, 4)
        ]);

        var result = await new NativeCaptureRunner().CaptureAsync(plan, session, CancellationToken.None);

        Assert.Equal("partial", result.Status);
        Assert.Equal(1, result.AttemptedSampleCount);
        Assert.Equal(0, result.SuccessfulSampleCount);
        Assert.Equal(1, session.RevalidationCount);
        var sample = Assert.Single(result.Samples);
        Assert.Equal(1, sample.Sequence);
        Assert.Equal("0x10", sample.Ranges[0].RequestedAddress);
        Assert.Equal("0x140000010", sample.Ranges[0].ResolvedAddress);
        Assert.Equal("9F64A747E1B97F131FABB6B447296C9B6F0201E79FB3C5356E6C77E89B6A806A", sample.Ranges[0].BytesSha256);
        Assert.Equal("partial", sample.Ranges[1].Status);
        Assert.Equal(2, sample.Ranges[1].BytesRead);
        Assert.Equal(299, sample.Ranges[1].Win32ErrorCode);
    }

    [Fact]
    public async Task Capture_FailsClosedWhenTerminalIdentityChanges()
    {
        var session = new FakeSession(Identity, new NativeReadResult("success", [1], null, null))
        {
            RevalidationFailure = "Process creation identity changed after capture."
        };
        var result = await new NativeCaptureRunner().CaptureAsync(
            Plan([new("byte", NativeAddressKind.Absolute, 0x20000, 1)]), session, CancellationToken.None);
        Assert.Equal("identity-invalidated", result.Status);
    }

    [Theory]
    [InlineData("success", 0)]
    [InlineData("success", 1)]
    [InlineData("unknown", 2)]
    public async Task Capture_RejectsIncoherentAdapterResults(string status, int bytes)
    {
        var session = new FakeSession(Identity,
            new NativeReadResult(status, Enumerable.Repeat((byte)1, bytes).ToArray(), null, status == "success" ? null : "bad"));
        await Assert.ThrowsAsync<InvalidDataException>(() => new NativeCaptureRunner().CaptureAsync(
            Plan([new("bytes", NativeAddressKind.Absolute, 0x20000, 2)]), session, CancellationToken.None));
    }

    [Fact]
    public void Validate_RejectsUndefinedKindOverflowScheduleAndBounds()
    {
        Assert.Throws<ArgumentException>(() => NativeCaptureRunner.Validate(Plan([new("bad", (NativeAddressKind)99, 0x20000, 1)])));
        Assert.Throws<OverflowException>(() => NativeCaptureRunner.Validate(Plan([new("overflow", NativeAddressKind.Absolute, ulong.MaxValue, 2)])));
        Assert.Throws<ArgumentException>(() => NativeCaptureRunner.Validate(Plan(
            [new("schedule", NativeAddressKind.Absolute, 0x20000, 1)], 2, 5_000, 5_000)));
        Assert.Throws<ArgumentException>(() => NativeCaptureRunner.Validate(Plan(
            [new("sample", NativeAddressKind.Absolute, 0x20000, 1)], 33)));
    }

    [Fact]
    public async Task Capture_HonorsCancellationBeforeRead()
    {
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        var session = new FakeSession(Identity, new NativeReadResult("success", [1], null, null));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => new NativeCaptureRunner().CaptureAsync(
            Plan([new("byte", NativeAddressKind.Absolute, 0x20000, 1)]), session, cancellation.Token));
        Assert.Empty(session.Addresses);
    }

    [Fact]
    public async Task Capture_ChecksDeadlineImmediatelyAfterLastReadAndRevalidates()
    {
        var session = new FakeSession(Identity, new NativeReadResult("success", [1], null, null));
        var time = new ScriptedTimeProvider([0, 0, 0, 0, 10, 10, 10, 10]);
        var result = await new NativeCaptureRunner(time).CaptureAsync(
            Plan([new("byte", NativeAddressKind.Absolute, 0x20000, 1)], duration: 5), session, CancellationToken.None);
        Assert.Equal("time-budget-exceeded", result.Status);
        Assert.Equal(1, result.AttemptedSampleCount);
        Assert.Equal(1, session.RevalidationCount);
    }

    [Fact]
    public async Task Capture_PreservesIdentityInvalidationAndDoesNotCountTruncatedSampleSuccessful()
    {
        var session = new FakeSession(Identity, new NativeReadResult("success", [1], null, null))
        {
            RevalidationFailure = "Process creation identity changed after capture."
        };
        var time = new ScriptedTimeProvider([0, 0, 0, 0, 10, 10, 10, 10]);
        var result = await new NativeCaptureRunner(time).CaptureAsync(
            Plan([
                new("first", NativeAddressKind.Absolute, 0x20000, 1),
                new("second", NativeAddressKind.Absolute, 0x30000, 1)
            ], duration: 5), session, CancellationToken.None);
        Assert.Equal("identity-invalidated", result.Status);
        Assert.Equal(1, result.AttemptedSampleCount);
        Assert.Equal(0, result.SuccessfulSampleCount);
        Assert.Single(Assert.Single(result.Samples).Ranges);
    }

    [Fact]
    public async Task RequestParser_IsStrictAndRequiresCanonicalHex()
    {
        var directory = CreateDirectory();
        try
        {
            var path = Path.Combine(directory, "request.json");
            await File.WriteAllTextAsync(path, RequestJson("0x0001"));
            var error = await Assert.ThrowsAsync<InvalidDataException>(() => NativeCaptureRequest.LoadAsync(path, CancellationToken.None));
            Assert.Contains("canonical", error.Message);
            await File.WriteAllTextAsync(path, RequestJson("0x1").Replace("\"ranges\"", "\"unexpected\":true,\"ranges\"", StringComparison.Ordinal));
            await Assert.ThrowsAsync<JsonException>(() => NativeCaptureRequest.LoadAsync(path, CancellationToken.None));

            await File.WriteAllTextAsync(path, new string(' ', 65_537));
            var oversized = await Assert.ThrowsAsync<InvalidDataException>(() => NativeCaptureRequest.LoadAsync(path, CancellationToken.None));
            Assert.Contains("65536", oversized.Message);
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    private static NativeCapturePlan Plan(IReadOnlyList<NativeCaptureRange> ranges, int samples = 1, int interval = 0, int duration = 5_000) =>
        new(Identity.ProcessId, Identity.ProcessStartUtcTicks, Identity.ExecutableSha256, ranges, samples, interval, duration);

    private static string RequestJson(string address) => JsonSerializer.Serialize(new
    {
        schemaVersion = 1,
        evidenceKind = "native-memory-read-request/1",
        target = new { processId = Identity.ProcessId, processStartUtcTicks = Identity.ProcessStartUtcTicks, executableSha256 = Identity.ExecutableSha256 },
        sampling = new { sampleCount = 1, intervalMilliseconds = 0, maxDurationMilliseconds = 5000 },
        ranges = new[] { new { id = "header", addressKind = "module-relative-rva", address, byteLength = 2 } }
    }, JsonFormat.Options);

    private static string CreateDirectory()
    {
        var path = Path.Combine(Path.GetTempPath(), $"rr2-native-{Guid.NewGuid():N}");
        Directory.CreateDirectory(path);
        return path;
    }

    private sealed class FakeSession(NativeProcessIdentity identity, params NativeReadResult[] reads) : IReadOnlyNativeMemorySession
    {
        private int index;
        public NativeProcessIdentity Identity { get; } = identity;
        public string? RevalidationFailure { get; init; }
        public int RevalidationCount { get; private set; }
        public List<ulong> Addresses { get; } = [];
        public NativeReadResult Read(ulong address, int byteLength) { Addresses.Add(address); return reads[index++]; }
        public ValueTask<string?> RevalidateAsync(CancellationToken cancellationToken) { cancellationToken.ThrowIfCancellationRequested(); RevalidationCount++; return ValueTask.FromResult(RevalidationFailure); }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }

    private sealed class ScriptedTimeProvider(IReadOnlyList<long> timestamps) : TimeProvider
    {
        private int index;
        public override long TimestampFrequency => 1_000;
        public override DateTimeOffset GetUtcNow() => DateTimeOffset.UnixEpoch;
        public override long GetTimestamp() { var current = Math.Min(index, timestamps.Count - 1); index++; return timestamps[current]; }
    }
}
