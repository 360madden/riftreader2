using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Cli;

internal static class MemoryDiscoveryCommand
{
    private const int MaxMatches = 10_000;

    public static async Task<int> RunAsync(
        string command,
        IReadOnlyDictionary<string, string> options,
        TextWriter output,
        CancellationToken cancellationToken)
    {
        object report = command switch
        {
            "search-memory" => await SearchAsync(options, cancellationToken),
            "find-pattern" => await FindPatternAsync(options, cancellationToken),
            "compare-memory" => await CompareAsync(options, cancellationToken),
            "find-pointers" => await FindPointersAsync(options, cancellationToken),
            _ => throw new ArgumentException($"Unknown memory discovery command '{command}'.")
        };
        cancellationToken.ThrowIfCancellationRequested();
        if (options.TryGetValue("--output", out var destination))
            await JsonReportWriter.WriteNewAsync(destination, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(report, JsonFormat.Options));
        return 0;
    }

    private static async Task<object> SearchAsync(IReadOnlyDictionary<string, string> options, CancellationToken cancellationToken)
    {
        Require(options, "--snapshot", "--type", "--value");
        var loaded = await NativeMemorySnapshotFile.LoadAsync(options["--snapshot"], cancellationToken);
        EnsureAnalyzable(loaded);
        var kind = ParseKind(options["--type"]);
        double? tolerance = null;
        if (options.TryGetValue("--tolerance", out var toleranceText))
        {
            if (!double.TryParse(toleranceText, NumberStyles.Float, CultureInfo.InvariantCulture, out var parsed) ||
                !double.IsFinite(parsed) || parsed < 0)
                throw new ArgumentException("--tolerance must be a finite non-negative invariant number.");
            tolerance = parsed;
        }
        var result = MemoryDiscovery.Search(loaded.Snapshot, kind, options["--value"], tolerance, MaxMatches, cancellationToken);
        return Report("search-memory", [Input(loaded)], new
        {
            type = options["--type"],
            value = options["--value"],
            tolerance,
            maxMatches = MaxMatches
        }, "Candidates are byte positions whose retained bytes decode as the requested value; a match does not establish field meaning.",
            SearchResult(result), loaded.CoverageWarnings);
    }

    private static async Task<object> FindPatternAsync(IReadOnlyDictionary<string, string> options, CancellationToken cancellationToken)
    {
        Require(options, "--snapshot", "--pattern");
        var loaded = await NativeMemorySnapshotFile.LoadAsync(options["--snapshot"], cancellationToken);
        EnsureAnalyzable(loaded);
        var result = MemoryDiscovery.SearchPattern(loaded.Snapshot, options["--pattern"], MaxMatches, cancellationToken);
        return Report("find-pattern", [Input(loaded)], new
        {
            pattern = options["--pattern"],
            maxMatches = MaxMatches
        }, "Candidates are byte positions matching the requested byte pattern in retained coverage; wildcards and matches do not establish field meaning.",
            SearchResult(result), loaded.CoverageWarnings);
    }

    private static async Task<object> CompareAsync(IReadOnlyDictionary<string, string> options, CancellationToken cancellationToken)
    {
        Require(options, "--before", "--after", "--type", "--mode");
        var before = await NativeMemorySnapshotFile.LoadAsync(options["--before"], cancellationToken);
        var after = await NativeMemorySnapshotFile.LoadAsync(options["--after"], cancellationToken);
        EnsureAnalyzable(before);
        EnsureAnalyzable(after);
        var kind = ParseKind(options["--type"]);
        var comparison = ParseComparison(options["--mode"]);
        var result = MemoryDiscovery.Compare(before.Snapshot, after.Snapshot, kind, comparison, MaxMatches, cancellationToken);
        return Report("compare-memory", [Input(before), Input(after)], new
        {
            type = options["--type"],
            mode = options["--mode"],
            maxMatches = MaxMatches
        }, "Candidates compare the same retained address and value width in two snapshots of the exact same process epoch; change alone does not establish field meaning.",
            SearchResult(result), [.. before.CoverageWarnings.Select(value => $"before: {value}"),
                .. after.CoverageWarnings.Select(value => $"after: {value}")]);
    }

