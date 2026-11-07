using System.Globalization;
using System.Text.Json;
using RiftReader2.Infrastructure;
namespace RiftReader2.Live;
internal sealed record CurrentBuildLocalizationDictionaryReport(CurrentBuildLocalizationDictionaryObservation Observation)
{
    public int SchemaVersion => 1;
    public string ContractVersion => "native-current-localization-dictionary-candidate-sample/1";
    public string Status => "complete";
    public string[] Limitations => ["Executable SHA256 identifies on-disk bytes; loaded module bytes are not independently hashed.", "Sequential reads and anchors cannot exclude ABA or establish atomicity.", "Cache misses do not establish absence; compressed framing remains a candidate.", "No native getter, initialization, refcount or memory write is performed; freshness and restart are unverified."];
}
internal static class CurrentBuildLocalizationDictionarySampleCommand
{
    internal static async Task<int> RunAsync(IReadOnlyDictionary<string,string> options, TextWriter output, CancellationToken cancellationToken)
    {
        if (!options.TryGetValue("--pid",out var p) || !int.TryParse(p,NumberStyles.None,CultureInfo.InvariantCulture,out var pid) || pid <= 0 || !options.TryGetValue("--start-ticks",out var t) || !long.TryParse(t,NumberStyles.None,CultureInfo.InvariantCulture,out var ticks) || ticks <= 0 || !options.TryGetValue("--keys",out var k) || !options.TryGetValue("--output",out var path) || string.IsNullOrWhiteSpace(path)) throw new ArgumentException("--pid, --start-ticks, --keys and --output are required.");
        var parts = k.Split(','); var keys = new List<uint>(); if (parts.Length is < 1 or > 128) throw new ArgumentException("Provide 1..128 distinct decimal DWORD keys.");
        foreach (var part in parts) { if (!uint.TryParse(part,NumberStyles.None,CultureInfo.InvariantCulture,out var key) || keys.Contains(key)) throw new ArgumentException("Provide 1..128 distinct decimal DWORD keys."); keys.Add(key); }
        if (File.Exists(path)) throw new IOException("Output exists; never overwrite an earlier observation.");
        await using var session = await WindowsNativeMemorySession.OpenAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,cancellationToken);
        cancellationToken.ThrowIfCancellationRequested(); var observation = CurrentBuildLocalizationDictionaryCandidateReader.Read(session,keys);
        if (await session.RevalidateAsync(cancellationToken) is not null) throw new InvalidDataException("Process identity invalidated; no report published.");
        cancellationToken.ThrowIfCancellationRequested(); var report = new CurrentBuildLocalizationDictionaryReport(observation); await JsonReportWriter.WriteNewAsync(path,report,cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(new { recordType = "native-current-localization-dictionary-candidate-summary/1", report.Status, observation.Qualification, output = Path.GetFullPath(path) },new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false })); return 0;
    }
}
