using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Live;

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
    private sealed class Harness
    {
        public readonly List<Session> Sessions = [];
        public int Acquires, Releases;
        public bool Held;
        public readonly SemaphoreSlim Gate = new(1, 1);
        public Func<int, Session>? Create;
        public Func<TimeSpan>? Elapsed;
        public Func<Session, CurrentBuildFacingCandidate>? Read;
        public Func<IReadOnlyNativeMemorySession, CurrentBuildPairedPositionObservation>? ReadTarget;
        public Dictionary<string, string> OptionsOverride = new(Options);
        public Task<int> Run(TextWriter writer, CancellationToken ct = default) =>
            CurrentBuildFacingStreamCommand.RunAsync(OptionsOverride, writer, ct,
                async (_, _, remaining, token) => { Assert.InRange(remaining.TotalMilliseconds, 0.001, 2000);
                    await Gate.WaitAsync(token); Assert.False(Held); Held = true; Acquires++;
                    return new Lease(() => {
                        if (Sessions.Count > Releases) Assert.True(Sessions[^1].Disposed);
                        Held = false; Releases++; Gate.Release();
                    }); },
                (_, _, _) => { var session = Create?.Invoke(Sessions.Count) ?? new Session(); Sessions.Add(session);
                    return Task.FromResult<IReadOnlyNativeMemorySession>(session); },
                (session, _) => Read?.Invoke((Session)session) ?? Sample((Session)session), Elapsed, ReadTarget);
    }
    private sealed class CheckingWriter(Harness harness) : StringWriter
    {
        public override Task WriteLineAsync(string? value) { Assert.False(harness.Held); Assert.All(harness.Sessions, s => Assert.True(s.Disposed)); return base.WriteLineAsync(value); }
    }
    [Fact]
    public async Task PerRowRevalidatesDisposesAndReleasesBeforeWriting()
    {
        var h = new Harness(); var writer = new CheckingWriter(h);
        Assert.Equal(0, await h.Run(writer));
        Assert.Equal(2, h.Acquires); Assert.Equal(2, h.Releases); Assert.Equal(2, h.Sessions.Count);
        Assert.All(h.Sessions, s => Assert.Equal(1, s.Validations));
        var lines = writer.ToString().Split('\n', StringSplitOptions.RemoveEmptyEntries);
        Assert.Equal(3, lines.Length);
        for (var i = 0; i < 2; i++) { using var row = JsonDocument.Parse(lines[i]); Assert.Equal(i, row.RootElement.GetProperty("sequence").GetInt32()); Assert.True(row.RootElement.GetProperty("captureElapsedMilliseconds").GetDouble() > 0); }
        using var end = JsonDocument.Parse(lines[2]); Assert.Equal("complete", end.RootElement.GetProperty("status").GetString());
    }
    [Fact]
    public async Task IdentityOwnerAndValidationChangesWithholdBadRow()
    {
        for (var fault = 0; fault < 3; fault++)
        {
            var h = new Harness(); var writer = new StringWriter();
            h.Create = i => new Session { Identity = i == 1 && fault == 0 ? new(123, 456, "other.exe", CurrentBuildPlayerLookup.GameSha256, 0x140000000, 64 * 1024 * 1024) : new(123, 456, "rift_x64.exe", CurrentBuildPlayerLookup.GameSha256, 0x140000000, 64 * 1024 * 1024), Failure = i == 1 && fault == 2 ? "changed" : null };
            h.Read = s => Sample(s, h.Sessions.Count == 2 && fault == 1 ? 43UL : 42UL);
            await Assert.ThrowsAsync<InvalidDataException>(() => h.Run(writer));
            Assert.Equal(2, h.Releases); Assert.False(h.Held); Assert.DoesNotContain("stream-end", writer.ToString());
            Assert.Single(writer.ToString().Split('\n', StringSplitOptions.RemoveEmptyEntries));
        }
    }
    [Fact]
    public async Task DeadlineAfterAcquireReleasesWithoutOpening()
    {
        var h = new Harness(); h.Elapsed = () => h.Acquires > 0 ? TimeSpan.FromSeconds(2) : TimeSpan.Zero;
        var writer = new StringWriter(); Assert.Equal(0, await h.Run(writer));
        Assert.Empty(h.Sessions); Assert.Equal(1, h.Releases); Assert.Contains("duration-limit", writer.ToString());
    }
    private sealed class BlockedWriter : StringWriter
    {
        public readonly TaskCompletionSource Started = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public readonly TaskCompletionSource Unblock = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public override async Task WriteLineAsync(string? value) { Started.TrySetResult(); await Unblock.Task; await base.WriteLineAsync(value); }
    }
    [Fact]
    public async Task BlockedWriterDoesNotHoldLease()
    {
        var h = new Harness(); var writer = new BlockedWriter(); var run = h.Run(writer);
        await writer.Started.Task.WaitAsync(TimeSpan.FromSeconds(2));
        Assert.False(h.Held); Assert.Equal(1, h.Releases); Assert.True(h.Sessions[0].Disposed);
        // A second participant may acquire the now-free lease while output is blocked.
        Assert.True(await h.Gate.WaitAsync(TimeSpan.FromSeconds(1)));
        h.Gate.Release();
        writer.Unblock.SetResult(); Assert.Equal(0, await run);
    }
    [Fact]
    public async Task OpenFailureReleasesLease()
    {
        var h = new Harness { Create = _ => throw new IOException("open") };
        await Assert.ThrowsAsync<IOException>(() => h.Run(new StringWriter()));
        Assert.False(h.Held); Assert.Empty(h.Sessions); Assert.Equal(1, h.Releases);
    }
    [Fact]
    public async Task OptionalTargetAbsentAndUnstableCameraRemainExplicit()
    {
        var h = new Harness(); h.OptionsOverride["--include-target"] = "true"; var targetReads = 0;
        h.ReadTarget = source => {
            targetReads++; var now = DateTimeOffset.UtcNow;
            var self = new PairedPositionCandidateSample("candidate", "42", "u000000000000002A", new(0, 0, 0), now, now, 0, 0);
            return new(source.Identity, now, now, "test", self, null, "unavailable", "same", "same", 0, null, null);
        };
        var writer = new CheckingWriter(h); Assert.Equal(0, await h.Run(writer));
        Assert.Equal(2, targetReads); Assert.Equal(2, h.Releases);
        using var row = JsonDocument.Parse(writer.ToString().Split('\n')[0]);
        var observation = row.RootElement.GetProperty("observation");
        Assert.Equal("target-unavailable", observation.GetProperty("targetPositionPairCandidate").GetProperty("status").GetString());
        Assert.False(observation.GetProperty("targetProjectionCameraStableCandidate").GetBoolean());
    }

    [Fact]
    public async Task MovingCameraMarksTargetProjectionUnstable()
    {
        var h = new Harness(); h.OptionsOverride["--include-target"] = "true"; var reads = 0;
        h.Read = session => {
            reads++;
            var camera = new CurrentBuildOpticalCameraCandidate("available-candidate", null, "300000",
                new float[9], new float[3], new float[3], Enumerable.Repeat((uint)reads, 15).ToArray(), 0, 0, new double[3])
                { ProjectionRowMajor = new float[16], ViewportLeftRightTopBottom = new float[4], ProjectionRawBits = new uint[20] };
            return Sample(session) with { OpticalCameraCandidate = camera };
        };
        h.ReadTarget = source => {
            var now = DateTimeOffset.UtcNow;
            var self = new PairedPositionCandidateSample("candidate", "42", "u000000000000002A", new(0, 0, 0), now, now, 0, 0);
            var target = new PairedPositionCandidateSample("candidate", "99", "u0000000000000063", new(1, 0, 1), now, now, 0, 0);
            return new(source.Identity, now, now, "test", self, target, "candidate", "same", "same", 0, 0, 0);
        };
        var writer = new StringWriter(); Assert.Equal(0, await h.Run(writer));
        using var row = JsonDocument.Parse(writer.ToString().Split('\n')[0]);
        var observation = row.RootElement.GetProperty("observation");
        Assert.Equal("paired-candidate", observation.GetProperty("targetPositionPairCandidate").GetProperty("status").GetString());
        Assert.False(observation.GetProperty("targetProjectionCameraStableCandidate").GetBoolean());
    }

    [Fact]
    public async Task TargetFalseSkipsPairAndChangedTargetOwnerRejectsRow()
    {
        var h = new Harness(); h.OptionsOverride["--include-target"] = "false";
        h.ReadTarget = _ => throw new Exception("target read must not occur");
        Assert.Equal(0, await h.Run(new StringWriter()));
        h = new Harness(); h.OptionsOverride["--include-target"] = "true";
        h.ReadTarget = source => {
            var now = DateTimeOffset.UtcNow;
            var self = new PairedPositionCandidateSample("candidate", "99", "u0000000000000063", new(0, 0, 0), now, now, 0, 0);
            return new(source.Identity, now, now, "test", self, null, "unavailable", "same", "same", 0, null, null);
        };
        var writer = new StringWriter(); await Assert.ThrowsAsync<InvalidDataException>(() => h.Run(writer));
        Assert.Equal("", writer.ToString()); Assert.False(h.Held); Assert.Equal(1, h.Releases);
    }

    private sealed class BrokenWriter : StringWriter
    { public override Task WriteLineAsync(string? value) => Task.FromException(new IOException("closed")); }
    [Fact]
    public async Task ReadWriteValidationAndCancellationFailuresRelease()
    {
        for (var fault = 0; fault < 4; fault++)
        {
            var h = new Harness(); using var cts = new CancellationTokenSource();
            h.Create = _ => new Session { Failure = fault == 1 ? "changed" : null };
            h.Read = s => { if (fault == 0) throw new IOException("read"); if (fault == 2) cts.Cancel(); return Sample(s); };
            var writer = fault == 3 ? (TextWriter)new BrokenWriter() : new StringWriter();
            await Assert.ThrowsAnyAsync<Exception>(() => h.Run(writer, cts.Token));
            Assert.False(h.Held); Assert.Equal(1, h.Releases); Assert.True(h.Sessions[0].Disposed);
        }
    }
}