    private static async Task<object> FindPointersAsync(IReadOnlyDictionary<string, string> options, CancellationToken cancellationToken)
    {
        Require(options, "--snapshot", "--target", "--max-depth", "--max-offset");
        var loaded = await NativeMemorySnapshotFile.LoadAsync(options["--snapshot"], cancellationToken);
        EnsureAnalyzable(loaded);
        var target = ParseCanonicalAddress(options["--target"], "--target");
        if (!int.TryParse(options["--max-depth"], NumberStyles.None, CultureInfo.InvariantCulture, out var maxDepth) || maxDepth is < 1 or > 4)
            throw new ArgumentException("--max-depth must be 1..4.");
        if (!uint.TryParse(options["--max-offset"], NumberStyles.None, CultureInfo.InvariantCulture, out var maxOffset) || maxOffset > 4096)
            throw new ArgumentException("--max-offset must be 0..4096.");
        var searchOptions = new MemoryPointerSearchOptions(maxDepth, maxOffset, MaxMatches, 1_000_000, 100_000);
        var result = MemoryDiscovery.FindPointerChains(loaded.Snapshot, target, searchOptions, cancellationToken);
        var outputResult = new
        {
            chains = result.Chains.Select(chain => new
            {
                rootRva = $"0x{chain.RootRva:X}",
                offsets = chain.Offsets.Select(offset => $"0x{offset:X}").ToArray()
            }).ToArray(),
            result.Truncated,
            result.IndexTruncated
        };
        return Report("find-pointers", [Input(loaded)], new
        {
            target = $"0x{target:X}",
            maxDepth,
            maxOffset,
            maxCandidates = MaxMatches,
            maxIndexEntries = searchOptions.MaxIndexEntries,
            maxFrontier = searchOptions.MaxFrontier
        }, "Chains are candidates rooted at the captured module RVA and followed through retained 64-bit pointer values plus offsets; they require live identity-bound resolution and restart/update evidence.",
            outputResult, loaded.CoverageWarnings);
    }

    private static object Report(string operation, IReadOnlyList<object> inputs, object query,
        string candidateSemantics, object result, IReadOnlyList<string> coverageWarnings) => new
        {
            schemaVersion = 1,
            evidenceKind = "memory-discovery-report/1",
            operation,
            implementation = ToolIdentity.FromAssemblies(
            typeof(CliRunner).Assembly.GetName().Version!.ToString(),
            typeof(CliRunner).Assembly, typeof(MemoryDiscovery).Assembly,
            typeof(MemorySnapshot).Assembly, typeof(NativeMemorySnapshotFile).Assembly),
            inputs,
            query,
            candidateSemantics,
            result,
            coverageWarnings,
            limitations = new[]
        {
            "Only valid retained snapshot bytes were searched; holes and partial or unavailable chunks were not synthesized.",
            "Addresses and pointer chains are candidates for the recorded process epoch, not durable field qualifications.",
            "The snapshot source request hash is producer-declared; the loader independently verifies each chunk hash and the complete snapshot file hash."
        }
        };

    private static object Input(LoadedMemorySnapshot loaded) => new
    {
        snapshotSha256 = loaded.FileSha256,
        loaded.File.EvidenceKind,
        loaded.File.Status,
        loaded.File.Identity,
        loaded.File.StartedAtUtc,
        loaded.File.CompletedAtUtc,
        loaded.File.Source,
        analyzableSegmentCount = loaded.Snapshot.Segments.Count,
        analyzableByteCount = loaded.Snapshot.Segments.Sum(segment => (long)segment.Bytes.Length)
    };

    private static object SearchResult(MemorySearchResult result) => new
    {
        result.SearchedBytes,
        result.MatchWidth,
        matches = result.Matches.Select(match => new { address = $"0x{match.Address:X}", match.Value }).ToArray(),
        result.Truncated
    };

    private static MemoryValueKind ParseKind(string value) => value switch
    {
        "int32" => MemoryValueKind.Int32,
        "uint32" => MemoryValueKind.UInt32,
        "int64" => MemoryValueKind.Int64,
        "uint64" => MemoryValueKind.UInt64,
        "float32" => MemoryValueKind.Float32,
        "float64" => MemoryValueKind.Float64,
        _ => throw new ArgumentException("--type must be int32, uint32, int64, uint64, float32, or float64.")
    };

    private static MemoryComparison ParseComparison(string value) => value switch
    {
        "changed" => MemoryComparison.Changed,
        "unchanged" => MemoryComparison.Unchanged,
        "increased" => MemoryComparison.Increased,
        "decreased" => MemoryComparison.Decreased,
        _ => throw new ArgumentException("--mode must be changed, unchanged, increased, or decreased.")
    };

    private static ulong ParseCanonicalAddress(string value, string option)
    {
        if (value.Length is < 3 or > 18 || !value.StartsWith("0x", StringComparison.Ordinal) ||
            !value.AsSpan(2).ToString().All(Uri.IsHexDigit) ||
            !ulong.TryParse(value.AsSpan(2), NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out var address) ||
            value != $"0x{address:X}")
            throw new ArgumentException($"{option} must be canonical uppercase hexadecimal such as 0x1000.");
        return address;
    }

    private static void Require(IReadOnlyDictionary<string, string> options, params string[] required)
    {
        foreach (var name in required)
            if (!options.ContainsKey(name))
                throw new ArgumentException($"{name} is required.");
    }

    private static void EnsureAnalyzable(LoadedMemorySnapshot loaded)
    {
        if (loaded.File.Status == "identity-invalidated")
            throw new InvalidDataException("Memory snapshot identity was invalidated; none of its bytes are analyzable.");
        if (loaded.Snapshot.Segments.Count == 0)
            throw new InvalidDataException("Memory snapshot contains no successful bytes to analyze.");
    }
}
