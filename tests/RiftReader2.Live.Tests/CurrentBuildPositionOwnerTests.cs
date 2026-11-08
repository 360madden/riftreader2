using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildPositionOwnerTests
{
    private const ulong Component = 0x20060000;
    private const ulong Entity = 0x20040000;

    [Fact]
    public void ReadsInjectedNonSelfOwnerAndVerifies()
    {
        var session = new FakeSession();
        var verified = false;
        var xyz = CurrentBuildPositionCandidateReader.Read(session, _ =>
            new(0x123456789ABCDEF0, Entity, Component, () => verified = true));
        Assert.True(verified);
        Assert.Equal(1.5f, xyz.X);
        Assert.Equal(-2f, xyz.Y);
        Assert.Equal(3f, xyz.Z);
    }

    [Fact]
    public void RejectsChangedXyzAndInvalidatedOwner()
    {
        var session = new FakeSession { ChangeXyz = true };
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.Read(session,
            _ => new(123, Entity, Component, () => { })));
        session = new FakeSession();
        Assert.Throws<InvalidDataException>(() => CurrentBuildPositionCandidateReader.Read(session,
            _ => new(123, Entity, Component, () => throw new InvalidDataException("target changed"))));
    }

    private sealed class FakeSession : IReadOnlyNativeMemorySession
    {
        public bool ChangeXyz { get; init; }
        public NativeProcessIdentity Identity { get; } = new(123, 456, "rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 64 * 1024 * 1024);
        public NativeReadResult Read(ulong address, int length)
        {
            var bytes = new byte[length];
            if (address == Component && length == 0x110)
            {
                BinaryPrimitives.WriteUInt64LittleEndian(bytes.AsSpan(0x10), Entity);
                BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(0x48), BitConverter.SingleToInt32Bits(1.5f));
                BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(0x4c), BitConverter.SingleToInt32Bits(-2f));
                BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(0x50), BitConverter.SingleToInt32Bits(3f));
                return new("success", bytes, null, null);
            }
            if (address == Component + 0x48 && length == 12)
            {
                BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(0), BitConverter.SingleToInt32Bits(ChangeXyz ? 7f : 1.5f));
                BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(4), BitConverter.SingleToInt32Bits(-2f));
                BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(8), BitConverter.SingleToInt32Bits(3f));
                return new("success", bytes, null, null);
            }
            if (address == Component + 0x10 && length == 8)
            {
                BinaryPrimitives.WriteUInt64LittleEndian(bytes, Entity);
                return new("success", bytes, null, null);
            }
            return new("unavailable", [], null, "missing");
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken _) => ValueTask.FromResult<string?>(null);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
