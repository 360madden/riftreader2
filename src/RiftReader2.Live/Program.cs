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
                }

                lastScan = await Task.Run(
                    () => WindowsMemoryScanner.Scan(
                        attachedTarget,
                        nonce,
                        configuration.MaxScanBytes,
                        TimeSpan.FromSeconds(configuration.MaxScanSeconds),
                        cancellation.Token),
                    cancellation.Token);

                var after = await TargetDiscovery.DiscoverAsync(
                    configuration.ProcessName,
                    nonce,
                    cancellation.Token);
                if (after.Target is null || !SameProcess(attachedTarget, after.Target))
                {
                    lastSelection = new(
                        LiveAddonSelectionStatus.Conflict,
                        null,
                        0,
                        0,
                        after.Reason ?? "target-identity-changed-during-scan");
                }
                else
                {
                    lastSelection = LiveAddonCandidateSelector.Select(
                        lastScan.Candidates,
                        nonce,
                        lastScan.Completed);
                }

                var freshnessResult = tracker!.Observe(
                    after.Target?.Identity ?? attachedTarget.Identity,
                    lastSelection,
                    scanStartedAt);
                var nativePower = after.Target is not null && SameProcess(attachedTarget, after.Target)
                    ? await LivePowerReader.ReadAsync(after.Target, timeProvider, cancellation.Token)
                    : new LivePowerRead(null, null, timeProvider.GetTimestamp(), "target-identity-changed-during-scan");
                var sequence = ++outerSequence;
                var beforeDelivery = CreateSnapshot(
                    instanceId,
                    nonce,
                    sequence,
                    launchedAt,
                    "running",
                    null,
                    attachedTarget,
                    tracker,
                    freshnessResult,
                    lastSelection,
                    lastScan,
                    scanStartedAt,
                    configuration,
                    delivery.State,
                    timeProvider) with
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
                    null,
                    attachedTarget,
                    tracker,
                    tracker.GetCurrent(),
                    lastSelection,
                    lastScan,
                    scanStartedAt,
                    configuration,
                    delivery.State,
                    timeProvider) with
                {
                    NativePower = nativePower.Present(timeProvider, TimeSpan.FromSeconds(configuration.FreshnessTimeoutSeconds))
                };
                await LiveOutput.WriteAtomicAsync(outputPath, afterDelivery, cancellation.Token);
                PrintStatus(afterDelivery);

                if (freshnessResult.Status == LiveFreshnessStatus.Invalidated)
                {
                    tracker = null;
                    attachedTarget = null;
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
        TimeProvider timeProvider)
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
            delivery);
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
        Console.WriteLine("============================================================");
        Console.WriteLine("Enter this command locally in RIFT chat:");
        Console.WriteLine($"/rr2bind {nonce}");
        Console.WriteLine("This challenge is valid only for this reader attachment.");
        Console.WriteLine("============================================================");
        Console.WriteLine();
    }

    private static void PrintStatus(LiveReaderSnapshot snapshot) =>
        Console.WriteLine(
            $"{snapshot.CapturedAtUtc} scan={snapshot.RiftReader2.Scan.Status} " +
            $"selection={snapshot.RiftReader2.SelectionStatus} freshness={snapshot.RiftReader2.FreshnessStatus} " +
            $"ageMs={snapshot.RiftReader2.LastAdvanceAgeMilliseconds?.ToString("F0") ?? "-"} " +
            $"delivery={snapshot.Delivery.Status}");

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
