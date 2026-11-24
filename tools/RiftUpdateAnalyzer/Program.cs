using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace RiftUpdateAnalyzer;

public sealed class FileFact
{
    public long Bytes { get; set; }
    public string Sha256 { get; set; } = "";
    public string ModifiedUtc { get; set; } = "";
}

public sealed class SourceFact
{
    public string Group { get; set; } = "";
    public string Origin { get; set; } = "";
    public string Kind { get; set; } = "";
    public string Status { get; set; } = "present";
}

public sealed class Snapshot
{
    public int SchemaVersion { get; set; } = 1;
    public string Machine { get; set; } = "";
    public string CapturedUtc { get; set; } = "";
    public string Scope { get; set; } = "Selected files only, not a full game installation";
    public List<SourceFact> Sources { get; set; } = [];
    public SortedDictionary<string, FileFact> Files { get; set; } = new(StringComparer.OrdinalIgnoreCase);
}

public sealed class FileDelta
{
    public string Key { get; set; } = "";
    public string Kind { get; set; } = "";
    public FileFact? Before { get; set; }
    public FileFact? After { get; set; }
}

public sealed class Comparison
{
    public int SchemaVersion { get; set; } = 1;
    public string ComparedUtc { get; set; } = "";
    public string BeforeMachine { get; set; } = "";
    public string AfterMachine { get; set; } = "";
    public string BeforeCapturedUtc { get; set; } = "";
    public string AfterCapturedUtc { get; set; } = "";
    public int BeforeFiles { get; set; }
    public int AfterFiles { get; set; }
    public int UnchangedFiles { get; set; }
    public string Scope { get; set; } = "Selected files only; unselected game assets are not compared";
    public List<SourceFact> BeforeSources { get; set; } = [];
    public List<SourceFact> AfterSources { get; set; } = [];
    public List<FileDelta> Deltas { get; set; } = [];
    public bool? GameExecutableObserved { get; set; }
    public bool SourceCoverageChanged { get; set; }
    public bool GameExecutableChanged { get; set; }
    public bool DataOnlyChangePossible { get; set; }
    public bool RuntimeRequalificationRequired { get; set; }
}

internal sealed record SourceSpec(string Group, string Location, bool OptionalMissingDirectory = false);
internal sealed record Limits(int Files, long Bytes);

