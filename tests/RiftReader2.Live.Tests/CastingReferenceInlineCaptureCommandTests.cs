using System.Text.Json;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class CastingReferenceInlineCaptureCommandTests
{
    [Fact]
    public async Task RequestLoaderRetainsExactHashAndRejectsDuplicateOrExtraKeys()
    {
        using var temp = new TempDirectory();
        var valid = Path.Combine(temp.Path, "valid.json");
        var raw = JsonSerializer.SerializeToUtf8Bytes(new
        {
            schemaVersion = 1,
            evidenceKind = CastingReferenceInlineCaptureCore.RequestKind,
            target = new
            {
                processId = 77,
                processStartUtcTicks = 88,
                executableSha256 = CastingReferenceInlineCaptureCore.CurrentBuildSha256
            },
            startAddress = "0x10000",
            maxScanBytes = CastingReferenceInlineCaptureCore.ChunkBytes,
            maxDurationMilliseconds = 30_000,
            maxRegionCount = 32_768,
            maxMatchCount = 128,
            maxCopiedCandidates = 8
        });
        await File.WriteAllBytesAsync(valid, raw);
        var loaded = await CastingReferenceInlineCaptureCommand.LoadRequestAsync(valid, default);
        Assert.Equal(Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(raw)), loaded.Sha256);
        Assert.Equal(raw, loaded.Raw);
        Assert.Equal(77, loaded.Request.Target.ProcessId);

        var duplicate = Path.Combine(temp.Path, "duplicate.json");
        await File.WriteAllTextAsync(duplicate,
            "{\"schemaVersion\":1,\"schemaVersion\":1,\"evidenceKind\":\"x\",\"target\":{}," +
            "\"startAddress\":\"0x10000\",\"maxScanBytes\":65536," +
            "\"maxDurationMilliseconds\":1,\"maxRegionCount\":1," +
            "\"maxMatchCount\":1,\"maxCopiedCandidates\":1}");
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            CastingReferenceInlineCaptureCommand.LoadRequestAsync(duplicate, default));

        var extra = Path.Combine(temp.Path, "extra.json");
        await File.WriteAllTextAsync(extra,
            System.Text.Encoding.UTF8.GetString(raw)[..^1] + ",\"marker\":\"arbitrary\"}");
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            CastingReferenceInlineCaptureCommand.LoadRequestAsync(extra, default));
    }

    [Fact]
    public async Task ExistingOutputBlocksBeforeOpeningAnyProcess()
    {
        using var temp = new TempDirectory();
        var output = Path.Combine(temp.Path, "existing");
        Directory.CreateDirectory(output);
        var error = await Assert.ThrowsAsync<IOException>(() =>
            CastingReferenceInlineCaptureCommand.RunAsync(
                new Dictionary<string, string>
                {
                    ["--request"] = Path.Combine(temp.Path, "missing.json"),
                    ["--output"] = output
                }, TextWriter.Null, default));
        Assert.Contains("overwriting evidence", error.Message);
    }

    [Fact]
    public async Task InvalidBoundsFailBeforeOpeningRequestedProcess()
    {
        using var temp = new TempDirectory();
        var request = Path.Combine(temp.Path, "invalid.json");
        await File.WriteAllTextAsync(request, JsonSerializer.Serialize(new
        {
            schemaVersion = 1,
            evidenceKind = CastingReferenceInlineCaptureCore.RequestKind,
            target = new
            {
                processId = int.MaxValue,
                processStartUtcTicks = 88,
                executableSha256 = CastingReferenceInlineCaptureCore.CurrentBuildSha256
            },
            startAddress = "0x10000",
            maxScanBytes = CastingReferenceInlineCaptureCore.MaxScanBytes + 1,
            maxDurationMilliseconds = 30_000,
            maxRegionCount = 32_768,
            maxMatchCount = 128,
            maxCopiedCandidates = 8
        }));
        var error = await Assert.ThrowsAsync<InvalidDataException>(() =>
            CastingReferenceInlineCaptureCommand.RunAsync(
                new Dictionary<string, string>
                {
                    ["--request"] = request,
                    ["--output"] = Path.Combine(temp.Path, "unused")
                }, TextWriter.Null, default));
        Assert.Contains("bounds", error.Message);
    }

    [Fact]
    public async Task NativeRunnerHelpRegistersOnlyFixedCastingReferenceCommand()
    {
        var output = new StringWriter();
        var exit = await NativeCommandRunner.RunAsync(["help"], output, TextWriter.Null);
        Assert.Equal(0, exit);
        Assert.Contains("scout-copy-casting-reference-native --request PATH --output NEW_DIRECTORY",
            output.ToString());
    }

    [Fact]
    public void CommandClaimsExactCollectorScopeWithoutOverstatingCoreInventory()
    {
        Assert.Contains(CastingReferenceInlineCaptureCommand.CommandLimitations,
            value => value.Contains("committed, readable, nonguard MEM_PRIVATE", StringComparison.Ordinal));
        Assert.Contains(CastingReferenceInlineCaptureCommand.CommandLimitations,
            value => value.Contains("exact requested process epoch", StringComparison.Ordinal));
        Assert.DoesNotContain(CastingReferenceInlineCaptureCommand.CommandLimitations,
            value => value.Contains("future Windows collector", StringComparison.Ordinal));
    }

    [Fact]
    public async Task RawRequestAndManifestPublicationPreserveExactBytesHashesAndNoOverwrite()
    {
        using var temp = new TempDirectory();
        var staging = Path.Combine(temp.Path, "staging");
        var output = Path.Combine(temp.Path, "published");
        Directory.CreateDirectory(staging);
        var raw = System.Text.Encoding.UTF8.GetBytes("{\r\n  \"exact\": true\r\n}");
        var requestSha = Convert.ToHexString(
            System.Security.Cryptography.SHA256.HashData(raw));
        var sourceName = await CastingReferenceInlineCaptureCommand.RetainSourceRequestAsync(
            staging, raw, requestSha, default);
        Assert.Equal("source-request.json", sourceName);
        Assert.Equal(raw, await File.ReadAllBytesAsync(Path.Combine(staging, sourceName)));
        await File.WriteAllTextAsync(Path.Combine(staging, "candidate.json"), "retained");

        var indexSha = await CastingReferenceInlineCaptureCommand.PublishManifestAsync(
            staging, output,
            new { schemaVersion = 1, sourceRequestFile = sourceName, requestSha256 = requestSha },
            default);
        var indexPath = Path.Combine(output, "index.json");
        Assert.Equal(Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(
            await File.ReadAllBytesAsync(indexPath))), indexSha);
        var receipt = new CastingReferenceInlineCaptureReceipt(
            1, CastingReferenceInlineCaptureCore.EvidenceKind, "complete", null,
            "2026-11-06T00:00:00Z", "2026-11-06T00:00:01Z", 1, 1,
            indexSha, output);
        using (var receiptJson = JsonDocument.Parse(JsonSerializer.Serialize(
            receipt, RiftReader2.Infrastructure.JsonFormat.Options)))
            Assert.Equal(indexSha, receiptJson.RootElement.GetProperty("indexSha256").GetString());
        Assert.Equal(raw, await File.ReadAllBytesAsync(Path.Combine(output, sourceName)));
        Assert.Equal("retained", await File.ReadAllTextAsync(Path.Combine(output, "candidate.json")));
        Assert.False(Directory.Exists(staging));

        var second = Path.Combine(temp.Path, "second");
        Directory.CreateDirectory(second);
        await Assert.ThrowsAsync<IOException>(() =>
            CastingReferenceInlineCaptureCommand.PublishManifestAsync(
                second, output, new { schemaVersion = 1 }, default));
        Assert.Equal("retained", await File.ReadAllTextAsync(Path.Combine(output, "candidate.json")));
    }

    private sealed class TempDirectory : IDisposable
    {
        internal TempDirectory()
        {
            Path = System.IO.Path.Combine(
                System.IO.Path.GetTempPath(), "rr2-cast-command-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(Path);
        }
        internal string Path { get; }
        public void Dispose()
        {
            if (Directory.Exists(Path)) Directory.Delete(Path, recursive: true);
        }
    }
}
