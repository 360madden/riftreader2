using System.Security.Cryptography;
using RiftReader2.Domain;

namespace RiftReader2.Application;

public sealed record NativeReadResult(
    string Status,
    byte[] Bytes,
    int? Win32ErrorCode,
    string? Reason);

public interface IReadOnlyNativeMemorySession : IAsyncDisposable
{
    NativeProcessIdentity Identity { get; }

    NativeReadResult Read(ulong address, int byteLength);

    ValueTask<string?> RevalidateAsync(CancellationToken cancellationToken);
}

public sealed class NativeCaptureRunner(TimeProvider? timeProvider = null)
{
    private readonly TimeProvider timeProvider = timeProvider ?? TimeProvider.System;

    public async Task<NativeCaptureSummary> CaptureAsync(
        NativeCapturePlan plan,
        IReadOnlyNativeMemorySession session,
        CancellationToken cancellationToken)
    {
        Validate(plan);
        RequireIdentity(plan, session.Identity);
        var captureId = Guid.NewGuid();
        var startedUtc = timeProvider.GetUtcNow();
        var started = timeProvider.GetTimestamp();
        var deadline = TimeSpan.FromMilliseconds(plan.MaxDurationMilliseconds);
        var samples = new List<NativeCaptureSample>(plan.SampleCount);

        for (var sampleIndex = 0; sampleIndex < plan.SampleCount; sampleIndex++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (timeProvider.GetElapsedTime(started) > deadline)
                return await CompleteAsync("time-budget-exceeded", "Capture exceeded its declared time budget.");

            var sampleStartedUtc = timeProvider.GetUtcNow();
            var sampleStarted = timeProvider.GetTimestamp();
            var results = new List<NativeRangeCapture>(plan.Ranges.Count);
            void AddCurrentSample()
            {
                var sampleCompleted = timeProvider.GetTimestamp();
                samples.Add(new(
                    sampleIndex + 1,
                    sampleStartedUtc.ToString("O"),
                    timeProvider.GetUtcNow().ToString("O"),
                    timeProvider.GetElapsedTime(started, sampleStarted).TotalMilliseconds,
                    timeProvider.GetElapsedTime(started, sampleCompleted).TotalMilliseconds,
                    results));
            }
            foreach (var range in plan.Ranges)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (timeProvider.GetElapsedTime(started) > deadline)
                {
                    AddCurrentSample();
                    return await CompleteAsync("time-budget-exceeded", "Capture exceeded its declared time budget before a range read.");
                }
                var resolved = Resolve(range, session.Identity);
                var read = session.Read(resolved, range.ByteLength);
                ValidateRead(range, read);
                var hash = read.Bytes.Length == 0 ? null : Convert.ToHexString(SHA256.HashData(read.Bytes));
                results.Add(new(
                    range.Id,
                    range.AddressKind == NativeAddressKind.ModuleRelative ? "module-relative-rva" : "absolute-session-address",
                    Hex(range.Address),
                    Hex(resolved),
                    range.ByteLength,
                    read.Status,
                    read.Bytes.Length,
                    read.Bytes.Length == 0 ? null : Convert.ToBase64String(read.Bytes),
                    hash,
                    read.Win32ErrorCode,
                    read.Reason));
                cancellationToken.ThrowIfCancellationRequested();
                if (timeProvider.GetElapsedTime(started) > deadline)
                {
                    AddCurrentSample();
                    return await CompleteAsync("time-budget-exceeded", "A memory read exceeded the declared time budget.");
                }
            }

            AddCurrentSample();

            // A final read may itself consume the remaining budget.
            cancellationToken.ThrowIfCancellationRequested();
            if (timeProvider.GetElapsedTime(started) > deadline)
                return await CompleteAsync("time-budget-exceeded", "The final memory read exceeded the declared time budget.");

            if (sampleIndex + 1 < plan.SampleCount && plan.IntervalMilliseconds > 0)
                await Task.Delay(TimeSpan.FromMilliseconds(plan.IntervalMilliseconds), timeProvider, cancellationToken);
        }

