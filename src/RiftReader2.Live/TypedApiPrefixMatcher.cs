using System.Text;

namespace RiftReader2.Live;

/// <summary>
/// Finds possible typed-API frame prefixes in contiguous read-only memory chunks.
/// A prefix is not a verified frame; callers must independently inspect saved snapshots.
/// </summary>
public sealed class TypedApiPrefixMatcher
{
    public const string MarkerText = "RRAPIVAL2|";
    public const int MaxSupportedMatches = 128;

    public const string ReferenceMarkerText = "RR2R1|";
    // The unbound Lua producer publishes RR2A1 before any manual reader nonce.
    // Matching its bytes is discovery only, never a live/freshness qualification.
    public const string BaselineMarkerText = "RR2A1|";

    public static string ValidateMarker(string marker) => marker is MarkerText or ReferenceMarkerText or BaselineMarkerText
        ? marker : throw new ArgumentException("Unsupported typed API marker.", nameof(marker));

    private readonly byte[] MarkerBytes;
    private readonly int[] FailureTable;

    private readonly List<ulong> _addresses = [];
    private readonly int _maxMatches;
    private ulong? _nextExpectedAddress;
    private int _matchedLength;

    public TypedApiPrefixMatcher(string marker, int maxMatches = MaxSupportedMatches)
    {
        if (maxMatches is < 1 or > MaxSupportedMatches)
            throw new ArgumentOutOfRangeException(nameof(maxMatches));
        _maxMatches = maxMatches;
        MarkerBytes = Encoding.ASCII.GetBytes(ValidateMarker(marker));
        FailureTable = BuildFailureTable();
    }

    public IReadOnlyList<ulong> Addresses => _addresses;

    /// <summary>True only after an additional match would exceed the retained-address limit.</summary>
    public bool MatchBudgetExceeded { get; private set; }

    /// <summary>Address of the first complete marker that could not be retained.</summary>
    public ulong? FirstUnretainedAddress { get; private set; }

    /// <summary>Breaks prefix carry-over across holes, failed reads or unrelated regions.</summary>
    public void ResetMemoryBoundary()
    {
        _matchedLength = 0;
        _nextExpectedAddress = null;
    }

    public void Feed(ulong baseAddress, ReadOnlySpan<byte> bytes)
    {
        if (bytes.IsEmpty || MatchBudgetExceeded)
            return;

        // Reject an unrepresentable exclusive end before mutating the stream state.
        var endAddress = checked(baseAddress + (ulong)bytes.Length);
        if (_nextExpectedAddress != baseAddress)
            _matchedLength = 0;
        _nextExpectedAddress = endAddress;

        for (var i = 0; i < bytes.Length; i++)
        {
            var current = bytes[i];
            while (_matchedLength > 0 && current != MarkerBytes[_matchedLength])
                _matchedLength = FailureTable[_matchedLength - 1];
            if (current == MarkerBytes[_matchedLength])
                _matchedLength++;

            if (_matchedLength != MarkerBytes.Length)
                continue;

            if (_addresses.Count == _maxMatches)
            {
                FirstUnretainedAddress = checked(baseAddress + (ulong)i - (ulong)(MarkerBytes.Length - 1));
                MatchBudgetExceeded = true;
                _matchedLength = FailureTable[_matchedLength - 1];
                return;
            }

            _addresses.Add(checked(baseAddress + (ulong)i - (ulong)(MarkerBytes.Length - 1)));
            _matchedLength = FailureTable[_matchedLength - 1];
        }
    }

    private int[] BuildFailureTable()
    {
        var table = new int[MarkerBytes.Length];
        for (var i = 1; i < MarkerBytes.Length; i++)
        {
            var prefixLength = table[i - 1];
            while (prefixLength > 0 && MarkerBytes[i] != MarkerBytes[prefixLength])
                prefixLength = table[prefixLength - 1];
            if (MarkerBytes[i] == MarkerBytes[prefixLength])
                prefixLength++;
            table[i] = prefixLength;
        }
        return table;
    }
}
