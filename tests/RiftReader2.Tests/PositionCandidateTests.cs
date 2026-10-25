using System.Buffers.Binary;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Tests;

public sealed class PositionCandidateTests
{
    private const string BuildSha = "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD";
    private static readonly PositionCandidateProfile Profile = new(BuildSha, 0x32E0200, 0x320, 0x324, 0x328);
    private static readonly NativeProcessIdentity Identity = new(
        42, 638000000000000000, @"C:\RIFT\rift_x64.exe", BuildSha, 0x140000000, 0x4000000);

    [Fact]
    public async Task KnownBuild_UsesFreshPointerReadsAndDecodesChangingFiniteXyz()
    {
        var session = new FixtureSession(Identity, [Owner(1.5f, 2.5f, 3.5f), Owner(2.5f, 3.5f, 4.5f)]);
        var streamed = new List<PositionCandidateObservation>();
        var result = await PositionCandidateSampler.SampleAsync(Profile, session, 2, 0, CancellationToken.None,
            observation => { streamed.Add(observation); return Task.CompletedTask; });
        Assert.Equal(result.Observations, streamed);
        Assert.Equal("complete", result.Status);
        Assert.Equal(2, result.CompletedSamples);
        Assert.Equal([1.5f, 2.5f], result.Observations.Select(sample => sample.X!.Value));
        Assert.Equal([2.5f, 3.5f], result.Observations.Select(sample => sample.Y!.Value));
        Assert.Equal([3.5f, 4.5f], result.Observations.Select(sample => sample.Z!.Value));
        Assert.All(result.Observations, sample =>
        {
            Assert.Equal("complete", sample.Status);
            Assert.Equal("0x400000", sample.OwnerAddress);
            Assert.Equal(64, sample.TerminalBytesSha256!.Length);
        });
        Assert.Equal(2, session.PointerReads);
        Assert.Equal(2, session.TerminalReads);
        Assert.Equal(4, session.Revalidations);
    }

