using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Live;
using Xunit;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildFacingStreamTests
{
    private static readonly Dictionary<string, string> Options = new() {
        ["--pid"] = "123", ["--start-ticks"] = "456", ["--samples"] = "2", ["--interval-ms"] = "20" };
    private sealed class Session : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; set; } = new(123, 456, "rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 64 * 1024 * 1024);
        public bool Disposed { get; private set; }
        public int Validations { get; private set; }
        public string? Failure { get; set; }
        public NativeReadResult Read(ulong address, int length) => throw new NotSupportedException();
        public ValueTask<string?> RevalidateAsync(CancellationToken ct) { ct.ThrowIfCancellationRequested(); Validations++; return ValueTask.FromResult(Failure); }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
    private sealed class Lease(Action action) : IAsyncDisposable
    { public ValueTask DisposeAsync() { action(); return ValueTask.CompletedTask; } }
    private static CurrentBuildFacingCandidate Sample(Session session, ulong key = 42)
    {
        float[] matrix = [0, 0, -1, 0, 1, 0, 1, 0, 0];
        var bytes = matrix.SelectMany(BitConverter.GetBytes).ToArray();
        var orientation = new CurrentBuildOrientationCandidate(session.Identity, DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow, key, 30, 0, 0, CurrentBuildOrientationCandidateReader.Decode(bytes, 0x60),
            CurrentBuildOrientationCandidateReader.Decode(bytes, 0x94));
        return new(session.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, key, 10, 20, [], 0, 0,
            new(0, 0, 0), new(0, 0, 0), null, orientation);
    }

    private static Task<int> Run(Session session, TextWriter writer,
        Func<IReadOnlyNativeMemorySession, CancellationToken, CurrentBuildFacingCandidate> read,
        Action release, CancellationToken token = default, Func<TimeSpan>? elapsed = null) =>
        CurrentBuildFacingStreamCommand.RunAsync(Options, writer, token,
            (_, _, _) => Task.FromResult<IAsyncDisposable>(new Lease(() => { Assert.True(session.Disposed); release(); })),
            (_, _, _) => Task.FromResult<IReadOnlyNativeMemorySession>(session), read, elapsed);

    [Fact]
    public async Task EachRowIsRevalidatedAndEmittedBeforeNextRead()
    {
        var session = new Session(); var writer = new StringWriter(); var reads = 0; var released = false;
        var totalTimer = System.Diagnostics.Stopwatch.StartNew();
        Assert.Equal(0, await Run(session, writer, (_, _) => {
            Assert.Equal(reads, session.Validations);
            if (reads > 0) Assert.Contains("native-current-facing-stream-row/1", writer.ToString());
            reads++; return Sample(session);
        }, () => released = true));
        Assert.True(released); Assert.Equal(2, session.Validations);
        var lines = writer.ToString().Split('\n', StringSplitOptions.RemoveEmptyEntries);
        Assert.Equal(3, lines.Length);
        for (var i = 0; i < 2; i++)
        {
            using var row = JsonDocument.Parse(lines[i]);
            Assert.Equal(i, row.RootElement.GetProperty("sequence").GetInt32());
            var captureMs = row.RootElement.GetProperty("captureElapsedMilliseconds").GetDouble();
            Assert.True(captureMs > 0);
            if (i == 1) Assert.True(totalTimer.Elapsed.TotalMilliseconds - captureMs >= 15,
                "Second row should exclude the inter-row delay.");
        }
        using var end = JsonDocument.Parse(lines[2]); Assert.Equal("complete", end.RootElement.GetProperty("status").GetString());
    }

    [Fact]
    public async Task RevalidationFailureOrOwnerChangeDoesNotEmitBadRow()
    {
        var session = new Session { Failure = "changed" }; var writer = new StringWriter(); var released = false;
        await Assert.ThrowsAsync<InvalidDataException>(() => Run(session, writer, (_, _) => Sample(session), () => released = true));
        Assert.Equal("", writer.ToString()); Assert.True(released);
        session = new Session(); writer = new StringWriter(); var count = 0;
        await Assert.ThrowsAsync<InvalidDataException>(() => Run(session, writer, (_, _) => Sample(session, ++count == 1 ? 42UL : 43UL), () => { }));
        Assert.Equal(1, session.Validations); Assert.DoesNotContain("stream-end", writer.ToString());
    }

    [Fact]
    public async Task DeadlineReportsTruncationAndReleases()
    {
        var session = new Session(); var writer = new StringWriter(); var released = false;
        Assert.Equal(0, await Run(session, writer, (_, _) => throw new Exception("must not read"),
            () => released = true, elapsed: () => TimeSpan.FromSeconds(2)));
        Assert.True(released); Assert.Contains("duration-limit", writer.ToString()); Assert.Equal(0, session.Validations);
    }

    private sealed class BrokenWriter : StringWriter
    { public override Task WriteLineAsync(string? value) => Task.FromException(new IOException("closed")); }

    [Fact]
    public async Task BrokenOutputAndCancellationReleaseSessionAndLease()
    {
        var session = new Session(); var released = false;
        await Assert.ThrowsAsync<IOException>(() => Run(session, new BrokenWriter(), (_, _) => Sample(session), () => released = true));
        Assert.True(released);
        session = new Session(); released = false; using var cts = new CancellationTokenSource();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Run(session, new StringWriter(), (_, _) => { cts.Cancel(); return Sample(session); }, () => released = true, cts.Token));
        Assert.True(released);
    }
}
