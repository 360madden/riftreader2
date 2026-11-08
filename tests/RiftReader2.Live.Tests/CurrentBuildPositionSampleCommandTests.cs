using System.Buffers.Binary;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildPositionSampleCommandTests
{
    private const ulong ModuleBase = 0x140000000;
    private const ulong Manager = 0x20000000;
    private const ulong PlayerSystem = 0x20010000;
    private const ulong Table = 0x20020000;
    private const ulong Buckets = 0x20030000;
    private const ulong Entity = 0x20040000;
    private const ulong Components = 0x20050000;
    private const ulong Position = 0x20060000;
    private const ulong Key = 12345;
    private const ulong BucketCount = 681;

    [Fact]
    public void ReadsExactBuildPlayerComponentAndFiniteXyz()
    {
        var session = Fixture();
        var result = CurrentBuildPositionCandidateReader.Read(session);
        Assert.Equal(7181.80078125f, result.X);
        Assert.Equal(820.8821411132812f, result.Y);
        Assert.Equal(3135.876220703125f, result.Z);
        Assert.True(session.Calls >= 20);
    }

    [Fact]
    public void OwnedReadRetainsSamePlayerKeyWithoutAdditionalReads()
    {
        var legacySession = Fixture();
        var legacy = CurrentBuildPositionCandidateReader.Read(legacySession);
        var ownedSession = Fixture();
        var owned = CurrentBuildPositionCandidateReader.ReadOwned(ownedSession);
        Assert.Equal(Key, owned.UnitKey);
        Assert.Equal(legacy, owned.Position);
        Assert.Equal(legacySession.Calls, ownedSession.Calls);
    }

    [Fact]
    public void ObservationSerializesLosslessIdentityWithoutChangingExistingFields()
    {
        var owned = new CurrentBuildOwnedPosition(ulong.MaxValue, new(1.5f, -2f, 3f));
        var row = new CurrentBuildPositionObservation(1, "2026-11-08T01:00:00Z",
            "2026-11-08T01:00:00.1Z", 0, 100, owned.Position.X, owned.Position.Y, owned.Position.Z)
        {
            UnitKey = owned.UnitKeyText,
            UnitIdCandidate = owned.UnitIdCandidate,
            OwnerIdentityStatus = "player-component-chain-anchored"
        };
        using var json = JsonDocument.Parse(JsonSerializer.Serialize(row, JsonFormat.Options));
        var value = json.RootElement;
        Assert.Equal("18446744073709551615", value.GetProperty("unitKey").GetString());
        Assert.Equal("uFFFFFFFFFFFFFFFF", value.GetProperty("unitIdCandidate").GetString());
        Assert.Equal("player-component-chain-anchored", value.GetProperty("ownerIdentityStatus").GetString());
        Assert.Equal(1.5f, value.GetProperty("x").GetSingle());
        Assert.Equal(100, value.GetProperty("monotonicEndMilliseconds").GetDouble());
        var legacy = new CurrentBuildPositionObservation(1, row.StartedAtUtc, row.CompletedAtUtc, 0, 100, 1, 2, 3);
        Assert.Null(legacy.UnitKey);
        Assert.Null(legacy.UnitIdCandidate);
        Assert.Equal("unavailable", legacy.OwnerIdentityStatus);
    }

    [Fact]
    public void OwnedReadUsesOneResolvedSnapshotAndTwoVerifications()
    {
        var session = Fixture();
        var resolutions = 0; var verifications = 0;
        var owned = CurrentBuildPositionCandidateReader.ReadOwned(session, _ =>
        {
            resolutions++;
            return new(ulong.MaxValue, Entity, Position, () => verifications++);
        });
        Assert.Equal(1, resolutions);
        Assert.Equal(2, verifications);
        Assert.Equal(3, session.Calls);
        Assert.Equal(ulong.MaxValue, owned.UnitKey);
        Assert.Equal(new CurrentBuildXyz(7181.80078125f, 820.8821411132812f, 3135.876220703125f), owned.Position);
    }

    [Fact]
    public void OwnedReadRetainsDistinctKeysAcrossSamplesWithoutAssumingContinuity()
    {
        var session = Fixture();
        var first = CurrentBuildPositionCandidateReader.ReadOwned(session,
            _ => new(123, Entity, Position, () => { }));
        var second = CurrentBuildPositionCandidateReader.ReadOwned(session,
            _ => new(456, Entity, Position, () => { }));
        Assert.Equal(123UL, first.UnitKey);
        Assert.Equal(456UL, second.UnitKey);
        Assert.Equal(first.Position, second.Position);
    }

    [Theory]
    [InlineData(0UL)]
    [InlineData(Entity + 8)]
    public void OwnedReadRejectsZeroOrMismatchedComponentBacklink(ulong backlink)
    {
        var session = Fixture();
        var raw = session.Get(Position, 0x110);
        BinaryPrimitives.WriteUInt64LittleEndian(raw.AsSpan(0x10, 8), backlink);
        session.Set(Position, raw);
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.ReadOwned(session,
            _ => new(Key, Entity, Position, () => { })));
        Assert.Equal(1, session.Calls);
    }

    [Fact]
    public void OwnedReadRejectsMissingOwnerAndChangedProcess()
    {
        var session = Fixture();
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.ReadOwned(session,
            _ => new(0, Entity, Position, () => { })));
        Assert.Equal(0, session.Calls);
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.ReadOwned(session,
            _ => new(123, Entity, Position, () => session.Identity = session.Identity with { ProcessStartUtcTicks = 789 })));
    }

    [Fact]
    public void OwnedReadRejectsChangedComponentBacklinkWithStableXyz()
    {
        var session = Fixture();
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.ReadOwned(session,
            _ => new(Key, Entity, Position, () =>
                session.Set(Position + 0x10, Bytes64(Entity + 8)))));
        Assert.Equal(3, session.Calls);
    }

    [Fact]
    public void RejectsPersistentOwnerKeyChangeDuringFinalXyzRead()
    {
        var session = Fixture();
        var xyzBefore = session.Get(Position + 0x48, 12);
        session.ChangeOwnerKeyOnFinalXyzRead = true;
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.Read(session));
        Assert.Equal(Key + 1, BinaryPrimitives.ReadUInt64LittleEndian(session.Get(PlayerSystem + 0x360, 8)));
        Assert.Equal(xyzBefore, session.Get(Position + 0x48, 12));
        Assert.Equal(Entity, BinaryPrimitives.ReadUInt64LittleEndian(session.Get(Position + 0x10, 8)));
    }

    [Fact]
    public void RejectsWrongBuildBeforeReadingMemory()
    {
        var session = Fixture();
        session.Identity = session.Identity with { ExecutableSha256 = new string('0', 64) };
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.Read(session));
        Assert.Equal(0, session.Calls);
    }

    [Fact]
    public void RejectsAbsentPlayerKeyOrMissingTableData()
    {
        var session = Fixture();
        session.Remove(PlayerSystem + 0x360, 8);
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.Read(session));
        session = Fixture();
        session.Set(PlayerSystem + 0x360, Bytes64(0));
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.Read(session));
    }

    [Fact]
    public void RejectsNonfiniteXyzAndPartialRead()
    {
        var session = Fixture();
        var payload = session.Get(Position, 0x110);
        BinaryPrimitives.WriteInt32LittleEndian(payload.AsSpan(0x48, 4), BitConverter.SingleToInt32Bits(float.NaN));
        session.Set(Position, payload);
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.Read(session));
        session = Fixture();
        session.Remove(Position, 0x110);
        session.Set(Position, new byte[4]);
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.Read(session));
    }

    [Fact]
    public void RejectsChangedOwnerBetweenFirstAndSecondRead()
    {
        var session = Fixture();
        session.ReplaceAfterFirstRead(ModuleBase + 0x33624A8, 8, Bytes64(Manager + 0x100));
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.Read(session));
    }

    [Theory]
    [InlineData("system")]
    [InlineData("player-key")]
    [InlineData("table-header")]
    [InlineData("bucket-link")]
    [InlineData("entity-slot")]
    [InlineData("selector")]
    [InlineData("component-slot")]
    public void SharedLookupRetainsEveryOwnershipAnchor(string anchor)
    {
        var session = Fixture();
        var bucket = Buckets + CurrentBuildPlayerLookup.BucketIndex(Key, BucketCount) * 24;
        var (address, length) = anchor switch
        {
            "system" => (ModuleBase + 0x33623E0, 8),
            "player-key" => (PlayerSystem + 0x360, 8),
            "table-header" => (Table, 24),
            "bucket-link" => (bucket, 24),
            "entity-slot" => (Entity, 128),
            "selector" => (ModuleBase + 0x2F588A0, 4),
            "component-slot" => (Components + 16, 8),
            _ => throw new ArgumentException(nameof(anchor))
        };
        var changed = session.Get(address, length);
        changed[anchor == "entity-slot" ? 0x18 + 34 : 0] ^= 1;
        session.ReplaceAfterFirstRead(address, length, changed);
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.Read(session));
    }

    [Fact]
    public void SharedLookupResolvesOtherSelectorAndRetainsOriginalEpoch()
    {
        var session = Fixture();
        var bytes = session.Get(Entity, 128);
        bytes[0x18 + 6] = 3;
        session.Set(Entity, bytes);
        session.Set(ModuleBase + 0x2F57850, Bytes32(6));
        session.Set(Components + 24, Bytes64(Position + 0x1000));
        var owner = CurrentBuildPlayerLookup.Resolve(session);
        Assert.Equal(Key, owner.PlayerKey);
        Assert.Equal(Entity, owner.EntityAddress);
        Assert.Equal(Position + 0x1000, owner.ResolveComponent(0x2F57850));
        owner.VerifyUnchanged();
        session.Identity = session.Identity with { ProcessStartUtcTicks = 999 };
        Assert.Throws<InvalidDataException>(owner.VerifyUnchanged);
    }

    [Fact]
    public void RejectsChangedPositionBetweenReads()
    {
        var session = Fixture();
        session.Set(Position + 0x48, new byte[12]);
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.Read(session));
    }

    [Fact]
    public void RejectsCycleAndInvalidSelector()
    {
        var session = Fixture();
        var entity = session.Get(Entity, 128);
        entity[0x18 + 34] = 0xFF;
        session.Set(Entity, entity);
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.Read(session));

        session = Fixture();
        var idx = CurrentBuildPositionCandidateReader.BucketIndex(Key, BucketCount);
        var bucket = Buckets + idx * 24;
        var raw = session.Get(bucket, 24);
        BinaryPrimitives.WriteUInt64LittleEndian(raw.AsSpan(0, 8), bucket | 1);
        BinaryPrimitives.WriteUInt64LittleEndian(raw.AsSpan(8, 8), 999);
        session.Set(bucket, raw);
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.Read(session));
    }

    [Fact]
    public void HashMatchesNativeSignedLow32Reference()
    {
        Assert.Equal(463UL, CurrentBuildPositionCandidateReader.BucketIndex(1, 681));
        Assert.Equal(CurrentBuildPositionCandidateReader.BucketIndex(0x80000001, 681),
                     CurrentBuildPositionCandidateReader.BucketIndex(0x1234000080000001, 681));
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            CurrentBuildPositionCandidateReader.BucketIndex(1, 0));
    }

    private static FakeSession Fixture()
    {
        var session = new FakeSession();
        session.Set(ModuleBase + 0x33624A8, Bytes64(Manager));
        session.Set(ModuleBase + 0x33623E0, Bytes64(PlayerSystem));
        session.Set(ModuleBase + 0x2F588A0, Bytes32(34));
        session.Set(Manager + 0x50, Bytes64(Table));
        session.Set(PlayerSystem + 0x360, Bytes64(Key));
        var header = new byte[24];
        BinaryPrimitives.WriteUInt64LittleEndian(header.AsSpan(0, 8), Buckets);
        BinaryPrimitives.WriteUInt64LittleEndian(header.AsSpan(8, 8), 24);
        BinaryPrimitives.WriteUInt64LittleEndian(header.AsSpan(16, 8), BucketCount);
        session.Set(Table, header);
        var bucket = Buckets + CurrentBuildPositionCandidateReader.BucketIndex(Key, BucketCount) * 24;
        var node = new byte[24];
        BinaryPrimitives.WriteUInt64LittleEndian(node.AsSpan(8, 8), Key);
        BinaryPrimitives.WriteUInt64LittleEndian(node.AsSpan(16, 8), Entity);
        session.Set(bucket, node);
        var entity = new byte[128];
        entity[0x18 + 34] = 2;
        BinaryPrimitives.WriteUInt64LittleEndian(entity.AsSpan(0x78, 8), Components);
        session.Set(Entity, entity);
        session.Set(Components + 16, Bytes64(Position));
        var candidate = new byte[0x110];
        BinaryPrimitives.WriteUInt64LittleEndian(candidate.AsSpan(0x10, 8), Entity);
        BinaryPrimitives.WriteInt32LittleEndian(candidate.AsSpan(0x48, 4),
            BitConverter.SingleToInt32Bits(7181.80078125f));
        BinaryPrimitives.WriteInt32LittleEndian(candidate.AsSpan(0x4C, 4),
            BitConverter.SingleToInt32Bits(820.8821411132812f));
        BinaryPrimitives.WriteInt32LittleEndian(candidate.AsSpan(0x50, 4),
            BitConverter.SingleToInt32Bits(3135.876220703125f));
        session.Set(Position, candidate);
        session.Set(Position + 0x48, candidate.AsSpan(0x48, 12).ToArray());
        session.Set(Position + 0x10, candidate.AsSpan(0x10, 8).ToArray());
        return session;
    }

    private static byte[] Bytes64(ulong value)
    {
        var result = new byte[8];
        BinaryPrimitives.WriteUInt64LittleEndian(result, value);
        return result;
    }

    private static byte[] Bytes32(int value)
    {
        var result = new byte[4];
        BinaryPrimitives.WriteInt32LittleEndian(result, value);
        return result;
    }

    [Fact]
    public void CachedXyzAndRefreshGuardsComeFromTheSameExistingComponentRead()
    {
        foreach (var (handle, flag, status) in new (ulong Handle, byte Flag, string Status)[]
        {
            (0, 0, "guard-ineligible-candidate"),
            (0x123456789ABCDEF0UL, 0, "handle-present-guard-candidate"),
            (0, 1, "alternate-flag-guard-candidate")
        })
        {
            var session = Fixture();
            var raw = session.Get(Position, 0x110);
            BinaryPrimitives.WriteUInt64LittleEndian(raw.AsSpan(0x100, 8), handle);
            raw[0x108] = flag;
            session.Set(Position, raw);
            var owned = CurrentBuildPositionCandidateReader.ReadOwned(session,
                _ => new(Key, Entity, Position, () => { }));
            Assert.Equal(3, session.Calls); // component + XYZ and backlink rechecks
            Assert.Equal($"0x{handle:X16}", owned.RefreshHandleHex);
            Assert.Equal(flag, owned.RefreshFlagRaw);
            Assert.Equal(status, owned.RefreshGuardStatus);
            Assert.Equal(new CurrentBuildXyz(7181.80078125f, 820.8821411132812f, 3135.876220703125f),
                owned.Position);
        }
    }

    [Fact]
    public async Task RealReaderPublishesOptionalSameBufferGuardFieldsWithoutChangingXyzContract()
    {
        var path = Path.Combine(Path.GetTempPath(), "rr2-xyz-guards-" + Guid.NewGuid().ToString("N") + ".json");
        var session = Fixture();
        try
        {
            var opts = new Dictionary<string, string>
            {
                ["--pid"] = "123",
                ["--start-ticks"] = "456",
                ["--output"] = path,
                ["--samples"] = "1",
                ["--interval-ms"] = "0"
            };
            Assert.Equal(0, await CurrentBuildPositionSampleCommand.RunAsync(opts, TextWriter.Null, default,
                (_, _, _) => Task.FromResult<IAsyncDisposable>(new TestLease(() => { })),
                (_, _, _) => Task.FromResult<IReadOnlyNativeMemorySession>(session),
                CurrentBuildPositionCandidateReader.ReadOwned));
            using var json = JsonDocument.Parse(await File.ReadAllTextAsync(path));
            var root = json.RootElement;
            Assert.Equal("native-current-position-candidate-samples/1",
                root.GetProperty("contractVersion").GetString());
            var row = root.GetProperty("observations")[0];
            Assert.Equal("12345", row.GetProperty("unitKey").GetString());
            Assert.Equal(7181.80078125f, row.GetProperty("x").GetSingle());
            Assert.Equal("0x0000000000000000", row.GetProperty("refreshHandleHex").GetString());
            Assert.Equal(0, row.GetProperty("refreshFlagRaw").GetInt32());
            Assert.Equal("guard-ineligible-candidate", row.GetProperty("refreshGuardStatus").GetString());
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Fact]
    public async Task ThirtySampleRunHoldsLeaseUntilSessionDisposed()
    {
        var path = Path.Combine(Path.GetTempPath(), "rr2-xyz-lease-" + Guid.NewGuid().ToString("N") + ".json");
        var session = new FakeSession();
        var held = false;
        var disposedAfterSession = false;
        var count = 0;
        try
        {
            var options = new Dictionary<string, string>
            {
                ["--pid"] = "123",
                ["--start-ticks"] = "456",
                ["--output"] = path,
                ["--samples"] = "30",
                ["--interval-ms"] = "0"
            };
            var code = await CurrentBuildPositionSampleCommand.RunAsync(options, TextWriter.Null, default,
                (_, _, _) =>
                {
                    held = true; return Task.FromResult<IAsyncDisposable>(new TestLease(() =>
                    { held = false; disposedAfterSession = session.Disposed; }));
                },
                (_, _, _) => { Assert.True(held); return Task.FromResult<IReadOnlyNativeMemorySession>(session); },
                _ => { Assert.True(held); count++; return new CurrentBuildOwnedPosition(1, new(1, 2, 3)); });
            Assert.Equal(0, code); Assert.Equal(30, count);
            Assert.True(session.Disposed); Assert.True(disposedAfterSession); Assert.False(held);
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Fact]
    public async Task LeaseDenialDoesNotOpenPositionSession()
    {
        var path = Path.Combine(Path.GetTempPath(), "rr2-xyz-lease-" + Guid.NewGuid().ToString("N") + ".json");
        var options = new Dictionary<string, string>
        {
            ["--pid"] = "123",
            ["--start-ticks"] = "456",
            ["--output"] = path
        };
        var opened = false;
        await Assert.ThrowsAsync<TimeoutException>(() => CurrentBuildPositionSampleCommand.RunAsync(
            options, TextWriter.Null, default, (_, _, _) => throw new TimeoutException("busy"),
            (_, _, _) => { opened = true; throw new Exception("must not open"); },
            _ => throw new Exception("must not read")));
        Assert.False(opened); Assert.False(File.Exists(path));
    }

    private sealed class TestLease(Action dispose) : IAsyncDisposable
    {
        public ValueTask DisposeAsync() { dispose(); return ValueTask.CompletedTask; }
    }

    private sealed class FakeSession : IReadOnlyNativeMemorySession
    {
        private readonly Dictionary<(ulong Address, int Length), byte[]> entries = [];
        private readonly Dictionary<(ulong Address, int Length), byte[]> swapAfterFirst = [];
        private readonly Dictionary<(ulong Address, int Length), int> reads = [];

        public NativeProcessIdentity Identity { get; set; } = new(
            123, 456, @"C:\RIFT_TRANSFER\RIFT\rift_x64.exe",
            CurrentBuildPositionSampleCommand.GameSha256, ModuleBase, 64 * 1024 * 1024);
        public int Calls { get; private set; }
        public bool Disposed { get; private set; }
        public bool ChangeOwnerKeyOnFinalXyzRead { get; set; }

        public void Set(ulong address, byte[] bytes) => entries[(address, bytes.Length)] = (byte[])bytes.Clone();
        public void Remove(ulong address, int length) => entries.Remove((address, length));
        public byte[] Get(ulong address, int length) => (byte[])entries[(address, length)].Clone();
        public void ReplaceAfterFirstRead(ulong address, int length, byte[] bytes) =>
            swapAfterFirst[(address, length)] = bytes;

        public NativeReadResult Read(ulong address, int length)
        {
            Calls++;
            var key = (address, length);
            var n = reads.TryGetValue(key, out var seen) ? seen : 0;
            reads[key] = n + 1;
            if (ChangeOwnerKeyOnFinalXyzRead && address == Position + 0x48 && length == 12)
                Set(PlayerSystem + 0x360, Bytes64(Key + 1));
            if (n > 0 && swapAfterFirst.TryGetValue(key, out var swapped))
                return new("success", (byte[])swapped.Clone(), null, null);
            if (!entries.TryGetValue(key, out var bytes))
                return new("unavailable", [], null, "No synthetic bytes for address.");
            return new("success", (byte[])bytes.Clone(), null, null);
        }

        public ValueTask<string?> RevalidateAsync(CancellationToken _) => ValueTask.FromResult<string?>(null);
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
