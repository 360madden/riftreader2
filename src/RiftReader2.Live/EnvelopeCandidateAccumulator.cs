using System.Text;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

public sealed class EnvelopeCandidateAccumulator
{
    public const int MaxEndpointCandidates = 4096;
    public const int MaxValidCandidates = 256;
    private static readonly byte[] Suffix = "|ENDRR2L1"u8.ToArray();
    private readonly string challenge;
    private readonly byte[] prefix;
    private byte[] tail = [];
    private readonly List<ReadOnlyMemory<byte>> validCandidates = [];

    public EnvelopeCandidateAccumulator(string challenge)
    {
        if (challenge.Length != 32 || challenge.Any(character =>
                character is not (>= '0' and <= '9') and not (>= 'a' and <= 'f')))
            throw new ArgumentException("Challenge must be 32 lowercase hexadecimal characters.", nameof(challenge));
        this.challenge = challenge;
        prefix = Encoding.ASCII.GetBytes($"RR2L1|{challenge}|");
    }

    public IReadOnlyList<ReadOnlyMemory<byte>> ValidCandidates => validCandidates;
    public int EndpointCandidateCount { get; private set; }
    public int MalformedCandidateCount { get; private set; }
    public bool BudgetExceeded { get; private set; }

    public void ResetMemoryBoundary() => tail = [];

    public void Feed(ReadOnlySpan<byte> bytes)
    {
        if (bytes.Length == 0 || BudgetExceeded)
            return;
        var tailLength = tail.Length;
        var window = GC.AllocateUninitializedArray<byte>(tailLength + bytes.Length);
        tail.CopyTo(window, 0);
        bytes.CopyTo(window.AsSpan(tailLength));
        Extract(window, tailLength);
        var keep = Math.Min(LiveAddonEnvelopeDecoder.MaxEnvelopeBytes - 1, window.Length);
        tail = window[^keep..];
    }

    private void Extract(ReadOnlySpan<byte> window, int newDataOffset)
    {
        var prefixSearch = 0;
        while (prefixSearch <= window.Length - prefix.Length)
        {
            var relativePrefix = window[prefixSearch..].IndexOf(prefix);
            if (relativePrefix < 0)
                break;
            var start = prefixSearch + relativePrefix;
            var suffixSearch = start + prefix.Length;
            while (suffixSearch <= window.Length - Suffix.Length)
            {
                var relativeSuffix = window[suffixSearch..].IndexOf(Suffix);
                if (relativeSuffix < 0)
                    break;
                var end = suffixSearch + relativeSuffix + Suffix.Length;
                var length = end - start;
                if (length > LiveAddonEnvelopeDecoder.MaxEnvelopeBytes)
                    break;
                if (end > newDataOffset)
                {
                    if (EndpointCandidateCount >= MaxEndpointCandidates)
                    {
                        BudgetExceeded = true;
                        return;
                    }
                    EndpointCandidateCount++;
                    var candidate = window[start..end].ToArray();
                    try
                    {
                        _ = LiveAddonEnvelopeDecoder.Decode(candidate, challenge);
                        if (validCandidates.Count >= MaxValidCandidates)
                        {
                            BudgetExceeded = true;
                            return;
                        }
                        validCandidates.Add(candidate);
                    }
                    catch (InvalidDataException)
                    {
                        MalformedCandidateCount++;
                    }
                }
                suffixSearch = end - Suffix.Length + 1;
            }
            prefixSearch = start + 1;
        }
    }
}
