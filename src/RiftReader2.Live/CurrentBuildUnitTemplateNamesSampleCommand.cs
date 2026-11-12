using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal sealed class UnitTemplateNameUnavailableException(string status, ulong? entity) : Exception(status)
{
    internal string Status => Message;
    internal ulong? Entity => entity;
}

internal sealed record UnitTemplateNameRow(string UnitKey, string? EntityAddressDecimal,
    DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc, string Status,
    uint? TemplateKey = null, uint? LocalizationKey = null, int? LocalizationMode = null,
    uint? FormattingFlag = null, string? FallbackText = null);

internal sealed record UnitTemplateNamesObservation(NativeProcessIdentity Identity,
    DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc, string SelfKey,
    IReadOnlyList<UnitTemplateNameRow> Rows)
{
    public string Qualification => "cache-only template base-name candidates; names, passive freshness and restart unverified; dictionary payload not acquired";
}

internal static class CurrentBuildUnitTemplateNamesSampleCommand
{
    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct)
    {
        if (!options.TryGetValue("--pid", out var p) || !int.TryParse(p, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var t) || !long.TryParse(t, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 ||
            !options.TryGetValue("--output", out var path) || string.IsNullOrWhiteSpace(path) ||
            !options.TryGetValue("--keys", out var rawKeys))
            throw new ArgumentException("--pid, --start-ticks, --keys and --output required.");
        var keys = ParseKeys(rawKeys);
        if (File.Exists(path)) throw new IOException("Output exists.");
        await using var lease = await NativeReadFileLease.AcquireAsync(pid, ticks,
            CurrentBuildPlayerLookup.GameSha256, TimeSpan.FromSeconds(1), ct);
        await using var source = await WindowsNativeMemorySession.OpenAsync(pid, ticks, CurrentBuildPlayerLookup.GameSha256, ct);
        var observation = Read(source, keys, () => WindowsThreadTlsSnapshot.Capture(pid), ct);
        if (await source.RevalidateAsync(ct) is not null) throw new InvalidDataException("Process identity invalidated.");
        ct.ThrowIfCancellationRequested();
        await JsonReportWriter.WriteNewAsync(path, new { schemaVersion = 1,
            contractVersion = "native-unit-template-names-candidate/1", status = "complete", observation }, ct);
        await output.WriteLineAsync(JsonSerializer.Serialize(new { recordType = "native-unit-template-names-summary/1",
            status = "complete", output = Path.GetFullPath(path) }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }

    internal static IReadOnlyList<ulong> ParseKeys(string rawKeys)
    {
        var parts = rawKeys.Split(',');
        if (parts.Length is < 1 or > 32) throw new ArgumentException("Supply 1..32 unique unit keys.");
        var keys = new List<ulong>();
        foreach (var part in parts)
        {
            if (!ulong.TryParse(part, NumberStyles.None, CultureInfo.InvariantCulture, out var key) || key == 0 ||
                key.ToString(CultureInfo.InvariantCulture) != part || keys.Contains(key))
                throw new ArgumentException("Unit keys must be unique canonical nonzero UInt64 decimal strings.");
            keys.Add(key);
        }
        return keys;
    }

    internal static UnitTemplateNamesObservation Read(IReadOnlyNativeMemorySession source, IReadOnlyList<ulong> keys,
        Func<IReadOnlyList<NativeThreadEpoch>> threads, CancellationToken ct,
        Func<IReadOnlyNativeMemorySession, CurrentBuildPlayerContextObservation>? context = null)
    {
        if (keys.Count is < 1 or > 32 || keys.Any(k => k == 0) || keys.Distinct().Count() != keys.Count)
            throw new ArgumentException("Supply 1..32 unique nonzero unit keys.");
        context ??= CurrentBuildPlayerContextCandidateReader.Read;
        var started = DateTimeOffset.UtcNow;
        var session = new BoundedSession(source, ct);
        var identity = session.Identity;
        var self = context(session);
        if (self is null || self.Identity != identity) throw new InvalidDataException("Player identity changed.");
        var rows = new List<UnitTemplateNameRow>();
        foreach (var key in keys)
        {
            session.Check();
            var rowStarted = DateTimeOffset.UtcNow;
            try
            {
                var name = CurrentBuildTargetTemplateNameSampleCommand.Read(session,
                    context, threads, key, includeDictionary: false);
                if (!Equals(name.Identity, identity) || name.SelfKey != self.UnitKey)
                    throw new InvalidDataException("Player identity changed.");
                rows.Add(new(key.ToString(CultureInfo.InvariantCulture), name.TargetEntity.ToString(CultureInfo.InvariantCulture),
                    name.StartedAtUtc, name.CompletedAtUtc, name.Status, name.TemplateKey, name.LocalizationKey,
                    name.LocalizationMode, name.FormattingFlag, name.FallbackText));
            }
            catch (UnitTemplateNameUnavailableException ex)
            {
                rows.Add(new(key.ToString(CultureInfo.InvariantCulture), ex.Entity?.ToString(CultureInfo.InvariantCulture),
                    rowStarted, DateTimeOffset.UtcNow, ex.Status));
            }
        }
        var final = context(session);
        if (final is null || final.Identity != identity || final.UnitKey != self.UnitKey || final.Entity != self.Entity || session.Identity != identity)
            throw new InvalidDataException("Player or process changed across unit names.");
        session.Check();
        return new(identity, started, DateTimeOffset.UtcNow, self.UnitKey.ToString(CultureInfo.InvariantCulture), rows);
    }

    internal sealed class BoundedSession(IReadOnlyNativeMemorySession source, CancellationToken ct, Func<TimeSpan>? elapsed = null) : IReadOnlyNativeMemorySession
    {
        private readonly Stopwatch clock = Stopwatch.StartNew();
        private int usedBytes;
        internal void Check()
        {
            ct.ThrowIfCancellationRequested();
            if ((elapsed?.Invoke() ?? clock.Elapsed) > TimeSpan.FromSeconds(3)) throw new InvalidDataException("Unit-name batch wall budget exceeded.");
        }
        public NativeProcessIdentity Identity => source.Identity;
        public NativeReadResult Read(ulong address, int length)
        {
            Check();
            usedBytes = checked(usedBytes + length);
            if (usedBytes > 2 * 1024 * 1024) throw new InvalidDataException("Unit-name batch read budget exceeded.");
            var result = source.Read(address, length);
            Check();
            return result;
        }
        public ValueTask<string?> RevalidateAsync(CancellationToken token) => source.RevalidateAsync(token);
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