internal static class Program
{
    private const string ExeKey = "game/rift_x64.exe";
    private const long MaxManifestBytes = 32L * 1024 * 1024;
    private const int MaxManifestEntries = 100_000;
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true, PropertyNameCaseInsensitive = true };

    public static int Main(string[] args)
    {
        try
        {
            if (args.Length == 0 || args[0] is "--help" or "-h" or "help")
            {
                Help();
                return 0;
            }

            var command = args[0].ToLowerInvariant();
            var options = ParseOptions(args.Skip(1).ToArray());
            return command switch
            {
                "capture" => CaptureCommand(options),
                "compare" => CompareCommand(options),
                "report" => ReportCommand(options),
                "run" => RunCommand(options),
                _ => throw new ArgumentException("Unknown command: " + args[0])
            };
        }
        catch (ArgumentException ex)
        {
            Console.Error.WriteLine("INVALID: " + ex.Message);
            return 2;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException or InvalidDataException or CryptographicException)
        {
            Console.Error.WriteLine("FAILED: " + ex.Message);
            return 3;
        }
    }

    private static void Help()
    {
        Console.WriteLine("""
            RiftUpdateAnalyzer — standalone read-only RIFT game-update comparator (.NET 10)
            Commands:
              capture --expected-host VERIFIED_LOCAL_HOST --source game=C:\path\rift_x64.exe
                      --source saved=C:\path\Saved --out C:\path\before.json
                      [--max-files 5000] [--max-bytes 536870912]
              compare --before before.json --after after.json --out changes.json
              report  --comparison changes.json --out changes.md
              run --expected-host VERIFIED_LOCAL_HOST --baseline-dir C:\path\prepatch
                  --game-exe C:\path\rift_x64.exe --interface-dir C:\path\Interface
                  --routes-dir C:\path\waypoint-routes --out-dir C:\path\new-report
                  [--max-files 5000] [--max-bytes 536870912]

            In PowerShell, get the local hostname with [Environment]::MachineName.
            'run' compares the selected prepatch game executable, SavedVariables, named
            backed-up addon folders and waypoint route files against current locations.
            File content is NEVER modified. No RIFT input, update, or memory reading occurs.
            Exit: 0 = success/no differences; 1 = differences detected;
                  2 = bad arguments; 3 = unsafe/incomplete scan or I/O failure.
            """);
    }

    private static Dictionary<string, List<string>> ParseOptions(string[] args)
    {
        var parsed = new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase);
        for (int index = 0; index < args.Length; index += 2)
        {
            if (!args[index].StartsWith("--", StringComparison.Ordinal) || index + 1 >= args.Length ||
                args[index + 1].StartsWith("--", StringComparison.Ordinal))
                throw new ArgumentException("Expected --option value pairs.");
            var name = args[index][2..];
            if (!parsed.TryGetValue(name, out var values))
                parsed[name] = values = [];
            values.Add(args[index + 1]);
        }
        return parsed;
    }

    private static string Require(Dictionary<string, List<string>> options, string key)
    {
        if (!options.TryGetValue(key, out var values) || values.Count != 1 || string.IsNullOrWhiteSpace(values[0]))
            throw new ArgumentException("Exactly one --" + key + " is required.");
        return values[0];
    }

    private static string? Optional(Dictionary<string, List<string>> options, string key)
    {
        if (!options.TryGetValue(key, out var values)) return null;
        if (values.Count != 1) throw new ArgumentException("Duplicate --" + key + ".");
        return values[0];
    }

    private static void Only(Dictionary<string, List<string>> options, params string[] valid)
    {
        var allowed = new HashSet<string>(valid, StringComparer.OrdinalIgnoreCase);
        foreach (var key in options.Keys)
            if (!allowed.Contains(key))
                throw new ArgumentException("Unexpected --" + key + ".");
    }

    private static Limits GetLimits(Dictionary<string, List<string>> options)
    {
        if (!int.TryParse(Optional(options, "max-files") ?? "5000", NumberStyles.Integer, CultureInfo.InvariantCulture, out var fileLimit) ||
            !long.TryParse(Optional(options, "max-bytes") ?? "536870912", NumberStyles.Integer, CultureInfo.InvariantCulture, out var byteLimit))
            throw new ArgumentException("Scan limits must be integers.");
        if (fileLimit is < 1 or > MaxManifestEntries || byteLimit is < 1 or > 32L * 1024 * 1024 * 1024)
            throw new ArgumentException("Scan limits must be positive and bounded.");
        return new Limits(fileLimit, byteLimit);
    }

    private static void HostGuard(string expected)
    {
        if (!string.Equals(Environment.MachineName, expected, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Host mismatch: expected " + expected + "; actual " + Environment.MachineName);
    }

    private static List<SourceSpec> SourceArgs(Dictionary<string, List<string>> options)
    {
        if (!options.TryGetValue("source", out var sources) || sources.Count == 0)
            throw new ArgumentException("At least one --source group=path is required.");
        var result = new List<SourceSpec>();
        foreach (var source in sources)
        {
            var split = source.IndexOf('=');
            if (split <= 0 || split == source.Length - 1)
                throw new ArgumentException("Source must be group=absolute_path.");
            result.Add(new SourceSpec(source[..split], source[(split + 1)..]));
        }
        return result;
    }

    private static int CaptureCommand(Dictionary<string, List<string>> options)
    {
        Only(options, "expected-host", "source", "out", "max-files", "max-bytes");
        HostGuard(Require(options, "expected-host"));
        var snapshot = Capture(SourceArgs(options), GetLimits(options));
        WriteJson(Require(options, "out"), snapshot);
        Console.WriteLine(JsonSerializer.Serialize(new { status = "captured", host = snapshot.Machine, files = snapshot.Files.Count, output = Require(options, "out") }));
        return 0;
    }

    private static int CompareCommand(Dictionary<string, List<string>> options)
    {
        Only(options, "before", "after", "out");
        var before = LoadSnapshot(Require(options, "before"));
        var after = LoadSnapshot(Require(options, "after"));
        var result = Compare(before, after);
        WriteJson(Require(options, "out"), result);
        OutputComparison(result, Require(options, "out"));
        return result.RuntimeRequalificationRequired ? 1 : 0;
    }

    private static int ReportCommand(Dictionary<string, List<string>> options)
    {
        Only(options, "comparison", "out");
        var comparison = LoadComparison(Require(options, "comparison"));
        WriteText(Require(options, "out"), RenderMarkdown(comparison));
        Console.WriteLine(JsonSerializer.Serialize(new { status = "reported", changes = comparison.Deltas.Count, output = Require(options, "out") }));
        return comparison.RuntimeRequalificationRequired || comparison.Deltas.Count > 0 ? 1 : 0;
    }

    private static int RunCommand(Dictionary<string, List<string>> options)
    {
        Only(options, "expected-host", "baseline-dir", "game-exe", "interface-dir", "routes-dir", "out-dir", "max-files", "max-bytes");
        HostGuard(Require(options, "expected-host"));
        var baseline = FullPath(Require(options, "baseline-dir"));
        var gameExe = FullPath(Require(options, "game-exe"));
        var iface = FullPath(Require(options, "interface-dir"));
        var routes = FullPath(Require(options, "routes-dir"));
        var output = FullPath(Require(options, "out-dir"));
        if (!Directory.Exists(baseline)) throw new InvalidDataException("Prepatch baseline directory is missing.");
        if (!File.Exists(gameExe)) throw new InvalidDataException("Current RIFT game executable missing; do not compare during an incomplete update.");
        if (!Directory.Exists(iface)) throw new InvalidDataException("Current RIFT Interface directory is missing.");
        if (!Directory.Exists(System.IO.Path.Combine(iface, "AddOns"))) throw new InvalidDataException("Current AddOns directory is missing; incomplete installation.");
        if (!Directory.Exists(routes)) throw new InvalidDataException("Current waypoint-routes directory is missing.");
        if (Directory.Exists(output) || File.Exists(output))
            throw new IOException("Output directory already exists: " + output + ". Pick a new directory to avoid overwriting evidence.");

        var addonRoot = System.IO.Path.Combine(baseline, "interface-addons");
        if (!Directory.Exists(addonRoot)) throw new InvalidDataException("Baseline addon directory missing.");
        var baselineSources = new List<SourceSpec>
        {
            new("game", System.IO.Path.Combine(baseline, "game", "rift_x64.exe")),
            new("saved", System.IO.Path.Combine(baseline, "interface-saved")),
            new("routes", System.IO.Path.Combine(baseline, "waypoint-routes"))
        };
        var currentSources = new List<SourceSpec>
        {
            new("game", gameExe),
            new("saved", System.IO.Path.Combine(iface, "Saved")),
            new("routes", routes)
        };
        foreach (var addon in Directory.EnumerateDirectories(addonRoot).OrderBy(x => x, StringComparer.OrdinalIgnoreCase))
        {
            CheckNoReparse(addon);
            var name = System.IO.Path.GetFileName(addon);
            ValidateGroup(name);
            baselineSources.Add(new SourceSpec("addon-" + name, addon));
            currentSources.Add(new SourceSpec("addon-" + name, System.IO.Path.Combine(iface, "AddOns", name), true));
        }
        var limits = GetLimits(options);
        var before = Capture(baselineSources, limits);
        var after = Capture(currentSources, limits);
        var comparison = Compare(before, after);
        Directory.CreateDirectory(output);
        WriteJson(System.IO.Path.Combine(output, "before.json"), before);
        WriteJson(System.IO.Path.Combine(output, "after.json"), after);
        WriteJson(System.IO.Path.Combine(output, "changes.json"), comparison);
        WriteText(System.IO.Path.Combine(output, "REPORT.md"), RenderMarkdown(comparison));
        OutputComparison(comparison, System.IO.Path.Combine(output, "REPORT.md"));
        return comparison.RuntimeRequalificationRequired || comparison.Deltas.Count > 0 ? 1 : 0;
    }

    private static string FullPath(string path)
    {
        if (!System.IO.Path.IsPathFullyQualified(path))
            throw new ArgumentException("Absolute paths required: " + path);
        if (path.Split(['\\', '/']).Any(part => part is "." or ".."))
            throw new ArgumentException("Path traversal components not allowed: " + path);
        return System.IO.Path.GetFullPath(path);
    }

    private static void ValidateGroup(string name)
    {
        if (string.IsNullOrWhiteSpace(name) || name.Length > 100 ||
            name is "." or ".." || name.Any(c => !(char.IsAsciiLetterOrDigit(c) || c is '_' or '-' or '.')))
            throw new ArgumentException("Invalid source group: " + name);
    }

    private static void CheckNoReparse(string path)
    {
        var info = System.IO.Path.GetFullPath(path);
        while (true)
        {
            if (File.Exists(info) || Directory.Exists(info))
            {
                if ((File.GetAttributes(info) & FileAttributes.ReparsePoint) != 0)
                    throw new InvalidDataException("Reparse point/junction refused: " + info);
            }
            var parent = Directory.GetParent(info)?.FullName;
            if (parent is null || parent == info) break;
            info = parent;
        }
    }

    private static Snapshot Capture(IEnumerable<SourceSpec> sources, Limits limits)
    {
        var snapshot = new Snapshot { Machine = Environment.MachineName, CapturedUtc = DateTimeOffset.UtcNow.ToString("O") };
        var groups = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        long scannedBytes = 0;
        foreach (var source in sources)
        {
            ValidateGroup(source.Group);
            if (!groups.Add(source.Group))
                throw new ArgumentException("Duplicate source group: " + source.Group);
            var root = FullPath(source.Location);
            CheckNoReparse(root);
            if (File.Exists(root))
            {
                snapshot.Sources.Add(new SourceFact { Group = source.Group, Origin = root, Kind = "file" });
                AddFile(snapshot, source.Group + "/" + System.IO.Path.GetFileName(root), root, limits, ref scannedBytes);
            }
            else if (Directory.Exists(root))
            {
                snapshot.Sources.Add(new SourceFact { Group = source.Group, Origin = root, Kind = "directory" });
                Traverse(root, root, source.Group, snapshot, limits, ref scannedBytes);
            }
            else if (source.OptionalMissingDirectory)
            {
                snapshot.Sources.Add(new SourceFact { Group = source.Group, Origin = root, Kind = "directory", Status = "missing" });
            }
            else
            {
                throw new InvalidDataException("Required source is missing: " + root);
            }
        }
        return snapshot;
    }

    private static void Traverse(string root, string current, string group, Snapshot snapshot, Limits limits, ref long scannedBytes)
    {
        foreach (var path in Directory.EnumerateFileSystemEntries(current).OrderBy(x => x, StringComparer.OrdinalIgnoreCase))
        {
            CheckNoReparse(path);
            var attributes = File.GetAttributes(path);
            if ((attributes & FileAttributes.Directory) != 0)
            {
                Traverse(root, path, group, snapshot, limits, ref scannedBytes);
                continue;
            }
            var relative = System.IO.Path.GetRelativePath(root, path).Replace('\\', '/');
            if (relative.Split('/').Any(part => part is "" or "." or ".."))
                throw new InvalidDataException("Unsafe relative path: " + relative);
            AddFile(snapshot, group + "/" + relative, path, limits, ref scannedBytes);
        }
    }

    private static void AddFile(Snapshot snapshot, string key, string path, Limits limits, ref long scannedBytes)
    {
        if (snapshot.Files.ContainsKey(key)) throw new InvalidDataException("Duplicate logical key: " + key);
        if (snapshot.Files.Count >= limits.Files) throw new InvalidDataException("Scan file count limit exceeded.");
        var file = new FileInfo(path);
        var beforeSize = file.Length;
        var beforeModified = file.LastWriteTimeUtc;
        if (beforeSize < 0 || beforeSize > limits.Bytes - scannedBytes)
            throw new InvalidDataException("Scan byte limit exceeded at " + path);
        string hash;
        using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
        {
            hash = Convert.ToHexString(SHA256.HashData(stream));
        }
        file.Refresh();
        if (!file.Exists || file.Length != beforeSize || file.LastWriteTimeUtc != beforeModified)
            throw new InvalidDataException("Source changed while hashing (incomplete capture): " + path);
        scannedBytes += beforeSize;
        snapshot.Files.Add(key, new FileFact { Bytes = beforeSize, Sha256 = hash, ModifiedUtc = beforeModified.ToString("O", CultureInfo.InvariantCulture) });
    }

    private static Comparison Compare(Snapshot before, Snapshot after)
    {
        if (!string.Equals(before.Machine, after.Machine, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Cross-host snapshots refused: " + before.Machine + " vs " + after.Machine);
        // Different groups or source kinds are not comparable, even if both contain zero files.
        var oldSources = before.Sources.ToDictionary(x => x.Group, StringComparer.OrdinalIgnoreCase);
        var newSources = after.Sources.ToDictionary(x => x.Group, StringComparer.OrdinalIgnoreCase);
        if (oldSources.Count != newSources.Count || oldSources.Any(x => !newSources.TryGetValue(x.Key, out var source) || source.Kind != x.Value.Kind))
            throw new InvalidDataException("Snapshot source coverage mismatch: compare the same logical groups and source kinds.");
        var result = new Comparison
        {
            ComparedUtc = DateTimeOffset.UtcNow.ToString("O"),
            BeforeMachine = before.Machine,
            AfterMachine = after.Machine,
            BeforeCapturedUtc = before.CapturedUtc,
            AfterCapturedUtc = after.CapturedUtc,
            BeforeFiles = before.Files.Count,
            AfterFiles = after.Files.Count,
            BeforeSources = before.Sources,
            AfterSources = after.Sources,
            SourceCoverageChanged = oldSources.Any(x => x.Value.Status != newSources[x.Key].Status)
        };
        foreach (var key in before.Files.Keys.Union(after.Files.Keys, StringComparer.OrdinalIgnoreCase).OrderBy(x => x, StringComparer.OrdinalIgnoreCase))
        {
            before.Files.TryGetValue(key, out var old);
            after.Files.TryGetValue(key, out var now);
            var kind = old is null ? "added" : now is null ? "removed" :
                old.Sha256.Equals(now.Sha256, StringComparison.OrdinalIgnoreCase) && old.Bytes == now.Bytes ? "unchanged" : "modified";
            if (kind != "unchanged")
                result.Deltas.Add(new FileDelta { Key = key, Kind = kind, Before = old, After = now });
        }
        var exeBefore = before.Files.GetValueOrDefault(ExeKey);
        var exeAfter = after.Files.GetValueOrDefault(ExeKey);
        result.UnchangedFiles = before.Files.Count - result.Deltas.Count(x => x.Kind is "removed" or "modified");
        // Generic selected-file comparisons may omit the executable altogether.
        // Absence from both snapshots is unknown coverage, not a changed binary.
        result.GameExecutableObserved = exeBefore is not null || exeAfter is not null;
        result.GameExecutableChanged = result.GameExecutableObserved == true &&
            (exeBefore is null || exeAfter is null || exeBefore.Bytes != exeAfter.Bytes ||
             !string.Equals(exeBefore.Sha256, exeAfter.Sha256, StringComparison.OrdinalIgnoreCase));
        result.RuntimeRequalificationRequired = result.Deltas.Count > 0 || result.SourceCoverageChanged;
        result.DataOnlyChangePossible = result.GameExecutableObserved == true && !result.GameExecutableChanged &&
            result.RuntimeRequalificationRequired;
        return result;
    }

    private static Snapshot LoadSnapshot(string path)
    {
        var snapshot = ReadJson<Snapshot>(path);
        if (snapshot.SchemaVersion != 1 || string.IsNullOrWhiteSpace(snapshot.Machine) ||
            snapshot.Files is null || snapshot.Sources is null || snapshot.Files.Count > MaxManifestEntries)
            throw new InvalidDataException("Invalid or unsupported snapshot schema.");
        if (!DateTimeOffset.TryParse(snapshot.CapturedUtc, out _) || snapshot.Sources.Count == 0)
            throw new InvalidDataException("Snapshot capture timestamp or source coverage missing.");
        var sources = new Dictionary<string, SourceFact>(StringComparer.OrdinalIgnoreCase);
        foreach (var source in snapshot.Sources)
        {
            if (source is null || string.IsNullOrWhiteSpace(source.Group) || string.IsNullOrWhiteSpace(source.Origin) ||
                source.Kind is not ("file" or "directory") || source.Status is not ("present" or "missing") ||
                (source.Status == "missing" && source.Kind != "directory") || !sources.TryAdd(source.Group, source))
                throw new InvalidDataException("Invalid or duplicate snapshot source.");
        }
        // JSON deserialization may replace the initialized dictionary comparer.
        // Restore case-insensitive lookup to match capture and union semantics.
        snapshot.Files = new SortedDictionary<string, FileFact>(snapshot.Files, StringComparer.OrdinalIgnoreCase);
        ValidateFileKeys(snapshot.Files, sources);
        return snapshot;
    }

    private static void ValidateFileKeys(SortedDictionary<string, FileFact> facts, Dictionary<string, SourceFact> sources)
    {
        var counts = sources.Keys.ToDictionary(key => key, _ => 0, StringComparer.OrdinalIgnoreCase);
        foreach (var (key, fact) in facts)
        {
            if (key.StartsWith('/') || key.Contains('\\') || key.Split('/').Length < 2 ||
                key.Split('/').Any(p => p is "" or "." or ".."))
                throw new InvalidDataException("Invalid manifest path: " + key);
            var group = key.Split('/')[0];
            if (!sources.TryGetValue(group, out var source) || source.Status != "present")
                throw new InvalidDataException("File fact outside present source coverage: " + key);
            counts[group]++;
            if (fact is null || fact.Bytes < 0 || fact.Sha256 is null || fact.Sha256.Length != 64 ||
                fact.Sha256.Any(c => !Uri.IsHexDigit(c)) ||
                !DateTimeOffset.TryParse(fact.ModifiedUtc, out _))
                throw new InvalidDataException("Invalid manifest file hash, length or timestamp: " + key);
        }
        foreach (var source in sources.Values)
            if (source.Kind == "file" && counts[source.Group] != 1)
                throw new InvalidDataException("File source must contain exactly one file fact: " + source.Group);
    }

    private static Comparison LoadComparison(string path)
    {
        var comparison = ReadJson<Comparison>(path);
        if (comparison.SchemaVersion != 1 || comparison.Deltas is null || comparison.Deltas.Count > MaxManifestEntries)
            throw new InvalidDataException("Invalid or unsupported comparison schema.");
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var delta in comparison.Deltas)
        {
            if (string.IsNullOrEmpty(delta.Key) || !seen.Add(delta.Key) ||
                delta.Kind is not ("added" or "removed" or "modified"))
                throw new InvalidDataException("Invalid comparison delta.");
        }
        return comparison;
    }

    private static T ReadJson<T>(string path)
    {
        path = FullPath(path);
        CheckNoReparse(path);
        if (new FileInfo(path).Length > MaxManifestBytes) throw new InvalidDataException("Manifest too large.");
        // Parse and validate the exact same bytes that are deserialized. A second
        // file read could validate different content during a concurrent replacement.
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        if (document.RootElement.ValueKind != JsonValueKind.Object)
            throw new InvalidDataException("Manifest root must be an object.");
        RejectDuplicateProperties(document.RootElement);
        if (typeof(T) == typeof(Snapshot) &&
            (!document.RootElement.TryGetProperty("Files", out var files) || files.ValueKind != JsonValueKind.Object))
            throw new InvalidDataException("Snapshot Files object is missing.");
        return document.RootElement.Deserialize<T>(JsonOptions) ??
            throw new InvalidDataException("Empty or invalid JSON manifest.");
    }

    private static void RejectDuplicateProperties(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var property in element.EnumerateObject())
            {
                if (!seen.Add(property.Name)) throw new InvalidDataException("Duplicate manifest key: " + property.Name);
                RejectDuplicateProperties(property.Value);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
            foreach (var item in element.EnumerateArray()) RejectDuplicateProperties(item);
    }

    private static void WriteJson<T>(string path, T value) => WriteText(path, JsonSerializer.Serialize(value, JsonOptions) + Environment.NewLine);

    private static void WriteText(string path, string content)
    {
        path = FullPath(path);
        var parent = System.IO.Path.GetDirectoryName(path) ?? throw new ArgumentException("Output path has no parent.");
        if (!Directory.Exists(parent)) Directory.CreateDirectory(parent);
        CheckNoReparse(parent);
        using var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        using var writer = new StreamWriter(stream, new UTF8Encoding(false));
        writer.Write(content);
    }

    private static void OutputComparison(Comparison comparison, string path)
    {
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            status = comparison.RuntimeRequalificationRequired ? "changes-detected" : "unchanged",
            host = comparison.AfterMachine,
            beforeFiles = comparison.BeforeFiles,
            afterFiles = comparison.AfterFiles,
            unchanged = comparison.UnchangedFiles,
            added = comparison.Deltas.Count(x => x.Kind == "added"),
            removed = comparison.Deltas.Count(x => x.Kind == "removed"),
            modified = comparison.Deltas.Count(x => x.Kind == "modified"),
            exeObserved = comparison.GameExecutableObserved,
            sourceCoverageChanged = comparison.SourceCoverageChanged,
            exeChanged = comparison.GameExecutableChanged,
            dataOnlyChangePossible = comparison.DataOnlyChangePossible,
            requalificationNeeded = comparison.RuntimeRequalificationRequired,
            output = path
        }));
    }

    private static string RenderMarkdown(Comparison c)
    {
        var sb = new StringBuilder();
        sb.AppendLine("# RIFT selected-file update comparison");
        sb.AppendLine();
        sb.AppendLine("- Compared UTC: " + c.ComparedUtc);
        sb.AppendLine("- Before host: " + c.BeforeMachine);
        sb.AppendLine("- After host: " + c.AfterMachine);
        sb.AppendLine("- Baseline captured UTC: " + c.BeforeCapturedUtc);
        sb.AppendLine("- Current captured UTC: " + c.AfterCapturedUtc);
        sb.AppendLine("- Coverage: " + c.Scope);
        sb.AppendLine("- **Executable changed:** " + (c.GameExecutableObserved == false ? "NOT COVERED" : c.GameExecutableChanged ? "YES or missing" : "NO"));
        sb.AppendLine("- **Source presence changed:** " + (c.SourceCoverageChanged ? "YES" : "NO"));
        sb.AppendLine("- **Other selected files changed while executable stayed identical:** " + (c.DataOnlyChangePossible ? "YES" : "NO"));
        sb.AppendLine("- **Runtime/native-reader requalification:** " + (c.RuntimeRequalificationRequired ? "REQUIRED before trusting affected live readers" : "No selected-file differences; this is NOT proof of runtime compatibility"));
        sb.AppendLine();
        sb.AppendLine("## Change summary");
        sb.AppendLine();
        sb.AppendLine("| Before files | After files | Unchanged | Added | Removed | Modified |");
        sb.AppendLine("|---:|---:|---:|---:|---:|---:|");
        sb.AppendLine($"| {c.BeforeFiles} | {c.AfterFiles} | {c.UnchangedFiles} | {c.Deltas.Count(x => x.Kind == "added")} | {c.Deltas.Count(x => x.Kind == "removed")} | {c.Deltas.Count(x => x.Kind == "modified")} |");
        sb.AppendLine();
        sb.AppendLine("## Selected sources and coverage");
        sb.AppendLine();
        sb.AppendLine("| Phase | Group | Status | Origin |");
        sb.AppendLine("|---|---|---|---|");
        foreach (var item in c.BeforeSources) sb.AppendLine($"| Before | {Esc(item.Group)} | {Esc(item.Status)} | {Esc(item.Origin)} |");
        foreach (var item in c.AfterSources) sb.AppendLine($"| After | {Esc(item.Group)} | {Esc(item.Status)} | {Esc(item.Origin)} |");
        sb.AppendLine();
        sb.AppendLine("## Changed selected files");
        sb.AppendLine();
        if (c.Deltas.Count == 0) sb.AppendLine("No SHA-256/size differences in the selected files.");
        else
        {
            sb.AppendLine("| Kind | Logical path | Before SHA-256 | After SHA-256 |");
            sb.AppendLine("|---|---|---|---|");
            foreach (var delta in c.Deltas)
                sb.AppendLine($"| {Esc(delta.Kind)} | {Esc(delta.Key)} | {delta.Before?.Sha256 ?? "—"} | {delta.After?.Sha256 ?? "—"} |");
        }
        sb.AppendLine();
        sb.AppendLine("## Operational interpretation");
        sb.AppendLine();
        sb.AppendLine("- Coverage is limited to the logical sources listed above. Unselected installation files and game data archives are not compared.");
        sb.AppendLine("- A matching executable SHA-256 does **not** prove that the patch changed nothing: unselected game data can change.");
        sb.AppendLine("- Changed executable bytes invalidate any assumption that historical native offsets/pointers or runtime semantic evidence still apply. Rebind to a fresh exact process/build and requalify before resuming affected live automation.");
        sb.AppendLine("- Game update installation state is not established by this report. Addon or route file changes can also come from user/project activity.");
        sb.AppendLine("- No client input, update initiation, game-file writes, or process-memory reads were performed.");
        return sb.ToString();
    }

    private static string Esc(string text) => text.Replace("|", "\\|").Replace("\r", " ").Replace("\n", " ");
}
