using RiftReader2.Domain;
using System.Text;

namespace RiftReader2.Infrastructure;

public static class LiveAddonCandidateSelector
{
    public static LiveAddonSelection Select(
        IEnumerable<ReadOnlyMemory<byte>> completeEnvelopeCandidates,
        string expectedChallenge,
        bool scanCompleted)
    {
        ArgumentNullException.ThrowIfNull(completeEnvelopeCandidates);
        LiveAddonEnvelopeDecoder.ValidateChallenge(expectedChallenge, nameof(expectedChallenge));
        if (!scanCompleted)
            return new(LiveAddonSelectionStatus.IncompleteScan, null, 0, 0, "scan-incomplete");

        var matchingPrefix = Encoding.ASCII.GetBytes($"RR2L1|{expectedChallenge}|");
        var groups = new Dictionary<long, List<(byte[] Bytes, LiveAddonFrame Frame, int Copies)>>();
        var matchingCount = 0;
        foreach (var candidateMemory in completeEnvelopeCandidates)
        {
            var candidate = candidateMemory.Span;
            // Old attachment envelopes are expected to remain in the Lua heap. Filter
            // them by the exact bound prefix before applying strict decoding to this
            // attachment's candidates.
            if (!candidate.StartsWith(matchingPrefix))
                continue;

            matchingCount++;
            var frame = LiveAddonEnvelopeDecoder.Decode(candidate, expectedChallenge);
            var bytes = candidate.ToArray();
            if (!groups.TryGetValue(frame.Observation.Sequence, out var versions))
            {
                versions = [];
                groups.Add(frame.Observation.Sequence, versions);
            }

            var identicalIndex = versions.FindIndex(item => item.Bytes.AsSpan().SequenceEqual(bytes));
            if (identicalIndex >= 0)
            {
                var identical = versions[identicalIndex];
                versions[identicalIndex] = (identical.Bytes, identical.Frame, identical.Copies + 1);
            }
            else
            {
                versions.Add((bytes, frame, 1));
                if (versions.Count > 1)
                    return new(LiveAddonSelectionStatus.Conflict, null, matchingCount, 0,
                        "same-sequence-conflicting-envelopes");
            }
        }

        if (groups.Count == 0)
            return new(LiveAddonSelectionStatus.NoMatchingCandidate, null, 0, 0, "matching-challenge-not-found");

        var selected = groups[groups.Keys.Max()][0];
        return new(LiveAddonSelectionStatus.Selected, selected.Frame, matchingCount, selected.Copies, null);
    }
}
