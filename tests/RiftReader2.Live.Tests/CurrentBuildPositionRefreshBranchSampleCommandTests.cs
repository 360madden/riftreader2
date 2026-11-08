using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildPositionRefreshBranchSampleCommandTests : IDisposable
{
    readonly string directory = Path.Combine(Path.GetTempPath(), "rr2-xyz-branch-" + Guid.NewGuid().ToString("N"));
    string PathForReport => Path.Combine(directory, "report.json");
    Dictionary<string, string> Options() => new()
    {
        ["--pid"] = "123", ["--start-ticks"] = "456", ["--output"] = PathForReport
    };

    [Fact]
    public async Task GuardIneligibleReportIsLosslessAndRevalidatedBeforePublication()
    {
        var steps = new List<string>();
        var s = new Fake { Steps = steps };
        s.OnRevalidate = () => Assert.False(File.Exists(PathForReport));
        var output = new StringWriter();
        Assert.Equal(0, await Run(s, Options(), output, steps));
        Assert.Equal(new[] { "lease-acquired", "opened", "read", "revalidated", "session-disposed", "lease-disposed" }, steps);
        using var json = JsonDocument.Parse(await File.ReadAllTextAsync(PathForReport));
        var root = json.RootElement;
        Assert.Equal(2, root.GetProperty("schemaVersion").GetInt32());
        Assert.Equal("native-current-position-refresh-branch-candidate/2", root.GetProperty("contractVersion").GetString());
        Assert.Equal("passed-before-publication", root.GetProperty("processRevalidationStatus").GetString());
        Assert.Equal("456", root.GetProperty("processIdentity").GetProperty("processStartUtcTicks").GetString());
        var o = root.GetProperty("observation");
        Assert.Equal("guard-ineligible-candidate", o.GetProperty("status").GetString());
        Assert.Equal("9223372036854775850", o.GetProperty("playerKeyDecimal").GetString());
        Assert.Equal("u800000000000002A", o.GetProperty("playerUnitIdCandidate").GetString());
        Assert.Equal("0x0000000020010000", o.GetProperty("playerEntityHex").GetString());
        Assert.Equal("0x0000000020020000", o.GetProperty("positionComponentHex").GetString());
        Assert.Equal("0x0000000000000000", o.GetProperty("referencedHandleHex").GetString());
        Assert.Equal(0, o.GetProperty("flag").GetInt32());
        Assert.Equal(JsonValueKind.Null, o.GetProperty("sourceSelector").ValueKind);
        Assert.Equal(JsonValueKind.Null, o.GetProperty("sourceComponentHex").ValueKind);
        Assert.Equal(JsonValueKind.Null, o.GetProperty("referencedEntityHex").ValueKind);
        Assert.Equal("not-evaluated-flag-zero", o.GetProperty("sourceGuardStatus").GetString());
        Assert.Equal(JsonValueKind.Null, o.GetProperty("sourceGuardEligible").ValueKind);
        Assert.Equal(JsonValueKind.Null, o.GetProperty("sourceGuardValue").ValueKind);
        Assert.Equal(JsonValueKind.Null, o.GetProperty("sourceProviderPresent").ValueKind);
        Assert.Contains("native-current-position-refresh-branch-candidate-summary/2", output.ToString());
        Assert.Single(Directory.GetFiles(directory));
    }

    [Fact]
    public async Task ReferencedSourceReportKeepsFullProvenanceLosslessly()
    {
        var s = new Fake();
        await Run(s, Options(), read: session => Candidate(session.Identity) with
        {
            ReferencedHandle = 0x800000010000002B, ReferencedEntity = 0x21005000,
            SourceSelector = 7, Status = "handle-branch-referenced-source-present-candidate",
            SourceComponent = 0x20030000, SourceGuardStatus = "not-applicable-handle-branch"
        });
        using var json = JsonDocument.Parse(await File.ReadAllTextAsync(PathForReport));
        var o = json.RootElement.GetProperty("observation");
        Assert.Equal("0x800000010000002B", o.GetProperty("referencedHandleHex").GetString());
        Assert.Equal("9223372041149743147", o.GetProperty("referencedHandleDecimal").GetString());
        Assert.Equal("0x0000000021005000", o.GetProperty("referencedEntityHex").GetString());
        Assert.Equal("0x0000000020030000", o.GetProperty("sourceComponentHex").GetString());
        Assert.False(o.TryGetProperty("referencedEntity", out _));
        Assert.False(o.TryGetProperty("referencedHandle", out _));
        Assert.Equal("not-applicable-handle-branch", o.GetProperty("sourceGuardStatus").GetString());
        Assert.Equal(JsonValueKind.Null, o.GetProperty("sourceGuardEligible").ValueKind);
    }

    [Fact]
    public async Task FlagBranchPredicateIsPublishedLosslessly()
    {
        var s = new Fake();
        var output = new StringWriter();
        await Run(s, Options(), output, read: session => Candidate(session.Identity) with
        {
            Flag = 1,
            Status = "flag-branch-guard-eligible-candidate",
            SourceComponent = 0x20030000,
            SourceGuardContext = 0x20040000,
            SourceGuardValue = 0,
            SourceProviderPresent = true,
            SourceGuardStatus = "eligible-candidate"
        });
        using var json = JsonDocument.Parse(await File.ReadAllTextAsync(PathForReport));
        var o = json.RootElement.GetProperty("observation");
        Assert.Equal("0x0000000020040000", o.GetProperty("sourceGuardContextHex").GetString());
        Assert.Equal(0, o.GetProperty("sourceGuardValue").GetInt32());
        Assert.True(o.GetProperty("sourceProviderPresent").GetBoolean());
        Assert.Equal("eligible-candidate", o.GetProperty("sourceGuardStatus").GetString());
        Assert.True(o.GetProperty("sourceGuardEligible").GetBoolean());
        Assert.Contains("sourceGuardEligible", output.ToString());
    }

    [Fact]
    public async Task MissingEvidenceRemainsUnavailableInsteadOfZero()
    {
        var s = new Fake();
        await Run(s, Options(), read: session => Candidate(session.Identity) with
        {
            ReferencedHandle = null, Flag = null, SourceSelector = null,
            Status = "unavailable", SourceComponent = null, SourceGuardStatus = "unavailable"
        });
        using var json = JsonDocument.Parse(await File.ReadAllTextAsync(PathForReport));
        var o = json.RootElement.GetProperty("observation");
        Assert.Equal("unavailable", o.GetProperty("status").GetString());
        Assert.Equal(JsonValueKind.Null, o.GetProperty("referencedHandleHex").ValueKind);
        Assert.Equal(JsonValueKind.Null, o.GetProperty("referencedHandleDecimal").ValueKind);
        Assert.Equal(JsonValueKind.Null, o.GetProperty("referencedEntityHex").ValueKind);
        Assert.Equal(JsonValueKind.Null, o.GetProperty("flag").ValueKind);
    }

    [Fact]
    public async Task InvalidOptionsAndExistingEvidenceNeverAcquire()
    {
        foreach (var (key, value) in new[] {
            ("--pid", "0"), ("--start-ticks", "-1"), ("--output", " "),
            ("--unreviewed", "1") })
        {
            var o = Options(); o[key] = value; var steps = new List<string>();
            await Assert.ThrowsAsync<ArgumentException>(() => Run(new Fake(), o, steps: steps));
            Assert.Empty(steps);
        }
        Directory.CreateDirectory(directory);
        await File.WriteAllTextAsync(PathForReport, "previous");
        var blocked = new List<string>();
        await Assert.ThrowsAsync<IOException>(() => Run(new Fake(), Options(), steps: blocked));
        Assert.Empty(blocked);
        Assert.Equal("previous", await File.ReadAllTextAsync(PathForReport));
    }

    [Fact]
    public async Task ChangedProcessOrOwnerNeverPublishes()
    {
        foreach (var kind in new[] { "pid", "start", "sha", "module", "observation" })
        {
            var s = new Fake();
            if (kind != "observation")
                s.Identity = kind switch
                {
                    "pid" => s.Identity with { ProcessId = 124 },
                    "start" => s.Identity with { ProcessStartUtcTicks = 457 },
                    "sha" => s.Identity with { ExecutableSha256 = new string('A', 64) },
                    _ => s.Identity with { ModuleSize = 8 }
                };
            await Assert.ThrowsAsync<InvalidDataException>(() => Run(s, Options(), read:
                session => Candidate(kind == "observation" ? session.Identity with { ProcessStartUtcTicks = 999 } : session.Identity)));
            Assert.False(File.Exists(PathForReport));
            Assert.True(s.Disposed);
        }
    }

    [Fact]
    public async Task RevalidationFailureAndCancellationNeverPublish()
    {
        var s = new Fake { Failure = "process-exited" };
        await Assert.ThrowsAsync<InvalidDataException>(() => Run(s, Options()));
        Assert.True(s.Disposed); Assert.False(File.Exists(PathForReport));
        s = new Fake();
        using var canceled = new CancellationTokenSource(); canceled.Cancel();
        var steps = new List<string>();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Run(s, Options(), steps: steps, token: canceled.Token));
        Assert.Empty(steps); Assert.False(File.Exists(PathForReport));
        s = new Fake();
        using var afterRead = new CancellationTokenSource();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Run(s, Options(), token: afterRead.Token,
            read: session => { afterRead.Cancel(); return Candidate(session.Identity); }));
        Assert.True(s.Disposed); Assert.False(File.Exists(PathForReport));
    }

    [Fact]
    public async Task LeaseFailureDoesNotOpenSessionOrPublish()
    {
        var steps = new List<string>();
        var s = new Fake();
        await Assert.ThrowsAsync<InvalidDataException>(() => CurrentBuildPositionRefreshBranchSampleCommand.RunAsync(
            Options(), new StringWriter(), CancellationToken.None,
            (_, _, _) => { steps.Add("opened"); return Task.FromResult<IReadOnlyNativeMemorySession>(s); },
            _ => Candidate(s.Identity),
            (_, _, _, _, _) => throw new InvalidDataException("lease denied")));
        Assert.Empty(steps); Assert.False(File.Exists(PathForReport));
    }

    static PositionRefreshBranchCandidate Candidate(NativeProcessIdentity id) =>
        new(id, DateTimeOffset.UtcNow.AddMilliseconds(-1), DateTimeOffset.UtcNow,
            9223372036854775850UL, 0x20010000, 0x20020000, 0, 0, null,
            "guard-ineligible-candidate", null, SourceGuardStatus: "not-evaluated-flag-zero");

    Task<int> Run(Fake s, IReadOnlyDictionary<string, string> opts, StringWriter? output = null,
        List<string>? steps = null, CancellationToken token = default,
        Func<IReadOnlyNativeMemorySession, PositionRefreshBranchCandidate>? read = null) =>
        CurrentBuildPositionRefreshBranchSampleCommand.RunAsync(opts, output ?? new StringWriter(), token,
            (_, _, _) =>
            {
                steps?.Add("opened");
                return Task.FromResult<IReadOnlyNativeMemorySession>(s);
            },
            session => { steps?.Add("read"); return (read ?? (_ => Candidate(s.Identity)))(session); },
            (pid, ticks, sha, timeout, _) =>
            {
                Assert.Equal(123, pid);
                Assert.Equal(456, ticks);
                Assert.Equal(CurrentBuildPlayerLookup.GameSha256, sha);
                Assert.Equal(TimeSpan.FromSeconds(5), timeout);
                steps?.Add("lease-acquired");
                return Task.FromResult<IAsyncDisposable>(new Lease(() => steps?.Add("lease-disposed")));
            });

    public void Dispose()
    {
        if (Directory.Exists(directory)) Directory.Delete(directory, recursive: true);
    }

    sealed class Lease(Action released) : IAsyncDisposable
    {
        public ValueTask DisposeAsync() { released(); return ValueTask.CompletedTask; }
    }

    sealed class Fake : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; set; } =
            new(123, 456, "rift_x64.exe", CurrentBuildPlayerLookup.GameSha256, 0x140000000, 64 * 1024 * 1024);
        public string? Failure { get; set; }
        public Action? OnRevalidate { get; set; }
        public List<string>? Steps { get; set; }
        public bool Disposed { get; private set; }
        public NativeReadResult Read(ulong address, int count) => new("unavailable", [], null, "not invoked");
        public ValueTask<string?> RevalidateAsync(CancellationToken _)
        {
            Steps?.Add("revalidated"); OnRevalidate?.Invoke();
            return ValueTask.FromResult(Failure);
        }
        public ValueTask DisposeAsync()
        {
            Steps?.Add("session-disposed"); Disposed = true; return ValueTask.CompletedTask;
        }
    }
}
