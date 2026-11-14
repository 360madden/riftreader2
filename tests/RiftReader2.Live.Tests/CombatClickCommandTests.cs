using RiftReader2.Application;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class CombatClickCommandTests
{
    private const ulong Player = 42;
    private const ulong Target = 84;

    private static string[] Args(params string[] extra) =>
    [
        "--expected-host", "AMD-DESKTOP", "--pid", "5",
        "--expect-start-ticks", "100", "--expect-sha256", new string('A', 64),
        "--expect-hwnd", "0x8", "--expect-player-key", Player.ToString(),
        "--expect-target-key", Target.ToString(), "--owner-pid", "10",
        "--owner-start-ticks", "200", "--action-id", "controls.actions.primary",
        "--nonce", "producer-1", "--client-x", "-1920", "--client-y", "29",
        "--client-width", "1920", "--client-height", "1009",
        "--rect-x", "800", "--rect-y", "900", "--rect-width", "30", "--rect-height", "30",
        "--stop-file", @"C:\temp\combat.stop", "--execute", "--json", .. extra
    ];

    private static CombatClickCommand.TargetPins Pins(ulong player = Player, ulong target = Target)
    {
        var completed = DateTimeOffset.UtcNow;
        return new(player, target, completed.AddMilliseconds(-2), completed);
    }

    private sealed class Input : IControlInput
    {
        public readonly List<string> Events = [];
        public bool Current = true;
        public bool IsTargetCurrent() => Current;
        public void ButtonDown(string button) => Events.Add("down:" + button);
        public void ButtonUp(string button) => Events.Add("up:" + button);
        public void KeyDown(string _) => throw new NotSupportedException();
        public void KeyUp(string _) => throw new NotSupportedException();
        public void MoveRelative(int _, int __) => throw new NotSupportedException();
        public void Wheel(int _) => throw new NotSupportedException();
    }

    [Fact]
    public void ParserPinsReviewedGeometryAndExplicitActionIdentity()
    {
        var options = CombatClickCommand.Parse(Args());
        Assert.Equal("controls.actions.primary", options.ActionId);
        Assert.Equal("producer-1", options.Nonce);
        Assert.Equal((-1920, 29, 1920, 1009),
            (options.ClientX, options.ClientY, options.ClientWidth, options.ClientHeight));
        Assert.Equal((800, 900, 30, 30),
            (options.Rectangle.X, options.Rectangle.Y, options.Rectangle.Width, options.Rectangle.Height));
        Assert.False(options.Cleanup);
    }

    [Fact]
    public void CleanupRequiresExactIdempotentCancelAction()
    {
        Assert.Throws<InvalidDataException>(() => CombatClickCommand.Parse([.. Args(), "--cleanup"]));
        var args = Args();
        args[Array.IndexOf(args, "controls.actions.primary")] = "controls.cancel";
        var options = CombatClickCommand.Parse([.. args, "--cleanup"]);
        Assert.True(options.Cleanup);
        Assert.Equal("controls.cancel", options.ActionId);
    }

    [Fact]
    public async Task ReviewedPinsAreRecheckedAfterCursorPreparationBeforeOneClick()
    {
        var options = CombatClickCommand.Parse(Args());
        var input = new Input();
        var prepared = 0;
        var result = await CombatClickCommand.ExecuteReviewedClickAsync(options,
            _ => Task.FromResult(Pins()), () => null,
            () => { prepared++; return new(new(1, 2), new(3, 4), true); }, input);

        Assert.True(result.DeliverySucceeded);
        Assert.True(result.ReleaseSucceeded);
        Assert.Equal(1, prepared);
        Assert.Equal(["down:left", "up:left"], input.Events);
    }

    [Fact]
    public async Task ChangedSelectedTargetAfterPreparationSendsNoInput()
    {
        var options = CombatClickCommand.Parse(Args());
        var input = new Input();
        var reads = 0;
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            CombatClickCommand.ExecuteReviewedClickAsync(options,
                _ => Task.FromResult(++reads == 1 ? Pins() : Pins(target: Target + 1)),
                () => null, () => new(new(1, 2), new(3, 4), true), input));
        Assert.Empty(input.Events);
    }

    [Fact]
    public async Task StopOrOwnerSafetyRefusalOccursBeforePreparationAndInput()
    {
        var options = CombatClickCommand.Parse(Args());
        var input = new Input();
        var prepared = false;
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            CombatClickCommand.ExecuteReviewedClickAsync(options,
                _ => Task.FromResult(Pins()), () => "stop-file-requested",
                () => { prepared = true; return default; }, input));
        Assert.Equal("stop-file-requested", error.Message);
        Assert.False(prepared);
        Assert.Empty(input.Events);
    }
}