    [Fact]
    public async Task WrongBuildRefusesAllReads_AndDoesNotFallBackToMemoryScan()
    {
        var session = new FixtureSession(Identity, [Owner(1, 2, 3)]);
        var wrongBuild = Profile with { ExecutableSha256 = new string('B', 64) };
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            PositionCandidateSampler.SampleAsync(wrongBuild, session, 1, 0, CancellationToken.None));
        Assert.Equal(0, session.PointerReads);
        Assert.Equal(0, session.Revalidations);
    }

    [Fact]
    public async Task IdentityInvalidationStopsAndNeverEmitsStaleCoordinates()
    {
        var session = new FixtureSession(Identity, [Owner(1, 2, 3)]) { FailRevalidationAt = 2 };
        var result = await PositionCandidateSampler.SampleAsync(Profile, session, 3, 0, CancellationToken.None);
        Assert.Equal("failed", result.Status);
        var item = Assert.Single(result.Observations);
        Assert.Equal("identity-invalidated", item.Status);
        Assert.Null(item.X);
        Assert.Null(item.Y);
        Assert.Null(item.Z);
        Assert.Equal(1, session.TerminalReads);
    }

    [Fact]
    public async Task InvalidFloatAndMissingPointerFailClosed()
    {
        var nonFinite = new FixtureSession(Identity, [Owner(float.NaN, 2, 3)]);
        var bad = await PositionCandidateSampler.SampleAsync(Profile, nonFinite, 2, 0, CancellationToken.None);
        Assert.Equal("failed", bad.Status);
        Assert.Equal("invalid-value", Assert.Single(bad.Observations).Status);
        Assert.Null(bad.Observations[0].X);

        var missing = new FixtureSession(Identity, []) { FailPointerRead = true };
        var unreadable = await PositionCandidateSampler.SampleAsync(Profile, missing, 2, 0, CancellationToken.None);
        Assert.Equal("failed", unreadable.Status);
        Assert.Equal("read-failed", Assert.Single(unreadable.Observations).Status);
        Assert.Equal(0, missing.TerminalReads);
    }

    [Fact]
    public async Task ReadFailureAfterGoodSampleIsPartialWithoutReusingLastValue()
    {
        var session = new FixtureSession(Identity, [Owner(1, 2, 3)]) { FailAfterTerminalReads = 1 };
        var result = await PositionCandidateSampler.SampleAsync(Profile, session, 3, 0, CancellationToken.None);
        Assert.Equal("partial", result.Status);
        Assert.Equal(2, result.CompletedSamples);
        Assert.Equal(1f, result.Observations[0].X);
        Assert.Equal("read-failed", result.Observations[1].Status);
        Assert.Null(result.Observations[1].X);
    }

    [Fact]
    public async Task InvalidRecipeAndSchedulesAreRejected()
    {
        Assert.Throws<InvalidDataException>(() => (Profile with { ZOffset = 0x1000 }).Validate());
        Assert.Throws<InvalidDataException>(() => (Profile with { XOffset = Profile.YOffset }).Validate());
        Assert.Throws<InvalidDataException>(() => (Profile with { ExecutableSha256 = "bad" }).Validate());
        var session = new FixtureSession(Identity, [Owner(1, 2, 3)]);
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() =>
            PositionCandidateSampler.SampleAsync(Profile, session, 31, 0, CancellationToken.None));
        Assert.Equal(0, session.PointerReads);
    }

    [Fact]
    public async Task StrictProfileFileIsHashedAndUnknownOrDuplicateFieldsAreRejected()
    {
        var path = Path.Combine(Path.GetTempPath(), $"rr2-position-{Guid.NewGuid():N}.json");
        try
        {
            var source = new NativePositionProfileFile(1, "native-position-profile/1", "player.position.xyz",
                BuildSha, "0x32E0200", ["0x320", "0x324", "0x328"], "candidate-only", "docs/validation/example.md");
            var json = JsonSerializer.Serialize(source, JsonFormat.Options);
            await File.WriteAllTextAsync(path, json);
            var loaded = await NativePositionProfileLoader.LoadAsync(path);
            Assert.Equal(Profile, loaded.Profile);
            Assert.Equal(64, loaded.SourceSha256.Length);
            Assert.Equal("docs/validation/example.md", loaded.EvidenceReference);

            await File.WriteAllTextAsync(path, json.Replace("\"schemaVersion\": 1",
                "\"schemaVersion\": 1, \"unexpected\": true", StringComparison.Ordinal));
            await Assert.ThrowsAsync<JsonException>(() => NativePositionProfileLoader.LoadAsync(path));
            await File.WriteAllTextAsync(path, json.Replace("\"fieldId\": \"player.position.xyz\"",
                "\"fieldId\": \"player.position.xyz\", \"fieldId\": \"player.position.xyz\"",
                StringComparison.Ordinal));
            await Assert.ThrowsAsync<JsonException>(() => NativePositionProfileLoader.LoadAsync(path));
        }
        finally
        {
            if (File.Exists(path))
                File.Delete(path);
        }
    }

    private static byte[] Owner(float x, float y, float z)
    {
        var bytes = new byte[0x32C];
        BinaryPrimitives.WriteSingleLittleEndian(bytes.AsSpan(0x320), x);
        BinaryPrimitives.WriteSingleLittleEndian(bytes.AsSpan(0x324), y);
        BinaryPrimitives.WriteSingleLittleEndian(bytes.AsSpan(0x328), z);
        return bytes;
    }

    private sealed class FixtureSession(NativeProcessIdentity identity, IReadOnlyList<byte[]> ownerFrames)
        : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; } = identity;
        public int PointerReads { get; private set; }
        public int TerminalReads { get; private set; }
        public int Revalidations { get; private set; }
        public int? FailRevalidationAt { get; init; }
        public int? FailAfterTerminalReads { get; init; }
        public bool FailPointerRead { get; init; }

        public NativeReadResult Read(ulong address, int byteLength)
        {
            if (address == Identity.ModuleBaseAddress + Profile.RootRva && byteLength == 8)
            {
                PointerReads++;
                if (FailPointerRead)
                    return new("unavailable", [], 299, "Root unreadable.");
                var pointer = new byte[8];
                BinaryPrimitives.WriteUInt64LittleEndian(pointer, 0x400000);
                return new("success", pointer, null, null);
            }
            if (address == 0x400000 && byteLength == Profile.TerminalByteLength)
            {
                TerminalReads++;
                if (FailAfterTerminalReads is { } maximum && TerminalReads > maximum)
                    return new("unavailable", [], 299, "Owner unreadable.");
                var index = Math.Min(TerminalReads - 1, ownerFrames.Count - 1);
                return new("success", ownerFrames[index], null, null);
            }
            return new("unavailable", [], 299, "Unexpected address.");
        }

        public ValueTask<string?> RevalidateAsync(CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Revalidations++;
            return ValueTask.FromResult(FailRevalidationAt == Revalidations
                ? "Process epoch invalidated." : (string?)null);
        }

        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
