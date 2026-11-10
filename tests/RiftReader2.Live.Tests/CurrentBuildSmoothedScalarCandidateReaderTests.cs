using System.Buffers.Binary;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using RiftReader2.Live;
using RiftReader2.Live.Control;

namespace RiftReader2.Tests;

public sealed class CurrentBuildSmoothedScalarCandidateReaderTests
{
    private static readonly NativeProcessIdentity Identity = new(
        123, 639298670575905950, @"C:\RIFT\rift_x64.exe",
        CurrentBuildPlayerLookup.GameSha256, 0x140000000, 0x4000000);
    private const ulong Entity = 0x200000;
    private const ulong Component = 0x400000;

    [Fact]
    public void ReadsFourExactBitsAfterVtableAndOwnerGateAndBracketsPayload()
    {
        var source = Source();
        var verified = 0;
        var result = CurrentBuildSmoothedScalarCandidateReader.ReadResolved(
            source, Identity, DateTimeOffset.UtcNow, 0x1234, Entity, Component,
            () => verified++);
        Assert.Equal(1, verified);
        Assert.Equal(new[] { 0.5f, 1.5f, 2.5f, 0.25f },
            new[] { result.CurrentCandidate, result.SourceCandidate,
                result.TargetCandidate, result.FactorCandidate });
        Assert.Equal(4, result.RawBits.Length);
        Assert.Equal(2, source.ReadCount(Component + 0x88, 16));
        Assert.Equal(2, source.ReadCount(Component + 0x10, 8));
        using var document = JsonDocument.Parse(JsonSerializer.Serialize(result, JsonFormat.Options));
        var root = document.RootElement;
        Assert.False(root.GetProperty("headingQualified").GetBoolean());
        Assert.Contains("unverified", root.GetProperty("qualification").GetString());
        Assert.False(root.TryGetProperty("playerEntity", out _));
        Assert.Equal("4194304", root.GetProperty("componentAddressDecimal").GetString());
    }

    [Fact]
    public void WrongVtableOrBacklinkRejectsBeforeReadingScalar()
    {
        var wrongVtable = Source(vtableRva: 0x26B4FB0);
        Assert.Throws<InvalidDataException>(() => Read(wrongVtable));
        Assert.Equal(0, wrongVtable.ReadCount(Component + 0x88, 16));
        var wrongOwner = Source(owner: 0x300000);
        Assert.Throws<InvalidDataException>(() => Read(wrongOwner));
        Assert.Equal(0, wrongOwner.ReadCount(Component + 0x88, 16));
    }

    [Fact]
    public void NonfiniteOrChangingValueOrOwnerFailsClosed()
    {
        var nan = Source(nonfinite: true);
        Assert.Throws<InvalidDataException>(() => Read(nan));
        var changed = Source(mutateScalar: true);
        Assert.Throws<InvalidDataException>(() => Read(changed));
        var owner = Source();
        Assert.Throws<InvalidDataException>(() =>
            CurrentBuildSmoothedScalarCandidateReader.ReadResolved(owner, Identity,
                DateTimeOffset.UtcNow, 1, Entity, Component,
                () => throw new InvalidDataException("ownership changed")));
    }

    [Fact]
    public void WrongExactBuildRefusesReads()
    {
        var source = Source();
        Assert.Throws<InvalidDataException>(() =>
            CurrentBuildSmoothedScalarCandidateReader.ReadResolved(source,
                Identity with { ExecutableSha256 = new string('F', 64) },
                DateTimeOffset.UtcNow, 1, Entity, Component, () => { }));
        Assert.Equal(0, source.TotalReads);
    }

    private static CurrentBuildSmoothedScalarCandidate Read(Fake source) =>
        CurrentBuildSmoothedScalarCandidateReader.ReadResolved(source, Identity,
            DateTimeOffset.UtcNow, 1, Entity, Component, () => { });

    private static Fake Source(ulong vtableRva = 0x26AFBA0,
        ulong owner = Entity, bool nonfinite = false, bool mutateScalar = false)
    {
        var vtableBytes = new byte[8];
        BinaryPrimitives.WriteUInt64LittleEndian(vtableBytes, Identity.ModuleBaseAddress + vtableRva);
        var ownerBytes = new byte[8];
        BinaryPrimitives.WriteUInt64LittleEndian(ownerBytes, owner);
        var scalarBytes = new byte[16];
        var values = new[] { 0.5f, 1.5f, 2.5f, nonfinite ? float.NaN : 0.25f };
        for (var i = 0; i < 4; i++)
            BinaryPrimitives.WriteSingleLittleEndian(scalarBytes.AsSpan(i * 4), values[i]);
        return new(new Dictionary<(ulong, int), byte[]>
        {
            [(Component, 8)] = vtableBytes,
            [(Component + 0x10, 8)] = ownerBytes,
            [(Component + 0x88, 16)] = scalarBytes
        }) { MutateScalar = mutateScalar };
    }

    private sealed class Fake(Dictionary<(ulong, int), byte[]> blocks) : IReadOnlyNativeMemorySession
    {
        private readonly Dictionary<(ulong, int), int> counts = [];
        public NativeProcessIdentity Identity => CurrentBuildSmoothedScalarCandidateReaderTests.Identity;
        public bool MutateScalar { get; init; }
        public int TotalReads { get; private set; }
        public int ReadCount(ulong address, int length) => counts.GetValueOrDefault((address, length));
        public NativeReadResult Read(ulong address, int length)
        {
            TotalReads++;
            var key = (address, length);
            counts[key] = ReadCount(address, length) + 1;
            if (!blocks.TryGetValue(key, out var bytes))
                return new("unavailable", [], 299, "missing");
            var copy = bytes.ToArray();
            if (MutateScalar && key == (Component + 0x88, 16) && counts[key] == 2)
                copy[0] ^= 1;
            return new("success", copy, null, null);
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken token) =>
            ValueTask.FromResult((string?)null);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
