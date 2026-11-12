using System.Buffers.Binary;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildUnitPositionsTests
{
    private const ulong Module = 0x140000000, SystemAddress = 0x20000000, Manager = 0x20001000,
        Table = 0x20002000, Bucket = 0x20003000, SelfEntity = 0x20004000, SelfSlots = 0x20005000,
        SelfPosition = 0x20006000, TargetNode = 0x20007000, TargetEntity = 0x20008000,
        TargetSlots = 0x20009000, TargetPosition = 0x2000A000;

    [Fact]
    public void ReadsBoundedTypedPositionsWithLosslessKeysAndDistance()
    {
        var value = CurrentBuildUnitPositionsCandidateReader.Read(new Fake());
        Assert.Equal(2, value.Examined);
        Assert.Equal(0, value.Unavailable);
        Assert.Equal(0, value.NoPosition);
        Assert.Equal("42", value.SelfKey);
        var target = Assert.Single(value.Rows, row => row.UnitKey == ulong.MaxValue.ToString());
        Assert.Equal("uFFFFFFFFFFFFFFFF", target.UnitIdCandidate);
        Assert.Equal(5, target.HorizontalDistanceCandidate);
        Assert.Equal(new CurrentBuildXyz(103, 20, 204), target.PositionCandidate);
        Assert.False(value.CameraStableCandidate);
        Assert.InRange(value.ReadBytes, 1, 2 * 1024 * 1024);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    public void WrongTypeOwnerOrChangedRowWithholdsOnlyThatUnit(int fault)
    {
        var session = new Fake { ChangeTargetPosition = fault == 2, ChangeTargetNode = fault == 3 };
        if (fault == 0) BinaryPrimitives.WriteUInt64LittleEndian(session.Memory[TargetPosition], 0);
        if (fault == 1) BinaryPrimitives.WriteUInt64LittleEndian(session.Memory[TargetPosition].AsSpan(0x10), SelfEntity);
        var value = CurrentBuildUnitPositionsCandidateReader.Read(session);
        Assert.Equal(2, value.Examined);
        Assert.Equal(1, value.Unavailable);
        Assert.Equal("42", Assert.Single(value.Rows).UnitKey);
    }

    [Fact]
    public void AbsentComponentAndLimitAreExplicit()
    {
        var session = new Fake();
        session.Memory[TargetEntity][0x18] = 0xFF;
        var value = CurrentBuildUnitPositionsCandidateReader.Read(session);
        Assert.Equal(1, value.NoPosition);
        Assert.Single(value.Rows);
        value = CurrentBuildUnitPositionsCandidateReader.Read(new Fake(), 1);
        Assert.Equal(1, value.Examined);
        Assert.True(value.UnitLimitReached);
        Assert.Single(value.Rows);
    }

    [Fact]
    public void CyclicChainsStayBoundedAndAreReported()
    {
        var session = new Fake();
        BinaryPrimitives.WriteUInt64LittleEndian(session.Memory[TargetNode], TargetNode);
        var value = CurrentBuildUnitPositionsCandidateReader.Read(session);
        Assert.Equal(1, value.UnavailableChains);
        Assert.Equal(2, value.Examined);
        Assert.InRange(session.Reads, 1, 200);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void ChangedGlobalRootOrSelfPositionRejectsWholeScan(bool selfMoved)
    {
        var session = new Fake { ChangeGlobalAfterTarget = !selfMoved, MoveSelfAfterTarget = selfMoved };
        Assert.Throws<InvalidDataException>(() => CurrentBuildUnitPositionsCandidateReader.Read(session));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("changed")]
    public async Task CommandPublishesOnlyAfterRevalidationAndReleasesSessionBeforeLease(string? error)
    {
        var path = Path.Combine(Path.GetTempPath(), "rr2-unit-positions-" + Guid.NewGuid().ToString("N") + ".json");
        try
        {
            var session = new Fake { RevalidationError = error };
            var released = false;
            var options = new Dictionary<string, string> { ["--pid"] = "123", ["--start-ticks"] = "456", ["--output"] = path };
            var run = CurrentBuildUnitPositionsSampleCommand.RunAsync(options, new StringWriter(), CancellationToken.None,
                (_, _, _) => Task.FromResult<IAsyncDisposable>(new Lease(() => { Assert.True(session.Disposed); released = true; })),
                (_, _, _) => Task.FromResult<IReadOnlyNativeMemorySession>(session), CurrentBuildUnitPositionsCandidateReader.Read);
            if (error is not null)
            {
                await Assert.ThrowsAsync<InvalidDataException>(() => run);
                Assert.False(File.Exists(path));
            }
            else
            {
                Assert.Equal(0, await run);
                using var report = JsonDocument.Parse(await File.ReadAllTextAsync(path));
                Assert.Equal("18446744073709551615", report.RootElement.GetProperty("observation")
                    .GetProperty("rows")[1].GetProperty("unitKey").GetString());
            }
            Assert.True(released);
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    private sealed class Lease(Action release) : IAsyncDisposable
    {
        public ValueTask DisposeAsync() { release(); return ValueTask.CompletedTask; }
    }

    private sealed class Fake : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; } = new(123, 456, "rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256, Module, 64 * 1024 * 1024);
        public Dictionary<ulong, byte[]> Memory { get; } = [];
        public bool ChangeTargetPosition { get; init; }
        public bool ChangeTargetNode { get; init; }
        public bool ChangeGlobalAfterTarget { get; init; }
        public bool MoveSelfAfterTarget { get; init; }
        public string? RevalidationError { get; init; }
        public bool Disposed { get; private set; }
        public int Reads { get; private set; }
        private bool readTarget;
        private int targetNodeReads;
        public Fake()
        {
            Memory[Module + 0x33623E0] = Q(SystemAddress);
            Memory[SystemAddress + 0x360] = Q(42);
            Memory[Module + 0x33624A8] = Q(Manager);
            Memory[Manager + 0x50] = Q(Table);
            Memory[Table] = Q(Bucket).Concat(Q(24)).Concat(Q(1)).ToArray();
            Memory[Module + 0x2F588A0] = BitConverter.GetBytes(0);
            Memory[Bucket] = Q(TargetNode).Concat(Q(42)).Concat(Q(SelfEntity)).ToArray();
            Memory[TargetNode] = Q(0).Concat(Q(ulong.MaxValue)).Concat(Q(TargetEntity)).ToArray();
            Entity(SelfEntity, SelfSlots, SelfPosition, 100, 200);
            Entity(TargetEntity, TargetSlots, TargetPosition, 103, 204);
        }
        private void Entity(ulong entity, ulong slots, ulong position, float x, float z)
        {
            var bytes = new byte[128];
            Q(slots).CopyTo(bytes, 0x78);
            Memory[entity] = bytes;
            Memory[slots] = Q(position);
            bytes = new byte[0x110];
            Q(Module + 0x26B4FB0).CopyTo(bytes, 0);
            Q(entity).CopyTo(bytes, 0x10);
            BinaryPrimitives.WriteSingleLittleEndian(bytes.AsSpan(0x48), x);
            BinaryPrimitives.WriteSingleLittleEndian(bytes.AsSpan(0x4C), 20);
            BinaryPrimitives.WriteSingleLittleEndian(bytes.AsSpan(0x50), z);
            Memory[position] = bytes;
        }
        public NativeReadResult Read(ulong address, int length)
        {
            Reads++;
            if (address == TargetPosition && length == 0x110)
            {
                readTarget = true;
                if (MoveSelfAfterTarget) BinaryPrimitives.WriteSingleLittleEndian(Memory[SelfPosition].AsSpan(0x48), 101);
            }
            if (ChangeGlobalAfterTarget && readTarget && address == Manager + 0x50)
                return new("success", Q(Table + 8), null, null);
            var pair = Memory.FirstOrDefault(row => address >= row.Key && address + (ulong)length <= row.Key + (ulong)row.Value.Length);
            if (pair.Value is null) return new("unavailable", [], null, "hole");
            var result = pair.Value.AsSpan((int)(address - pair.Key), length).ToArray();
            if (ChangeTargetPosition && address == TargetPosition + 0x48 && length == 12) result[0] ^= 1;
            if (ChangeTargetNode && address == TargetNode && ++targetNodeReads > 1) result[16] ^= 8;
            return new("success", result, null, null);
        }
        private static byte[] Q(ulong value) { var bytes = new byte[8]; BinaryPrimitives.WriteUInt64LittleEndian(bytes, value); return bytes; }
        public ValueTask<string?> RevalidateAsync(CancellationToken ct) => ValueTask.FromResult(RevalidationError);
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
