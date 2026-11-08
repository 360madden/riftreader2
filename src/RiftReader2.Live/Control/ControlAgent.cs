using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live.Control;

public sealed record ControlAgentConfiguration(
    int SchemaVersion, string HostAddress, int Port, string Token,
    string ExpectedMachineName, string ProcessName, string ExecutablePath,
    string ExecutableSha256, string OutputDirectory)
{
    public void Validate()
    {
        if (SchemaVersion != 1 || !IPAddress.TryParse(HostAddress, out var address)
            || address.AddressFamily != AddressFamily.InterNetwork
            || !IsPrivate(address.GetAddressBytes()) || Port is < 1024 or > 65535
            || Token.Length is < 32 or > 256
            || !string.Equals(ExpectedMachineName, Environment.MachineName, StringComparison.OrdinalIgnoreCase)
            || ProcessName != "rift_x64" || !Path.IsPathFullyQualified(ExecutablePath)
            || !Path.IsPathFullyQualified(OutputDirectory)
            || ExecutableSha256.Length != 64 || !ExecutableSha256.All(Uri.IsHexDigit))
            throw new InvalidDataException("Invalid control-agent configuration or machine binding.");
    }

    private static bool IsPrivate(byte[] bytes) => bytes[0] == 10
        || (bytes[0] == 172 && bytes[1] is >= 16 and <= 31)
        || (bytes[0] == 192 && bytes[1] == 168);
}

