using System.Text;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class EnvelopeCandidateAccumulatorTests
{
    private const string Challenge = "0123456789abcdef0123456789abcdef";

    [Fact]
    public void Feed_ReassemblesEnvelopeAcrossEveryChunkBoundary()
    {
        var envelope = ValidEnvelope("player-1");

        for (var split = 1; split < envelope.Length; split++)
        {
            var accumulator = new EnvelopeCandidateAccumulator(Challenge);
            accumulator.Feed(envelope.AsSpan(0, split));
            accumulator.Feed(envelope.AsSpan(split));

            var candidate = Assert.Single(accumulator.ValidCandidates);
            Assert.True(candidate.Span.SequenceEqual(envelope));
        }
    }

    [Fact]
    public void Feed_UsesValidOuterSuffixWhenPlayerContainsSuffixText()
    {
        var envelope = ValidEnvelope("player-|ENDRR2L1");
        var accumulator = new EnvelopeCandidateAccumulator(Challenge);

        accumulator.Feed(envelope);

        var candidate = Assert.Single(accumulator.ValidCandidates);
        Assert.True(candidate.Span.SequenceEqual(envelope));
        Assert.True(accumulator.EndpointCandidateCount >= 2);
    }

    [Fact]
    public void Feed_IgnoresEnvelopeFromAnotherAttachment()
    {
        var other = Encoding.ASCII.GetBytes(
            Encoding.ASCII.GetString(ValidEnvelope("player-1")).Replace(Challenge, new string('a', 32), StringComparison.Ordinal));
        var accumulator = new EnvelopeCandidateAccumulator(Challenge);

        accumulator.Feed(other);

        Assert.Empty(accumulator.ValidCandidates);
        Assert.Equal(0, accumulator.EndpointCandidateCount);
    }

    [Fact]
    public void ResetMemoryBoundary_DoesNotJoinNoncontiguousRegions()
    {
        var envelope = ValidEnvelope("player-1");
        var split = envelope.Length / 2;
        var accumulator = new EnvelopeCandidateAccumulator(Challenge);

        accumulator.Feed(envelope.AsSpan(0, split));
        accumulator.ResetMemoryBoundary();
        accumulator.Feed(envelope.AsSpan(split));

        Assert.Empty(accumulator.ValidCandidates);
    }

    [Fact]
    public void Feed_ReportsMalformedCurrentChallengeWithoutPublishingCandidate()
    {
        var malformed = Encoding.ASCII.GetBytes($"RR2L1|{Challenge}|not-json|ENDRR2L1");
        var accumulator = new EnvelopeCandidateAccumulator(Challenge);

        accumulator.Feed(malformed);

        Assert.Empty(accumulator.ValidCandidates);
        Assert.Equal(1, accumulator.MalformedCandidateCount);
    }

    [Fact]
    public void Feed_StopsAtEndpointBudgetWithoutGrowingCandidateStorage()
    {
        var malformed = Encoding.ASCII.GetBytes($"RR2L1|{Challenge}|x|ENDRR2L1");
        var input = new byte[malformed.Length * (EnvelopeCandidateAccumulator.MaxEndpointCandidates + 1)];
        for (var offset = 0; offset < input.Length; offset += malformed.Length)
            malformed.CopyTo(input, offset);
        var accumulator = new EnvelopeCandidateAccumulator(Challenge);

        accumulator.Feed(input);

        Assert.True(accumulator.BudgetExceeded);
        Assert.Equal(EnvelopeCandidateAccumulator.MaxEndpointCandidates, accumulator.EndpointCandidateCount);
        Assert.Empty(accumulator.ValidCandidates);
    }

    private static byte[] ValidEnvelope(string player)
    {
        var escapedPlayer = System.Text.Json.JsonSerializer.Serialize(player);
        var addon =
            "RR2A1|{\"schemaVersion\":1,\"addonVersion\":\"0.1.0\",\"sequence\":1,\"epoch\":1," +
            "\"clock\":{\"status\":\"ok\",\"value\":10},\"player\":{\"status\":\"ok\",\"value\":" + escapedPlayer + "}," +
            "\"fields\":{\"coordX\":{\"status\":\"unavailable\"},\"coordY\":{\"status\":\"unavailable\"}," +
            "\"coordZ\":{\"status\":\"unavailable\"},\"health\":{\"status\":\"unavailable\"}," +
            "\"healthMax\":{\"status\":\"unavailable\"},\"combat\":{\"status\":\"unavailable\"}}}|ENDRR2A1";
        return Encoding.ASCII.GetBytes($"RR2L1|{Challenge}|{addon}|ENDRR2L1");
    }
}
