using RiftReader2.Application;

namespace RiftReader2.Tests;

public sealed class TurnSkeletonPlannerTests
{
    private static TurnSkeletonFacing Facing(double angle = 90, bool cached = false) =>
        new("current-build-position-matrix-primary", 6228, 639298670575905950,
            "u035400012DFEB5BC", angle, DateTimeOffset.UtcNow, cached);

    [Fact]
    public void ProbeReturnsExactlyOneBoundedAWithoutExecutingIt()
    {
        var action = TurnSkeletonPlanner.ProbeA();
        Assert.Equal(["a"], action.Keys);
        Assert.Equal(100, action.HoldMilliseconds);
        Assert.Null(action.MouseButton);
        Assert.Throws<ArgumentOutOfRangeException>(() => TurnSkeletonPlanner.ProbeA(300));
    }

    [Theory]
    [InlineData(359, 1, 2)]
    [InlineData(1, 359, -2)]
    [InlineData(180, 0, -180)]
    [InlineData(-1, 361, 2)]
    public void UsesShortestSignedCandidateDelta(double before, double target, double expected)
    {
        var plan = TurnSkeletonPlanner.PlanNext(Facing(before), target,
            new(10, true));
        Assert.Equal(expected, plan.SignedCandidateDeltaDegrees, 8);
        Assert.Equal("one-bounded-pulse-candidate", plan.Status);
    }

    [Fact]
    public void MappingSelectsAOrDAndClampsAtOnePulse()
    {
        var a = TurnSkeletonPlanner.PlanNext(Facing(), 130, new(100, true));
        Assert.Equal("a", Assert.Single(a.Action!.Keys));
        Assert.Equal(125, a.Action.HoldMilliseconds);
        Assert.Contains("candidate-matrix-planning-only", a.Qualification);
        var d = TurnSkeletonPlanner.PlanNext(Facing(), 130, new(100, false));
        Assert.Equal("d", Assert.Single(d.Action!.Keys));
        var opposite = TurnSkeletonPlanner.PlanNext(Facing(), 50, new(100, true));
        Assert.Equal("d", Assert.Single(opposite.Action!.Keys));
    }

    [Fact]
    public void CachedScaffoldKeepsItsProvenance()
    {
        var plan = TurnSkeletonPlanner.PlanNext(Facing(cached: true), 140, new(120, true));
        Assert.True(plan.Facing.IsCached);
        Assert.Equal("candidate-matrix-planning-only; never proof of player-facing or game-input success",
            plan.Qualification);
    }

    [Fact]
    public void DoesNotOvershootWithAnUnreliablyShortPulse()
    {
        var close = TurnSkeletonPlanner.PlanNext(Facing(), 90.5, new(100, true));
        Assert.Equal("within-tolerance", close.Status);
        Assert.Null(close.Action);
        var tiny = TurnSkeletonPlanner.PlanNext(Facing(), 93, new(200, true));
        Assert.Equal("below-minimum-pulse", tiny.Status);
        Assert.Null(tiny.Action);
    }

    [Fact]
    public void RejectsInvalidHeadingOrCalibrationBeforeSuggestingInput()
    {
        Assert.Throws<ArgumentException>(() => TurnSkeletonPlanner.PlanNext(
            Facing() with { GameProcessId = 0 }, 120, new(100, true)));
        Assert.Throws<ArgumentException>(() => TurnSkeletonPlanner.PlanNext(
            Facing(double.NaN), 120, new(100, true)));
        Assert.Throws<ArgumentOutOfRangeException>(() => TurnSkeletonPlanner.PlanNext(
            Facing(), double.PositiveInfinity, new(100, true)));
        Assert.Throws<ArgumentException>(() => TurnSkeletonPlanner.PlanNext(
            Facing(), 120, new(0, true)));
        Assert.Throws<ArgumentException>(() => TurnSkeletonPlanner.PlanNext(
            Facing(), 120, new(100, true, 125, 75)));
        Assert.Throws<ArgumentOutOfRangeException>(() => TurnSkeletonPlanner.PlanNext(
            Facing(), 120, new(100, true), -1));
    }
}
