using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;
namespace RiftReader2.Live;
internal static class CurrentBuildBuffSeedSampleCommand
{
 internal static Task<int> RunAsync(IReadOnlyDictionary<string,string> options, TextWriter output, CancellationToken ct) =>
  RunAsync(options, output, ct,
   async (pid, ticks, token) => await WindowsNativeMemorySession.OpenAsync(pid, ticks, CurrentBuildPlayerLookup.GameSha256, token),
   CurrentBuildBuffSeedCandidateReader.Read,
   async (pid, ticks, sha, token) => await NativeReadFileLease.AcquireAsync(pid, ticks, sha, TimeSpan.FromSeconds(1), token));

 // Explicit offline seam; production always owns the shared lease before opening.
 internal static async Task<int> RunAsync(IReadOnlyDictionary<string,string> options, TextWriter output, CancellationToken ct,
  Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> open,
  Func<IReadOnlyNativeMemorySession, bool, CurrentBuildBuffSeedObservation> read,
  Func<int, long, string, CancellationToken, Task<IAsyncDisposable>> acquireLease)
 {
  ArgumentNullException.ThrowIfNull(options);
  ArgumentNullException.ThrowIfNull(output);
  ArgumentNullException.ThrowIfNull(open);
  ArgumentNullException.ThrowIfNull(read);
  ArgumentNullException.ThrowIfNull(acquireLease);
  if(!options.TryGetValue("--pid",out var p)||!int.TryParse(p,NumberStyles.None,CultureInfo.InvariantCulture,out var pid)||pid<=0||!options.TryGetValue("--start-ticks",out var t)||!long.TryParse(t,NumberStyles.None,CultureInfo.InvariantCulture,out var ticks)||ticks<=0||!options.TryGetValue("--output",out var path)||string.IsNullOrWhiteSpace(path))throw new ArgumentException("--pid, --start-ticks and --output required.");
  var includeTiming = options.TryGetValue("--include-timing", out var timing)
      ? timing == "true" ? true : throw new ArgumentException("--include-timing must be true.") : false;
  if(File.Exists(path))throw new IOException("Output exists; never overwrite an earlier observation.");
  ct.ThrowIfCancellationRequested();
  await using var lease = await acquireLease(pid, ticks, CurrentBuildPlayerLookup.GameSha256, ct);
  ct.ThrowIfCancellationRequested();
  // Reverse disposal order retains the lease through asynchronous session cleanup.
  await using var session = await open(pid, ticks, ct);
  ct.ThrowIfCancellationRequested();
  var identity = session.Identity;
  if(identity.ProcessId != pid || identity.ProcessStartUtcTicks != ticks ||
     !string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase))
   throw new InvalidDataException("Buff session does not match requested process epoch/build.");
  var observation = read(session, includeTiming);
  if(!Equals(observation.Identity, identity) || session.Identity != identity)
   throw new InvalidDataException("Buff observation process identity changed.");
  ct.ThrowIfCancellationRequested();
  if(await session.RevalidateAsync(ct) is not null || session.Identity != identity)
   throw new InvalidDataException("Process identity invalidated; no report published.");
  ct.ThrowIfCancellationRequested();
  var report=new{schemaVersion=1,contractVersion="native-current-buff-seeds-candidate/1",status="complete",observation,limitations=new[]{"Raw nodes do not establish API buff count, visible IDs, names or semantics.","Sequential reads are not atomic and cannot exclude ABA; freshness and restart remain unverified.","Executable SHA256 identifies on-disk bytes; loaded module bytes are not independently hashed.","No getter, initializer, reference-count operation or memory write is performed."}};
  await JsonReportWriter.WriteNewAsync(path,report,ct);
  await output.WriteLineAsync(JsonSerializer.Serialize(new{recordType="native-current-buff-seeds-summary/1",status="complete",observation.Qualification,nodeCount=observation.Nodes.Count,output=Path.GetFullPath(path)},new JsonSerializerOptions(JsonFormat.Options){WriteIndented=false}));return 0;
 }

}
