using System.Buffers.Binary;
using System.Globalization;
using RiftReader2.Application;

namespace RiftReader2.Live;

internal sealed record CurrentBuildOpticalCameraCandidate(
    string Status, string? UnavailableReason, string? CameraAddressDecimal,
    float[]? RotationRowMajor, float[]? RendererEyeXYZ, float[]? RenderOriginXYZ,
    uint[]? RawBits, double? BearingDegreesCandidate, double? PitchDegreesCandidate,
    double[]? WorldEyeXYZ)
{
    public string SourceRootRva => "0x3362848";
    public string SelectedModeCameraGetterRva => "0xF88580";
    public bool CameraYawQualified => false;
}

internal static class CurrentBuildOpticalCameraCandidateReader
{
    internal static CurrentBuildOpticalCameraCandidate TryRead(
        IReadOnlyNativeMemorySession session, ulong playerSystem)
    {
        try { return Read(session, playerSystem); }
        catch (Exception error) when (error is InvalidDataException or IOException or OverflowException)
        {
            return new("unavailable", error.Message, null, null, null, null, null, null, null, null);
        }
    }

    private static CurrentBuildOpticalCameraCandidate Read(
        IReadOnlyNativeMemorySession session, ulong playerSystem)
    {
        var identity = session.Identity;
        if (!string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256,
                           StringComparison.OrdinalIgnoreCase) || identity.ModuleSize < 0x33724F8)
            throw new InvalidDataException("Optical camera build or module mismatch.");
        var anchors = new List<(ulong Address, byte[] Bytes)>();
        byte[] Take(ulong address, int count)
        {
            var bytes = CurrentBuildPlayerLookup.Exact(session, address, count);
            anchors.Add((address, bytes));
            return bytes;
        }
        ulong PointerAt(ulong address) => CurrentBuildPlayerLookup.Pointer(
            BinaryPrimitives.ReadUInt64LittleEndian(Take(address, 8)));
        var module = identity.ModuleBaseAddress;
        // The selected provider's getter has a statically verified direct chain.
        // Validate the dispatch slot without calling any game code.
        var manager = PointerAt(checked(module + 0x33724F0));
        var provider = PointerAt(checked(manager + 0x1B0));
        var providerVtable = PointerAt(provider);
        if (providerVtable != module + 0x2710320 ||
            PointerAt(providerVtable + 0xB8) != module + 0xF88580)
            throw new InvalidDataException("Optical camera selected mode is unsupported.");
        var owner = PointerAt(module + 0x3362848);
        var wrapper = PointerAt(checked(owner + 0x78));
        if (PointerAt(wrapper) != module + 0x27106A8)
            throw new InvalidDataException("Optical camera wrapper type mismatch.");
        var camera = PointerAt(checked(wrapper + 0x28));
        if (PointerAt(camera) != module + 0x274D630)
            throw new InvalidDataException("Optical camera type mismatch.");
        var transform = Take(checked(camera + 0xD4), 48);
        var origin = Take(checked(CurrentBuildPlayerLookup.Pointer(playerSystem, 0x444) + 0x438), 12);
        var bits = new uint[15];
        var values = new float[15];
        var payload = transform.Concat(origin).ToArray();
        for (var i = 0; i < values.Length; i++)
        {
            bits[i] = BinaryPrimitives.ReadUInt32LittleEndian(payload.AsSpan(i * 4));
            values[i] = BitConverter.UInt32BitsToSingle(bits[i]);
        }
        if (values.Any(value => !float.IsFinite(value)))
            throw new InvalidDataException("Optical camera transform contains nonfinite values.");
        for (var row = 0; row < 3; row++)
        {
            for (var other = 0; other < 3; other++)
            {
                double dot = 0;
                for (var column = 0; column < 3; column++)
                    dot += (double)values[row * 3 + column] * values[other * 3 + column];
                if (Math.Abs(dot - (row == other ? 1 : 0)) > .001)
                    throw new InvalidDataException("Optical camera rotation is not orthonormal.");
            }
        }
        foreach (var anchor in anchors)
            CurrentBuildPlayerLookup.RequireSame(
                CurrentBuildPlayerLookup.Exact(session, anchor.Address, anchor.Bytes.Length), anchor.Bytes);
        if (session.Identity != identity) throw new InvalidDataException("Optical camera process epoch changed.");
        var forwardX = (double)values[0];
        var forwardY = (double)values[3];
        var forwardZ = (double)values[6];
        var horizontal = Math.Sqrt(forwardX * forwardX + forwardZ * forwardZ);
        return new("available-candidate", null, camera.ToString(CultureInfo.InvariantCulture),
            values[..9], values[9..12], values[12..15], bits,
            horizontal < 1e-8 ? null : Math.Atan2(forwardX, forwardZ) * 180 / Math.PI,
            Math.Atan2(forwardY, horizontal) * 180 / Math.PI,
            [(double)values[9] + values[12], (double)values[10] + values[13], (double)values[11] + values[14]]);
    }
}
