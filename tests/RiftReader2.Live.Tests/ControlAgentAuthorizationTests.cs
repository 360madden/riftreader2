using System.Diagnostics;
using System.Reflection;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class ControlAgentAuthorizationTests
{
    private static readonly DesktopTarget Target = new(
        Environment.MachineName,
        123,
        456,
        "0x789",
        @"C:\RIFT Game\rift_x64.exe",
        new string('A', 64),
        true,
        100,
        200,
        1280,
        720);

    [Fact]
    public void CaptureThenStop_RejectsArmFromPreStopCapture()
    {
        var agent = CreateUninitializedAgent();
        SetReviewedCapture(agent, "capture-before-stop");
        var request = new ControlArmRequest("capture-before-stop", "reviewed target frame");
        Assert.True(CanArm(agent, request));

        Invoke(agent, "StopSession");

        Assert.False(CanArm(agent, request));
        Assert.Null(GetField(agent, "captureId"));
        Assert.Null(GetField(agent, "reviewedTarget"));
        Assert.Equal(0L, GetField(agent, "capturedAt"));
    }

    [Fact]
    public void NewCaptureAfterStop_CanAuthorizeArm()
    {
        var agent = CreateUninitializedAgent();
        SetReviewedCapture(agent, "old-capture");
        Invoke(agent, "StopSession");
        SetReviewedCapture(agent, "new-capture");

        Assert.True(CanArm(
            agent,
            new ControlArmRequest("new-capture", "new reviewed target frame")));
    }

    [Fact]
    public void ArmThenStop_DisarmsAndInvalidatesReview()
    {
        var agent = CreateUninitializedAgent();
        SetField(agent, "armToken", "active-arm-token");
        SetField(agent, "armedAt", Stopwatch.GetTimestamp());
        SetReviewedCapture(agent, "retained-capture");
        Assert.True(IsArmed(agent));

        Invoke(agent, "StopSession");

        Assert.False(IsArmed(agent));
        Assert.Null(GetField(agent, "armToken"));
        Assert.False(CanArm(
            agent,
            new ControlArmRequest("retained-capture", "reviewed target frame")));
    }

    [Theory]
    [InlineData("BeginRecovery")]
    [InlineData("BeginCapture")]
    public void FallibleLifecycleWork_InvalidatesOldReviewBeforeWorkBegins(string method)
    {
        var agent = CreateUninitializedAgent();
        SetReviewedCapture(agent, "obsolete-capture");
        var oldRequest = new ControlArmRequest("obsolete-capture", "reviewed target frame");
        Assert.True(CanArm(agent, oldRequest));

        Invoke(agent, method);
        // Simulate recovery or replacement capture failing before publishing new state.

        Assert.False(CanArm(agent, oldRequest));
        Assert.Null(GetField(agent, "captureId"));
        Assert.Null(GetField(agent, "reviewedTarget"));
    }

    [Fact]
    public void ReleaseCancellation_PreservesArmAndReviewState()
    {
        var agent = CreateUninitializedAgent();
        using var cancellation = new CancellationTokenSource();
        SetField(agent, "armToken", "active-arm-token");
        SetField(agent, "armedAt", Stopwatch.GetTimestamp());
        SetField(agent, "reviewedTarget", Target);
        SetField(agent, "actionCancellation", cancellation);

        Invoke(agent, "CancelActiveAction");

        Assert.True(cancellation.IsCancellationRequested);
        Assert.True(IsArmed(agent));
        Assert.Equal(Target, GetField(agent, "reviewedTarget"));
    }

    private static ControlAgent CreateUninitializedAgent() =>
        (ControlAgent)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(
            typeof(ControlAgent));

    private static void SetReviewedCapture(ControlAgent agent, string id)
    {
        SetField(agent, "captureId", id);
        SetField(agent, "reviewedTarget", Target);
        SetField(agent, "capturedAt", Stopwatch.GetTimestamp());
    }

    private static bool CanArm(ControlAgent agent, ControlArmRequest request) =>
        Assert.IsType<bool>(Invoke(agent, "CanArm", request, Target));

    private static bool IsArmed(ControlAgent agent) =>
        Assert.IsType<bool>(Invoke(agent, "IsArmed"));

    private static object? Invoke(ControlAgent agent, string methodName, params object[] arguments)
    {
        var method = typeof(ControlAgent).GetMethod(
            methodName,
            BindingFlags.Instance | BindingFlags.NonPublic);
        Assert.NotNull(method);
        return method.Invoke(agent, arguments);
    }

    private static void SetField(ControlAgent agent, string fieldName, object? value)
    {
        var field = typeof(ControlAgent).GetField(
            fieldName,
            BindingFlags.Instance | BindingFlags.NonPublic);
        Assert.NotNull(field);
        field.SetValue(agent, value);
    }

    private static object? GetField(ControlAgent agent, string fieldName)
    {
        var field = typeof(ControlAgent).GetField(
            fieldName,
            BindingFlags.Instance | BindingFlags.NonPublic);
        Assert.NotNull(field);
        return field.GetValue(agent);
    }
}
