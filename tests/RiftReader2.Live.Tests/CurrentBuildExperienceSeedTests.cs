using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildExperienceSeedTests
{
    const ulong M = 0x140000000, S = 0x20000000, E = 0x20010000, H = 0x20020000, X = 0x20030000, O = 0x20040000, V = 0x20050000, R = 0x20060000;
    [Fact]
    public void IndexedRawCandidateAndOwnerVerification()
    {
        var f = Fixture(); bool verified = false; var x = Read(f, () => verified = true); Assert.True(verified); Assert.Equal("indexed-raw-candidate", x.Branch);
        Assert.Equal(42L, x.Selected!.RawInt64_18); Assert.Equal(19U, x.Selected.RawDword24); Assert.Equal(2.5f, x.Selected.RawFloat20);
    }
    [Fact]
    public void SpecialBranchAndChangedAnchors()
    {
        var f = Fixture(); f.D(O + 0x1D8, unchecked((uint)-1)); f.B(O + 0x24F, 1); f.Q(O + 0x7D8, 3); f.Q(O + 0x7E0, 4);
        var x = Read(f, () => { }); Assert.Equal("special-index-minus-one", x.Branch); Assert.Equal(3UL, x.Special7D8);
        f = Fixture(); f.Changed = (R + 0x18, 8); Assert.Throws<InvalidDataException>(() => Read(f, () => { }));
        f = Fixture(); Assert.Throws<InvalidDataException>(() => Read(f, () => throw new InvalidDataException()));
    }
    [Fact]
    public void UpdatedBuildResolvesTheVerifiedSelfComponentRoute()
    {
        var f = Fixture(updated: true);
        const ulong manager = 0x20070000, table = 0x20080000, bucket = 0x20090000, components = 0x200A0000;
        f.Q(M + 0x3373C68, manager);
        f.Q(manager + 0x50, table);
        var header = new byte[24];
        BinaryPrimitives.WriteUInt64LittleEndian(header, bucket);
        BinaryPrimitives.WriteUInt64LittleEndian(header.AsSpan(8), 24);
        BinaryPrimitives.WriteUInt64LittleEndian(header.AsSpan(16), 1);
        f.Put(table, header);
        var node = new byte[24];
        BinaryPrimitives.WriteUInt64LittleEndian(node.AsSpan(8), 1);
        BinaryPrimitives.WriteUInt64LittleEndian(node.AsSpan(16), E);
        f.Put(bucket, node);
        var entity = new byte[128];
        entity[0x19] = 0;
        entity[0x1A] = 1;
        BinaryPrimitives.WriteUInt64LittleEndian(entity.AsSpan(0x78), components);
        f.Put(E, entity);
        f.D(M + 0x2F68850, 1);
        f.D(M + 0x2F692E0, 2);
        f.Q(components, H);
        f.Q(components + 8, X);

        var observation = CurrentBuildExperienceSeedCandidateReader.Read(f);
        Assert.Equal(1UL, observation.UnitKey);
        Assert.Equal(E, observation.Entity);
        Assert.Equal(X, observation.Component);
        Assert.Equal("indexed-raw-candidate", observation.Branch);
        Assert.Equal(42L, observation.Selected!.RawInt64_18);

        // Refuse a component from a different player, even if its payload is readable.
        f.Q(X + 0x10, E + 0x1000);
        Assert.Throws<InvalidDataException>(() => CurrentBuildExperienceSeedCandidateReader.Read(f));
    }

    [Fact]
    public void UpdatedBuildRefusesChangedKeyAndUnmappedModuleReferences()
    {
        var f = Fixture(updated: true);
        f.Q(S + 0x360, 2);
        Assert.Throws<InvalidDataException>(() => Read(f, () => { }));
        f = Fixture(updated: true);
        f.Q(O, 0x7FFF00000000);
        Assert.Throws<InvalidDataException>(() => Read(f, () => { }));
        f = Fixture(updated: true);
        f.Q(R, 0x7FFF00000000);
        Assert.Throws<InvalidDataException>(() => Read(f, () => { }));
        f = Fixture(updated: true);
        f.Changed = (R + 0x18, 8);
        Assert.Throws<InvalidDataException>(() => Read(f, () => { }));
    }

    [Fact]
    public async Task RequestedBuildMustMatchOpenedSessionBeforeReading()
    {
        var path = Path.Combine(Path.GetTempPath(), "rr2-xp-admission-" + Guid.NewGuid() + ".json");
        var options = new Dictionary<string, string>
        {
            ["--pid"] = "1",
            ["--start-ticks"] = "2",
            ["--output"] = path,
            ["--sha256"] = CurrentBuildPlayerLookup.UpdatedGameSha256
        };
        var acquired = 0;
        Task<IAsyncDisposable> Acquire(int _, long __, CancellationToken ___)
        { acquired++; return Task.FromResult<IAsyncDisposable>(new Fake()); }
        Task<IReadOnlyNativeMemorySession> Open(int _, long __, CancellationToken ___) =>
            Task.FromResult<IReadOnlyNativeMemorySession>(new Fake());
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            CurrentBuildExperienceSeedSampleCommand.RunAsync(options, TextWriter.Null, default,
                Acquire, Open, _ => throw new InvalidOperationException("Must not read.")));
        Assert.Equal(1, acquired);
        Assert.False(File.Exists(path));
        options["--sha256"] = new string('F', 64);
        await Assert.ThrowsAsync<ArgumentException>(() =>
            CurrentBuildExperienceSeedSampleCommand.RunAsync(options, TextWriter.Null, default,
                Acquire, Open, _ => throw new InvalidOperationException("Must not read.")));
        Assert.Equal(1, acquired);
    }

    static ExperienceSeedObservation Read(Fake f, Action verify) => CurrentBuildExperienceSeedCandidateReader.ReadResolved(f, f.Identity, DateTimeOffset.UtcNow, 1, E, H, X, verify);
    static Fake Fixture(bool updated = false)
    {
        var f = new Fake(updated);
        f.Q(M + (updated ? 0x3373BA0UL : 0x33623E0UL), S);
        f.Q(S + 0x360, 1);
        f.Q(S + 0x3F8, E); f.Q(H + 0x10, E); f.Q(X + 0x10, E); f.Q(X + 0x48, O);
        f.Q(O, M + 0x1000); f.Q(M + 0x1040, M + 0x2000); f.D(O + 0x1D8, 0); f.D(O + 0x160, 5); f.B(O + 0x24F, 0);
        f.Q(O + 0xDE0, V); f.Q(O + 0xDE8, V + 8); f.Q(V, R); f.Q(R, M + 0x3000); f.Q(M + 0x3040, M + 0x4000);
        f.Q(R + 0x18, 42); f.D(R + 0x20, (uint)BitConverter.SingleToInt32Bits(2.5f)); f.D(R + 0x24, 19); return f;
    }
    sealed class Fake(bool updated = false) : IReadOnlyNativeMemorySession
    {
        readonly Dictionary<(ulong, int), byte[]> data = []; readonly Dictionary<(ulong, int), int> reads = []; public (ulong, int)? Changed { get; set; }
        public NativeProcessIdentity Identity { get; } = new(1, 2, "rift.exe",
            updated ? CurrentBuildPlayerLookup.UpdatedGameSha256 : CurrentBuildPlayerLookup.GameSha256,
            M, 64 * 1024 * 1024);
        public void Put(ulong address, byte[] bytes) => data[(address, bytes.Length)] = bytes;
        public void Q(ulong a, ulong v) { var b = new byte[8]; BinaryPrimitives.WriteUInt64LittleEndian(b, v); data[(a, 8)] = b; }
        public void D(ulong a, uint v) { var b = new byte[4]; BinaryPrimitives.WriteUInt32LittleEndian(b, v); data[(a, 4)] = b; }
        public void B(ulong a, byte v) => data[(a, 1)] = [v];
        public NativeReadResult Read(ulong a, int n) { var k = (a, n); var old = reads.GetValueOrDefault(k); reads[k] = old + 1; if (!data.TryGetValue(k, out var b)) return new("unavailable", [], null, "missing"); var copy = b.ToArray(); if (Changed == k && old > 0) copy[0] ^= 1; return new("success", copy, null, null); }
        public ValueTask<string?> RevalidateAsync(CancellationToken _) => ValueTask.FromResult<string?>(null);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