public sealed record ControlCommand(string Type, string Id, long Sequence, string Operation, JsonElement Payload);
public sealed record ControlPending(DesktopTarget Target, ControlAction Action);
public sealed record ControlArmRequest(string CaptureId, string ReviewNote);
public sealed record ControlActionRequest(string ArmToken, ControlAction Action);
public sealed record ControlIdentityRequest(
    string MachineName, int ProcessId, long ProcessStartUtcTicks, string ExecutableSha256)
{
    internal void Validate()
    {
        if (string.IsNullOrWhiteSpace(MachineName) || MachineName != MachineName.Trim()
            || ProcessId <= 0 || ProcessStartUtcTicks <= 0 || ProcessStartUtcTicks > DateTime.MaxValue.Ticks
            || ExecutableSha256 is null || ExecutableSha256.Length != 64
            || !ExecutableSha256.All(Uri.IsHexDigit))
            throw new InvalidDataException("Invalid expected identity; machine, process epoch and SHA-256 are required.");
    }

    internal void RequireMatch(DesktopTarget target)
    {
        Validate();
        if (MachineName != target.MachineName || ProcessId != target.ProcessId
            || ProcessStartUtcTicks != target.ProcessStartUtcTicks
            || !string.Equals(ExecutableSha256, target.ExecutableSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Fresh target does not match the expected identity.");
    }
}
public sealed record ControlIdentityResponse(
    int IdentityVersion, string HashMode, DateTimeOffset ObservedAtUtc, DesktopTarget Target);

/// <summary>Outbound-only, interactive-session input adapter. No arbitrary command execution.</summary>
public sealed class ControlAgent
{
    internal const int NativeReadLeaseVersion = 1;
    private static readonly JsonSerializerOptions Wire = new(JsonFormat.Options) { WriteIndented = false };
    private readonly ControlAgentConfiguration configuration;
    private readonly string instanceId = Guid.NewGuid().ToString("N");
    private readonly SemaphoreSlim writeLock = new(1, 1);
    private readonly object stateLock = new();
    private string? captureId;
    private DesktopTarget? reviewedTarget;
    private long capturedAt;
    private string? armToken;
    private long armedAt;
    private CancellationTokenSource? actionCancellation;
    private Task? activeAction;
    private Task? activeNativeRead;
    private CancellationTokenSource? nativeReadCancellation;
    private readonly Func<ControlAgentConfiguration, ControlIdentityRequest, CancellationToken,
        Task<ControlNativeVitalsResponse>> nativeVitalsCapture;
    private readonly Func<ControlAgentConfiguration, ControlIdentityRequest, CancellationToken,
        Task<ControlNativeXyzResponse>> nativeXyzCapture;
    private readonly Func<ControlIdentityRequest, CancellationToken, Task<IAsyncDisposable>> nativeReadLease;
    private string PendingPath => Path.Combine(configuration.OutputDirectory, "pending.json");

    public ControlAgent(ControlAgentConfiguration configuration)
        : this(configuration, ControlNativeVitals.CaptureAsync) { }

    internal ControlAgent(ControlAgentConfiguration configuration,
        Func<ControlAgentConfiguration, ControlIdentityRequest, CancellationToken,
            Task<ControlNativeVitalsResponse>> nativeVitalsCapture)
        : this(configuration, nativeVitalsCapture, ControlNativeXyz.CaptureAsync) { }

    internal ControlAgent(ControlAgentConfiguration configuration,
        Func<ControlAgentConfiguration, ControlIdentityRequest, CancellationToken,
            Task<ControlNativeVitalsResponse>> nativeVitalsCapture,
        Func<ControlAgentConfiguration, ControlIdentityRequest, CancellationToken,
            Task<ControlNativeXyzResponse>> nativeXyzCapture)
        : this(configuration, nativeVitalsCapture, nativeXyzCapture, AcquireNativeReadLeaseAsync) { }

    // Injectable lease is an explicit offline test seam; production uses the shared file lease.
    internal ControlAgent(ControlAgentConfiguration configuration,
        Func<ControlAgentConfiguration, ControlIdentityRequest, CancellationToken,
            Task<ControlNativeVitalsResponse>> nativeVitalsCapture,
        Func<ControlAgentConfiguration, ControlIdentityRequest, CancellationToken,
            Task<ControlNativeXyzResponse>> nativeXyzCapture,
        Func<ControlIdentityRequest, CancellationToken, Task<IAsyncDisposable>> nativeReadLease)
    {
        configuration.Validate();
        ArgumentNullException.ThrowIfNull(nativeReadLease);
        this.nativeReadLease = nativeReadLease;
        this.nativeXyzCapture = nativeXyzCapture;
        this.nativeVitalsCapture = nativeVitalsCapture;
        this.configuration = configuration;
        Directory.CreateDirectory(configuration.OutputDirectory);
    }

    private static async Task<IAsyncDisposable> AcquireNativeReadLeaseAsync(
        ControlIdentityRequest identity, CancellationToken token) =>
        await NativeReadFileLease.AcquireAsync(identity.ProcessId, identity.ProcessStartUtcTicks,
            identity.ExecutableSha256.ToUpperInvariant(), TimeSpan.FromSeconds(1), token);

    public static async Task<int> RunAsync(string[] args, CancellationToken cancellationToken)
    {
        if (args.Length != 3 || args[1] != "--config")
        {
            Console.Error.WriteLine("Usage: control-agent --config ABSOLUTE_CONFIG.json");
            return 2;
        }
        try
        {
            var configBytes = await ReadBoundedFileAsync(args[2], 65_536, cancellationToken);
            var config = JsonSerializer.Deserialize<ControlAgentConfiguration>(configBytes, JsonFormat.Options)
                ?? throw new InvalidDataException("Null control configuration.");
            config.Validate();
            var mutexName = "Local\\RiftReader2-Control-" +
                Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(config.ProcessName)))[..16];
            using var owner = new Semaphore(1, 1, mutexName);
            if (!owner.WaitOne(0))
                throw new InvalidOperationException("Another RR2 control agent owns this session.");
            try
            {
                var agent = new ControlAgent(config);
                await ControlAgentLifetime.RunAsync(config.OutputDirectory,
                    agent.RunConnectionLoopAsync, cancellationToken);
            }
            finally { owner.Release(); }
            return 0;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { return 0; }
        catch (Exception exception)
        {
            Console.Error.WriteLine($"Control agent failed: {exception.GetType().Name}: {exception.Message}");
            return 2;
        }
    }

    private DesktopTarget Inspect() => WindowsControlDesktop.Inspect(
        configuration.ProcessName, configuration.ExecutablePath, configuration.ExecutableSha256);

    private async Task RunConnectionLoopAsync(CancellationToken cancellationToken)
    {
        Console.WriteLine($"RR2 control agent {instanceId}; starts disarmed; no unattended input.");
        var readinessWritten = false;
        while (!cancellationToken.IsCancellationRequested)
        {
            using var client = new TcpClient { NoDelay = true };
            try
            {
                using var connectTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
                connectTimeout.CancelAfter(TimeSpan.FromSeconds(5));
                await client.ConnectAsync(configuration.HostAddress, configuration.Port, connectTimeout.Token);
                using var stream = client.GetStream();
                using var reader = new StreamReader(stream, new UTF8Encoding(false, true), false, 4096, true);
                await SendAsync(stream, new
                {
                    type = "hello",
                    token = configuration.Token,
                    instanceId,
                    machineName = Environment.MachineName,
                    targetedClickVersion = 1
                }, cancellationToken);
                using var welcome = JsonDocument.Parse(await ReadLineAsync(reader, cancellationToken));
                if (welcome.RootElement.GetProperty("type").GetString() != "welcome")
                    throw new InvalidDataException("Host authentication handshake failed.");
                if (!readinessWritten)
                {
                    using var process = Process.GetCurrentProcess();
                    await WriteAtomicAsync(Path.Combine(configuration.OutputDirectory, "ready.json"),
                        new
                        {
                            instanceId,
                            processId = process.Id,
                            processStartUtcTicks = process.StartTime.ToUniversalTime().Ticks,
                            gracefulShutdownVersion = 1,
                            connectedAtUtc = DateTimeOffset.UtcNow
                        },
                        cancellationToken, false);
                    readinessWritten = true;
                }
                long sequence = 0;
                var requestIds = new HashSet<string>(StringComparer.Ordinal);
                while (!cancellationToken.IsCancellationRequested)
                {
                    var command = JsonSerializer.Deserialize<ControlCommand>(
                        await ReadLineAsync(reader, cancellationToken), JsonFormat.Options)
                        ?? throw new InvalidDataException("Null command.");
                    if (command.Type != "command" || command.Sequence <= sequence
                        || !Guid.TryParseExact(command.Id, "N", out _)
                        || !requestIds.Add(command.Id) || requestIds.Count > 4096
                        || File.Exists(Path.Combine(configuration.OutputDirectory, command.Id + ".json")))
                        throw new InvalidDataException("Invalid or replayed command.");
                    sequence = command.Sequence;
                    await DispatchCommandAsync(stream, command, cancellationToken);
                }
            }
            catch (Exception exception) when (!cancellationToken.IsCancellationRequested)
            {
                Console.WriteLine($"Control connection unavailable ({exception.GetType().Name}); disarming.");
            }
            finally
            {
                nativeReadCancellation?.Cancel();
                Disarm();
                captureId = null;
                var pendingRead = activeNativeRead;
                if (pendingRead is not null)
                {
                    try { await pendingRead; }
                    catch (Exception) { /* Session disposal must finish before reconnect. */ }
                }
                var pendingTask = activeAction;
                if (pendingTask is not null)
                {
                    try { await pendingTask; }
                    catch (Exception) { /* Pending journal survives failure to deliver response. */ }
                }
                reviewedTarget = null;
            }
            await Task.Delay(1000, cancellationToken);
        }
    }

    internal async Task DispatchCommandAsync(NetworkStream stream, ControlCommand command, CancellationToken token)
    {
        Task? refusal = null;
        if (command.Operation is "native-vitals" or "native-xyz")
        {
            lock (stateLock)
            {
                if (activeNativeRead is { IsCompleted: false })
                    refusal = ReplyAsync(stream, command,
                        new { error = "Native read still active.", errorType = "InvalidOperationException" }, token);
                else
                {
                    nativeReadCancellation?.Dispose();
                    nativeReadCancellation = CancellationTokenSource.CreateLinkedTokenSource(token);
                    nativeReadCancellation.CancelAfter(TimeSpan.FromSeconds(5));
                    activeNativeRead = HandleNativeReadAsync(stream, command, nativeReadCancellation.Token);
                }
            }
        }
        else if (command.Operation == "action")
        {
            lock (stateLock)
            {
                if (activeNativeRead is { IsCompleted: false })
                    refusal = ReplyAsync(stream, command,
                        new { error = "Native read still active.", errorType = "InvalidOperationException" }, token);
                else
                {
                    if (activeAction is { IsCompleted: false })
                        throw new InvalidDataException("Concurrent action rejected; connection disarmed.");
                    actionCancellation?.Dispose();
                    actionCancellation = CancellationTokenSource.CreateLinkedTokenSource(token);
                    activeAction = HandleActionAsync(stream, command, actionCancellation.Token);
                }
            }
        }
        else
            await HandleCommandAsync(stream, command, token);
        if (refusal is not null)
            await refusal;
    }

    private async Task HandleNativeReadAsync(NetworkStream stream, ControlCommand command, CancellationToken token)
    {
        await Task.Yield();
        object response;
        try
        {
            if (activeAction is { IsCompleted: false } || IsArmed() || File.Exists(PendingPath))
                throw new InvalidOperationException("Native reads require disarmed, idle control with no pending recovery.");
            var identity = command.Payload.Deserialize<ControlIdentityRequest>(JsonFormat.Options)
                ?? throw new InvalidDataException("Missing expected identity.");
            identity.Validate();
            token.ThrowIfCancellationRequested();
            await using var lease = await nativeReadLease(identity, token);
            token.ThrowIfCancellationRequested();
            if (command.Operation == "native-xyz")
            {
                var result = await nativeXyzCapture(configuration, identity, token);
                token.ThrowIfCancellationRequested();
                response = result with { InstanceId = instanceId };
            }
            else
            {
                var result = await nativeVitalsCapture(configuration, identity, token);
                token.ThrowIfCancellationRequested();
                response = result with { InstanceId = instanceId };
            }
        }
        catch (Exception exception)
        {
            response = new { error = exception.Message, errorType = exception.GetType().Name };
        }
        await ReplyAsync(stream, command, response, CancellationToken.None);
    }

    private async Task HandleCommandAsync(NetworkStream stream, ControlCommand command, CancellationToken token)
    {
        object response;
        try
        {
            switch (command.Operation)
            {
                case "status":
                    response = new
                    {
                        instanceId,
                        targetedClickVersion = 1,
                        freshIdentityVersion = 1,
                        nativeVitalsVersion = 1,
                        nativeXyzVersion = 1,
                        nativeReadLeaseVersion = NativeReadLeaseVersion,
                        gracefulShutdownVersion = 1,
                        target = Inspect(),
                        armed = IsArmed(),
                        expiresInSeconds = IsArmed() ? Math.Max(0, 15 - Stopwatch.GetElapsedTime(armedAt).TotalSeconds) : 0,
                        busy = activeAction is { IsCompleted: false } || activeNativeRead is { IsCompleted: false },
                        nativeReadBusy = activeNativeRead is { IsCompleted: false },
                        recoveryRequired = File.Exists(PendingPath),
                        desktopInputsDown = WindowsControlDesktop.ReadPressedInputs(),
                        desktopInputEvidence = "Sampled Windows key/button state, not RIFT consumption or ownership.",
                        nativeTextEntryState = "unknown",
                        responseVerified = false
                    };
                    break;
                case "identity":
                    RequireIdle();
                    var identity = command.Payload.Deserialize<ControlIdentityRequest>(JsonFormat.Options)
                        ?? throw new InvalidDataException("Missing expected identity.");
                    response = InspectFreshIdentity(identity, () => WindowsControlDesktop.InspectFreshIdentity(
                        configuration.ProcessName, configuration.ExecutablePath,
                        configuration.ExecutableSha256, identity));
                    break;
                case "stop":
                    StopSession();
                    if (activeAction is not null)
                        await activeAction;
                    response = new { stopped = true, recoveryRequired = File.Exists(PendingPath) };
                    break;
                case "release":
                    CancelActiveAction();
                    if (activeAction is not null)
                        await activeAction;
                    response = new { released = true, armed = IsArmed(), recoveryRequired = File.Exists(PendingPath) };
                    break;
                case "recover":
                    RequireNoNativeRead();
                    BeginRecovery();
                    if (activeAction is not null)
                        await activeAction;
                    response = await RecoverAsync(token);
                    break;
                case "capture":
                    RequireIdle();
                    BeginCapture();
                    var target = Inspect();
                    if (!target.IsForeground)
                        throw new InvalidOperationException("RIFT must already be foreground.");
                    var image = WindowsControlDesktop.CaptureBmp(target);
                    if (image.Length > 10 * 1024 * 1024)
                        throw new InvalidDataException("Control screenshot exceeds 10 MiB; use a smaller window.");
                    var after = Inspect();
                    if (target != after)
                        throw new InvalidOperationException("Target changed during capture.");
                    var id = Guid.NewGuid().ToString("N");
                    await File.WriteAllBytesAsync(Path.Combine(configuration.OutputDirectory, id + ".bmp"), image, token);
                    captureId = id;
                    reviewedTarget = target;
                    capturedAt = Stopwatch.GetTimestamp();
                    response = new ControlCaptureResponse(captureId, target, "bmp",
                        Convert.ToBase64String(image), Convert.ToHexString(SHA256.HashData(image)),
                        DateTimeOffset.UtcNow, 45, "window-client-gdi-unqualified-until-visual-review");
                    break;
                case "arm":
                    RequireIdle();
                    var request = command.Payload.Deserialize<ControlArmRequest>(JsonFormat.Options)
                        ?? throw new InvalidDataException("Missing arm request.");
                    if (File.Exists(PendingPath))
                        throw new InvalidOperationException("Recover pending release intent before arming.");
                    if (!CanArm(request, Inspect()))
                        throw new InvalidOperationException("Review missing, stale or target changed.");
                    armToken = Guid.NewGuid().ToString("N");
                    armedAt = Stopwatch.GetTimestamp();
                    captureId = null; // The review can authorize exactly one finite arm session.
                    response = new { armToken, expiresInSeconds = 15, target = reviewedTarget };
                    break;
                default:
                    throw new InvalidDataException("Unknown operation.");
            }
        }
        catch (Exception exception)
        {
            response = new { error = exception.Message, errorType = exception.GetType().Name };
        }
        await ReplyAsync(stream, command, response, token);
    }

    internal static ControlIdentityResponse InspectFreshIdentity(
        ControlIdentityRequest expectedIdentity, Func<DesktopTarget> inspectFresh)
    {
        expectedIdentity.Validate();
        var target = inspectFresh();
        expectedIdentity.RequireMatch(target);
        return new ControlIdentityResponse(1, "fresh-bytes", DateTimeOffset.UtcNow, target);
    }

    private async Task HandleActionAsync(NetworkStream stream, ControlCommand command, CancellationToken token)
    {
        // Yield before taking the state lock so dispatch can publish activeAction first.
        await Task.Yield();
        object response;
        object? cursorPreparation = null;
        var started = Stopwatch.GetTimestamp();
        try
        {
            var request = command.Payload.Deserialize<ControlActionRequest>(JsonFormat.Options)
                ?? throw new InvalidDataException("Missing action.");
            if (!IsArmed() || request.ArmToken != armToken || reviewedTarget != Inspect())
                throw new InvalidOperationException("Control session is disarmed, expired or target changed.");
            if (File.Exists(PendingPath))
                throw new InvalidOperationException("Recovery required.");
            BoundedControlExecutor.Validate(request.Action);
            var target = reviewedTarget!;
            response = await ExecuteActionUnderNativeLeaseAsync(target, request.ArmToken, async () =>
            {
                var pending = new ControlPending(target, request.Action);
                await WriteAtomicAsync(PendingPath, pending, token, false);
                token.ThrowIfCancellationRequested();
                if (!IsArmed() || target != Inspect())
                    throw new InvalidOperationException("Control target changed before cursor setup.");
                if (request.Action.ClickTarget is { } click)
                {
                    cursorPreparation = WindowsControlDesktop.PrepareTargetedClick(target, click);
                    // Allow hover to settle; the button-down path rechecks position and window.
                    await Task.Delay(50, token);
                }
                else if (request.Action.MouseButton is not null || request.Action.WheelNotches != 0)
                {
                    var placement = WindowsControlDesktop.PrepareCursor(
                        target, request.Action.DeltaX, request.Action.DeltaY);
                    cursorPreparation = placement;
                    if (placement.Repositioned)
                    {
                        // Let the game consume positioning before a drag starts.
                        // This is outside the input hold and remains cancellable.
                        var settledAt = Stopwatch.GetTimestamp();
                        while (Stopwatch.GetElapsedTime(settledAt).TotalMilliseconds < 50)
                        {
                            token.ThrowIfCancellationRequested();
                            if (!IsArmed() || target != Inspect())
                                throw new InvalidOperationException("Control target changed during cursor preparation.");
                            await Task.Delay(10, token);
                        }
                    }
                }
                token.ThrowIfCancellationRequested();
                var input = new BoundInput(this, target, request.Action.ClickTarget);
                var result = await new BoundedControlExecutor(input).ExecuteAsync(request.Action, token);
                if (result.ReleaseSucceeded)
                    File.Delete(PendingPath);
                if (result.RequiresCallerDisarm || result.TargetLost || (!result.DeliverySucceeded && !result.Cancelled))
                    Disarm();
                return (object)new
                {
                    result,
                    target,
                    action = request.Action,
                    inputEvents = input.Events,
                    cursorPreparation,
                    cursorRestoration = "none; cursor remains under game control",
                    startedAtUtc = DateTimeOffset.UtcNow - Stopwatch.GetElapsedTime(started),
                    completedAtUtc = DateTimeOffset.UtcNow,
                    elapsedMilliseconds = Stopwatch.GetElapsedTime(started).TotalMilliseconds,
                    recoveryRequired = File.Exists(PendingPath),
                    responseEvidence = request.Action.WheelNotches != 0
                        ? "Wheel window-message dispatch only; compare a later independent frame to establish zoom."
                        : "Windows input insertion and release only; compare a later independent frame/API observation."
                };
            }, token);
        }
        catch (Exception exception)
        {
            Disarm();
            response = new { error = exception.Message, errorType = exception.GetType().Name, recoveryRequired = File.Exists(PendingPath) };
        }
        // Cancellation must not erase the release outcome from disk.
        await ReplyAsync(stream, command, response, CancellationToken.None);
    }

    /// <summary>
    /// Excludes participating native readers only during new action input and its
    /// release/journal outcome. Not an arm-wide lock or proof of globally clean input;
    /// failed release still requires pending recovery. STOP/key-up never wait here.
    /// </summary>
    internal async Task<T> ExecuteActionUnderNativeLeaseAsync<T>(DesktopTarget target,
        string expectedArmToken, Func<Task<T>> actionBody, CancellationToken token,
        Func<DesktopTarget>? inspectForTest = null)
    {
        ArgumentNullException.ThrowIfNull(target);
        ArgumentNullException.ThrowIfNull(actionBody);
        var inspect = inspectForTest ?? Inspect;
        void RequireAdmission()
        {
            token.ThrowIfCancellationRequested();
            if (!IsArmed() || expectedArmToken != armToken || reviewedTarget != target || target != inspect())
                throw new InvalidOperationException("Control session changed or expired while awaiting native-read exclusion.");
            if (File.Exists(PendingPath))
                throw new InvalidOperationException("Recovery required before new action input.");
        }
        RequireAdmission();
        var identity = new ControlIdentityRequest(target.MachineName, target.ProcessId,
            target.ProcessStartUtcTicks, target.ExecutableSha256.ToUpperInvariant());
        identity.Validate();
        // Never hold stateLock/writeLock across this await. The existing action token
        // cancels the wait on STOP/release; waiting never extends the 15-second arm.
        await using var lease = await nativeReadLease(identity, token)
            ?? throw new InvalidDataException("Action native-read exclusion returned no lease.");
        RequireAdmission();
        // Production body begins with PendingPath creation and retains the lease
        // through cursor preparation, executor's release finally and journal outcome.
        return await actionBody();
    }

    private async Task<object> RecoverAsync(CancellationToken token)
    {
        if (!File.Exists(PendingPath))
            return new { recovered = true, inputSent = false, recoveryRequired = false };
        var pending = JsonSerializer.Deserialize<ControlPending>(
            await ReadBoundedFileAsync(PendingPath, 65_536, token), JsonFormat.Options)
            ?? throw new InvalidDataException("Invalid release journal.");
        BoundedControlExecutor.Validate(pending.Action);
        var current = Inspect();
        if (!SameProcess(pending.Target, current))
            throw new InvalidOperationException("Pending journal belongs to another game epoch; no input sent. Retain it for manual review.");
        var errors = new List<string>();
        foreach (var key in pending.Action.Keys)
        {
            try { WindowsControlDesktop.SendKeys(key, false); }
            catch (Exception exception) { errors.Add(exception.GetType().Name); }
        }
        if (pending.Action.MouseButton is not null)
        {
            try { WindowsControlDesktop.SendMouseButton(ParseButton(pending.Action.MouseButton), false); }
            catch (Exception exception) { errors.Add(exception.GetType().Name); }
        }
        if (errors.Count == 0)
            File.Delete(PendingPath);
        return new { recovered = errors.Count == 0, inputSent = true, recoveryRequired = errors.Count != 0, errors };
    }

    private bool IsArmed() => armToken is not null && Stopwatch.GetElapsedTime(armedAt).TotalSeconds < 15;
    private void RequireIdle()
    {
        if (activeAction is { IsCompleted: false })
            throw new InvalidOperationException("Action still active.");
        RequireNoNativeRead();
    }
    private void RequireNoNativeRead()
    {
        if (activeNativeRead is { IsCompleted: false })
            throw new InvalidOperationException("Native read still active.");
    }
    private void Disarm()
    {
        armToken = null;
        actionCancellation?.Cancel();
    }
    private void CancelActiveAction() => actionCancellation?.Cancel();
    private void BeginRecovery() => StopSession();
    private void BeginCapture() => StopSession();
    private void StopSession()
    {
        nativeReadCancellation?.Cancel();
        Disarm();
        captureId = null;
        reviewedTarget = null;
        capturedAt = 0;
    }
    private bool CanArm(ControlArmRequest request, DesktopTarget currentTarget) =>
        request.CaptureId == captureId && captureId is not null
        && Stopwatch.GetElapsedTime(capturedAt).TotalSeconds <= 45
        && request.ReviewNote.Trim().Length is >= 12 and <= 1024
        && reviewedTarget == currentTarget;
    private static bool SameProcess(DesktopTarget a, DesktopTarget b) =>
        a.MachineName == b.MachineName && a.ProcessId == b.ProcessId
        && a.ProcessStartUtcTicks == b.ProcessStartUtcTicks && a.WindowHandle == b.WindowHandle
        && a.ExecutablePath == b.ExecutablePath && a.ExecutableSha256 == b.ExecutableSha256;
    private static MouseButton ParseButton(string value) =>
        value == "left" ? MouseButton.Left : value == "right" ? MouseButton.Right
            : throw new InvalidDataException("Invalid mouse button.");

    private sealed class BoundInput(ControlAgent owner, DesktopTarget target, ClickTarget? clickTarget = null) : IControlInput
    {
        private readonly long started = Stopwatch.GetTimestamp();
        public List<object> Events { get; } = [];
        private void Record(string kind, object value) => Events.Add(new
        {
            kind,
            value,
            timestampUtc = DateTimeOffset.UtcNow,
            elapsedMilliseconds = Stopwatch.GetElapsedTime(started).TotalMilliseconds
        });
        public bool IsTargetCurrent() => owner.IsArmed() && owner.Inspect() == target;
        private void RequireTarget()
        {
            if (!IsTargetCurrent())
                throw new InvalidOperationException("Target changed immediately before input.");
        }
        public void KeyDown(string key)
        {
            RequireTarget();
            WindowsControlDesktop.SendKeys(key, true);
            Record("keyDownInserted", key);
        }
        public void KeyUp(string key)
        {
            WindowsControlDesktop.SendKeys(key, false);
            Record("keyUpInserted", key);
        }
        public void ButtonDown(string button)
        {
            RequireTarget();
            if (clickTarget is not null)
            {
                WindowsControlDesktop.RequireTargetedClickWindow(target);
                var position = WindowsControlDesktop.GetCursorPosition();
                WindowsControlDesktop.ValidateTargetedClickPosition(target, clickTarget, position);
                Record("targetedClickPositionVerified", position);
            }
            WindowsControlDesktop.SendMouseButton(ParseButton(button), true);
            Record("buttonDownInserted", button);
        }
        public void ButtonUp(string button)
        {
            WindowsControlDesktop.SendMouseButton(ParseButton(button), false);
            Record("buttonUpInserted", button);
        }
        public void MoveRelative(int dx, int dy)
        {
            RequireTarget();
            WindowsControlDesktop.MoveRelative(dx, dy);
            Record("relativeMoveInserted", new { dx, dy });
        }
        public void Wheel(int notches)
        {
            RequireTarget();
            WindowsControlDesktop.WheelToWindow(target, notches);
            Record("wheelMessageDispatched", new
            {
                notches,
                backend = "WM_MOUSEWHEEL",
                timeoutMilliseconds = 100
            });
        }
    }

    private async Task ReplyAsync(NetworkStream stream, ControlCommand command, object payload, CancellationToken token)
    {
        var response = new { type = "response", id = command.Id, payload };
        var retained = RetainResponsePayload(payload);
        await WriteAtomicAsync(Path.Combine(configuration.OutputDirectory, command.Id + ".json"),
            new { instanceId, command.Id, command.Sequence, command.Operation, response = retained }, CancellationToken.None, false);
        await SendAsync(stream, response, token);
    }

    internal static System.Text.Json.Nodes.JsonNode? RetainResponsePayload(object payload)
    {
        var metadata = payload is ControlCaptureResponse capture ? capture.RetainedMetadata() : payload;
        var retained = JsonSerializer.SerializeToNode(metadata, Wire);
        if (retained is System.Text.Json.Nodes.JsonObject fields)
        {
            fields.Remove("armToken");
            fields.Remove("imageBase64");
        }
        return retained;
    }

    private async Task SendAsync(NetworkStream stream, object value, CancellationToken token)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
        deadline.CancelAfter(TimeSpan.FromSeconds(5));
        var bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(value, Wire) + "\n");
        await writeLock.WaitAsync(deadline.Token);
        try { await stream.WriteAsync(bytes, deadline.Token); }
        finally { writeLock.Release(); }
    }

    internal static async Task<string> ReadLineAsync(StreamReader reader, CancellationToken token)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
        // An idle connection must outlive the 45-second review plus 15-second arm.
        // Input safety is enforced independently by the arm and action deadlines.
        deadline.CancelAfter(TimeSpan.FromSeconds(120));
        var text = new StringBuilder();
        var character = new char[1];
        while (text.Length <= 65_536)
        {
            if (await reader.ReadAsync(character, deadline.Token) == 0)
                throw new EndOfStreamException();
            if (character[0] == '\n')
                return text.ToString();
            text.Append(character[0]);
        }
        throw new InvalidDataException("Control command exceeds 65536 characters.");
    }

    private static async Task<byte[]> ReadBoundedFileAsync(string path, int max, CancellationToken token)
    {
        using var stream = File.OpenRead(path);
        var buffer = new byte[max + 1];
        var length = await stream.ReadAtLeastAsync(buffer, max + 1, false, token);
        if (length > max)
            throw new InvalidDataException("Control file exceeds limit.");
        return buffer[..length];
    }

    private static async Task WriteAtomicAsync(string path, object value, CancellationToken token, bool overwrite = true)
    {
        var temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            await using (var file = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None,
                4096, FileOptions.WriteThrough))
            {
                await file.WriteAsync(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(value, JsonFormat.Options)), token);
                await file.FlushAsync(token);
                file.Flush(flushToDisk: true);
            }
            File.Move(temp, path, overwrite);
        }
        finally
        {
            if (File.Exists(temp))
                File.Delete(temp);
        }
    }
}
