using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildOpticalCameraTests
{
    private const ulong Module = 0x140000000;
    private const ulong Camera = 0x30004000;
    private const ulong SystemAddress = 0x30006000;

    [Fact]
    public void ResolvesSelectedCameraAndAppliesRendererOrigin()
    {
        var session = new Fake();
        var result = CurrentBuildOpticalCameraCandidateReader.TryRead(session, SystemAddress);
        Assert.Equal("available-candidate", result.Status);
        Assert.Equal(0, result.BearingDegreesCandidate);
        Assert.Equal(0, result.PitchDegreesCandidate);
        Assert.Equal(new double[] { 7427, 871, 2936 }, result.WorldEyeXYZ);
        Assert.Equal(15, result.RawBits!.Length);
        Assert.Equal(20, result.ProjectionRawBits!.Length);
        Assert.Equal(new float[] { 0, 1, 1, 0 }, result.ViewportLeftRightTopBottom);
        Assert.False(result.CameraYawQualified);
    }

    [Fact]
    public void UnsupportedSelectedModeReturnsUnavailable()
    {
        var session = new Fake();
        session.Qword(Module + 0x2710320 + 0xB8, Module + 0xF88590);
        var result = CurrentBuildOpticalCameraCandidateReader.TryRead(session, SystemAddress);
        Assert.Equal("unavailable", result.Status);
        Assert.Contains("selected mode", result.UnavailableReason);
        Assert.Null(result.BearingDegreesCandidate);
        Assert.Null(result.WorldEyeXYZ);
    }

    [Fact]
    public void PayloadChangeRetriesAndReturnsNextCoherentSnapshot()
    {
        var session = new Fake { ChangeTransformOnce = true };

        var result = CurrentBuildOpticalCameraCandidateReader.TryRead(session, SystemAddress);

        Assert.Equal("available-candidate", result.Status);
        Assert.Equal(4, session.CameraTransformReadCount);
    }

    [Fact]
    public void ContinuouslyChangingPayloadStopsAfterBoundedAttempts()
    {
        var session = new Fake { ChangeTransformEveryReread = true };

        var result = CurrentBuildOpticalCameraCandidateReader.TryRead(session, SystemAddress);

        Assert.Equal("unavailable", result.Status);
        Assert.Contains("payload changed", result.UnavailableReason);
        Assert.Equal(6, session.CameraTransformReadCount);
    }

    [Fact]
    public void StructuralOwnerChangeDoesNotRetry()
    {
        var session = new Fake { ChangeCameraPointer = true };

        var result = CurrentBuildOpticalCameraCandidateReader.TryRead(session, SystemAddress);

        Assert.Equal("unavailable", result.Status);
        Assert.Equal(2, session.CameraPointerReadCount);
        Assert.Equal(1, session.CameraTransformReadCount);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    [InlineData(5)]
    public void ChangingPointersAndInvalidTransformsWithholdCamera(int fault)
    {
        var session = new Fake { ChangeCameraPointer = fault == 0 };
        if (fault == 1)
            session.Memory[Camera + 0xD4] = new byte[48];
        if (fault == 2)
            BinaryPrimitives.WriteUInt32LittleEndian(session.Memory[Camera + 0xD4],
                BitConverter.SingleToUInt32Bits(float.NaN));
        if (fault == 3)
            BinaryPrimitives.WriteUInt32LittleEndian(session.Memory[Camera + 0x138].AsSpan(48),
                BitConverter.SingleToUInt32Bits(1));
        if (fault == 4)
            session.Memory[Camera + 0x19C] = new byte[16];
        if (fault == 5)
            BinaryPrimitives.WriteUInt32LittleEndian(session.Memory[Camera + 0x138].AsSpan(60), 0);
        var result = CurrentBuildOpticalCameraCandidateReader.TryRead(session, SystemAddress);
        Assert.Equal("unavailable", result.Status);
        Assert.Null(result.RawBits);
        Assert.Null(result.BearingDegreesCandidate);
    }

    private sealed class Fake : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; } = new(123, 456, "rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256, Module, 64 * 1024 * 1024);
        public Dictionary<ulong, byte[]> Memory { get; } = [];
        public bool ChangeCameraPointer { get; init; }
        public bool ChangeTransformOnce { get; init; }
        public bool ChangeTransformEveryReread { get; init; }
        private int cameraPointerReads;
        private int cameraTransformReads;
        public int CameraPointerReadCount => cameraPointerReads;
        public int CameraTransformReadCount => cameraTransformReads;
        public Fake()
        {
            Qword(Module + 0x33724F0, 0x30000000);
            Qword(0x30000000 + 0x1B0, 0x30001000);
            Qword(0x30001000, Module + 0x2710320);
            Qword(Module + 0x2710320 + 0xB8, Module + 0xF88580);
            Qword(Module + 0x3362848, 0x30002000);
            Qword(0x30002000 + 0x78, 0x30003000);
            Qword(0x30003000, Module + 0x27106A8);
            Qword(0x30003000 + 0x28, Camera);
            Qword(Camera, Module + 0x274D630);
            Memory[Camera + 0xD4] = Floats([0, 0, -1, 0, 1, 0, 1, 0, 0, 3, 39, -8]);
            Memory[Camera + 0x138] = Floats([-1, 0, 0, 3, 0, 1, 0, -39, 0, 0, 1, 8, 0, 0, 1, 8]);
            Memory[Camera + 0x19C] = Floats([0, 1, 1, 0]);
            Memory[SystemAddress + 0x438] = Floats([7424, 832, 2944]);
        }
        public void Qword(ulong address, ulong value)
        {
            var bytes = new byte[8];
            BinaryPrimitives.WriteUInt64LittleEndian(bytes, value);
            Memory[address] = bytes;
        }
        private static byte[] Floats(float[] values) => values.SelectMany(BitConverter.GetBytes).ToArray();
        public NativeReadResult Read(ulong address, int length)
        {
            if (!Memory.TryGetValue(address, out var bytes) || bytes.Length != length)
                return new("unavailable", [], null, "hole");
            if (address == 0x30003000 + 0x28 && ++cameraPointerReads > 1 && ChangeCameraPointer)
                return new("success", new byte[8], null, null);
            if (address == Camera + 0xD4)
            {
                cameraTransformReads++;
                if ((ChangeTransformOnce && cameraTransformReads == 2) ||
                    (ChangeTransformEveryReread && cameraTransformReads % 2 == 0))
                {
                    var changed = bytes.ToArray();
                    BinaryPrimitives.WriteUInt32LittleEndian(changed.AsSpan(36),
                        BitConverter.SingleToUInt32Bits(ChangeTransformEveryReread
                            ? 3 + cameraTransformReads / 2
                            : 4));
                    Memory[address] = changed;
                    return new("success", changed, null, null);
                }
            }
            return new("success", bytes.ToArray(), null, null);
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken ct) => ValueTask.FromResult<string?>(null);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
