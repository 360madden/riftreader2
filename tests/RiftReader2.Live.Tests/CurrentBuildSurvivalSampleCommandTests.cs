using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildSurvivalSampleCommandTests
{
    private static readonly NativeProcessIdentity Identity = new(5, 100, "rift_x64.exe",
        new string('A', 64), 0x140000000, 0x4000000);
    private static readonly DateTimeOffset At = DateTimeOffset.UtcNow;

    private static CurrentBuildPlayerContextObservation Context(ulong key = 42, ulong? target = 84,
        int level = 12, byte combat = 0) => new(Identity, At.AddMilliseconds(-4), At,
        key, 1000, 2000, 3000, 4000, target ?? 0,
        target.HasValue ? "fallback-key-candidate" : "raw-getter-zero-candidate",
        target, target.HasValue ? $"u{target:X16}" : null, level,
        "numeric-getter-and-presentation-candidate", combat, "raw-byte-candidate", combat != 0);

    private static CurrentBuildVitalsObservation Vitals(ulong key, long health, long maximum) =>
        new(Identity, At.AddMilliseconds(-3), At, key,
            new("calculated-candidate", null, health, maximum),
            new("unavailable", "not-energy-kind-four"));

    private static SelectedTargetObservation Selected(bool available = true)
    {
        if (!available)
            return new(Identity, At.AddMilliseconds(-2), At, 42, "unavailable",
                "raw-getter-zero-candidate", null, null, null, null, null);
        var targetContext = new TargetRawContext("raw-typed-candidate", 9000, 15, 1, true,
            "numeric-getter-candidate", "owner", 15);
        return new(Identity, At.AddMilliseconds(-2), At, 42, "candidate",
            "fallback-key-candidate", "fallback-key-candidate", 84, "u0000000000000054",
            8000, Vitals(84, 0, 50), TargetContext: targetContext);
    }

    [Fact]
    public void ProjectionEmitsExplicitSelfAndSelectedTargetBooleans()
    {
        var values = CurrentBuildSurvivalSampleCommand.Project(Context(), Vitals(42, 80, 100), Selected());

        Assert.True(values.Player.Health.Available);
        Assert.False(values.Player.Health.Dead);
        Assert.True(values.Player.Combat.Available);
        Assert.False(values.Player.Combat.Value);
        Assert.Equal(12, values.Player.Level.Value);
        Assert.True(values.SelectedTarget.Available);
        Assert.True(values.SelectedTarget.Health.Dead);
        Assert.True(values.SelectedTarget.Combat.Value);
        Assert.Equal(15, values.SelectedTarget.Level.Value);
        Assert.False(values.SelectedTarget.Relation!.Available);
        Assert.Equal("native-relation-source-unavailable", values.SelectedTarget.Relation.Reason);
    }

    [Fact]
    public void MissingSelectionRemainsStructuredAndNeverInventsRelationOrDead()
    {
        var values = CurrentBuildSurvivalSampleCommand.Project(
            Context(target: null), Vitals(42, 80, 100), Selected(available: false));

        Assert.False(values.SelectedTarget.Available);
        Assert.Null(values.SelectedTarget.Key);
        Assert.False(values.SelectedTarget.Health.DeadAvailable);
        Assert.Null(values.SelectedTarget.Health.Dead);
        Assert.False(values.SelectedTarget.Combat.Available);
        Assert.Null(values.SelectedTarget.Combat.Value);
        Assert.False(values.SelectedTarget.Relation!.Available);
    }

    [Fact]
    public void MixedSelfOwnersAreRejected()
    {
        Assert.Throws<InvalidDataException>(() => CurrentBuildSurvivalSampleCommand.Project(
            Context(), Vitals(43, 80, 100), Selected()));
    }
}
