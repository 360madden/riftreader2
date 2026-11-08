using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildPairedPositionSampleCommandTests : IDisposable
{
    readonly string directory = Path.Combine(Path.GetTempPath(), "rr2-paired-command-" + Guid.NewGuid().ToString("N"));
    string PathFor(string file = "report.json") => Path.Combine(directory, file);
    Dictionary<string, string> Options() => new() { ["--pid"] = "123", ["--start-ticks"] = "456", ["--output"] = PathFor() };

    [Fact] public async Task OneSessionRevalidatesBeforeAtomicMissingTargetPublication()
    {
        var s = new Fake(); var opened = 0; var read = 0; var output = new StringWriter();
        s.OnRevalidate = () => Assert.False(File.Exists(PathFor()));
        var result = await Run(Options(), s, output, (pid, ticks) =>
        {
            opened++; Assert.Equal(123, pid); Assert.Equal(456, ticks);
        }, (session, maxSpan) =>
        {
            read++; Assert.Same(s, session); Assert.Equal(1000, maxSpan);
            Assert.Equal(0, s.Revalidations); return Observation(s);
        });
        Assert.Equal(0, result); Assert.Equal(1, opened); Assert.Equal(1, read);
        Assert.Equal(1, s.Revalidations); Assert.True(s.Disposed);
        using var json = JsonDocument.Parse(await File.ReadAllTextAsync(PathFor()));
        var root = json.RootElement; var observation = root.GetProperty("observation");
        Assert.Equal("native-current-paired-position-candidate-sample/1", root.GetProperty("contractVersion").GetString());
        Assert.Equal("passed-before-publication", root.GetProperty("processRevalidationStatus").GetString());
        Assert.Equal("complete", root.GetProperty("status").GetString());
        Assert.Equal("target-unavailable", observation.GetProperty("status").GetString());
        Assert.Equal(JsonValueKind.Null, observation.GetProperty("target").ValueKind);
        Assert.Equal("unavailable", observation.GetProperty("zoneIdentityStatus").GetString());
        Assert.Equal("unavailable", observation.GetProperty("worldIdentityStatus").GetString());
        Assert.False(observation.GetProperty("atomicityQualified").GetBoolean());
        Assert.Equal("18446744073709551615", observation.GetProperty("self").GetProperty("unitKey").GetString());
        Assert.Single(Directory.GetFiles(directory));
        Assert.Contains("native-current-paired-position-candidate-summary/1", output.ToString());
    }

    [Fact] public async Task ExplicitTargetPositionAndBoundArePreserved()
    {
        var s = new Fake(); var options = Options(); options["--max-pair-span-ms"] = "500";
        await Run(options, s, new StringWriter(), read: (source, span) =>
        {
            Assert.Equal(500, span);
            var o = Observation(s);
            return o with { Target = o.Self with { UnitKey = "42", UnitIdCandidate = "u000000000000002A" }, TargetStatus = "candidate",
                StartSkewMilliseconds = 2, MaximumSampleSeparationMilliseconds = 3 };
        });
        using var json = JsonDocument.Parse(await File.ReadAllTextAsync(PathFor()));
        var o = json.RootElement.GetProperty("observation");
        Assert.Equal("paired-candidate", o.GetProperty("status").GetString());
        Assert.Equal("42", o.GetProperty("target").GetProperty("unitKey").GetString());
        Assert.Equal(3, o.GetProperty("maximumSampleSeparationMilliseconds").GetDouble());
    }

    [Fact] public async Task ExistingEvidenceRejectsBeforeSessionOpen()
    {
        Directory.CreateDirectory(directory); await File.WriteAllTextAsync(PathFor(), "original");
        var opened = false;
        await Assert.ThrowsAsync<IOException>(() => Run(Options(), new Fake(), new StringWriter(), (_, _) => opened = true));
        Assert.False(opened); Assert.Equal("original", await File.ReadAllTextAsync(PathFor()));
    }

    [Fact] public async Task InvalidArgumentsRejectBeforeOpening()
    {
        foreach (var item in new[] { ("--pid", "0"), ("--start-ticks", "-1"), ("--max-pair-span-ms", "0"),
            ("--max-pair-span-ms", "5001"), ("--max-pair-span-ms", "true"), ("--output", " "), ("--unknown", "x") })
        {
            var options = Options(); options[item.Item1] = item.Item2; var opened = false;
            await Assert.ThrowsAsync<ArgumentException>(() => Run(options, new Fake(), new StringWriter(), (_, _) => opened = true));
            Assert.False(opened);
        }
    }

    [Fact] public async Task WrongOpenedOrObservationIdentityNeverPublishes()
    {
        foreach (var field in new[] { "pid", "ticks", "sha", "module", "observation" })
        {
            var s = new Fake();
            s.Identity = field switch
            {
                "pid" => s.Identity with { ProcessId = 124 },
                "ticks" => s.Identity with { ProcessStartUtcTicks = 457 },
                "sha" => s.Identity with { ExecutableSha256 = new string('A', 64) },
                "module" => s.Identity with { ModuleSize = 8 },
                _ => s.Identity
            };
            await Assert.ThrowsAsync<InvalidDataException>(() => Run(Options(), s, new StringWriter(),
                read: (_, _) => field == "observation" ? Observation(s) with { Identity = s.Identity with { ModuleBaseAddress = 0x150000000 } } : Observation(s)));
            Assert.False(File.Exists(PathFor())); Assert.True(s.Disposed);
        }
    }

    [Fact] public async Task FailedRevalidationOrChangedModuleNeverPublishes()
    {
        foreach (var changed in new[] { false, true })
        {
            var s = new Fake { Failure = changed ? null : "process-exited" };
            if (changed) s.OnRevalidate = () => s.Identity = s.Identity with { ModuleBaseAddress = 0x150000000 };
            await Assert.ThrowsAsync<InvalidDataException>(() => Run(Options(), s, new StringWriter()));
            Assert.Equal(1, s.Revalidations); Assert.False(File.Exists(PathFor())); Assert.True(s.Disposed);
        }
    }

    [Fact] public async Task CancellationBeforeOpenAndAfterReadNeverPublishes()
    {
        using var c = new CancellationTokenSource(); c.Cancel(); var opened = false;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Run(Options(), new Fake(), new StringWriter(), (_, _) => opened = true, token: c.Token));
        Assert.False(opened);
        using var afterRead = new CancellationTokenSource(); var s = new Fake();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Run(Options(), s, new StringWriter(),
            read: (_, _) => { afterRead.Cancel(); return Observation(s); }, token: afterRead.Token));
        Assert.Equal(0, s.Revalidations); Assert.True(s.Disposed); Assert.False(File.Exists(PathFor()));
    }

    [Fact] public async Task AcquisitionAndPublicationFailuresDisposeAndPreserveEvidence()
    {
        var s = new Fake();
        await Assert.ThrowsAsync<InvalidDataException>(() => Run(Options(), s, new StringWriter(), read: (_, _) => throw new InvalidDataException("source changed")));
        Assert.True(s.Disposed); Assert.False(File.Exists(PathFor()));
        s = new Fake();
        s.OnRevalidate = () => { Directory.CreateDirectory(directory); File.WriteAllText(PathFor(), "race-winner"); };
        await Assert.ThrowsAsync<IOException>(() => Run(Options(), s, new StringWriter()));
        Assert.True(s.Disposed); Assert.Equal("race-winner", await File.ReadAllTextAsync(PathFor()));
        Assert.Single(Directory.GetFiles(directory));
    }

    static Task<int> Run(Dictionary<string, string> options, Fake s, TextWriter output,
        Action<int, long>? opened = null,
        Func<IReadOnlyNativeMemorySession, int, CurrentBuildPairedPositionObservation>? read = null,
        CancellationToken token = default) =>
        CurrentBuildPairedPositionSampleCommand.RunAsync(options, output, token,
            (pid, ticks, _) => { opened?.Invoke(pid, ticks); return Task.FromResult<IReadOnlyNativeMemorySession>(s); },
            read ?? ((_, _) => Observation(s)));

    static CurrentBuildPairedPositionObservation Observation(Fake s)
    {
        var time = new DateTimeOffset(2026, 11, 8, 0, 0, 0, TimeSpan.Zero);
        var self = new PairedPositionCandidateSample("candidate", "18446744073709551615", "uFFFFFFFFFFFFFFFF", new(1, 2, 3), time, time.AddMilliseconds(1), 0, 1);
        return new(s.Identity, time, time.AddMilliseconds(4), "one-pair-clock", self, null,
            "unavailable", "override-unavailable", "override-unavailable", 4, null, null);
    }

    public void Dispose() { if (Directory.Exists(directory)) Directory.Delete(directory, recursive: true); }

    sealed class Fake : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; set; } = new(123, 456, "rift_x64.exe", CurrentBuildPlayerLookup.GameSha256, 0x140000000, 0x4000000);
        public int Revalidations { get; private set; }
        public bool Disposed { get; private set; }
        public string? Failure { get; set; }
        public Action? OnRevalidate { get; set; }
        public NativeReadResult Read(ulong address, int count) => throw new Exception("Wrapper must delegate memory acquisition");
        public ValueTask<string?> RevalidateAsync(CancellationToken token)
        {
            token.ThrowIfCancellationRequested(); Revalidations++; OnRevalidate?.Invoke();
            return ValueTask.FromResult(Failure);
        }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
