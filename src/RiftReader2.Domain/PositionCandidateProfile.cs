namespace RiftReader2.Domain;

/// <summary>
/// Build-pinned native XYZ locator; its existence does not qualify field semantics.
/// </summary>
public sealed record PositionCandidateProfile(
    string ExecutableSha256,
    ulong RootRva,
    uint XOffset,
    uint YOffset,
    uint ZOffset)
{
    public int TerminalByteLength => checked((int)ZOffset + sizeof(float));

    public void Validate()
    {
        if (ExecutableSha256 is null || ExecutableSha256.Length != 64 ||
            ExecutableSha256.Any(character => !((character is >= '0' and <= '9') ||
                (character is >= 'A' and <= 'F'))))
            throw new InvalidDataException("Position profile requires an uppercase 64-character executable SHA-256.");
        if (XOffset >= YOffset || YOffset >= ZOffset || ZOffset > 4092 ||
            XOffset % 4 != 0 || YOffset % 4 != 0 || ZOffset % 4 != 0)
            throw new InvalidDataException("XYZ offsets must be distinct, ascending, float32-aligned, and within one 4096-byte terminal read.");
    }
}
