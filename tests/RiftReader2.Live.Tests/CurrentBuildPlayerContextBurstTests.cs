using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildPlayerContextBurstTests
{
    [Fact]
    public async Task BurstUsesOneLeaseAndSessionAndPreservesAllThreeSamples()
    {
        var path = TempPath();
        var lease = new Lease();
        var session = new Session(lease);
        var count = 0;
        try
        {
            var result = await Run(path, session, lease, s => Make(s, ++count), 3);
            Assert.Equal(0, result);
            Assert.Equal(3, count);
            Assert.Equal(3, session.Revalidations);
            Assert.True(session.Disposed && lease.Disposed);
            using var doc = JsonDocument.Parse(await File.ReadAllTextAsync(path));
            var root = doc.RootElement;
            Assert.Equal("native-current-player-context-candidate-burst/1",
                root.GetProperty("contractVersion").GetString());
            Assert.Equal(3, root.GetProperty("requestedSamples").GetInt32());
            Assert.Equal(3, root.GetProperty("completedSamples").GetInt32());
            Assert.Equal(3, root.GetProperty("observations").GetArrayLength());
            Assert.True(JsonElement.DeepEquals(root.GetProperty("observation"),
                root.GetProperty("observations")[2]));
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Theory]
    [InlineData("player")]
    [InlineData("epoch")]
    [InlineData("order")]
    public async Task RefusesMixedOwnerOrOverlappingTimeWithoutPublishing(string mutation)
    {
        var path = TempPath();
        var lease = new Lease();
        var session = new Session(lease);
        var count = 0;
        await Assert.ThrowsAsync<InvalidDataException>(() => Run(path, session, lease,
            s =>
            {
                count++;
                var observation = Make(s, count);
                if (count != 2) return observation;
                return mutation switch
                {
                    "player" => observation with { UnitKey = 42 },
                    "epoch" => observation with { Identity = observation.Identity with { ProcessId = 999 } },
                    _ => observation with { StartedAtUtc = observation.StartedAtUtc.AddSeconds(-2) }
                };
            }, 3));
        Assert.False(File.Exists(path));
        Assert.True(session.Disposed && lease.Disposed);
    }

    [Theory]
    [InlineData("--samples", "0")]
    [InlineData("--samples", "31")]
    [InlineData("--interval-ms", "2001")]
    [InlineData("--interval-ms", "-1")]
    public async Task InvalidBoundsFailBeforeLeaseAcquisition(string option, string value)
    {
        var path = TempPath();
        var options = Options(path);
        options[option] = value;
        var opened = false;
        await Assert.ThrowsAsync<ArgumentException>(() =>
            CurrentBuildPlayerContextSampleCommand.RunAsync(options, TextWriter.Null,
                CancellationToken.None,
                (_, _, _) => { opened = true; throw new Exception(); },
                (_, _, _) => throw new Exception(), _ => throw new Exception()));
        Assert.False(opened);
        Assert.False(File.Exists(path));
    }

    static async Task<int> Run(string path, Session session, Lease lease,
        Func<IReadOnlyNativeMemorySession, CurrentBuildPlayerContextObservation> read, int samples)
    {
        var options = Options(path);
        options["--samples"] = samples.ToString();
        options["--interval-ms"] = "0";
        return await CurrentBuildPlayerContextSampleCommand.RunAsync(options, TextWriter.Null,
            CancellationToken.None, (_, _, _) => Task.FromResult<IAsyncDisposable>(lease),
            (_, _, _) => Task.FromResult<IReadOnlyNativeMemorySession>(session), read);
    }

    static Dictionary<string, string> Options(string path) =>
        new() { ["--pid"] = "123", ["--start-ticks"] = "456", ["--output"] = path };

    static string TempPath() => Path.Combine(Path.GetTempPath(),
        "rr2-context-burst-" + Guid.NewGuid().ToString("N") + ".json");

    static CurrentBuildPlayerContextObservation Make(IReadOnlyNativeMemorySession s, int n)
    {
        var time = new DateTimeOffset(2026, 11, 11, 11, 0, 0, TimeSpan.Zero).AddSeconds(n);
        return new(s.Identity, time, time.AddMilliseconds(1), 239816685251645959UL,
            1, 1, 1, 1, 0, "raw-getter-zero-candidate", 0, null, 45,
            "numeric-getter-and-presentation-candidate", 0, "raw-byte-candidate", false, 1, "warrior");
    }

    sealed class Lease : IAsyncDisposable
    {
        public bool Disposed { get; private set; }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }

    sealed class Session(Lease lease) : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; } = new(123, 456,
            @"C:\RIFT\rift_x64.exe", CurrentBuildPlayerLookup.GameSha256,
            0x140000000, 0x4000000);
        public int Revalidations { get; private set; }
        public bool Disposed { get; private set; }
        public NativeReadResult Read(ulong address, int length) => throw new NotSupportedException();
        public ValueTask<string?> RevalidateAsync(CancellationToken token)
        {
            Assert.False(lease.Disposed);
            Revalidations++;
            return ValueTask.FromResult<string?>(null);
        }
        public ValueTask DisposeAsync()
        {
            Assert.False(lease.Disposed);
            Disposed = true;
            return ValueTask.CompletedTask;
        }
    }
}
