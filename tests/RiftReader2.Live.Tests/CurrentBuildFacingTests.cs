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
