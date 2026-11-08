using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildPairedZoneKeySampleCommandTests : IDisposable
{
    readonly string directory = Path.Combine(Path.GetTempPath(), "rr2-paired-zone-command-" + Guid.NewGuid().ToString("N"));
    string ReportPath => Path.Combine(directory, "report.json");
    Dictionary<string, string> Options() => new() { ["--pid"] = "123", ["--start-ticks"] = "456", ["--output"] = ReportPath };

    [Fact] public async Task OneSessionRevalidatedBeforeAtomicCandidatePublication()
    {
        var s = new Fake(); var opens = 0; var reads = 0; var output = new StringWriter();
        s.Check = () => Assert.False(File.Exists(ReportPath));
        Assert.Equal(0, await Run(s, output: output, opened: (pid, ticks) =>
        { opens++; Assert.Equal(123, pid); Assert.Equal(456, ticks); },
            read: (session, max) =>
            { reads++; Assert.Same(s, session); Assert.Equal(1000, max); Assert.Equal(0, s.Checks); return Observation(s); }));
        Assert.Equal(1, opens); Assert.Equal(1, reads); Assert.Equal(1, s.Checks); Assert.True(s.Disposed);
        using var json = JsonDocument.Parse(await File.ReadAllTextAsync(ReportPath));
        var root = json.RootElement; var o = root.GetProperty("observation");
        Assert.Equal("native-current-paired-zone-key-candidate-sample/1", root.GetProperty("contractVersion").GetString());
        Assert.Equal("complete", root.GetProperty("status").GetString());
        Assert.Equal("passed-before-publication", root.GetProperty("processRevalidationStatus").GetString());
        Assert.Equal("matching-zone-key-candidate", o.GetProperty("zoneKeyRelation").GetString());
        Assert.Equal("unavailable", o.GetProperty("sameWorldStatus").GetString());
        Assert.Equal("not-derived", o.GetProperty("publicZoneIdStatus").GetString());
        Assert.False(o.GetProperty("atomicityQualified").GetBoolean());
        Assert.Equal("18446744073709551615", o.GetProperty("selfZone").GetProperty("unitKey").GetString());
        Assert.Single(Directory.GetFiles(directory));
        Assert.Contains("native-current-paired-zone-key-candidate-summary/1", output.ToString());
    }

    [Fact] public async Task MissingHealthPreservesTargetXyzAndUnavailableZone()
    {
        var s = new Fake(); var options = Options(); options["--max-acquisition-ms"] = "500";
        await Run(s, options, read: (_, max) =>
        {
            Assert.Equal(500, max);
            var o = Observation(s);
            return o with { TargetZone = o.TargetZone with { Status = "unavailable", RawZoneKey = null, UnavailableReason = "health-component-absent", Health = null, Owner = null } };
        });
        using var json = JsonDocument.Parse(await File.ReadAllTextAsync(ReportPath));
        var o = json.RootElement.GetProperty("observation");
        Assert.Equal("unavailable", o.GetProperty("zoneKeyRelation").GetString());
        Assert.Equal("health-component-absent", o.GetProperty("targetZone").GetProperty("unavailableReason").GetString());
        Assert.Equal(7, o.GetProperty("positions").GetProperty("target").GetProperty("position").GetProperty("x").GetSingle());
        Assert.Equal("unavailable", o.GetProperty("sameWorldStatus").GetString());
    }

    [Fact] public async Task NoSelectedTargetRemainsExplicitlyUnavailable()
    {
        var s = new Fake();
        await Run(s, read: (_, _) =>
        {
            var o = Observation(s);
            return o with { Positions = o.Positions with { Target = null, TargetStatus = "unavailable" },
                TargetZone = new("unavailable", null, null, null, null, null, null, "guarded-target-unavailable") };
        });
        using var json = JsonDocument.Parse(await File.ReadAllTextAsync(ReportPath));
        var o = json.RootElement.GetProperty("observation");
        Assert.Equal(JsonValueKind.Null, o.GetProperty("positions").GetProperty("target").ValueKind);
        Assert.Equal(JsonValueKind.Null, o.GetProperty("targetZone").GetProperty("rawZoneKey").ValueKind);
        Assert.Equal("unavailable", o.GetProperty("zoneKeyRelation").GetString());
    }

    [Fact] public async Task InvalidOptionsAndExistingEvidenceDoNotOpen()
    {
        foreach (var (key, value) in new[] { ("--pid", "0"), ("--start-ticks", "-1"), ("--output", " "),
            ("--max-acquisition-ms", "0"), ("--max-acquisition-ms", "5001"), ("--unknown", "x") })
        {
            var options = Options(); options[key] = value; bool opened = false;
            await Assert.ThrowsAsync<ArgumentException>(() => Run(new Fake(), options, opened: (_, _) => opened = true));
            Assert.False(opened);
        }
        Directory.CreateDirectory(directory); await File.WriteAllTextAsync(ReportPath, "original");
        var didOpen = false;
        await Assert.ThrowsAsync<IOException>(() => Run(new Fake(), opened: (_, _) => didOpen = true));
        Assert.False(didOpen); Assert.Equal("original", await File.ReadAllTextAsync(ReportPath));
    }

    [Fact] public async Task WrongOpenedIdentityNeverPublishes()
    {
        foreach (var kind in new[] { "pid", "start", "sha", "module" })
        {
            var s = new Fake();
            s.Identity = kind switch
            {
                "pid" => s.Identity with { ProcessId = 124 },
                "start" => s.Identity with { ProcessStartUtcTicks = 457 },
                "sha" => s.Identity with { ExecutableSha256 = new string('A', 64) },
                _ => s.Identity with { ModuleSize = 8 }
            };
            await Assert.ThrowsAsync<InvalidDataException>(() => Run(s));
            Assert.True(s.Disposed); Assert.False(File.Exists(ReportPath));
        }
    }

    [Fact] public async Task ForeignNestedIdentityAndUnitJoinsRejectBeforeRevalidation()
    {
        foreach (var kind in new[] { "outer", "positions", "self", "target" })
        {
            var s = new Fake();
            await Assert.ThrowsAsync<InvalidDataException>(() => Run(s, read: (_, _) =>
            {
                var o = Observation(s); var foreign = s.Identity with { ModuleBaseAddress = 0x150000000 };
                return kind switch
                {
                    "outer" => o with { Identity = foreign },
                    "positions" => o with { Positions = o.Positions with { Identity = foreign } },
                    "self" => o with { SelfZone = o.SelfZone with { UnitKey = "42" } },
                    _ => o with { TargetZone = o.TargetZone with { UnitKey = "43" } }
                };
            }));
            Assert.Equal(0, s.Checks); Assert.True(s.Disposed); Assert.False(File.Exists(ReportPath));
        }
    }

    [Fact] public async Task RevalidationFailureOrChangedModuleNeverPublishes()
    {
        foreach (var changed in new[] { false, true })
        {
            var s = new Fake { Failure = changed ? null : "process-exited" };
            if (changed) s.Check = () => s.Identity = s.Identity with { ModuleBaseAddress = 0x150000000 };
            await Assert.ThrowsAsync<InvalidDataException>(() => Run(s));
            Assert.Equal(1, s.Checks); Assert.True(s.Disposed); Assert.False(File.Exists(ReportPath));
        }
    }

    [Fact] public async Task CancellationAndAcquisitionFailureNeverPublishes()
    {
        using var canceled = new CancellationTokenSource(); canceled.Cancel(); bool opened = false;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Run(new Fake(), token: canceled.Token, opened: (_, _) => opened = true));
        Assert.False(opened);
        using var afterRead = new CancellationTokenSource(); var s = new Fake();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Run(s, token: afterRead.Token,
            read: (_, _) => { afterRead.Cancel(); return Observation(s); }));
        Assert.Equal(0, s.Checks); Assert.True(s.Disposed); Assert.False(File.Exists(ReportPath));
        s = new Fake();
        await Assert.ThrowsAsync<InvalidDataException>(() => Run(s, read: (_, _) => throw new InvalidDataException("source changed")));
        Assert.True(s.Disposed); Assert.False(File.Exists(ReportPath));
    }

    [Fact] public async Task AtomicPublicationRacePreservesWinnerAndCleansTemporary()
    {
        var s = new Fake();
        s.Check = () => { Directory.CreateDirectory(directory); File.WriteAllText(ReportPath, "race-winner"); };
        await Assert.ThrowsAsync<IOException>(() => Run(s));
        Assert.Equal("race-winner", await File.ReadAllTextAsync(ReportPath));
        Assert.Single(Directory.GetFiles(directory)); Assert.True(s.Disposed);
    }

    Task<int> Run(Fake s, Dictionary<string, string>? options = null, TextWriter? output = null,
        Action<int, long>? opened = null,
        Func<IReadOnlyNativeMemorySession, int, CurrentBuildPairedZoneKeyObservation>? read = null,
        CancellationToken token = default) =>
        CurrentBuildPairedZoneKeySampleCommand.RunAsync(options ?? Options(), output ?? new StringWriter(), token,
            (pid, ticks, _) => { opened?.Invoke(pid, ticks); return Task.FromResult<IReadOnlyNativeMemorySession>(s); },
            read ?? ((_, _) => Observation(s)));

    static CurrentBuildPairedZoneKeyObservation Observation(Fake s)
    {
        var utc = new DateTimeOffset(2026, 11, 8, 0, 0, 0, TimeSpan.Zero);
        var self = new PairedPositionCandidateSample("candidate", "18446744073709551615", "uFFFFFFFFFFFFFFFF", new(1, 2, 3), utc, utc, 0, 1);
        var target = self with { UnitKey = "42", UnitIdCandidate = "u000000000000002A", Position = new(7, 8, 9) };
        var pair = new CurrentBuildPairedPositionObservation(s.Identity, utc, utc, "one-pair-clock", self, target,
            "candidate", "fallback-key-candidate", "fallback-key-candidate", 4, 2, 3);
        return new(s.Identity, utc, utc, pair,
            new("raw-zone-key-candidate", self.UnitKey, self.UnitIdCandidate, 0x20000000, 0x20010000, 0x20020000, 123, null),
            new("raw-zone-key-candidate", target.UnitKey, target.UnitIdCandidate, 0x20030000, 0x20040000, 0x20050000, 123, null), 5);
    }

    public void Dispose() { if (Directory.Exists(directory)) Directory.Delete(directory, recursive: true); }

    sealed class Fake : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; set; } = new(123, 456, "rift_x64.exe", CurrentBuildPlayerLookup.GameSha256, 0x140000000, 0x4000000);
        public int Checks { get; private set; }
        public bool Disposed { get; private set; }
        public string? Failure { get; set; }
        public Action? Check { get; set; }
        public NativeReadResult Read(ulong a, int n) => throw new Exception("Command must delegate acquisition");
        public ValueTask<string?> RevalidateAsync(CancellationToken ct) { ct.ThrowIfCancellationRequested(); Checks++; Check?.Invoke(); return ValueTask.FromResult(Failure); }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
