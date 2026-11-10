using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Live;

namespace RiftReader2.Tests;

public sealed class CurrentBuildActorPoseCandidateReaderTests
{
    private static readonly NativeProcessIdentity Identity = new(
        6228, 639298670575905950, @"C:\RIFT\rift_x64.exe",
        CurrentBuildPlayerLookup.GameSha256, 0x140000000, 0x4000000);
    private const ulong PlayerEntity = 0x200000;
    private const ulong Actor = 0x400000;
    private const ulong Position = 0x300000;
    private const ulong Renderer = 0x500000;
    private static readonly float[] IdentityMatrix = [1, 0, 0, 0, 1, 0, 0, 0, 1];
    private static readonly float[] QuarterTurnY = [0, 0, -1, 0, 1, 0, 1, 0, 0];

    [Fact]
    public void ReadsOwnedMatricesAndNormalRendererWithMatchingComposition()
    {
        var source = Source(0, Renderer);
        var verified = 0;
        var result = CurrentBuildActorPoseCandidateReader.ReadResolved(source, Identity,
            DateTimeOffset.UtcNow.AddSeconds(-1), 0x1234, PlayerEntity, Actor, Position, () => verified++);
        Assert.Equal(1, verified);
        Assert.Equal("normal-render-matrix-candidate", result.RenderStatus);
        Assert.True(result.NormalRenderBranch);
        Assert.False(result.ActorHeadingQualified);
        Assert.Equal(9, result.ActorMatrix.RawBits.Length);
        Assert.Equal(90, result.ActorMatrix.PlanarAngleDegreesCandidate!.Value, 6);
        Assert.Equal(0, result.RenderCompositionMaxAbsDelta!.Value, 8);
        Assert.Equal("structural-y-planar-matrix-candidate", result.RenderMatrix!.Status);
        Assert.Contains("candidate-only", result.Qualification);
        Assert.Equal("4660", result.PlayerKeyDecimal);
        Assert.True(source.ReadCount(Renderer + 0xA0, 0x30) >= 2);
    }

    [Fact]
    public void AlternateBranchDoesNotFollowRenderPointer()
    {
        var source = Source(1, Renderer, includeRenderer: false);
        var result = CurrentBuildActorPoseCandidateReader.ReadResolved(source, Identity,
            DateTimeOffset.UtcNow, 1, PlayerEntity, Actor, Position, () => { });
        Assert.False(result.NormalRenderBranch);
        Assert.Null(result.RenderMatrix);
        Assert.Null(result.RenderCompositionMaxAbsDelta);
        Assert.Equal("alternate-reference-branch-not-followed", result.RenderStatus);
        Assert.Equal(0, source.ReadCount(Actor + 0x410, 8));
        Assert.Equal(0, source.ReadCount(Renderer + 0xA0, 0x30));
    }

    [Fact]
    public void NormalBranchWithNoRendererRetainsActorCandidate()
    {
        var source = Source(0, 0, includeRenderer: false);
        var result = CurrentBuildActorPoseCandidateReader.ReadResolved(source, Identity,
            DateTimeOffset.UtcNow, 1, PlayerEntity, Actor, Position, () => { });
        Assert.Equal("normal-render-pointer-absent", result.RenderStatus);
        Assert.NotNull(result.ActorMatrix.RowMajorF32);
        Assert.Null(result.RenderMatrix);
    }

    [Fact]
    public void WrongBuildAndAliasedComponentsFailBeforeReading()
    {
        var source = Source(0, Renderer);
        Assert.Throws<InvalidDataException>(() => CurrentBuildActorPoseCandidateReader.ReadResolved(
            source, Identity with { ExecutableSha256 = new string('F', 64) },
            DateTimeOffset.UtcNow, 1, PlayerEntity, Actor, Position, () => { }));
        Assert.Equal(0, source.Reads);
        Assert.Throws<InvalidDataException>(() => CurrentBuildActorPoseCandidateReader.ReadResolved(
            source, Identity, DateTimeOffset.UtcNow, 1, PlayerEntity, Actor, Actor, () => { }));
        Assert.Equal(0, source.Reads);
    }

    [Fact]
    public void ChangedOwnerOrPayloadRefusesPublication()
    {
        var source = Source(0, Renderer);
        Assert.Throws<InvalidDataException>(() => CurrentBuildActorPoseCandidateReader.ReadResolved(
            source, Identity, DateTimeOffset.UtcNow, 1, PlayerEntity, Actor, Position,
            () => throw new InvalidDataException("owner changed")));
        var changed = Source(0, Renderer, mutateActorOnSecondRead: true);
        Assert.Throws<InvalidDataException>(() => CurrentBuildActorPoseCandidateReader.ReadResolved(
            changed, Identity, DateTimeOffset.UtcNow, 1, PlayerEntity, Actor, Position, () => { }));
    }

    private static FakeSession Source(uint flags, ulong render, bool includeRenderer = true,
        bool mutateActorOnSecondRead = false)
    {
        var blocks = new Dictionary<(ulong, int), byte[]>
        {
            [(Actor + 0x1C0, 4)] = new byte[4],
            [(Actor + 0x398, 0x30)] = Floats(QuarterTurnY, 0x30),
            [(Actor + 0x3EC, 0x24)] = Floats(IdentityMatrix, 0x24),
            [(Actor + 0x410, 8)] = new byte[8]
        };
        BinaryPrimitives.WriteUInt32LittleEndian(blocks[(Actor + 0x1C0, 4)], flags);
        BinaryPrimitives.WriteUInt64LittleEndian(blocks[(Actor + 0x410, 8)], render);
        if (includeRenderer)
            blocks[(Renderer + 0xA0, 0x30)] = Floats(QuarterTurnY, 0x30);
        return new(Identity, blocks) { MutateActorOnSecondRead = mutateActorOnSecondRead };
    }

    private static byte[] Floats(IReadOnlyList<float> values, int length)
    {
        var bytes = new byte[length];
        for (var i = 0; i < values.Count; i++)
            BinaryPrimitives.WriteSingleLittleEndian(bytes.AsSpan(i * 4), values[i]);
        return bytes;
    }

    private sealed class FakeSession(NativeProcessIdentity identity,
        Dictionary<(ulong, int), byte[]> blocks) : IReadOnlyNativeMemorySession
    {
        private readonly Dictionary<(ulong, int), int> counts = [];
        public NativeProcessIdentity Identity { get; } = identity;
        public bool MutateActorOnSecondRead { get; init; }
        public int Reads { get; private set; }
        public int ReadCount(ulong address, int size) =>
            counts.GetValueOrDefault((address, size));

        public NativeReadResult Read(ulong address, int byteLength)
        {
            Reads++;
            var key = (address, byteLength);
            counts[key] = counts.GetValueOrDefault(key) + 1;
            if (!blocks.TryGetValue(key, out var bytes))
                return new("unavailable", [], 299, "Unknown fixture range.");
            var copy = bytes.ToArray();
            if (MutateActorOnSecondRead && key == (Actor + 0x398, 0x30) && counts[key] == 2)
                copy[0] ^= 1;
            return new("success", copy, null, null);
        }

        public ValueTask<string?> RevalidateAsync(CancellationToken cancellationToken) =>
            ValueTask.FromResult((string?)null);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
