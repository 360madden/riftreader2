using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildExperienceValuesTests
{
    const ulong M = 0x140000000, O = 0x20000000, R = 0x20010000, G = 0x20020000, CV = 0x20030000, C = 0x20040000, BV = 0x20050000, P = 0x20060000, W = 0x20070000, REG = 0x20080000, TEB = 0x20090000, TABLE = 0x200A0000, HOLDER = 0x200B0000, DATA = 0x200C0000;
    [Fact]
    public void ReadsTypedDatasetAndCalculatesCandidate()
    {
        var f = Fixture(); var result = Run(f); Assert.Equal("raw-values-candidate", result.ValueStatus); Assert.Equal(43, result.Level); Assert.Equal(1000L, result.Baseline); Assert.Equal(200, result.Needed); Assert.Equal(3506622L, result.AccumulatedCandidate);
    }
    [Fact]
    public void RejectsThreadEpochChangeDuringFinalSeedRead()
    {
        var f = Fixture(); var seedReads = 0;
        Assert.Throws<InvalidDataException>(() => CurrentBuildExperienceValuesCandidateReader.Read(f,
         _ => { seedReads++; return Seed(f); }, () => [new(7, seedReads >= 2 ? 9 : 8, TEB)]));
        Assert.Equal(2, seedReads);
    }
    [Fact]
    public void RestedSelectsFlaggedSourceAndRejectsNonfinite()
    {
        var f = Fixture(); f.Q(M + 0x33E0B08, 0x200D0000); f.B(0x200D0087, 1); f.D(R + 0x20, BitConverter.SingleToInt32Bits(12.9f));
        var x = Run(f); Assert.Equal("raw-rested-candidate", x.RestedStatus); Assert.Equal(12L, x.RestedCandidate);
        f = Fixture(); f.Q(M + 0x33E0B08, 0x200D0000); f.B(0x200D0087, 0); f.D(O + 0x138, BitConverter.SingleToInt32Bits(float.NaN));
        x = Run(f); Assert.Equal("nonfinite-or-out-of-range", x.RestedStatus); Assert.Null(x.RestedCandidate);
    }
    [Fact]
    public void CapAndColdCacheAreExplicit()
    {
        var f = Fixture(); f.D(C + 0x34, 43); Assert.Equal("native-minus-one-level-cap", Run(f).ValueStatus);
        f = Fixture(); f.Q(M + 0x33E0D88, 0); Assert.Equal("provider-uninitialized", Run(f).ValueStatus);
        f = Fixture(); f.Changed = (DATA + 0x20, 4); Assert.Throws<InvalidDataException>(() => Run(f));
    }
    [Fact]
    public void UpdatedBuildReadsTypedCacheAndCalculatesCandidate()
    {
        var f = UpdatedFixture();
        var result = RunUpdated(f);
        Assert.Equal("raw-values-candidate", result.ValueStatus);
        Assert.Equal(43, result.Level);
        Assert.Equal(51, result.Limit);
        Assert.Equal(3700000L, result.Baseline);
        Assert.Equal(300000, result.Needed);
        Assert.Equal(107422L, result.AccumulatedCandidate);
        Assert.Equal("provider-uninitialized", result.RestedStatus);
        Assert.Null(result.RestedCandidate);
    }

    [Fact]
    public void UpdatedNeededCacheRefusalsPreserveBaselineWithoutGuessing()
    {
        var f = UpdatedFixture();
        f.Q(M + 0x33F2548, 0);
        var result = RunUpdated(f);
        Assert.Equal("provider-uninitialized", result.ValueStatus);
        Assert.Equal(3700000L, result.Baseline);
        Assert.Null(result.Needed);
        Assert.Null(result.AccumulatedCandidate);

        f = UpdatedFixture();
        f.Put(TABLE + 12 * 24, new byte[24]);
        Assert.Equal("cold-cache-or-null", RunUpdated(f).ValueStatus);

        f = UpdatedFixture();
        f.Q(DATA, M + 0x2C04110);
        Assert.Equal("needed-type-unavailable", RunUpdated(f).ValueStatus);

        f = UpdatedFixture();
        f.D(DATA + 0x20, -1);
        result = RunUpdated(f);
        Assert.Equal("native-minus-one-needed", result.ValueStatus);
        Assert.Null(result.AccumulatedCandidate);

        f = UpdatedFixture();
        f.Changed = (DATA + 0x20, 4);
        Assert.Throws<InvalidDataException>(() => RunUpdated(f));
    }

    [Fact]
    public void UpdatedProviderRefusalsAndMutationStayExplicit()
    {
        var f = UpdatedFixture();
        f.Q(M + 0x33F2270, 0);
        var result = RunUpdated(f);
        Assert.Equal("cap-provider-uninitialized", result.ValueStatus);
        Assert.Null(result.Baseline);
        Assert.Null(result.Limit);
        f = UpdatedFixture();
        f.Q(C, M + 0x1000);
        Assert.Equal("cap-type-unavailable", RunUpdated(f).ValueStatus);
        f = UpdatedFixture();
        f.D(C + 0x34, 43);
        Assert.Equal("native-minus-one-level-cap", RunUpdated(f).ValueStatus);
        f = UpdatedFixture();
        f.Changed = (BV + 43 * 8, 8);
        Assert.Throws<InvalidDataException>(() => RunUpdated(f));
    }

    [Fact]
    public void UpdatedTypeGuardsDoNotInheritOldBuildTypes()
    {
        var f = UpdatedFixture();
        f.Q(O, M + 0x2A46738);
        Assert.Equal("owner-type-unavailable", RunUpdated(f).ValueStatus);
        f = UpdatedFixture();
        f.Q(R, M + 0x2BD4388);
        Assert.Equal("progress-type-unavailable", RunUpdated(f).ValueStatus);
    }

    static ExperienceValuesObservation RunUpdated(Fake f) => Run(f);

    static Fake UpdatedFixture()
    {
        var f = new Fake(updated: true);
        f.Type(O, 0x2A31740, 0x1C503E0, 0x34DABC0, 0x2A5A880, 0x1C89BE0);
        f.Type(R, 0x2BDF520, 0x201A040, 0x355B0C0, 0x2BF12B8, 0x204C3D0);
        f.Q(R + 0x18, 3507422); f.D(R + 0x24, 43);
        f.Q(M + 0x33F22C8, 0); f.Q(M + 0x33F2270, G);
        f.Q(G + 0x870, CV); f.Q(G + 0x878, CV + 8); f.Q(CV, C);
        f.Type(C, 0x2BB7430, 0x1FB15F0, 0x35497F0, 0x2BBD010, 0x1FD09D0);
        f.D(C + 0x34, 51); f.Q(M + 0x33F2458, BV);
        f.Q(M + 0x33F2460, BV + 52 * 8); f.Q(BV + 43 * 8, 3700000);
        f.Q(M + 0x33F2548, P); f.U16(P + 0x40, 83);
        f.Q(M + 0x33843D8, W); f.Q(W, REG); f.D(REG + 0x274, 1);
        var ti = new byte[32]; BinaryPrimitives.WriteUInt64LittleEndian(ti, TEB);
        BinaryPrimitives.WriteUInt64LittleEndian(ti.AsSpan(16), 1);
        BinaryPrimitives.WriteUInt64LittleEndian(ti.AsSpan(24), 7);
        f.Put(TEB + 0x30, ti); f.Q(TEB + 0x1488, 0);
        // A nontrivial bucket count exercises the actual double-hash route.
        const ulong buckets = 17;
        var header = new byte[32]; BinaryPrimitives.WriteUInt64LittleEndian(header, TABLE);
        BinaryPrimitives.WriteUInt64LittleEndian(header.AsSpan(8), 24);
        BinaryPrimitives.WriteUInt64LittleEndian(header.AsSpan(16), buckets);
        f.Put(REG + 0x220, header);
        var node = new byte[24]; BinaryPrimitives.WriteUInt16LittleEndian(node.AsSpan(8), 83);
        BinaryPrimitives.WriteUInt32LittleEndian(node.AsSpan(12), 43);
        BinaryPrimitives.WriteUInt64LittleEndian(node.AsSpan(16), HOLDER);
        var bucket = TABLE + 12 * 24;
        f.Put(bucket, node); f.Q(HOLDER + 0x18, DATA);
        f.Type(DATA, 0x2C09F28, 0x2087E70, 0x3569260, 0x2C1D700, 0x20B6610);
        f.D(M + 0x2FA6CF4, 2); f.D(DATA + 0x20, 300000);
        return f;
    }

    static ExperienceValuesObservation Run(Fake f) => CurrentBuildExperienceValuesCandidateReader.Read(f, _ => Seed(f), () => [new(7, 8, TEB)]);
    static ExperienceSeedObservation Seed(Fake f)
    {
        var updated = CurrentBuildPlayerLookup.IsUpdatedBuild(f.Identity.ExecutableSha256);
        return new(f.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, 1, 0x21000000, 0x21010000, O,
            updated ? 0x2A31740UL : 0x2A46738UL, updated ? 0x1C503E0UL : 0x1C48CC0UL,
            0, 0, 0, 0x21020000, 0x21020008, [R], "indexed-raw-candidate",
            new(R, updated ? 0x2BDF520UL : 0x2BD4388UL, updated ? 0x201A040UL : 0x201A050UL,
                3507422, 43, 0, 0), null, null);
    }
    static Fake Fixture()
    {
        var f = new Fake(); f.Type(O, 0x2A46738, 0x1C48CC0, 0x34C9670, 0x2A4B760, 0x1C84130); f.Type(R, 0x2BD4388, 0x201A050, 0x3548720, 0x2BE0EF8, 0x20482A0);
        f.Q(M + 0x33E0B08, 0); f.Q(R + 0x18, 3507422); f.D(R + 0x24, 43); f.Q(M + 0x33E0AB0, G); f.Q(G + 0x870, CV); f.Q(G + 0x878, CV + 8); f.Q(CV, C);
        f.Type(C, 0x2BA1608, 0x1FA64F0, 0x3538760, 0x2BADC68, 0x1FCBC00); f.D(C + 0x34, 51); f.Q(M + 0x33E0C98, BV); f.Q(M + 0x33E0CA0, BV + 52 * 8); f.Q(BV + 43 * 8, 1000);
        f.Q(M + 0x33E0D88, P); f.U16(P + 0x40, 83); f.Q(M + 0x3372C18, W); f.Q(W, REG); f.D(REG + 0x274, 1);
        var ti = new byte[32]; BinaryPrimitives.WriteUInt64LittleEndian(ti, TEB); BinaryPrimitives.WriteUInt64LittleEndian(ti.AsSpan(16), 1); BinaryPrimitives.WriteUInt64LittleEndian(ti.AsSpan(24), 7); f.Put(TEB + 0x30, ti); f.Q(TEB + 0x1488, 0);
        var header = new byte[32]; BinaryPrimitives.WriteUInt64LittleEndian(header, TABLE); BinaryPrimitives.WriteUInt64LittleEndian(header.AsSpan(8), 24); BinaryPrimitives.WriteUInt64LittleEndian(header.AsSpan(16), 1); f.Put(REG + 0x220, header);
        var node = new byte[24]; BinaryPrimitives.WriteUInt16LittleEndian(node.AsSpan(8), 83); BinaryPrimitives.WriteUInt32LittleEndian(node.AsSpan(12), 43); BinaryPrimitives.WriteUInt64LittleEndian(node.AsSpan(16), HOLDER); f.Put(TABLE, node); f.Q(HOLDER + 0x18, DATA);
        f.Type(DATA, 0x2C04110, 0x208AF40, 0x3557780, 0x2C0DC80, 0x20AFB30); f.D(M + 0x2F95CF4, 2); f.D(DATA + 0x20, 200); return f;
    }
    sealed class Fake(bool updated = false) : IReadOnlyNativeMemorySession
    {
        readonly Dictionary<(ulong, int), byte[]> data = []; readonly Dictionary<(ulong, int), int> reads = []; public (ulong, int)? Changed { get; set; }
        public NativeProcessIdentity Identity { get; } = new(1, 2, "rift.exe",
            updated ? CurrentBuildPlayerLookup.UpdatedGameSha256 : CurrentBuildPlayerLookup.GameSha256,
            M, 64 * 1024 * 1024);
        public void Put(ulong a, byte[] b) => data[(a, b.Length)] = b; public void Q(ulong a, ulong v) { var b = new byte[8]; BinaryPrimitives.WriteUInt64LittleEndian(b, v); Put(a, b); }
        public void D(ulong a, int v) { var b = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(b, v); Put(a, b); }
        public void B(ulong a, byte v) => Put(a, [v]); public void U16(ulong a, ushort v) { var b = new byte[2]; BinaryPrimitives.WriteUInt16LittleEndian(b, v); Put(a, b); }
        public void Type(ulong a, ulong vt, ulong getter, ulong desc, ulong dvt, ulong dg) { Q(a, M + vt); Q(M + vt + 0x40, M + getter); Q(M + desc, M + dvt); Q(M + dvt + 8, M + dg); }
        public NativeReadResult Read(ulong a, int n) { var k = (a, n); var old = reads.GetValueOrDefault(k); reads[k] = old + 1; if (!data.TryGetValue(k, out var b)) return new("unavailable", [], null, "missing"); var copy = b.ToArray(); if (Changed == k && old > 0) copy[0] ^= 1; return new("success", copy, null, null); }
        public ValueTask<string?> RevalidateAsync(CancellationToken _) => ValueTask.FromResult<string?>(null); public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
