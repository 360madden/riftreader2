using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildOrientationSampleCommandTests
{
    [Fact]
    public async Task PublishesCandidateOnlyAfterRevalidationAndDisposesSession()
    {
        using var f = new Fixture();
        var output = new StringWriter();
        Assert.Equal(0, await f.Run(output));
        Assert.True(f.Session.Revalidated);
        Assert.True(f.Session.Disposed);
        Assert.True(f.LeaseDisposedAfterSession);
        using var json = JsonDocument.Parse(await File.ReadAllTextAsync(f.Path));
        var root = json.RootElement;
        Assert.Equal("native-current-orientation-candidate/1", root.GetProperty("contractVersion").GetString());
        var observation = root.GetProperty("observation");
        Assert.Equal("18446744073709551615", observation.GetProperty("unitKey").GetString());
        Assert.Equal("0xFFFFFFFFFFFFFFFF", observation.GetProperty("refreshHandleRaw").GetString());
        Assert.Equal(9, observation.GetProperty("primary").GetProperty("rawBits").GetArrayLength());
        Assert.Contains("unverified", observation.GetProperty("qualification").GetString());
        Assert.Contains("native-current-orientation-summary/1", output.ToString());
    }

    [Fact]
    public async Task PassiveBurstPublishesThreeOwnerPinnedMatricesAndRefreshStates()
    {
        using var f = new Fixture();
        f.Options["--samples"] = "3";
        f.Options["--interval-ms"] = "0";
        var output = new StringWriter();
        Assert.Equal(0, await f.Run(output));
        Assert.Equal(3, f.ReadCount);
        Assert.Equal(1, f.Session.RevalidationCount);
        Assert.True(f.LeaseDisposedAfterSession);
        using var json = JsonDocument.Parse(await File.ReadAllTextAsync(f.Path));
        Assert.Equal("native-current-orientation-candidate-burst/1",
            json.RootElement.GetProperty("contractVersion").GetString());
        Assert.Equal(3, json.RootElement.GetProperty("completedSamples").GetInt32());
        Assert.Equal(3, json.RootElement.GetProperty("observations").GetArrayLength());
        Assert.Equal(3, JsonDocument.Parse(output.ToString()).RootElement
            .GetProperty("completedSamples").GetInt32());
    }

    [Fact]
    public async Task BurstFullRevalidationRunsOnceAfterAllReadsAndRejectsInvalidatedBuild()
    {
        using var f = new Fixture();
        f.Options["--samples"] = "5";
        f.Options["--interval-ms"] = "0";
        f.Session.OnRevalidate = () =>
        {
            Assert.Equal(5, f.ReadCount);
            Assert.True(f.LeaseHeld);
            Assert.False(File.Exists(f.Path));
        };
        Assert.Equal(0, await f.Run(new StringWriter()));
        Assert.Equal(1, f.Session.RevalidationCount);
        Assert.True(f.LeaseDisposedAfterSession);

        using var failed = new Fixture();
        failed.Options["--samples"] = "5";
        failed.Options["--interval-ms"] = "0";
        failed.Session.RevalidationError = "post-burst-build-changed";
        failed.Session.OnRevalidate = () => Assert.Equal(5, failed.ReadCount);
        using var output = new StringWriter();
        await Assert.ThrowsAsync<InvalidDataException>(() => failed.Run(output));
        Assert.Equal(1, failed.Session.RevalidationCount);
        Assert.False(File.Exists(failed.Path));
        Assert.Empty(output.ToString());
        Assert.True(failed.LeaseDisposedAfterSession);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task PassiveBurstChangedOwnerOrComponentDoesNotPublish(bool changeOwner)
    {
        using var f = new Fixture();
        f.Options["--samples"] = "3";
        f.Options["--interval-ms"] = "0";
        if (changeOwner) f.ChangeUnitAtRead = 2;
        else f.ChangeComponentAtRead = 2;
        await Assert.ThrowsAsync<InvalidDataException>(() => f.Run(new StringWriter()));
        Assert.Equal(2, f.ReadCount);
        Assert.True(f.LeaseDisposedAfterSession);
        Assert.False(File.Exists(f.Path));
    }

    [Fact]
    public async Task LeaseDenialPreventsSessionOpen()
    {
        using var f = new Fixture();
        f.LeaseDenied = true;
        await Assert.ThrowsAsync<TimeoutException>(() => f.Run(new StringWriter()));
        Assert.False(f.Opened);
        Assert.False(File.Exists(f.Path));
    }

    [Theory]
    [InlineData("--samples", "0")]
    [InlineData("--samples", "31")]
    [InlineData("--interval-ms", "2001")]
    [InlineData("--pid", "0")]
    [InlineData("--pid", "abc")]
    [InlineData("--start-ticks", "-1")]
    [InlineData("--output", " ")]
    public async Task RejectsInvalidOptionsBeforeOpening(string key, string value)
    {
        using var f = new Fixture();
        f.Options[key] = value;
        await Assert.ThrowsAsync<ArgumentException>(() => f.Run(new StringWriter()));
        Assert.False(f.Opened);
        Assert.False(File.Exists(f.Path));
    }

    [Fact]
    public async Task ExistingOutputIsPreservedWithoutOpening()
    {
        using var f = new Fixture();
        await File.WriteAllTextAsync(f.Path, "original");
        await Assert.ThrowsAsync<IOException>(() => f.Run(new StringWriter()));
        Assert.Equal("original", await File.ReadAllTextAsync(f.Path));
        Assert.False(f.Opened);
    }

    [Fact]
    public async Task InvalidatedProcessProducesNoReportOrSummary()
    {
        using var f = new Fixture();
        f.Session.RevalidationError = "changed";
        var output = new StringWriter();
        await Assert.ThrowsAsync<InvalidDataException>(() => f.Run(output));
        Assert.False(File.Exists(f.Path));
        Assert.Equal("", output.ToString());
        Assert.True(f.Session.Disposed);
    }

    [Fact]
    public async Task CancellationBeforeOpenOrAfterCaptureDoesNotPublish()
    {
        using var f = new Fixture();
        using var cancelled = new CancellationTokenSource();
        cancelled.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => f.Run(new StringWriter(), cancelled.Token));
        Assert.False(f.Opened);
        using var after = new CancellationTokenSource();
        f.Session.OnRevalidate = after.Cancel;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => f.Run(new StringWriter(), after.Token));
        Assert.False(File.Exists(f.Path));
        Assert.True(f.Session.Disposed);
    }

    [Fact]
    public async Task RejectsOpenedAndObservationEpochMismatch()
    {
        using var f = new Fixture();
        f.Session.Identity = f.Session.Identity with { ProcessId = 999 };
        await Assert.ThrowsAsync<InvalidDataException>(() => f.Run(new StringWriter()));
        Assert.False(File.Exists(f.Path));
        f.Session.Identity = f.Session.Identity with { ProcessId = 123 };
        f.WrongObservation = true;
        await Assert.ThrowsAsync<InvalidDataException>(() => f.Run(new StringWriter()));
        Assert.False(File.Exists(f.Path));
    }

    [Fact]
    public async Task PublicationRaceDoesNotOverwriteOrEmitSuccess()
    {
        using var f = new Fixture();
        f.Session.OnRevalidate = () => File.WriteAllText(f.Path, "racer");
        var output = new StringWriter();
        await Assert.ThrowsAsync<IOException>(() => f.Run(output));
        Assert.Equal("racer", await File.ReadAllTextAsync(f.Path));
        Assert.Equal("", output.ToString());
    }

    sealed class Fixture : IDisposable
    {
        readonly string directory = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "rr2-orientation-test-" + Guid.NewGuid().ToString("N"));
        public string Path => System.IO.Path.Combine(directory, "candidate.json");
        public Fake Session { get; } = new();
        public bool Opened { get; private set; }
        public bool LeaseDenied { get; set; }
        public bool LeaseHeld { get; private set; }
        public bool LeaseDisposedAfterSession { get; private set; }
        public bool WrongObservation { get; set; }
        public int ReadCount { get; private set; }
        public int ChangeUnitAtRead { get; set; }
        public int ChangeComponentAtRead { get; set; }
        public Dictionary<string, string> Options { get; }
        public Fixture()
        {
            Directory.CreateDirectory(directory);
            Options = new() { ["--pid"] = "123", ["--start-ticks"] = "456", ["--output"] = Path };
        }
        public Task<int> Run(TextWriter output, CancellationToken ct = default) =>
            CurrentBuildOrientationSampleCommand.RunAsync(Options, output, ct,
                (_, _, _) =>
                {
                    if (LeaseDenied) throw new TimeoutException("busy");
                    LeaseHeld = true;
                    return Task.FromResult<IAsyncDisposable>(new TestLease(() =>
                    {
                        LeaseHeld = false;
                        LeaseDisposedAfterSession = !Opened || Session.Disposed;
                    }));
                },
                (_, _, _) =>
                {
                    Assert.True(LeaseHeld);
                    Opened = true;
                    return Task.FromResult<IReadOnlyNativeMemorySession>(Session);
                },
                s =>
                {
                    ReadCount++;
                    var matrix = CurrentBuildOrientationCandidateReader.Decode(new byte[36], 0x60);
                    return new(WrongObservation ? s.Identity with { ProcessStartUtcTicks = 999 } : s.Identity,
                        DateTimeOffset.UtcNow, DateTimeOffset.UtcNow,
                         ReadCount == ChangeUnitAtRead ? 42UL : ulong.MaxValue,
                         ReadCount == ChangeComponentAtRead ? 0x20061000UL : 0x20060000UL,
                        ulong.MaxValue, 0, matrix, matrix with { SourceOffset = 0x94 });
                });
        public void Dispose() => Directory.Delete(directory, true);
    }

    sealed class TestLease(Action dispose) : IAsyncDisposable
    {
        public ValueTask DisposeAsync() { dispose(); return ValueTask.CompletedTask; }
    }

    sealed class Fake : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; set; } = new(123, 456, "rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 64 * 1024 * 1024);
        public bool Revalidated { get; private set; }
        public int RevalidationCount { get; private set; }
        public bool Disposed { get; private set; }
        public string? RevalidationError { get; set; }
        public Action? OnRevalidate { get; set; }
        public NativeReadResult Read(ulong address, int length) => throw new InvalidOperationException("No live read in command test.");
        public ValueTask<string?> RevalidateAsync(CancellationToken ct)
        {
            Revalidated = true;
            RevalidationCount++;
            OnRevalidate?.Invoke();
            ct.ThrowIfCancellationRequested();
            return ValueTask.FromResult(RevalidationError);
        }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
