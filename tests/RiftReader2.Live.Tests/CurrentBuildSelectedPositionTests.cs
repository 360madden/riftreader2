using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildSelectedPositionTests
{
    private const ulong Module = 0x140000000, System = 0x20000000, Manager = 0x20001000,
        Table = 0x20002000, Bucket = 0x20003000, SelfEntity = 0x20004000,
        SelfSlots = 0x20005000, Health = 0x20006000, Owner = 0x20007000,
        TargetEntity = 0x20008000, TargetSlots = 0x20009000, TargetPosition = 0x2000A000,
        TargetNode = 0x2000B000, Selection = 0x2000C000;

    [Fact]
    public void UpdatedBuildReturnsFallbackTargetPositionWithExactOwner()
    {
        var value = CurrentBuildSelectedPositionCandidateReader.Read(new Fake());
        Assert.Equal("42", value.SelfKey);
        Assert.Equal("43", value.RawFallbackKey);
        Assert.Equal("43", value.TargetKey);
        Assert.Equal("u000000000000002B", value.TargetUnitIdCandidate);
        Assert.Equal("presence-component-fallback", value.SelectionBranch);
        Assert.Equal("position-candidate", value.Status);
        Assert.Equal(new CurrentBuildXyz(123, 20, 345), value.TargetPositionCandidate);
        Assert.Equal(3, value.TargetPositionRawBits!.Length);
    }

    [Fact]
    public void ZeroFallbackReportsNoTargetRatherThanInventingPosition()
    {
        var source = new Fake();
        BinaryPrimitives.WriteUInt64LittleEndian(source.Memory[Owner].AsSpan(0x20), 0);
        var value = CurrentBuildSelectedPositionCandidateReader.Read(source);
        Assert.Equal("no-target", value.Status);
        Assert.Equal("0", value.RawFallbackKey);
        Assert.Null(value.TargetKey);
        Assert.Null(value.TargetPositionCandidate);
    }

    [Fact]
    public void ActiveOverrideNeverPromotesRawFallbackToSelectedTarget()
    {
        var source = new Fake();
        // Presence gate absent; selection component is present and has an active child.
        source.Memory[SelfEntity][0x1A] = 0xFF;
        source.Memory[SelfEntity][0x1B] = 2;
        BinaryPrimitives.WriteUInt64LittleEndian(source.Memory[SelfSlots].AsSpan(16), Selection);
        var selection = new byte[0x2B0];
        BinaryPrimitives.WriteUInt64LittleEndian(selection.AsSpan(0x280), 0x2000D000);
        source.Memory[Selection] = selection;
        var value = CurrentBuildSelectedPositionCandidateReader.Read(source);
        Assert.Equal("selection-override-unresolved", value.Status);
        Assert.Equal("selection-override-active", value.SelectionBranch);
        Assert.Equal("43", value.RawFallbackKey);
        Assert.Null(value.TargetKey);
        Assert.Null(value.TargetPositionCandidate);
    }

    [Fact]
    public void WrongOwnerTypeOrChangedFallbackRejectsObservation()
    {
        var badType = new Fake();
        BinaryPrimitives.WriteUInt64LittleEndian(badType.Memory[Owner], 0);
        Assert.Throws<InvalidDataException>(() => CurrentBuildSelectedPositionCandidateReader.Read(badType));
        var changedKey = new Fake { ChangeFallbackAfterPosition = true };
        Assert.Throws<InvalidDataException>(() => CurrentBuildSelectedPositionCandidateReader.Read(changedKey));
    }

    [Fact]
    public async Task BurstRetainsOrderedSamplesWithStablePlayerAndChangingTarget()
    {
        var first = CurrentBuildSelectedPositionCandidateReader.Read(new Fake());
        var second = first with
        {
            StartedAtUtc = first.CompletedAtUtc.AddMilliseconds(1),
            CompletedAtUtc = first.CompletedAtUtc.AddMilliseconds(3),
            Status = "no-target",
            RawFallbackKey = "0",
            TargetKey = null,
            TargetUnitIdCandidate = null,
            TargetEntityDecimal = null,
            TargetPositionCandidate = null,
            TargetPositionRawBits = null
        };
        var queue = new Queue<CurrentBuildSelectedPositionObservation>([first, second]);
        var path = Path.Combine(Path.GetTempPath(), Guid.NewGuid() + "-target-burst.json");
        var options = new Dictionary<string, string>
        {
            ["--pid"] = "123",
            ["--start-ticks"] = "456",
            ["--sha256"] = CurrentBuildPlayerLookup.UpdatedGameSha256,
            ["--output"] = path,
            ["--samples"] = "2",
            ["--interval-ms"] = "0"
        };
        try
        {
            var code = await CurrentBuildSelectedPositionSampleCommand.RunAsync(
                options, new StringWriter(), CancellationToken.None,
                (_, _, _) => Task.FromResult<IAsyncDisposable>(new NoOpLease()),
                (_, _, _) => Task.FromResult<IReadOnlyNativeMemorySession>(new Fake()),
                _ => queue.Dequeue());
            Assert.Equal(0, code);
            using var json = global::System.Text.Json.JsonDocument.Parse(File.ReadAllText(path));
            var root = json.RootElement;
            Assert.Equal("native-current-selected-position-candidate-burst/1",
                root.GetProperty("contractVersion").GetString());
            Assert.Equal(2, root.GetProperty("requestedSamples").GetInt32());
            Assert.Equal(2, root.GetProperty("completedSamples").GetInt32());
            Assert.Equal("position-candidate", root.GetProperty("observations")[0]
                .GetProperty("status").GetString());
            Assert.Equal("no-target", root.GetProperty("observations")[1]
                .GetProperty("status").GetString());
            Assert.Equal("no-target", root.GetProperty("observation")
                .GetProperty("status").GetString());
            Assert.Empty(queue);
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Fact]
    public async Task BurstRejectsChangedSelfWithoutPublishingFile()
    {
        var first = CurrentBuildSelectedPositionCandidateReader.Read(new Fake());
        var second = first with
        {
            StartedAtUtc = first.CompletedAtUtc.AddMilliseconds(1),
            CompletedAtUtc = first.CompletedAtUtc.AddMilliseconds(2),
            SelfKey = "99"
        };
        var queue = new Queue<CurrentBuildSelectedPositionObservation>([first, second]);
        var path = Path.Combine(Path.GetTempPath(), Guid.NewGuid() + "-target-burst.json");
        var options = new Dictionary<string, string>
        {
            ["--pid"] = "123",
            ["--start-ticks"] = "456",
            ["--sha256"] = CurrentBuildPlayerLookup.UpdatedGameSha256,
            ["--output"] = path,
            ["--samples"] = "2",
            ["--interval-ms"] = "0"
        };
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            CurrentBuildSelectedPositionSampleCommand.RunAsync(
                options, new StringWriter(), CancellationToken.None,
                (_, _, _) => Task.FromResult<IAsyncDisposable>(new NoOpLease()),
                (_, _, _) => Task.FromResult<IReadOnlyNativeMemorySession>(new Fake()),
                _ => queue.Dequeue()));
        Assert.False(File.Exists(path));
    }

    private sealed class NoOpLease : IAsyncDisposable
    {
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }

    private sealed class Fake : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; } = new(123, 456, "rift_x64.exe",
            CurrentBuildPlayerLookup.UpdatedGameSha256, Module, 64 * 1024 * 1024);
        public Dictionary<ulong, byte[]> Memory { get; } = [];
        public bool ChangeFallbackAfterPosition { get; init; }
        private bool changed;

        public Fake()
        {
            Memory[Module + 0x3373BA0] = Q(System);
            Memory[System + 0x360] = Q(42);
            Memory[Module + 0x3373C68] = Q(Manager);
            Memory[Manager + 0x50] = Q(Table);
            Memory[Table] = Q(Bucket).Concat(Q(24)).Concat(Q(1)).ToArray();
            Memory[Bucket] = Q(TargetNode).Concat(Q(42)).Concat(Q(SelfEntity)).ToArray();
            Memory[TargetNode] = Q(0).Concat(Q(43)).Concat(Q(TargetEntity)).ToArray();
            Memory[Module + 0x2F68850] = BitConverter.GetBytes(0);
            Memory[Module + 0x2F698A0] = BitConverter.GetBytes(1);
            Memory[Module + 0x2F692E0] = BitConverter.GetBytes(2);
            Memory[Module + 0x2F68260] = BitConverter.GetBytes(3);
            Memory[Module + 0x2933258] = Q(Module + 0x19D2020);
            var entity = new byte[128];
            entity[0x18] = 0;
            entity[0x19] = 0xFF;
            entity[0x1A] = 0;
            entity[0x1B] = 0xFF;
            Q(SelfSlots).CopyTo(entity, 0x78);
            Memory[SelfEntity] = entity;
            var slots = new byte[32];
            Q(Health).CopyTo(slots, 0);
            Memory[SelfSlots] = slots;
            var health = new byte[0x328];
            Q(SelfEntity).CopyTo(health, 0x10);
            Q(Owner).CopyTo(health, 0x40);
            Memory[Health] = health;
            var owner = new byte[0x28];
            Q(Module + 0x2933218).CopyTo(owner, 0);
            Q(43).CopyTo(owner, 0x20);
            Memory[Owner] = owner;
            entity = new byte[128];
            entity[0x19] = 0;
            Q(TargetSlots).CopyTo(entity, 0x78);
            Memory[TargetEntity] = entity;
            Memory[TargetSlots] = Q(TargetPosition);
            var position = new byte[0x110];
            Q(Module + 0x26C35C0).CopyTo(position, 0);
            Q(TargetEntity).CopyTo(position, 0x10);
            BinaryPrimitives.WriteSingleLittleEndian(position.AsSpan(0x48), 123);
            BinaryPrimitives.WriteSingleLittleEndian(position.AsSpan(0x4C), 20);
            BinaryPrimitives.WriteSingleLittleEndian(position.AsSpan(0x50), 345);
            Memory[TargetPosition] = position;
        }

        public NativeReadResult Read(ulong address, int length)
        {
            var pair = Memory.FirstOrDefault(row => address >= row.Key &&
                address + (ulong)length <= row.Key + (ulong)row.Value.Length);
            if (pair.Value is null) return new("unavailable", [], null, "hole");
            var bytes = pair.Value.AsSpan((int)(address - pair.Key), length).ToArray();
            if (ChangeFallbackAfterPosition && !changed &&
                address == TargetPosition && length == 0x110)
            {
                BinaryPrimitives.WriteUInt64LittleEndian(Memory[Owner].AsSpan(0x20), 99);
                changed = true;
            }
            return new("success", bytes, null, null);
        }

        private static byte[] Q(ulong value)
        {
            var bytes = new byte[8];
            BinaryPrimitives.WriteUInt64LittleEndian(bytes, value);
            return bytes;
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken ct) => ValueTask.FromResult<string?>(null);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
