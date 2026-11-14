using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal sealed record SurvivalVitalValue(bool Available, string Status,
    long? Current, long? Maximum, bool DeadAvailable, bool? Dead);
internal sealed record SurvivalBoolValue(bool Available, string Status, byte? Raw, bool? Value);
internal sealed record SurvivalLevelValue(bool Available, string Status, int? Value);
internal sealed record SurvivalRelationValue(bool Available, string Status, string? Value, string Reason);
internal sealed record SurvivalUnitValues(bool Available, string Status, string? Key,
    SurvivalVitalValue Health, SurvivalBoolValue Combat, SurvivalLevelValue Level,
    SurvivalRelationValue? Relation = null);
internal sealed record CurrentBuildSurvivalNativeValues(DateTimeOffset SampledAtUtc,
    SurvivalUnitValues Player, SurvivalUnitValues SelectedTarget);

/// <summary>One idle-only combined self/selected-target survival snapshot.</summary>
internal static class CurrentBuildSurvivalSampleCommand
{
    private const double MaximumAcquisitionMilliseconds = 500;

    internal static async Task<int> RunAsync(string[] args, TextWriter output, CancellationToken token)
    {
        var json = args.Contains("--json", StringComparer.Ordinal);
        try
        {
            var options = Parse(args);
            if (!string.Equals(options.Host, Environment.MachineName, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Current machine does not match --expected-host.");
            if (!string.Equals(options.Sha256, CurrentBuildPlayerLookup.GameSha256,
                StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Requested executable SHA is not the supported exact build.");
            var elapsed = Stopwatch.StartNew();
            await using var lease = await NativeReadFileLease.AcquireAsync(options.Pid,
                options.StartTicks, options.Sha256, TimeSpan.FromMilliseconds(500), token);
            await using var session = await WindowsNativeMemorySession.OpenAsync(options.Pid,
                options.StartTicks, options.Sha256, token);
            var identity = session.Identity;
            if (identity.ProcessId != options.Pid || identity.ProcessStartUtcTicks != options.StartTicks
                || !string.Equals(identity.ExecutableSha256, options.Sha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Survival session identity differs from the exact request.");
            var selfContext = CurrentBuildPlayerContextCandidateReader.Read(session);
            var selfVitals = CurrentBuildVitalsCandidateReader.Read(session);
            var contextCalls = 0;
            var selected = CurrentBuildSelectedTargetCandidateReader.Read(session,
                source => contextCalls++ == 0 ? selfContext
                    : CurrentBuildPlayerContextCandidateReader.Read(source),
                (source, owner) => CurrentBuildVitalsCandidateReader.Read(source, _ => owner),
                includeContext: true);
            if (await session.RevalidateAsync(token) is not null || session.Identity != identity)
                throw new InvalidDataException("Survival process identity changed during capture.");
            if (selfContext.Identity != identity || selfVitals.Identity != identity
                || selected.Identity != identity || selfContext.UnitKey != options.PlayerKey
                || selfVitals.UnitKey != options.PlayerKey || selected.SelfKey != options.PlayerKey)
                throw new InvalidDataException("Survival self owner differs from the expected player.");
            elapsed.Stop();
            if (elapsed.Elapsed.TotalMilliseconds > MaximumAcquisitionMilliseconds)
                throw new TimeoutException("Combined survival acquisition exceeded 500 milliseconds.");
            var nativeValues = Project(selfContext, selfVitals, selected);
            var payload = new
            {
                status = "complete", identity,
                requested = new { host = options.Host, pid = options.Pid,
                    processStartUtcTicks = options.StartTicks, executableSha256 = options.Sha256,
                    playerKey = options.PlayerKey.ToString(CultureInfo.InvariantCulture) },
                acquisitionElapsedMilliseconds = elapsed.Elapsed.TotalMilliseconds,
                nativeValues,
                qualification = "candidate-only exact-build native survival snapshot; independently compare API values; relation unavailable",
                inputSent = false
            };
            await output.WriteLineAsync(JsonSerializer.Serialize(payload,
                new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = !json }));
            return 0;
        }
        catch (Exception error)
        {
            await output.WriteLineAsync(JsonSerializer.Serialize(new
            {
                status = "blocked", reason = error.Message, errorType = error.GetType().Name,
                inputSent = false
            }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = !json }));
            return 2;
        }
    }

    internal static CurrentBuildSurvivalNativeValues Project(
        CurrentBuildPlayerContextObservation selfContext,
        CurrentBuildVitalsObservation selfVitals,
        SelectedTargetObservation selected)
    {
        if (selfContext.UnitKey == 0 || selfVitals.UnitKey != selfContext.UnitKey
            || selected.SelfKey != selfContext.UnitKey)
            throw new InvalidDataException("Combined survival projection self owner mismatch.");
        var self = new SurvivalUnitValues(true, "available-candidate",
            selfContext.UnitKey.ToString(CultureInfo.InvariantCulture),
            Health(selfVitals.Health),
            new(selfContext.CombatStatus == "raw-byte-candidate", selfContext.CombatStatus,
                selfContext.RawCombat, selfContext.CombatStatus == "raw-byte-candidate"
                    ? selfContext.CombatCandidate : null),
            new(selfContext.RawLevel >= 0 && !selfContext.LevelStatus.Contains("unavailable", StringComparison.Ordinal),
                selfContext.LevelStatus, selfContext.RawLevel >= 0 ? selfContext.RawLevel : null));
        SurvivalUnitValues target;
        var relation = new SurvivalRelationValue(false, "unavailable", null,
            "native-relation-source-unavailable");
        if (selected.Status != "candidate" || selected.TargetKey is not ulong targetKey || targetKey == 0)
        {
            target = new(false, selected.Status, null, UnavailableHealth("target-unavailable"),
                new(false, "target-unavailable", null, null),
                new(false, "target-unavailable", null), relation);
        }
        else
        {
            var context = selected.TargetContext;
            var contextAvailable = context is { Status: "raw-typed-candidate" };
            var combatAvailable = contextAvailable && context!.CombatCandidate.HasValue;
            var numericLevel = contextAvailable ? context!.NumericLevelCandidate ?? context.RawLevel : null;
            target = new(true, selected.Status, targetKey.ToString(CultureInfo.InvariantCulture),
                selected.TargetVitals is null ? UnavailableHealth("target-health-unavailable")
                    : Health(selected.TargetVitals.Health),
                new(combatAvailable, context?.Status ?? "unavailable", context?.RawCombat,
                    combatAvailable ? context!.CombatCandidate : null),
                new(numericLevel.HasValue && numericLevel.Value >= 0,
                    context?.LevelStatus ?? context?.Status ?? "unavailable",
                    numericLevel is >= 0 ? numericLevel : null), relation);
        }
        var sampled = new[] { selfContext.CompletedAtUtc, selfVitals.CompletedAtUtc, selected.CompletedAtUtc }.Max();
        return new(sampled, self, target);
    }

    private static SurvivalVitalValue Health(CurrentBuildVitalCandidate value)
    {
        var available = value.Status == "calculated-candidate"
            && value.Current is long current && value.Maximum is long maximum
            && current >= 0 && maximum > 0 && current <= maximum;
        return new(available, value.Status, available ? value.Current : null,
            available ? value.Maximum : null, available,
            available ? value.Current == 0 : null);
    }

    private static SurvivalVitalValue UnavailableHealth(string status) =>
        new(false, status, null, null, false, null);

    private sealed record Options(string Host, int Pid, long StartTicks, string Sha256, ulong PlayerKey);

    private static Options Parse(string[] args)
    {
        var values = new Dictionary<string, string>(StringComparer.Ordinal);
        var json = false;
        for (var i = 0; i < args.Length; i++)
        {
            if (args[i] == "--json") { if (json) throw new InvalidDataException("Repeated --json."); json = true; continue; }
            if (i + 1 >= args.Length || !args[i].StartsWith("--", StringComparison.Ordinal)
                || !values.TryAdd(args[i], args[++i]))
                throw new InvalidDataException("Missing or repeated survival option.");
        }
        var allowed = new[] { "--expected-host", "--pid", "--expect-start-ticks",
            "--expect-sha256", "--expect-player-key" };
        if (values.Keys.Any(key => !allowed.Contains(key, StringComparer.Ordinal)))
            throw new InvalidDataException("Unknown survival option.");
        string Required(string name) => values.TryGetValue(name, out var value) && !string.IsNullOrWhiteSpace(value)
            ? value : throw new InvalidDataException("Required option missing: " + name);
        if (!int.TryParse(Required("--pid"), NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0
            || !long.TryParse(Required("--expect-start-ticks"), NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0
            || !ulong.TryParse(Required("--expect-player-key"), NumberStyles.None, CultureInfo.InvariantCulture, out var player) || player == 0)
            throw new InvalidDataException("PID, start ticks and player key must be positive decimal values.");
        var sha = Required("--expect-sha256");
        if (sha.Length != 64 || !sha.All(Uri.IsHexDigit))
            throw new InvalidDataException("--expect-sha256 must contain 64 hex digits.");
        return new(Required("--expected-host"), pid, ticks, sha.ToUpperInvariant(), player);
    }
}
