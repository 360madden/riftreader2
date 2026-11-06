using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

public sealed record NativePositionProfileFile(
    int SchemaVersion,
    string ContractVersion,
    string FieldId,
    string ExecutableSha256,
    string RootRva,
    IReadOnlyList<string> XyzOffsets,
    string Qualification,
    string EvidenceReference);

public sealed record LoadedNativePositionProfile(
    PositionCandidateProfile Profile,
    string SourceSha256,
    string EvidenceReference);

public static class NativePositionProfileLoader
{
    private const int MaximumBytes = 8192;

    public static async Task<LoadedNativePositionProfile> LoadAsync(
        string path, CancellationToken cancellationToken = default)
    {
        var bytes = await AddonFrameFile.ReadBoundedAsync(path, MaximumBytes, cancellationToken);
        if (bytes.Length is < 1 or > MaximumBytes)
            throw new InvalidDataException("Position profile must contain 1-8192 bytes.");
        var source = JsonSerializer.Deserialize<NativePositionProfileFile>(bytes, JsonFormat.Options)
            ?? throw new InvalidDataException("Position profile is empty.");
        if (source.SchemaVersion != 1 || source.ContractVersion != "native-position-profile/1" ||
            source.FieldId != "player.position.xyz" || source.Qualification != "candidate-only" ||
            string.IsNullOrWhiteSpace(source.EvidenceReference) || source.EvidenceReference.Length > 256 ||
            source.XyzOffsets is null || source.XyzOffsets.Count != 3)
            throw new InvalidDataException("Position profile has an unsupported contract, qualification, or coordinate layout.");
        var profile = new PositionCandidateProfile(
            source.ExecutableSha256,
            ParseHex(source.RootRva),
            checked((uint)ParseHex(source.XyzOffsets[0])),
            checked((uint)ParseHex(source.XyzOffsets[1])),
            checked((uint)ParseHex(source.XyzOffsets[2])));
        profile.Validate();
        return new(profile, Convert.ToHexString(SHA256.HashData(bytes)), source.EvidenceReference);
    }

    private static ulong ParseHex(string value)
    {
        if (string.IsNullOrEmpty(value) || !value.StartsWith("0x", StringComparison.Ordinal) ||
            value.Length < 3 || (value.Length > 3 && value[2] == '0') ||
            value.AsSpan(2).IndexOfAnyExcept("0123456789ABCDEF") >= 0 ||
            !ulong.TryParse(value.AsSpan(2), NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out var parsed))
            throw new InvalidDataException("Position profile addresses must use canonical uppercase 0x hexadecimal.");
        return parsed;
    }
}
