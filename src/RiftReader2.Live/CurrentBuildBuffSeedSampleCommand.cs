using System.Globalization;
using System.Text.Json;
using RiftReader2.Infrastructure;
namespace RiftReader2.Live;
internal static class CurrentBuildBuffSeedSampleCommand
{
 internal static async Task<int> RunAsync(IReadOnlyDictionary<string,string> options,TextWriter output,CancellationToken ct)
 {
  if(!options.TryGetValue("--pid",out var p)||!int.TryParse(p,NumberStyles.None,CultureInfo.InvariantCulture,out var pid)||pid<=0||!options.TryGetValue("--start-ticks",out var t)||!long.TryParse(t,NumberStyles.None,CultureInfo.InvariantCulture,out var ticks)||ticks<=0||!options.TryGetValue("--output",out var path)||string.IsNullOrWhiteSpace(path))throw new ArgumentException("--pid, --start-ticks and --output required.");
  if(File.Exists(path))throw new IOException("Output exists; never overwrite an earlier observation.");
  await using var session=await WindowsNativeMemorySession.OpenAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,ct);ct.ThrowIfCancellationRequested();
  var observation=CurrentBuildBuffSeedCandidateReader.Read(session);
  if(await session.RevalidateAsync(ct) is not null)throw new InvalidDataException("Process identity invalidated; no report published.");ct.ThrowIfCancellationRequested();
  var report=new{schemaVersion=1,contractVersion="native-current-buff-seeds-candidate/1",status="complete",observation,limitations=new[]{"Raw nodes do not establish API buff count, visible IDs, names or semantics.","Sequential reads are not atomic and cannot exclude ABA; freshness and restart remain unverified.","Executable SHA256 identifies on-disk bytes; loaded module bytes are not independently hashed.","No getter, initializer, reference-count operation or memory write is performed."}};
  await JsonReportWriter.WriteNewAsync(path,report,ct);
  await output.WriteLineAsync(JsonSerializer.Serialize(new{recordType="native-current-buff-seeds-summary/1",status="complete",observation.Qualification,nodeCount=observation.Nodes.Count,output=Path.GetFullPath(path)},new JsonSerializerOptions(JsonFormat.Options){WriteIndented=false}));return 0;
 }
}
