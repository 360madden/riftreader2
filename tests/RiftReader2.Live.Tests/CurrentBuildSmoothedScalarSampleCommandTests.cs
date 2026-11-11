using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildSmoothedScalarSampleCommandTests
{
    [Fact]
    public async Task WritesReadOnlyOwnerPinnedCandidateAfterRevalidation()
    {
        using var fixture = new Fixture();
        using var output = new StringWriter();
        Assert.Equal(0, await fixture.Run(output));
        Assert.True(fixture.Session.Revalidated);
        Assert.True(fixture.Session.Disposed);
        Assert.True(fixture.LeaseDisposedAfterSession);
        using var report = JsonDocument.Parse(await File.ReadAllTextAsync(fixture.Path));
        Assert.Equal("native-current-smoothed-scalar-candidate/1",
            report.RootElement.GetProperty("contractVersion").GetString());
        var observation = report.RootElement.GetProperty("observation");
        Assert.Equal(ulong.MaxValue.ToString(), observation.GetProperty("playerKeyDecimal").GetString());
        Assert.False(observation.GetProperty("headingQualified").GetBoolean());
        Assert.Equal(4, observation.GetProperty("rawBits").GetArrayLength());
        Assert.Equal(.5f, observation.GetProperty("currentCandidate").GetSingle());
        Assert.Contains("native-current-smoothed-scalar-summary/1", output.ToString());
    }

    [Fact]
    public async Task PassiveBurstPublishesOneOwnerPinnedSeriesUnderOneLease()
    {
        using var fixture = new Fixture();
        fixture.Options["--samples"] = "3";
        fixture.Options["--interval-ms"] = "0";
        using var output = new StringWriter();
        Assert.Equal(0, await fixture.Run(output));
        Assert.Equal(3, fixture.ReadCount);
        Assert.Equal(3, fixture.Session.RevalidationCount);
        Assert.Equal(1, fixture.LeaseAcquisitions);
        Assert.True(fixture.LeaseDisposedAfterSession);
        using var report = JsonDocument.Parse(await File.ReadAllTextAsync(fixture.Path));
        Assert.Equal("native-current-smoothed-scalar-candidate-burst/1",
            report.RootElement.GetProperty("contractVersion").GetString());
        Assert.Equal(3, report.RootElement.GetProperty("completedSamples").GetInt32());
        var observations = report.RootElement.GetProperty("observations");
        Assert.Equal(3, observations.GetArrayLength());
        foreach (var observation in observations.EnumerateArray())
        {
            Assert.Equal(ulong.MaxValue.ToString(), observation.GetProperty("playerKeyDecimal").GetString());
            Assert.False(observation.GetProperty("headingQualified").GetBoolean());
        }
        Assert.Equal(3, JsonDocument.Parse(output.ToString()).RootElement
            .GetProperty("completedSamples").GetInt32());
    }

    [Fact]
    public async Task PassiveBurstRejectsPlayerChangeWithoutPublishingPartialEvidence()
    {
        using var fixture = new Fixture();
        fixture.Options["--samples"] = "3";
        fixture.Options["--interval-ms"] = "0";
        fixture.ChangePlayerAtRead = 2;
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Run(new StringWriter()));
        Assert.Equal(2, fixture.ReadCount);
        Assert.Equal(2, fixture.Session.RevalidationCount);
        Assert.True(fixture.LeaseDisposedAfterSession);
        Assert.False(File.Exists(fixture.Path));
    }

    [Theory]
    [InlineData("--samples", "0")]
    [InlineData("--samples", "31")]
    [InlineData("--interval-ms", "2001")]
    [InlineData("--pid", "0")]
    [InlineData("--pid", "abc")]
    [InlineData("--start-ticks", "-1")]
    [InlineData("--output", " ")]
    public async Task MalformedInputsDoNotAcquireLease(string key, string value)
    {
        using var fixture = new Fixture();
        fixture.Options[key] = value;
        await Assert.ThrowsAsync<ArgumentException>(() => fixture.Run(new StringWriter()));
        Assert.False(fixture.LeaseHeld);
        Assert.False(fixture.Opened);
        Assert.False(File.Exists(fixture.Path));
    }

    [Fact]
    public async Task ExistingOutputAndDeniedLeaseNeverOpenSession()
    {
        using var fixture = new Fixture();
        await File.WriteAllTextAsync(fixture.Path, "original");
        await Assert.ThrowsAsync<IOException>(() => fixture.Run(new StringWriter()));
        Assert.Equal("original", await File.ReadAllTextAsync(fixture.Path));
        Assert.False(fixture.Opened);
        File.Delete(fixture.Path);
        fixture.LeaseDenied = true;
        await Assert.ThrowsAsync<TimeoutException>(() => fixture.Run(new StringWriter()));
        Assert.False(fixture.Opened);
    }

    [Fact]
    public async Task ChangedProcessOwnerAndLateRevalidationNeverPublish()
    {
        using var fixture = new Fixture();
        fixture.Session.Identity = fixture.Session.Identity with { ProcessId = 999 };
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Run(new StringWriter()));
        Assert.False(fixture.Read);
        fixture.Session.Identity = fixture.Session.Identity with { ProcessId = 123 };
        fixture.WrongObservation = true;
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Run(new StringWriter()));
        Assert.False(File.Exists(fixture.Path));
        fixture.WrongObservation = false;
        fixture.Session.Invalidated = true;
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Run(new StringWriter()));
        Assert.False(File.Exists(fixture.Path));
        Assert.True(fixture.LeaseDisposedAfterSession);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string directory = System.IO.Path.Combine(System.IO.Path.GetTempPath(),
            "rr2-physical-scalar-" + Guid.NewGuid().ToString("N"));
        public string Path => System.IO.Path.Combine(directory, "scalar.json");
        public Dictionary<string, string> Options { get; }
        public SessionFake Session { get; } = new();
        public bool LeaseHeld { get; private set; }
        public bool LeaseDenied { get; set; }
        public bool Opened { get; private set; }
        public bool Read { get; private set; }
        public int ReadCount { get; private set; }
        public int LeaseAcquisitions { get; private set; }
        public int ChangePlayerAtRead { get; set; }
        public bool WrongObservation { get; set; }
        public bool LeaseDisposedAfterSession { get; private set; }

        public Fixture()
        {
            Directory.CreateDirectory(directory);
            Options = new() { ["--pid"] = "123", ["--start-ticks"] = "456", ["--output"] = Path };
        }

        public Task<int> Run(TextWriter output) =>
            CurrentBuildSmoothedScalarSampleCommand.RunAsync(Options, output, CancellationToken.None,
                (_, _, _) =>
                {
                    if (LeaseDenied) throw new TimeoutException("busy");
                    LeaseHeld = true;
                    LeaseAcquisitions++;
                    return Task.FromResult<IAsyncDisposable>(new Lease(() =>
                    {
                        LeaseHeld = false;
                        LeaseDisposedAfterSession = Session.Disposed;
                    }));
                },
                (_, _, _) =>
                {
                    Assert.True(LeaseHeld);
                    Opened = true;
                    return Task.FromResult<IReadOnlyNativeMemorySession>(Session);
                },
                reader =>
                {
                    Read = true;
                    ReadCount++;
                    var identity = WrongObservation
                        ? reader.Identity with { ProcessStartUtcTicks = 999 } : reader.Identity;
                    return new(identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow,
                        ReadCount == ChangePlayerAtRead ? 42UL : ulong.MaxValue, 0x200000, 0x300000,
                        [0x3F000000, 0x3FC00000, 0x40200000, 0x3E800000],
                        .5f, 1.5f, 2.5f, .25f);
                });

        public void Dispose() => Directory.Delete(directory, recursive: true);
    }

    private sealed class Lease(Action dispose) : IAsyncDisposable
    {
        public ValueTask DisposeAsync() { dispose(); return ValueTask.CompletedTask; }
    }

    private sealed class SessionFake : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; set; } = new(123, 456, "rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 64 * 1024 * 1024);
        public bool Revalidated { get; private set; }
        public int RevalidationCount { get; private set; }
        public bool Invalidated { get; set; }
        public bool Disposed { get; private set; }
        public NativeReadResult Read(ulong address, int length) =>
            throw new InvalidOperationException("No actual native reads in offline lifecycle test.");
        public ValueTask<string?> RevalidateAsync(CancellationToken ct)
        {
            Revalidated = true;
            RevalidationCount++;
            return ValueTask.FromResult(Invalidated ? "epoch-changed" : (string?)null);
        }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
