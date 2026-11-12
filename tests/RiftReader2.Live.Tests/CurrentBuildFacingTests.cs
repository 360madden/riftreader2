using System.Buffers.Binary;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildFacingTests
{
    private const ulong SystemAddress = 0x20050000;
    private const ulong Entity = 0x20040000;

    private static CurrentBuildFacingCandidate Read(Fake session) =>
        CurrentBuildFacingCandidateReader.Read(session, _ => new(42, Entity, SystemAddress,
            () => session.OwnerVerified = true), Orientation);

    private static CurrentBuildOrientationCandidate Orientation(IReadOnlyNativeMemorySession session)
    {
        float[] matrix = [0, 0, -1, 0, 1, 0, 1, 0, 0];
        var bytes = matrix.SelectMany(value => BitConverter.GetBytes(value)).ToArray();
        return new(session.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow,
            42, 0x20060000, 0, 0, CurrentBuildOrientationCandidateReader.Decode(bytes, 0x60),
            CurrentBuildOrientationCandidateReader.Decode(bytes, 0x94));
    }

    [Fact]
    public void ReadsSeparateBodyAndAimBearingsFromMatchingSelfOwner()
    {
        var session = new Fake();
        var value = Read(session);
        Assert.True(session.OwnerVerified);
        Assert.Equal(-90, value.BodyBearingDegreesCandidate!.Value, 4);
        Assert.Equal(0, value.CameraAimBearingDegreesCandidate!.Value, 8);
        Assert.Equal(7, value.RawBits.Length);
        Assert.Equal(new CurrentBuildXyz(100, 20, 200), value.PositionCandidate);
        Assert.False(value.HeadingQualified);
        Assert.False(value.CameraYawQualified);
        Assert.Equal("unavailable", value.OpticalCameraCandidate!.Status);
        session.Float(0x304, 0);
        var divergent = Read(session);
        Assert.Equal(0, divergent.PlayerSystemBearingDegreesCandidate);
        Assert.Equal(-90, divergent.BodyBearingDegreesCandidate);
        Assert.Equal(90, divergent.PlayerSystemMinusBodyDegreesCandidate);
    }

    [Theory]
    [InlineData(0x304)]
    [InlineData(0x30C)]
    [InlineData(0x320)]
    [InlineData(0x3F8)]
    public void RejectsChangedConsumedBytes(int offset)
    {
        var session = new Fake { ChangeOnSecondRead = offset };
        Assert.Throws<InvalidDataException>(() => Read(session));
    }

    [Fact]
    public void ReportsPrimaryGetterYawSeparatelyFromSecondaryBodyAngle()
    {
        var session = new Fake();
        float[] primary = [MathF.Cos(MathF.PI / 6), 0, -.5f,
                           0, 1, 0, .5f, 0, MathF.Cos(MathF.PI / 6)];
        var bytes = primary.SelectMany(value => BitConverter.GetBytes(value)).ToArray();
        var value = CurrentBuildFacingCandidateReader.Read(session,
            _ => new(42, Entity, SystemAddress, () => { }), source =>
                Orientation(source) with { Primary = CurrentBuildOrientationCandidateReader.Decode(bytes, 0x60) });
        Assert.Equal(-30, value.PrimaryBearingDegreesCandidate!.Value, 4);
        Assert.Equal(-90, value.BodyBearingDegreesCandidate!.Value, 4);
        Assert.Equal(-60, value.PlayerSystemMinusPrimaryDegreesCandidate!.Value, 4);
    }

    [Fact]
    public void RejectsWrongSelfNonfiniteAndEpochChanges()
    {
        var session = new Fake();
        BinaryPrimitives.WriteUInt64LittleEndian(session.Raw.AsSpan(0x3F8), Entity + 8);
        Assert.Throws<InvalidDataException>(() => Read(session));
        session = new Fake();
        session.Float(0x304, float.NaN);
        Assert.Throws<InvalidDataException>(() => Read(session));
        session = new Fake();
        Assert.Throws<InvalidDataException>(() => CurrentBuildFacingCandidateReader.Read(session,
            _ => new(42, Entity, SystemAddress, () =>
                session.Identity = session.Identity with { ProcessStartUtcTicks = 789 }), Orientation));
        session = new Fake();
        session.Identity = session.Identity with { ExecutableSha256 = new string('0', 64) };
        Assert.Throws<InvalidDataException>(() => CurrentBuildFacingCandidateReader.Read(session,
            _ => throw new Exception("Must reject the build before resolving ownership."), Orientation));
    }

    [Fact]
    public async Task BurstPublishesAfterFinalRevalidationAndReleasesLeaseAfterSession()
    {
        var directory = Path.Combine(Path.GetTempPath(), "rr2-facing-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            var path = Path.Combine(directory, "facing.json");
            var session = new Fake();
            var leaseReleased = false;
            var options = new Dictionary<string, string> { ["--pid"] = "123",
                ["--start-ticks"] = "456", ["--output"] = path,
                ["--samples"] = "3", ["--interval-ms"] = "0" };
            var reads = 0;
            Task<int> Run(Func<IReadOnlyNativeMemorySession, CurrentBuildFacingCandidate> read) =>
                CurrentBuildFacingSampleCommand.RunAsync(options, new StringWriter(), CancellationToken.None,
                    (_, _, _) => Task.FromResult<IAsyncDisposable>(new Lease(() =>
                    {
                        Assert.True(session.Disposed);
                        leaseReleased = true;
                    })),
                    (_, _, _) => Task.FromResult<IReadOnlyNativeMemorySession>(session), read);
            Assert.Equal(0, await Run(_ => { reads++; return Read(session); }));
            Assert.Equal(3, reads);
            Assert.Equal(1, session.Revalidations);
            Assert.True(leaseReleased);
            using var report = JsonDocument.Parse(await File.ReadAllTextAsync(path));
            Assert.Equal(3, report.RootElement.GetProperty("completedSamples").GetInt32());
            Assert.Equal("42", report.RootElement.GetProperty("observation")
                .GetProperty("playerKeyDecimal").GetString());
            File.Delete(path);
            session = new Fake { RevalidationError = "changed" };
            await Assert.ThrowsAsync<InvalidDataException>(() => Run(_ => Read(session)));
            Assert.False(File.Exists(path));
            session = new Fake();
            reads = 0;
            await Assert.ThrowsAsync<InvalidDataException>(() => Run(_ =>
                Read(session) with { PlayerKey = ++reads == 2 ? 99UL : 42UL }));
            Assert.False(File.Exists(path));
        }
        finally { Directory.Delete(directory, true); }
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public async Task OptionalTargetChecksOwnerAndCameraAcrossAcquisition(int fault)
    {
        var path = Path.Combine(Path.GetTempPath(), "rr2-facing-target-" + Guid.NewGuid().ToString("N") + ".json");
        try
        {
            var session = new Fake();
            var options = new Dictionary<string, string> { ["--pid"] = "123", ["--start-ticks"] = "456",
                ["--output"] = path, ["--include-target"] = "true" };
            var reads = 0;
            CurrentBuildFacingCandidate Facing(IReadOnlyNativeMemorySession source)
            {
                reads++;
                float[] transform = [0, 0, -1, 0, 1, 0, 1, 0, 0, 3, 39, -8, 7424, 832, 2944];
                float[] projection = [-1, 0, 0, 3, 0, 1, 0, -39, 0, 0, 1, 8, 0, 0, 1, 8, 0, 1, 1, 0];
                var camera = new CurrentBuildOpticalCameraCandidate("available-candidate", null,
                    fault == 1 && reads == 2 ? "300008" : "300000", transform[..9], transform[9..12],
                    transform[12..15], transform.Select(BitConverter.SingleToUInt32Bits).ToArray(),
                    0, 0, [7427, 871, 2936])
                {
                    ProjectionRowMajor = projection[..16], ViewportLeftRightTopBottom = projection[16..],
                    ProjectionRawBits = projection.Select(BitConverter.SingleToUInt32Bits).ToArray()
                };
                return Read((Fake)source) with { OpticalCameraCandidate = camera };
            }
            CurrentBuildPairedPositionObservation Target(IReadOnlyNativeMemorySession source)
            {
                var start = DateTimeOffset.UtcNow;
                var self = new PairedPositionCandidateSample("candidate", fault == 2 ? "43" : "42",
                    "u000000000000002A", new(100, 20, 200), start, start, 0, 0);
                var target = new PairedPositionCandidateSample("candidate", "99", "u0000000000000063",
                    new(110, 20, 210), start, DateTimeOffset.UtcNow, 0, 0);
                return new(source.Identity, start, DateTimeOffset.UtcNow, "test", self, target,
                    "candidate", "fallback-key-candidate", "fallback-key-candidate", 0, 0, 0);
            }
            var run = CurrentBuildFacingSampleCommand.RunAsync(options, new StringWriter(), CancellationToken.None,
                (_, _, _) => Task.FromResult<IAsyncDisposable>(new Lease(() => Assert.True(session.Disposed))),
                (_, _, _) => Task.FromResult<IReadOnlyNativeMemorySession>(session), Facing, Target);
            if (fault == 2)
            {
                await Assert.ThrowsAsync<InvalidDataException>(() => run);
                Assert.False(File.Exists(path));
                return;
            }
            Assert.Equal(0, await run);
            Assert.Equal(2, reads);
            using var report = JsonDocument.Parse(await File.ReadAllTextAsync(path));
            var observation = report.RootElement.GetProperty("observation");
            Assert.Equal(fault == 0, observation.GetProperty("targetProjectionCameraStableCandidate").GetBoolean());
            Assert.Equal("99", observation.GetProperty("targetPositionPairCandidate").GetProperty("target")
                .GetProperty("unitKey").GetString());
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Fact]
    public async Task CommandRouterAcceptsTargetFlagBeforeCheckingRequiredIdentity()
    {
        var error = new StringWriter();
        Assert.Equal(2, await NativeCommandRunner.RunAsync(
            ["sample-current-facing", "--include-target", "true"], TextWriter.Null, error));
        Assert.Contains("Facing requires --pid", error.ToString());
        Assert.DoesNotContain("Unknown option", error.ToString());
    }

    private sealed class Lease(Action release) : IAsyncDisposable
    {
        public ValueTask DisposeAsync() { release(); return ValueTask.CompletedTask; }
    }

    private sealed class Fake : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; set; } = new(123, 456, "rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 64 * 1024 * 1024);
        public byte[] Raw { get; } = new byte[0x400];
        public int? ChangeOnSecondRead { get; init; }
        public bool OwnerVerified { get; set; }
        public bool Disposed { get; private set; }
        public int Revalidations { get; private set; }
        public string? RevalidationError { get; init; }
        private readonly Dictionary<int, int> counts = [];
        public Fake()
        {
            Float(0x304, -MathF.PI / 2);
            Float(0x30C, 100); Float(0x310, 20); Float(0x314, 210);
            Float(0x320, 100); Float(0x324, 20); Float(0x328, 200);
            BinaryPrimitives.WriteUInt64LittleEndian(Raw.AsSpan(0x3F8), Entity);
        }
        public void Float(int offset, float value) =>
            BinaryPrimitives.WriteUInt32LittleEndian(Raw.AsSpan(offset), BitConverter.SingleToUInt32Bits(value));
        public NativeReadResult Read(ulong address, int length)
        {
            var offset = checked((int)(address - SystemAddress));
            var value = Raw.AsSpan(offset, length).ToArray();
            counts[offset] = counts.GetValueOrDefault(offset) + 1;
            if (offset == ChangeOnSecondRead && counts[offset] > 1) value[0] ^= 1;
            return new("success", value, null, null);
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken ct)
        {
            Revalidations++;
            return ValueTask.FromResult(RevalidationError);
        }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
