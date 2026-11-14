using System.Diagnostics;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal static class Program
{
    private static async Task<int> Main(string[] args)
    {
        if (args.Length > 0)
        {
            using var commandCancellation = new CancellationTokenSource();
            Console.CancelKeyPress += (_, eventArgs) =>
            {
                eventArgs.Cancel = true;
                commandCancellation.Cancel();
            };
            if (args[0] == "control-agent")
                return await Control.ControlAgent.RunAsync(args, commandCancellation.Token);
            if (args[0] == "move-key")
                return await Control.MoveKeyCommand.RunAsync(args[1..], commandCancellation.Token);
            if (args[0] == "follow-route")
                return await Control.FollowRouteCommand.RunAsync(args[1..], commandCancellation.Token);
            if (args[0] == "combat-click")
                return await Control.CombatClickCommand.RunAsync(args[1..], commandCancellation.Token);
            if (args[0] == "sample-current-survival")
                return await CurrentBuildSurvivalSampleCommand.RunAsync(
                    args[1..], Console.Out, commandCancellation.Token);
            if (args[0] == "position-panel")
                return PositionPanelCommand.Run(args[1..]);
            return await NativeCommandRunner.RunAsync(args, Console.Out, Console.Error, commandCancellation.Token);
        }
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
        {
            Console.Error.WriteLine("RiftReader2.Live requires 64-bit Windows.");
            return 2;
        }

        LiveConfiguration configuration;
        try
        {
            configuration = LiveConfiguration.LoadBesideExecutable();
            configuration.Validate();
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine($"Configuration error: {exception.Message}");
            await Task.Delay(TimeSpan.FromSeconds(10));
            return 2;
        }

        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(configuration.DurationSeconds));
        Console.CancelKeyPress += (_, eventArgs) =>
        {
            eventArgs.Cancel = true;
            cancellation.Cancel();
        };
        var timeProvider = TimeProvider.System;
        var launchedAt = timeProvider.GetTimestamp();
        var instanceId = Guid.NewGuid();
        var nonce = NewNonce();
        PrintBindingInstruction(nonce);
        var outputPath = configuration.ResolveOutputPath();
        using var delivery = new LiveDeliveryClient(configuration.Delivery);
        LiveAddonFreshnessTracker? tracker = null;
        DiscoveredTarget? attachedTarget = null;
        LiveScanResult lastScan = EmptyScan("not-started", "No scan has completed.");
        LiveAddonSelection lastSelection = new(LiveAddonSelectionStatus.IncompleteScan, null, 0, 0, "scan-not-started");
        var lastFullScanStartedAt = launchedAt;
        FastObservationSession? fastSession = null;
        FastObservationReport? lastFastObservation = null;
        FastObservationAnchorDiagnostic? fastObservationDiagnostic = null;
        PendingFullScan? pendingFullScan = null;
        long outerSequence = 0;
        var failed = false;

        try
        {
            while (!cancellation.IsCancellationRequested)
            {
                var scanStartedAt = timeProvider.GetTimestamp();
                var discovery = await TargetDiscovery.DiscoverAsync(
                    configuration.ProcessName,
                    nonce,
                    cancellation.Token);

                if (discovery.Target is null)
                {
                    if (pendingFullScan is not null)
                    {
                        await CancelFullScanAsync(pendingFullScan);
                        pendingFullScan = null;
                    }
                    var hadAttachment = tracker is not null || attachedTarget is not null;
                    lastScan = EmptyScan("target-unavailable", discovery.Reason);
                    lastSelection = new(LiveAddonSelectionStatus.IncompleteScan, null, 0, 0, discovery.Reason);
                    LiveAddonFreshness? freshness = null;
                    if (tracker is not null)
                    {
                        var invalidating = new LiveAddonSelection(
                            LiveAddonSelectionStatus.Conflict,
                            null,
                            0,
                            0,
                            discovery.Reason ?? "target-unavailable");
                        freshness = tracker.Observe(tracker.Identity, invalidating, scanStartedAt);
                    }
                    await PublishUnavailableAsync(
                        configuration,
                        delivery,
                        instanceId,
                        nonce,
                        ++outerSequence,
                        launchedAt,
                        outputPath,
                        scanStartedAt,
                        freshness,
                        lastScan,
                        lastSelection,
                        discovery.Reason ?? "target-unavailable",
                        timeProvider,
                        cancellation.Token);
                    tracker = null;
                    attachedTarget = null;
                    fastSession = null;
                    lastFastObservation = null;
                    fastObservationDiagnostic = null;
                    if (hadAttachment)
                    {
                        nonce = NewNonce();
                        PrintBindingInstruction(nonce);
                    }
                    await DelayAsync(configuration.PollIntervalMilliseconds, cancellation.Token);
                    continue;
                }

                if (attachedTarget is null || !SameProcess(attachedTarget, discovery.Target))
                {
                    if (pendingFullScan is not null)
                    {
                        await CancelFullScanAsync(pendingFullScan);
                        pendingFullScan = null;
                    }
                    if (attachedTarget is not null)
                    {
                        nonce = NewNonce();
                        PrintBindingInstruction(nonce);
                        discovery = await TargetDiscovery.DiscoverAsync(
                            configuration.ProcessName,
                            nonce,
                            cancellation.Token);
                        if (discovery.Target is null)
                            continue;
                    }
                    attachedTarget = discovery.Target;
                    tracker = new LiveAddonFreshnessTracker(
                        attachedTarget.Identity,
                        new LiveFreshnessOptions
                        {
                            FreshnessTimeout = TimeSpan.FromSeconds(configuration.FreshnessTimeoutSeconds),
                            MaxClockSkew = TimeSpan.FromSeconds(1)
                        },
                        timeProvider);
                    fastSession = null;
                    lastFastObservation = null;
                    fastObservationDiagnostic = null;
                }

                var freshnessOptions = new LiveFreshnessOptions
                {
                    FreshnessTimeout = TimeSpan.FromSeconds(configuration.FreshnessTimeoutSeconds),
                    MaxClockSkew = TimeSpan.FromSeconds(1)
                };
                LiveAddonFreshness freshnessResult;
                TargetDiscoveryResult after;
                // Start renewal early enough to overlap more of the action-ready window.
                // Full scans can take seconds; the strict anchor and action gates remain unchanged.
                // The sole publication loop continues bounded scoped observations.
                // This is an experimental cadence adjustment, not a freshness relaxation.
                if (pendingFullScan is null &&
                    (fastSession is null ||
                     !fastSession.CanObserve(attachedTarget, scanStartedAt, out _) ||
                     timeProvider.GetElapsedTime(fastSession.Anchor.FullScanCompletedAtTimestamp, scanStartedAt) >=
                         FastObservationSession.RenewalStartAge))
                {
                    pendingFullScan = StartFullScan(
                        attachedTarget, nonce, configuration, fastSession, timeProvider, cancellation.Token);
                }

                if (pendingFullScan is not null && pendingFullScan.Task.IsCompleted)
                {

                    var completedScan = pendingFullScan!;
                    pendingFullScan = null;
                    BackgroundFullScanResult completedResult;
                    try
                    {
                        if (!SameProcess(completedScan.Target, attachedTarget) ||
                            !string.Equals(completedScan.Nonce, nonce, StringComparison.Ordinal))
                            throw new InvalidOperationException("Background full scan identity changed before admission.");
                        completedResult = await completedScan.Task;
                    }
                    finally
                    {
                        completedScan.Dispose();
                    }
                    var renewalSession = completedScan.RenewalSession;
                    var priorFresh = completedScan.PriorFresh;
                    lastScan = completedResult.Scan;
                    lastFullScanStartedAt = completedResult.AttemptStartedAt;
                    var scanCompletedAt = completedResult.CompletedAt;

                    after = await TargetDiscovery.DiscoverAsync(
                        configuration.ProcessName,
                        nonce,
                        cancellation.Token);
                    lastSelection = after.Target is null || !SameProcess(attachedTarget, after.Target)
                        ? new LiveAddonSelection(
                            LiveAddonSelectionStatus.Conflict, null, 0, 0,
                            after.Reason ?? "target-identity-changed-during-scan")
                        : LiveAddonCandidateSelector.Select(lastScan.Candidates, nonce, lastScan.Completed);
                    var fullFreshness = tracker!.Observe(
                        after.Target?.Identity ?? attachedTarget.Identity,
                        lastSelection,
                        lastFullScanStartedAt,
                        scanCompletedAt);
                    freshnessResult = fullFreshness;
                    if (fullFreshness.Status == LiveFreshnessStatus.Warming &&
                        renewalSession is not null &&
                        after.Target is not null &&
                        renewalSession.TryBridgeCompletedFullScan(
                            after.Target, lastScan, lastSelection,
                            lastFullScanStartedAt, scanCompletedAt, priorFresh, out var bridged))
                    {
                        // The promoted last observation is this completed FULL scan.
                        // Scoped history merely proves continuity; neither full-scan
                        // report publishes a prior scoped frame.
                        tracker = renewalSession.VerifiedTracker;
                        freshnessResult = bridged!;
                    }
                    lastFastObservation = null;
                    fastObservationDiagnostic = null;
                    fastSession = after.Target is not null && SameProcess(attachedTarget, after.Target) &&
                        FastObservationSession.TryCreate(
                            after.Target,
                            lastScan,
                            lastSelection,
                            lastFullScanStartedAt,
                            scanCompletedAt,
                            freshnessOptions,
                            timeProvider,
                            out var createdFastSession,
                            out _,
                            out fastObservationDiagnostic)
                        ? createdFastSession
                        : null;
                }
                else if (fastSession is not null && fastSession.CanObserve(attachedTarget, scanStartedAt, out _))
                {
                    var scopedScan = await Task.Run(
                        () => WindowsMemoryScanner.ScanCandidateRegions(
                            attachedTarget,
                            nonce,
                            fastSession.Regions,
                            FastObservationSession.MaximumRegionBytes,
                            TimeSpan.FromSeconds(Math.Min(2, configuration.MaxScanSeconds)),
                            cancellation.Token),
                        cancellation.Token);
                    var scopedCompletedAt = timeProvider.GetTimestamp();
                    after = await TargetDiscovery.DiscoverAsync(
                        configuration.ProcessName,
                        nonce,
                        cancellation.Token);
                    var scopedTargetStable = after.Target is not null && SameProcess(attachedTarget, after.Target);
                    var scopedSelection = !scopedTargetStable
                        ? new LiveAddonSelection(
                            LiveAddonSelectionStatus.Conflict, null, 0, 0,
                            after.Reason ?? "target-identity-changed-during-scoped-scan")
                        : LiveAddonCandidateSelector.Select(scopedScan.Candidates, nonce, scopedScan.Completed);
                    var scopedTarget = after.Target ?? attachedTarget;
                    lastFastObservation = fastSession.Observe(
                        scopedTarget,
                        scopedScan,
                        scopedSelection,
                        scanStartedAt,
                        scopedCompletedAt,
                        out var canContinue);
                    if (!canContinue &&
                        (lastFastObservation.Reason != "full-scan-anchor-expired" ||
                         fastSession.CaptureFullScanRenewal(scopedTarget) is null))
                        fastSession = null;
                    freshnessResult = scopedTargetStable
                        ? tracker!.GetCurrent()
                        : tracker!.Observe(
                            after.Target?.Identity ?? attachedTarget.Identity,
                            scopedSelection,
                            scanStartedAt,
                            scopedCompletedAt);
                }
                else
                {
                    // While the full scan is pending, publish an honest, non-scoped
                    // heartbeat after the ten-second anchor expires. Never carry
                    // a previous fast observation forward as if it were current.
                    after = discovery;
                    freshnessResult = tracker!.GetCurrent();
                    lastFastObservation = null;
                    // Preserve only diagnostic evidence from the last completed full scan.
                }
                var nativePower = after.Target is not null && SameProcess(attachedTarget, after.Target)
                    ? await LivePowerReader.ReadAsync(after.Target, timeProvider, cancellation.Token)
                    : new LivePowerRead(null, null, timeProvider.GetTimestamp(), "target-identity-changed-during-scan");
                var readerReason = pendingFullScan is not null && lastFastObservation is null
                    ? "full-scan-in-progress"
                    : null;
                var sequence = ++outerSequence;
                var beforeDelivery = CreateSnapshot(
                    instanceId,
                    nonce,
                    sequence,
                    launchedAt,
                    "running",
                    readerReason,
                    attachedTarget,
                    tracker,
                    freshnessResult,
                    lastSelection,
                    lastScan,
                    lastFullScanStartedAt,
                    configuration,
                    delivery.State,
                    timeProvider,
                    lastFastObservation,
                    fastObservationDiagnostic) with
                {
                    NativePower = nativePower.Present(timeProvider, TimeSpan.FromSeconds(configuration.FreshnessTimeoutSeconds))
                };
                await delivery.DeliverAsync(beforeDelivery, cancellation.Token);
                var afterDelivery = CreateSnapshot(
                    instanceId,
                    nonce,
                    sequence,
                    launchedAt,
                    "running",
                    readerReason,
                    attachedTarget,
                    tracker,
                    tracker.GetCurrent(),
                    lastSelection,
                    lastScan,
                    lastFullScanStartedAt,
                    configuration,
                    delivery.State,
                    timeProvider,
                    lastFastObservation,
                    fastObservationDiagnostic) with
                {
                    NativePower = nativePower.Present(timeProvider, TimeSpan.FromSeconds(configuration.FreshnessTimeoutSeconds))
                };
                await LiveOutput.WriteAtomicAsync(outputPath, afterDelivery, cancellation.Token);
                PrintStatus(afterDelivery);

                if (freshnessResult.Status == LiveFreshnessStatus.Invalidated)
                {
                    if (pendingFullScan is not null)
                    {
                        await CancelFullScanAsync(pendingFullScan);
                        pendingFullScan = null;
                    }
                    tracker = null;
                    attachedTarget = null;
                    fastSession = null;
                    lastFastObservation = null;
                    fastObservationDiagnostic = null;
                    nonce = NewNonce();
                    PrintBindingInstruction(nonce);
                }
                await DelayAsync(configuration.PollIntervalMilliseconds, cancellation.Token);
            }
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested)
        {
        }
        catch (Exception exception)
        {
            failed = true;
            Console.Error.WriteLine($"Live reader failed: {exception.Message}");
        }
        finally
        {
            if (pendingFullScan is not null)
            {
                await CancelFullScanAsync(pendingFullScan);
                pendingFullScan = null;
            }
            var sequence = ++outerSequence;
            var termination = CreateTerminationSnapshot(
                instanceId,
                nonce,
                sequence,
                launchedAt,
                attachedTarget,
                tracker,
                lastSelection,
                lastScan,
                configuration,
                delivery.State,
                timeProvider);
            try
            {
                using var terminationTimeout = new CancellationTokenSource(TimeSpan.FromSeconds(3));
                await delivery.DeliverAsync(termination, terminationTimeout.Token);
                termination = termination with { Delivery = delivery.State };
                await LiveOutput.WriteAtomicAsync(outputPath, termination, CancellationToken.None);
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine($"Termination report failed: {exception.Message}");
            }
            Console.WriteLine("RiftReader2.Live stopped. Prior observations must not be treated as current.");
        }
        return failed ? 1 : 0;
    }

    // One worker reads the full address space; the main loop remains the sole
    // owner of observation sequence numbers, freshness state and publication.
    private sealed record BackgroundFullScanResult(LiveScanResult Scan, long AttemptStartedAt, long CompletedAt);

    private sealed class PendingFullScan : IDisposable
    {
        internal PendingFullScan(
            DiscoveredTarget target,
            string nonce,
            FastObservationSession? renewalSession,
            LiveAddonFreshness? priorFresh,
            CancellationTokenSource cancellation,
            Task<BackgroundFullScanResult> task)
        {
            Target = target;
            Nonce = nonce;
            RenewalSession = renewalSession;
            PriorFresh = priorFresh;
            Cancellation = cancellation;
            Task = task;
        }

        internal DiscoveredTarget Target { get; }
        internal string Nonce { get; }
        internal FastObservationSession? RenewalSession { get; }
        internal LiveAddonFreshness? PriorFresh { get; }
        internal CancellationTokenSource Cancellation { get; }
        internal Task<BackgroundFullScanResult> Task { get; }
        public void Dispose() => Cancellation.Dispose();
    }

    private static PendingFullScan StartFullScan(
        DiscoveredTarget target,
        string nonce,
        LiveConfiguration configuration,
        FastObservationSession? renewalSession,
        TimeProvider timeProvider,
        CancellationToken cancellationToken)
    {
        var scopedCancellation = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        // Capture valid scoped continuity before the full scan may outlive its anchor.
        var priorFresh = renewalSession?.CaptureFullScanRenewal(target);
        var task = Task.Run(() =>
        {
            var attemptStartedAt = timeProvider.GetTimestamp();
            var scan = WindowsMemoryScanner.Scan(
                target,
                nonce,
                configuration.MaxScanBytes,
                TimeSpan.FromSeconds(configuration.MaxScanSeconds),
                scopedCancellation.Token,
                () => attemptStartedAt = timeProvider.GetTimestamp(),
                configuration.FullScanChunkKiB);
            return new BackgroundFullScanResult(scan, attemptStartedAt, timeProvider.GetTimestamp());
        }, scopedCancellation.Token);
        return new PendingFullScan(
            target, nonce, renewalSession, priorFresh, scopedCancellation, task);
    }

    private static async Task CancelFullScanAsync(PendingFullScan pending)
    {
        pending.Cancellation.Cancel();
        try
        {
            // Never leak the old process/nonce reader across identity changes.
            await pending.Task;
        }
        catch (OperationCanceledException)
        {
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine($"Canceled background scan failed: {exception.Message}");
        }
        finally
        {
            pending.Dispose();
        }
    }

    private static LiveReaderSnapshot CreateSnapshot(
        Guid instanceId,
        string nonce,
        long sequence,
        long launchedAt,
        string readerStatus,
        string? readerReason,
        DiscoveredTarget target,
        LiveAddonFreshnessTracker tracker,
        LiveAddonFreshness freshness,
        LiveAddonSelection selection,
        LiveScanResult scan,
        long scanStartedAt,
        LiveConfiguration configuration,
        LiveDeliveryReport delivery,
        TimeProvider timeProvider,
        FastObservationReport? fastObservation,
        FastObservationAnchorDiagnostic? fastObservationDiagnostic)
    {
        var publishedAt = timeProvider.GetTimestamp();
        return new(
            1,
            instanceId,
            nonce,
            sequence,
            DateTimeOffset.UtcNow.ToString("O"),
            timeProvider.GetElapsedTime(launchedAt, publishedAt).TotalMilliseconds,
            readerStatus,
            readerReason,
            TargetReport(target),
            LiveOutput.CreateRiftReader2Report(
                freshness,
                selection,
                scan,
                scanStartedAt,
                publishedAt,
                TimeSpan.FromSeconds(configuration.FreshnessTimeoutSeconds),
                timeProvider),
            delivery)
        {
            FastObservation = fastObservation is null
                ? null
                : LiveOutput.StampFastObservation(fastObservation, publishedAt, timeProvider),
            FastObservationDiagnostic = fastObservationDiagnostic
        };
    }

    private static async Task PublishUnavailableAsync(
        LiveConfiguration configuration,
        LiveDeliveryClient delivery,
        Guid instanceId,
        string nonce,
        long sequence,
        long launchedAt,
        string outputPath,
        long scanStartedAt,
        LiveAddonFreshness? freshness,
        LiveScanResult scan,
        LiveAddonSelection selection,
        string reason,
        TimeProvider timeProvider,
        CancellationToken cancellationToken)
    {
        var identity = freshness?.Identity ?? new LiveAttachmentIdentity(1, 1, new string('0', 64), nonce);
        var unavailable = freshness ?? new LiveAddonFreshness(
            LiveFreshnessStatus.Unavailable,
            identity,
            null,
            null,
            null,
            null,
            reason);
        LiveReaderSnapshot Build(LiveDeliveryReport deliveryState)
        {
            var now = timeProvider.GetTimestamp();
            return new(
                1,
                instanceId,
                nonce,
                sequence,
                DateTimeOffset.UtcNow.ToString("O"),
                timeProvider.GetElapsedTime(launchedAt, now).TotalMilliseconds,
                "running",
                reason,
                null,
                LiveOutput.CreateRiftReader2Report(
                    unavailable,
                    selection,
                    scan,
                    scanStartedAt,
                    now,
                    TimeSpan.FromSeconds(configuration.FreshnessTimeoutSeconds),
                    timeProvider,
                    "unavailable",
                    reason),
                deliveryState)
            {
                NativePower = LivePowerRead.Unavailable(reason)
            };
        }
        await delivery.DeliverAsync(Build(delivery.State), cancellationToken);
        await LiveOutput.WriteAtomicAsync(outputPath, Build(delivery.State), cancellationToken);
    }

    private static LiveReaderSnapshot CreateTerminationSnapshot(
        Guid instanceId,
        string nonce,
        long sequence,
        long launchedAt,
        DiscoveredTarget? target,
        LiveAddonFreshnessTracker? tracker,
        LiveAddonSelection selection,
        LiveScanResult scan,
        LiveConfiguration configuration,
        LiveDeliveryReport delivery,
        TimeProvider timeProvider)
    {
        var now = timeProvider.GetTimestamp();
        var identity = tracker?.Identity ?? new LiveAttachmentIdentity(1, 1, new string('0', 64), nonce);
        var freshness = tracker?.GetCurrent() ?? new LiveAddonFreshness(
            LiveFreshnessStatus.Unavailable,
            identity,
            null,
            null,
            null,
            null,
            "reader-terminated");
        return new(
            1,
            instanceId,
            nonce,
            sequence,
            DateTimeOffset.UtcNow.ToString("O"),
            timeProvider.GetElapsedTime(launchedAt, now).TotalMilliseconds,
            "terminated",
            "reader-terminated; prior observations expire no later than the reported freshness timeout",
            target is null ? null : TargetReport(target),
            LiveOutput.CreateRiftReader2Report(
                freshness,
                selection,
                scan,
                now,
                now,
                TimeSpan.FromSeconds(configuration.FreshnessTimeoutSeconds),
                timeProvider,
                "unavailable",
                "reader-terminated"),
            delivery)
        {
            NativePower = LivePowerRead.Unavailable("reader-terminated")
        };
    }

    private static LiveTargetReport TargetReport(DiscoveredTarget target) => new(
        target.Identity.ProcessId,
        target.Identity.ProcessStartUtcTicks,
        target.ExecutablePath,
        target.Identity.ExecutableSha256,
        target.Identity.ReaderSessionNonce);

    private static bool SameProcess(DiscoveredTarget left, DiscoveredTarget right) =>
        left.Identity.ProcessId == right.Identity.ProcessId &&
        left.Identity.ProcessStartUtcTicks == right.Identity.ProcessStartUtcTicks &&
        string.Equals(left.Identity.ExecutableSha256, right.Identity.ExecutableSha256, StringComparison.OrdinalIgnoreCase) &&
        string.Equals(left.ExecutablePath, right.ExecutablePath, StringComparison.OrdinalIgnoreCase);

    private static LiveScanResult EmptyScan(string status, string? reason) =>
        new(false, status, 0, 0, 0, TimeSpan.Zero, [], 0, 0, reason);

    private static string NewNonce() => Guid.NewGuid().ToString("N");

    private static void PrintBindingInstruction(string nonce)
    {
        Console.WriteLine();
        foreach (var line in BindingInstructions(nonce))
            Console.WriteLine(line);
        Console.WriteLine();
    }

    internal static IReadOnlyList<string> BindingInstructions(string nonce) =>
        new List<string>
        {
            "============================================================",
            "If this addon load is already bound to another reader, enter /reloadui and wait for it to finish first.",
            "Then enter this command locally in RIFT chat:",
            $"/rr2bind {nonce}",
            "This challenge is valid only for this reader attachment.",
            "============================================================"
        };

    private static void PrintStatus(LiveReaderSnapshot snapshot)
    {
        var fast = snapshot.FastObservation is null
            ? string.Empty
            : $" fastScan={snapshot.FastObservation.Scan.Status}" +
              $" fastFreshness={snapshot.FastObservation.FreshnessStatus}" +
              $" fastAgeMs={snapshot.FastObservation.LastAdvanceAgeMilliseconds?.ToString("F0") ?? "-"}";
        Console.WriteLine(
            $"{snapshot.CapturedAtUtc} scan={snapshot.RiftReader2.Scan.Status} " +
            $"selection={snapshot.RiftReader2.SelectionStatus} freshness={snapshot.RiftReader2.FreshnessStatus} " +
            $"ageMs={snapshot.RiftReader2.LastAdvanceAgeMilliseconds?.ToString("F0") ?? "-"}" +
            $"{fast} delivery={snapshot.Delivery.Status}");
    }

    private static async Task DelayAsync(int milliseconds, CancellationToken cancellationToken)
    {
        try
        {
            await Task.Delay(milliseconds, cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
        }
    }
}
