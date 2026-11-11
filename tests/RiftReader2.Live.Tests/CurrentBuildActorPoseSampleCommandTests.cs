using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildActorPoseSampleCommandTests
{
    [Fact]
    public async Task WritesLosslessCandidateOnlyAfterRevalidationAndReleasesLease()
    {
        using var fixture = new Fixture();
        using var output = new StringWriter();
        Assert.Equal(0, await fixture.Run(output));
        Assert.True(fixture.Session.Revalidated);
        Assert.True(fixture.Session.Disposed);
        Assert.True(fixture.LeaseDisposedAfterSession);
        using var json = JsonDocument.Parse(await File.ReadAllTextAsync(fixture.Path));
        var root = json.RootElement;
        Assert.Equal("native-current-actor-pose-candidate/1", root.GetProperty("contractVersion").GetString());
        var observation = root.GetProperty("observation");
        Assert.Equal(ulong.MaxValue.ToString(), observation.GetProperty("playerKeyDecimal").GetString());
        Assert.Equal(9, observation.GetProperty("actorMatrix").GetProperty("rawBits").GetArrayLength());
        Assert.False(observation.GetProperty("actorHeadingQualified").GetBoolean());
        Assert.Contains("unverified", observation.GetProperty("qualification").GetString());
        Assert.Contains("native-current-actor-pose-summary/1", output.ToString());
    }

    [Theory]
    [InlineData("--pid", "0")]
    [InlineData("--pid", "abc")]
    [InlineData("--start-ticks", "-2")]
    [InlineData("--output", " ")]
    public async Task InvalidArgumentsBlockBeforeOpening(string key, string value)
    {
        using var fixture = new Fixture();
        fixture.Options[key] = value;
        await Assert.ThrowsAsync<ArgumentException>(() => fixture.Run(new StringWriter()));
        Assert.False(fixture.Opened);
        Assert.False(File.Exists(fixture.Path));
    }

    [Fact]
    public async Task ExistingOutputAndLeaseDenialDoNotOpenSession()
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
    public async Task WrongSessionOrObservationEpochNeverPublishes()
    {
        using var fixture = new Fixture();
        fixture.Session.Identity = fixture.Session.Identity with { ProcessId = 999 };
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Run(new StringWriter()));
        Assert.False(fixture.Read);
        Assert.False(File.Exists(fixture.Path));
        fixture.Session.Identity = fixture.Session.Identity with { ProcessId = 123 };
        fixture.WrongObservation = true;
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Run(new StringWriter()));
        Assert.False(File.Exists(fixture.Path));
    }

    [Fact]
    public async Task InvalidatedOrMutatedSessionNeverPublishes()
    {
        using var fixture = new Fixture();
        fixture.Session.RevalidationError = "process-epoch-changed";
        using var output = new StringWriter();
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Run(output));
        Assert.False(File.Exists(fixture.Path));
        Assert.Empty(output.ToString());
        fixture.Session.RevalidationError = null;
        fixture.Session.ChangeIdentityOnRevalidate = true;
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Run(output));
        Assert.False(File.Exists(fixture.Path));
    }

    [Fact]
    public async Task CancelledRevalidationAndLateOutputRaceDoNotPublishSummary()
    {
        using var fixture = new Fixture();
        using var cancellation = new CancellationTokenSource();
        fixture.Session.OnRevalidate = cancellation.Cancel;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            () => fixture.Run(new StringWriter(), cancellation.Token));
        Assert.False(File.Exists(fixture.Path));

        fixture.Session.OnRevalidate = () => File.WriteAllText(fixture.Path, "racer");
        using var output = new StringWriter();
        await Assert.ThrowsAsync<IOException>(() => fixture.Run(output));
        Assert.Equal("racer", await File.ReadAllTextAsync(fixture.Path));
        Assert.Empty(output.ToString());
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string directory = System.IO.Path.Combine(System.IO.Path.GetTempPath(),
            "rr2-actor-pose-test-" + Guid.NewGuid().ToString("N"));
        public string Path => System.IO.Path.Combine(directory, "candidate.json");
        public Fake Session { get; } = new();
        public Dictionary<string, string> Options { get; }
        public bool Opened { get; private set; }
        public bool Read { get; private set; }
        public bool LeaseDenied { get; set; }
        public bool LeaseHeld { get; private set; }
        public bool LeaseDisposedAfterSession { get; private set; }
        public bool WrongObservation { get; set; }

        public Fixture()
        {
            Directory.CreateDirectory(directory);
            Options = new() { ["--pid"] = "123", ["--start-ticks"] = "456", ["--output"] = Path };
        }

        public Task<int> Run(TextWriter output, CancellationToken token = default) =>
            CurrentBuildActorPoseSampleCommand.RunAsync(Options, output, token,
                (_, _, _) =>
                {
                    if (LeaseDenied) throw new TimeoutException("busy");
                    LeaseHeld = true;
                    return Task.FromResult<IAsyncDisposable>(new TestLease(() =>
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
                source =>
                {
                    Read = true;
                    var matrix = CurrentBuildOrientationCandidateReader.Decode(new byte[36], 0x398);
                    return new(WrongObservation ? source.Identity with { ProcessStartUtcTicks = 999 } : source.Identity,
                        DateTimeOffset.UtcNow, DateTimeOffset.UtcNow,
                        ulong.MaxValue, 0x200000, 0x300000, 0x400000, 0,
                        matrix, matrix, null, "alternate-reference-branch-not-followed", null);
                });

        public void Dispose() => Directory.Delete(directory, recursive: true);
    }

    private sealed class TestLease(Action onDispose) : IAsyncDisposable
    {
        public ValueTask DisposeAsync() { onDispose(); return ValueTask.CompletedTask; }
    }

    private sealed class Fake : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; set; } = new(123, 456, "rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 64 * 1024 * 1024);
        public bool Revalidated { get; private set; }
        public bool Disposed { get; private set; }
        public string? RevalidationError { get; set; }
        public bool ChangeIdentityOnRevalidate { get; set; }
        public Action? OnRevalidate { get; set; }
        public NativeReadResult Read(ulong address, int length) => throw new InvalidOperationException();
        public ValueTask<string?> RevalidateAsync(CancellationToken token)
        {
            Revalidated = true;
            OnRevalidate?.Invoke();
            token.ThrowIfCancellationRequested();
            if (ChangeIdentityOnRevalidate)
                Identity = Identity with { ProcessStartUtcTicks = Identity.ProcessStartUtcTicks + 1 };
            return ValueTask.FromResult(RevalidationError);
        }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
