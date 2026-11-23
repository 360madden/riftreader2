using System.Buffers.Binary;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

// Read-only, exact-key native numeric-level candidates. These are not NPC
// hostility, difficulty, attackability, or world-instance determinations.
internal sealed record CurrentBuildUnitLevelCandidate(
    string UnitKey, string UnitIdCandidate, string Status,
    string? EntityAddressDecimal, int? NumericLevelCandidate,
    string? LevelBranch, string? UnavailableReason,
    DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc);

internal sealed record CurrentBuildUnitLevelsObservation(
    NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc,
    DateTimeOffset CompletedAtUtc, string SelfKey,
    IReadOnlyList<CurrentBuildUnitLevelCandidate> Rows)
{
    public string Qualification =>
        "candidate-only; exact keyed native level source, no UI/API meaning, " +
        "hostility, attackability, proximity freshness or world-instance proof";
}

internal static class CurrentBuildUnitLevelsSampleCommand
{
    internal static async Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct)
    {
        if (!options.TryGetValue("--pid", out var p) ||
            !int.TryParse(p, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) ||
            pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var ticksText) ||
            !long.TryParse(ticksText, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) ||
            ticks <= 0 ||
            !options.TryGetValue("--keys", out var rawKeys) ||
            !options.TryGetValue("--output", out var path) ||
            string.IsNullOrWhiteSpace(path))
            throw new ArgumentException("--pid, --start-ticks, --keys and --output are required.");
        var keys = CurrentBuildUnitTemplateNamesSampleCommand.ParseKeys(rawKeys);
        if (keys.Count > 12) throw new ArgumentException("Supply at most 12 level keys.");
        var sha = CurrentBuildTargetTemplateNameSampleCommand.ExpectedSha(options);
        if (File.Exists(path)) throw new IOException("Output exists.");
        await using var lease = await NativeReadFileLease.AcquireAsync(
            pid, ticks, sha, TimeSpan.FromSeconds(1), ct);
        await using var source = await WindowsNativeMemorySession.OpenAsync(
            pid, ticks, sha, ct);
        if (source.Identity.ProcessId != pid ||
            source.Identity.ProcessStartUtcTicks != ticks ||
            !string.Equals(source.Identity.ExecutableSha256, sha,
                StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Native level process/build identity changed.");
        var report = Read(source, keys, ct);
        if (await source.RevalidateAsync(ct) is not null)
            throw new InvalidDataException("Process identity invalidated.");
        ct.ThrowIfCancellationRequested();
        await JsonReportWriter.WriteNewAsync(path, new
        {
            schemaVersion = 1,
            contractVersion = "native-current-unit-levels-candidate/1",
            status = "complete",
            observation = report
        }, ct);
        await output.WriteLineAsync(JsonSerializer.Serialize(
            new
            {
                recordType = "native-current-unit-levels-summary/1",
                status = "complete",
                output = Path.GetFullPath(path)
            },
            new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }

    internal static CurrentBuildUnitLevelsObservation Read(
        IReadOnlyNativeMemorySession source, IReadOnlyList<ulong> keys,
        CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(source);
        if (keys.Count is < 1 or > 12 || keys.Any(k => k == 0) ||
            keys.Distinct().Count() != keys.Count)
            throw new ArgumentException("Supply 1..12 unique nonzero unit keys.");
        var bounded = new CurrentBuildUnitTemplateNamesSampleCommand.BoundedSession(source, ct);
        var identity = bounded.Identity;
        if (!CurrentBuildPlayerLookup.IsCoreBuild(identity.ExecutableSha256) ||
            identity.ProcessId <= 0 || identity.ProcessStartUtcTicks <= 0)
            throw new InvalidDataException("Unit level source requires an exact RIFT build and process.");
        var started = DateTimeOffset.UtcNow;
        var lookup = CurrentBuildPlayerLookup.Resolve(bounded);
        var rows = new List<CurrentBuildUnitLevelCandidate>();
        foreach (var key in keys)
        {
            bounded.Check();
            var began = DateTimeOffset.UtcNow;
            CurrentBuildUnitLevelCandidate row;
            try
            {
                row = ReadOne(bounded, lookup, key, began);
            }
            catch (InvalidDataException)
            {
                row = new(key.ToString(CultureInfo.InvariantCulture),
                    $"u{key:X16}", "unavailable", null, null, null,
                    "native-component-or-owner-unavailable", began,
                    DateTimeOffset.UtcNow);
            }
            lookup.VerifyUnchanged();
            if (bounded.Identity != identity)
                throw new InvalidDataException("Native unit level process changed.");
            rows.Add(row);
        }
        bounded.Check();
        lookup.VerifyUnchanged();
        return new(identity, started, DateTimeOffset.UtcNow,
            lookup.PlayerKey.ToString(CultureInfo.InvariantCulture), rows);
    }

    private static CurrentBuildUnitLevelCandidate ReadOne(
        IReadOnlyNativeMemorySession session,
        CurrentBuildPlayerLookup lookup, ulong key, DateTimeOffset began)
    {
        var identity = session.Identity;
        var updated = CurrentBuildPlayerLookup.IsUpdatedBuild(identity.ExecutableSha256);
        var original = new Dictionary<(ulong Address, int Length), byte[]>();
        byte[] Take(ulong address, int length)
        {
            var bytes = CurrentBuildPlayerLookup.Exact(session, address, length);
            if (original.TryGetValue((address, length), out var previous) &&
                !previous.AsSpan().SequenceEqual(bytes))
                throw new InvalidDataException("Unit level source changed.");
            original[(address, length)] = bytes.ToArray();
            return bytes;
        }
        ulong Q(ulong address) => BinaryPrimitives.ReadUInt64LittleEndian(Take(address, 8));
        ulong Ptr(ulong value, int length = 8) => CurrentBuildPlayerLookup.Pointer(value, length);
        int I32(ulong address) => BinaryPrimitives.ReadInt32LittleEndian(Take(address, 4));
        var (entity, health) = lookup.ResolveReferencedComponent(
            key, updated ? 0x2F68850UL : 0x2F57850UL);
        var entityText = entity.ToString(CultureInfo.InvariantCulture);
        var owner = Ptr(Q(checked(health + 0x40)), 0x19E);
        var vptr = updated ? 0x2933218UL : 0x2927448UL;
        var getter = updated ? 0x19D2020UL : 0x19D21E0UL;
        string status, reason;
        int? level = null;
        string? branch = null;
        if (Q(owner) != identity.ModuleBaseAddress + vptr ||
            Q(identity.ModuleBaseAddress + vptr + 0x40) !=
                identity.ModuleBaseAddress + getter ||
            (!updated &&
             (Q(identity.ModuleBaseAddress + 0x34731B0) !=
                  identity.ModuleBaseAddress + 0x2929BD0 ||
              Q(identity.ModuleBaseAddress + 0x2929BD8) !=
                  identity.ModuleBaseAddress + 0x19F4D60)))
        {
            status = "unverified-owner-type";
            reason = "owner-vptr-or-getter-mismatch";
        }
        else
        {
            var selectorRva = updated ? 0x2F69270UL : 0x2F58270UL;
            var index = I32(identity.ModuleBaseAddress + selectorRva);
            if (index is < 0 or >= 0x60)
                throw new InvalidDataException("Invalid native level selector.");
            var slot = Take(entity + 0x18 + (ulong)index, 1)[0];
            var componentTable = Ptr(Q(entity + 0x78));
            var alternate = slot == 0xFF ? 0 :
                Q(checked(componentTable + slot * 8UL));
            if (alternate == 0)
            {
                status = "unavailable";
                reason = "alternate-level-component-unavailable";
            }
            else
            {
                Ptr(alternate, 0x38);
                var first = Ptr(Q(alternate + 0x28), 0x68);
                var value = I32(first + 0x64);
                branch = "alternate-primary";
                if (value == -1)
                {
                    var second = Ptr(Q(alternate + 0x30), 0x68);
                    value = I32(second + 0x64);
                    branch = "alternate-secondary";
                }
                if (value is >= 1 and <= 1000)
                {
                    status = "numeric-level-candidate";
                    reason = "";
                    level = value;
                }
                else
                {
                    status = "unavailable";
                    reason = "numeric-level-outside-bounds";
                    branch = null;
                }
            }
        }
        foreach (var pair in original)
            CurrentBuildPlayerLookup.RequireSame(
                CurrentBuildPlayerLookup.Exact(session,
                    pair.Key.Address, pair.Key.Length), pair.Value);
        lookup.VerifyUnchanged();
        return new(key.ToString(CultureInfo.InvariantCulture),
            $"u{key:X16}", status, entityText, level, branch,
            status == "numeric-level-candidate" ? null : reason,
            began, DateTimeOffset.UtcNow);
    }
}
