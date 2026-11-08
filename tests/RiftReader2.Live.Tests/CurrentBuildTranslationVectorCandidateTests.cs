using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildTranslationVectorCandidateTests
{
    const ulong Module = 0x140000000, Size = 0x4000000, Singleton = 0x20000000;
    const ulong PointerAddress = Module + CurrentBuildTranslationVectorCandidate.SingletonRva;
    const ulong PayloadAddress = Singleton + CurrentBuildTranslationVectorCandidate.VectorOffset;

    [Fact]
    public void StableFinitePayloadPreservesBitsWithoutCombiningOtherCoordinates()
    {
        var session = new Fake();
        int guards = 0;
        var sample = Read(session, () => guards++);
        Assert.NotNull(sample);
        Assert.Equal(1.25f, sample.A);
        Assert.Equal(-2.5f, sample.B);
        Assert.Equal(0x80000000U, sample.CBits);
        Assert.Equal(BitConverter.SingleToUInt32Bits(1.25f), sample.ABits);
        Assert.Equal(BitConverter.SingleToUInt32Bits(-2.5f), sample.BBits);
        Assert.Equal(Singleton, sample.SingletonAddress);
        Assert.Equal("0x0000000020000000", sample.SingletonAddressHex);
        Assert.Contains("unqualified", sample.Qualification);
        Assert.Equal(2, guards);
        Assert.Equal(new[] { (PointerAddress, 8), (PayloadAddress, 12),
            (PayloadAddress, 12), (PointerAddress, 8) }, session.Requests);
        Assert.True(sample.CompletedAtUtc >= sample.StartedAtUtc);
    }

    [Theory]
    [InlineData(0UL)]
    [InlineData(0xFFF8UL)]
    [InlineData(0x20000001UL)]
    [InlineData(0x0000800000000000UL)]
    [InlineData(0x00007FFFFFFFFBC0UL)]
    [InlineData(ulong.MaxValue)]
    public void InvalidSingletonCannotPublish(ulong pointer)
    {
        var session = new Fake { Pointer = pointer };
        Assert.Null(Read(session));
        Assert.Single(session.Requests);
    }

    [Theory]
    [InlineData(0x7F800000U)]
    [InlineData(0xFF800000U)]
    [InlineData(0x7FC00001U)]
    public void NonfiniteAnyComponentCannotPublish(uint bits)
    {
        for (int i = 0; i < 3; i++)
        {
            var session = new Fake();
            BinaryPrimitives.WriteUInt32LittleEndian(session.Payload.AsSpan(i * 4), bits);
            Assert.Null(Read(session));
        }
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void ChangedPointerOrPayloadCannotPublish(bool pointer)
    {
        var session = new Fake { ChangePointer = pointer, ChangePayload = !pointer };
        Assert.Null(Read(session));
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    public void FailedOrShortReadCannotPublish(int ordinal)
    {
        Assert.Null(Read(new Fake { FailRead = ordinal }));
        Assert.Null(Read(new Fake { ShortRead = ordinal }));
    }

    [Fact]
    public void OwnerEpochGuardFailureCannotPublish()
    {
        int calls = 0;
        Assert.Null(Read(new Fake(), () =>
        {
            if (++calls == 2) throw new InvalidDataException("owner changed");
        }));
        Assert.Equal(2, calls);
    }

    [Fact]
    public void IdentityChangeDuringBracketCannotPublish()
    {
        var session = new Fake();
        Assert.Null(Read(session, () =>
        {
            if (session.Requests.Count > 0)
                session.Identity = session.Identity with { ProcessStartUtcTicks = 999 };
        }));
    }

    [Fact]
    public void WrongBuildOrEpochRejectsBeforeReads()
    {
        var session = new Fake();
        session.Identity = session.Identity with { ExecutableSha256 = "wrong" };
        Assert.Null(Read(session));
        Assert.Empty(session.Requests);
        session.Identity = new Fake().Identity with { ProcessId = 0 };
        Assert.Null(Read(session));
        Assert.Empty(session.Requests);
    }

    [Theory]
    [InlineData(Module + 8, Size)]
    [InlineData(Module, Size - 8)]
    [InlineData(ulong.MaxValue, Size)]
    [InlineData(Module, 0UL)]
    public void CallerModuleMustMatchExactIdentity(ulong module, ulong size)
    {
        var session = new Fake();
        Assert.Null(CurrentBuildTranslationVectorCandidate.TryRead(session, module, size, () => { }));
        Assert.Empty(session.Requests);
    }

    [Fact]
    public void TruncatedOrOverflowingModuleSpanRejectsBeforeReads()
    {
        var session = new Fake();
        session.Identity = session.Identity with { ModuleSize = CurrentBuildTranslationVectorCandidate.SingletonRva + 7 };
        Assert.Null(CurrentBuildTranslationVectorCandidate.TryRead(session, Module, session.Identity.ModuleSize, () => { }));
        session.Identity = session.Identity with { ModuleBaseAddress = 0x7FFFFFFFF000, ModuleSize = Size };
        Assert.Null(CurrentBuildTranslationVectorCandidate.TryRead(session, session.Identity.ModuleBaseAddress, Size, () => { }));
        Assert.Empty(session.Requests);
    }

    static CurrentBuildTranslationVectorCandidate.Sample? Read(Fake session, Action? guard = null) =>
        CurrentBuildTranslationVectorCandidate.TryRead(session, Module, Size, guard ?? (() => { }));

    sealed class Fake : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; set; } =
            new(123, 456, "rift_x64.exe", CurrentBuildPlayerLookup.GameSha256, Module, Size);
        public ulong Pointer { get; set; } = Singleton;
        public byte[] Payload { get; } = new byte[12];
        public bool ChangePointer { get; set; }
        public bool ChangePayload { get; set; }
        public int FailRead { get; set; }
        public int ShortRead { get; set; }
        public List<(ulong, int)> Requests { get; } = [];
        public Fake()
        {
            BinaryPrimitives.WriteSingleLittleEndian(Payload, 1.25f);
            BinaryPrimitives.WriteSingleLittleEndian(Payload.AsSpan(4), -2.5f);
            BinaryPrimitives.WriteUInt32LittleEndian(Payload.AsSpan(8), 0x80000000);
        }
        public NativeReadResult Read(ulong address, int count)
        {
            Requests.Add((address, count));
            if (Requests.Count == FailRead) return new("unavailable", [], null, "synthetic");
            byte[] bytes;
            if (address == PointerAddress && count == 8)
            {
                bytes = new byte[8];
                BinaryPrimitives.WriteUInt64LittleEndian(bytes,
                    ChangePointer && Requests.Count > 1 ? Pointer + 8 : Pointer);
            }
            else if (address == PayloadAddress && count == 12)
            {
                bytes = Payload.ToArray();
                if (ChangePayload && Requests.Count > 2) bytes[0] ^= 1;
            }
            else return new("unavailable", [], null, "unexpected");
            if (Requests.Count == ShortRead) bytes = bytes[..^1];
            return new("success", bytes, null, null);
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken _) => ValueTask.FromResult<string?>(null);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
