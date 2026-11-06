using System.Security.Cryptography;
using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

public static class LiveAddonEnvelopeDecoder
{
    private static readonly byte[] Prefix = "RR2L1|"u8.ToArray();
    private static readonly byte[] Suffix = "|ENDRR2L1"u8.ToArray();
    private const int ChallengeLength = 32;
    private const int SeparatorLength = 1;

    public const int MaxEnvelopeBytes = 4144;

    public static LiveAddonFrame Decode(ReadOnlySpan<byte> envelope, string expectedChallenge)
    {
        ValidateChallenge(expectedChallenge, nameof(expectedChallenge));
        var challenge = ReadChallenge(envelope, out var addonFrame);
        if (!string.Equals(challenge, expectedChallenge, StringComparison.Ordinal))
            throw new InvalidDataException("Live addon envelope challenge does not match the attachment challenge.");

        var observation = AddonFrameDecoder.Decode(addonFrame);
        return new LiveAddonFrame(
            challenge,
            observation,
            Convert.ToHexString(SHA256.HashData(envelope)),
            Convert.ToHexString(SHA256.HashData(addonFrame)));
    }

    internal static string ReadChallenge(ReadOnlySpan<byte> envelope, out ReadOnlySpan<byte> addonFrame)
    {
        var minimumLength = Prefix.Length + ChallengeLength + SeparatorLength + 1 + Suffix.Length;
        if (envelope.Length < minimumLength || envelope.Length > MaxEnvelopeBytes)
            throw new InvalidDataException($"Live addon envelope must contain {minimumLength} to {MaxEnvelopeBytes} bytes.");
        foreach (var value in envelope)
        {
            if (value > 0x7f)
                throw new InvalidDataException("Live addon envelope must contain ASCII bytes only.");
        }
        if (!envelope.StartsWith(Prefix) || !envelope.EndsWith(Suffix))
            throw new InvalidDataException("Live addon envelope markers are invalid.");

        var challengeBytes = envelope.Slice(Prefix.Length, ChallengeLength);
        foreach (var value in challengeBytes)
        {
            if (!IsLowerHex(value))
                throw new InvalidDataException("Live addon envelope challenge must be 32 lowercase hexadecimal characters.");
        }
        var separatorIndex = Prefix.Length + ChallengeLength;
        if (envelope[separatorIndex] != (byte)'|')
            throw new InvalidDataException("Live addon envelope challenge separator is invalid.");

        addonFrame = envelope[(separatorIndex + SeparatorLength)..^Suffix.Length];
        return System.Text.Encoding.ASCII.GetString(challengeBytes);
    }

    internal static void ValidateChallenge(string value, string parameterName)
    {
        ArgumentNullException.ThrowIfNull(value, parameterName);
        if (value.Length != ChallengeLength || value.Any(character =>
                character is not (>= '0' and <= '9') and not (>= 'a' and <= 'f')))
            throw new ArgumentException("Challenge must be 32 lowercase hexadecimal characters.", parameterName);
    }

    private static bool IsLowerHex(byte value) =>
        value is >= (byte)'0' and <= (byte)'9' or >= (byte)'a' and <= (byte)'f';
}