        return await CompleteAsync(
            samples.Count == plan.SampleCount && samples.All(sample =>
                sample.Ranges.Count == plan.Ranges.Count && sample.Ranges.All(range => range.Status == "success"))
                ? "complete"
                : "partial",
            null);

        async Task<NativeCaptureSummary> CompleteAsync(string status, string? reason)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var identityFailure = await session.RevalidateAsync(cancellationToken);
            cancellationToken.ThrowIfCancellationRequested();
            if (identityFailure is not null)
            {
                if (string.IsNullOrWhiteSpace(identityFailure) || identityFailure.Length > 1024)
                    throw new InvalidDataException("The native session returned an invalid identity failure reason.");
                status = "identity-invalidated";
                reason = identityFailure;
            }
            else if (timeProvider.GetElapsedTime(started) > deadline)
            {
                status = "time-budget-exceeded";
                reason = "Capture and terminal identity validation exceeded the declared time budget.";
            }
            var completed = timeProvider.GetTimestamp();
            return new(
                captureId,
                status,
                reason,
                session.Identity,
                startedUtc.ToString("O"),
                timeProvider.GetUtcNow().ToString("O"),
                timeProvider.GetElapsedTime(started, completed).TotalMilliseconds,
                plan.SampleCount,
                samples.Count,
                samples.Count(sample => sample.Ranges.Count == plan.Ranges.Count &&
                    sample.Ranges.All(range => range.Status == "success")),
                samples);
        }
    }

    public static void Validate(NativeCapturePlan plan)
    {
        ArgumentNullException.ThrowIfNull(plan);
        if (plan.ProcessId <= 0 || plan.ProcessStartUtcTicks <= 0)
            throw new ArgumentException("Process identity must contain a positive PID and UTC start ticks.", nameof(plan));
        if (string.IsNullOrWhiteSpace(plan.ExecutableSha256) || plan.ExecutableSha256.Length != 64 ||
            !plan.ExecutableSha256.All(Uri.IsHexDigit))
            throw new ArgumentException("ExecutableSha256 must be exactly 64 hexadecimal characters.", nameof(plan));
        ArgumentNullException.ThrowIfNull(plan.Ranges);
        if (plan.Ranges.Count is < 1 or > 32)
            throw new ArgumentException("Ranges must contain between 1 and 32 entries.", nameof(plan));
        if (plan.SampleCount is < 1 or > 32)
            throw new ArgumentException("SampleCount must be between 1 and 32.", nameof(plan));
        if (plan.IntervalMilliseconds is < 0 or > 30_000)
            throw new ArgumentException("IntervalMilliseconds must be between 0 and 30000.", nameof(plan));
        if (plan.MaxDurationMilliseconds is < 1 or > 30_000)
            throw new ArgumentException("MaxDurationMilliseconds must be between 1 and 30000.", nameof(plan));
        var ids = new HashSet<string>(StringComparer.Ordinal);
        long total = 0;
        foreach (var range in plan.Ranges)
        {
            if (range is null)
                throw new ArgumentException("Ranges cannot contain null entries.", nameof(plan));
            if (!Enum.IsDefined(range.AddressKind))
                throw new ArgumentException($"Range '{range.Id}' has an undefined address kind.", nameof(plan));
            if (string.IsNullOrWhiteSpace(range.Id) || range.Id.Length > 64 || !ids.Add(range.Id))
                throw new ArgumentException("Range IDs must be unique, nonempty, and at most 64 characters.", nameof(plan));
            if (range.ByteLength is < 1 or > 4096)
                throw new ArgumentException("Each range ByteLength must be between 1 and 4096.", nameof(plan));
            _ = CheckedEnd(range.Address, range.ByteLength);
            total = checked(total + (long)range.ByteLength * plan.SampleCount);
        }
        if (total > 4 * 1024 * 1024)
            throw new ArgumentException("The requested raw-byte total exceeds 4194304 bytes.", nameof(plan));
        if ((long)(plan.SampleCount - 1) * plan.IntervalMilliseconds >= plan.MaxDurationMilliseconds)
            throw new ArgumentException("The sampling schedule cannot fit inside MaxDurationMilliseconds.", nameof(plan));
        if ((long)plan.SampleCount * plan.Ranges.Count > 1024)
            throw new ArgumentException("The requested sample/range observation count exceeds 1024.", nameof(plan));
    }

    private static void RequireIdentity(NativeCapturePlan plan, NativeProcessIdentity identity)
    {
        ArgumentNullException.ThrowIfNull(identity);
        if (identity.ProcessId != plan.ProcessId || identity.ProcessStartUtcTicks != plan.ProcessStartUtcTicks ||
            !string.Equals(identity.ExecutableSha256, plan.ExecutableSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("The opened process identity does not exactly match the capture request.");
        ulong moduleEnd;
        try
        {
            moduleEnd = checked(identity.ModuleBaseAddress + identity.ModuleSize);
        }
        catch (OverflowException exception)
        {
            throw new InvalidDataException("The opened process returned an overflowing main-module identity.", exception);
        }
        if (string.IsNullOrWhiteSpace(identity.ExecutablePath) || identity.ExecutableSha256.Length != 64 ||
            !identity.ExecutableSha256.All(Uri.IsHexDigit) || identity.ModuleBaseAddress < 0x10000 || identity.ModuleSize == 0 ||
            moduleEnd > 0x00007FFF_FFFF_FFFF)
            throw new InvalidDataException("The opened process returned an invalid executable or main-module identity.");
    }

    private static void ValidateRead(NativeCaptureRange range, NativeReadResult read)
    {
        if (read is null)
            throw new InvalidDataException($"Range '{range.Id}' returned no read result.");
        if (read.Bytes is null || read.Bytes.Length > range.ByteLength)
            throw new InvalidDataException($"Range '{range.Id}' returned an invalid byte count.");
        if (read.Reason is { Length: > 1024 })
            throw new InvalidDataException($"Range '{range.Id}' returned an overlong failure reason.");
        var valid = read.Status switch
        {
            "success" => read.Bytes.Length == range.ByteLength && read.Win32ErrorCode is null && read.Reason is null,
            "partial" => read.Bytes.Length is > 0 && read.Bytes.Length < range.ByteLength &&
                !string.IsNullOrWhiteSpace(read.Reason),
            "unavailable" => read.Bytes.Length == 0 && !string.IsNullOrWhiteSpace(read.Reason),
            _ => false
        };
        if (!valid)
            throw new InvalidDataException($"Range '{range.Id}' returned an incoherent read result.");
    }

    private static ulong Resolve(NativeCaptureRange range, NativeProcessIdentity identity)
    {
        ulong resolved;
        if (range.AddressKind == NativeAddressKind.ModuleRelative)
        {
            if (range.Address >= identity.ModuleSize || CheckedEnd(range.Address, range.ByteLength) > identity.ModuleSize)
                throw new InvalidDataException($"Range '{range.Id}' extends outside the identified main module.");
            resolved = checked(identity.ModuleBaseAddress + range.Address);
        }
        else
        {
            resolved = range.Address;
        }
        var end = CheckedEnd(resolved, range.ByteLength);
        if (resolved < 0x10000 || end > 0x00007FFF_FFFF_FFFF)
            throw new InvalidDataException($"Range '{range.Id}' is outside the supported 64-bit user address range.");
        return resolved;
    }

    private static ulong CheckedEnd(ulong address, int length) => checked(address + (ulong)length);

    private static string Hex(ulong value) => $"0x{value:X}";
}
