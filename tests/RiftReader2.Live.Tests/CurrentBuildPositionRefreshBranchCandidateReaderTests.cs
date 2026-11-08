using System.Buffers.Binary;
using System.Text.Json;
using RiftReader2.Infrastructure;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildPositionRefreshBranchCandidateReaderTests
{
    const ulong Module = 0x140000000, Entity = 0x20010000, Position = 0x20020000, Source = 0x20030000;
    const ulong Selector = Module + CurrentBuildPositionRefreshBranchCandidateReader.SourceSelectorRva;

    [Fact] public void BothGuardsZeroAreIneligibleWithoutInvokingSource()
    {
        var s = Fixture(0, 0, 7);
        var result = Read(s, () => throw new Exception("must not resolve"));
        Assert.Equal("guard-ineligible-candidate", result.Status);
        Assert.Null(result.SourceSelector);
        Assert.Null(result.SourceComponent);
    }

    [Fact] public void NonzeroHandleNeverUsesSelfLookup()
    {
        var s = Fixture(123, 1, 7);
        var result = Read(s, () => throw new Exception("wrong entity"));
        Assert.Equal("handle-branch-referenced-entity-unavailable", result.Status);
        Assert.Equal(123UL, result.ReferencedHandle);
        Assert.Null(result.SourceComponent);
    }

    [Fact] public void UnusedFlagAndSelectorAreNotRequired()
    {
        var active = Fixture(123, 1, 7);
        active.Remove(Position + 0x108, 1); active.Remove(Selector, 4);
        var handle = Read(active, () => throw new Exception("must not resolve self"));
        Assert.Equal("handle-branch-referenced-entity-unavailable", handle.Status);
        Assert.Null(handle.Flag); Assert.Null(handle.SourceSelector);
        var inactive = Fixture(0, 0, 7); inactive.Remove(Selector, 4);
        var result = Read(inactive, () => throw new Exception("must not resolve"));
        Assert.Equal("guard-ineligible-candidate", result.Status);
        Assert.Null(result.SourceSelector);
    }

    [Fact] public void PlayerKeyJsonIsLosslessForUint64()
    {
        var s = Fixture(0, 0, 7);
        const ulong key = 9223372036854775850UL;
        var result = CurrentBuildPositionRefreshBranchCandidateReader.ReadResolved(s, s.Identity,
            DateTimeOffset.UtcNow, key, Entity, Position, () => { }, () => Source);
        using var json = JsonDocument.Parse(JsonSerializer.Serialize(result, JsonFormat.Options));
        var root = json.RootElement;
        Assert.False(root.TryGetProperty("playerKey", out _));
        Assert.Equal("9223372036854775850", root.GetProperty("playerKeyDecimal").GetString());
        Assert.Equal("u800000000000002A", root.GetProperty("playerUnitIdCandidate").GetString());
        Assert.Contains("lose precision", root.GetProperty("qualification").GetString());
    }

    [Fact] public void FlagBranchReportsSelfSourceCandidateOnly()
    {
        var s = Fixture(0, 1, 7);
        var result = Read(s, () => Source);
        Assert.Equal("flag-branch-self-source-present-candidate", result.Status);
        Assert.Equal(Source, result.SourceComponent);
        Assert.Contains("execution", result.Qualification);
        Assert.Contains("freshness unverified", result.Qualification);
    }

    [Theory]
    [InlineData(-1)]
    [InlineData(int.MinValue)]
    [InlineData(96)]
    public void SignedInvalidSelectorIsUnavailable(int selector)
    {
        var result = Read(Fixture(0, 1, selector), () => throw new Exception("invalid selector"));
        Assert.Equal(selector, result.SourceSelector);
        Assert.Equal("flag-branch-selector-unavailable", result.Status);
        Assert.Null(result.SourceComponent);
    }

    [Fact] public void MissingSourceAndGuardNeverBecomeZero()
    {
        var result = Read(Fixture(0, 1, 7), () => throw new InvalidDataException("unavailable"));
        Assert.Equal("flag-branch-self-source-unavailable", result.Status);
        Assert.Null(result.SourceComponent);
        var s = Fixture(0, 1, 7); s.Remove(Position + 0x100, 8);
        result = Read(s, () => throw new Exception("guard missing"));
        Assert.Equal("unavailable", result.Status);
        Assert.Null(result.ReferencedHandle);
    }

    [Fact] public void WrongOwnerDoesNotResolveSource()
    {
        var s = Fixture(0, 1, 7); s.Q(Position + 0x10, Entity + 0x1000);
        var result = Read(s, () => throw new Exception("wrong owner"));
        Assert.Equal("position-owner-mismatch", result.Status);
        Assert.Null(result.SourceComponent);
    }

    [Theory]
    [InlineData(Position + 0x10, 8)]
    [InlineData(Position + 0x100, 8)]
    [InlineData(Position + 0x108, 1)]
    [InlineData(Selector, 4)]
    public void ChangedAnchorRejectsObservation(ulong address, int length)
    {
        var s = Fixture(0, 1, 7); s.Changed = (address, length);
        Assert.Throws<InvalidDataException>(() => Read(s, () => Source));
    }

    [Fact] public void OwnerVerificationFailureRejectsObservation()
    {
        var s = Fixture(0, 1, 7);
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionRefreshBranchCandidateReader.ReadResolved(
            s, s.Identity, DateTimeOffset.UtcNow, 1, Entity, Position,
            () => throw new InvalidDataException("owner changed"), () => Source));
    }

    static PositionRefreshBranchCandidate Read(Fake s, Func<ulong> resolve) =>
        CurrentBuildPositionRefreshBranchCandidateReader.ReadResolved(s, s.Identity, DateTimeOffset.UtcNow,
            1, Entity, Position, () => { }, resolve);

    static Fake Fixture(ulong handle, byte flag, int selector)
    {
        var s = new Fake();
        s.Q(Position + 0x10, Entity); s.Q(Position + 0x100, handle);
        s.Put(Position + 0x108, [flag]);
        var bytes = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(bytes, selector);
        s.Put(Selector, bytes); return s;
    }

    sealed class Fake : IReadOnlyNativeMemorySession
    {
        readonly Dictionary<(ulong, int), byte[]> data = [];
        readonly Dictionary<(ulong, int), int> reads = [];
        public (ulong, int)? Changed { get; set; }
        public NativeProcessIdentity Identity { get; } =
            new(123, 456, "rift_x64.exe", CurrentBuildPlayerLookup.GameSha256, Module, 64 * 1024 * 1024);
        public void Put(ulong address, byte[] bytes) => data[(address, bytes.Length)] = bytes.ToArray();
        public void Q(ulong address, ulong value)
        { var bytes = new byte[8]; BinaryPrimitives.WriteUInt64LittleEndian(bytes, value); Put(address, bytes); }
        public void Remove(ulong address, int count) => data.Remove((address, count));
        public NativeReadResult Read(ulong address, int count)
        {
            var key = (address, count); var seen = reads.GetValueOrDefault(key); reads[key] = seen + 1;
            if (!data.TryGetValue(key, out var bytes)) return new("unavailable", [], null, "missing");
            var copy = bytes.ToArray(); if (Changed == key && seen > 0) copy[0] ^= 1;
            return new("success", copy, null, null);
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken _) => ValueTask.FromResult<string?>(null);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
