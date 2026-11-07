using System.Buffers.Binary;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;
namespace RiftReader2.Live;
internal sealed record PlayerNameObservation(object Identity,DateTimeOffset StartedAtUtc,DateTimeOffset CompletedAtUtc,ulong SelfKey,ulong SelfEntity,ulong Health,TargetNameSeed NameSeed,string? BaseNameCandidate,uint? RawDecoration)
{public string Qualification=>"raw self name seed; API name, decoration, freshness and restart unverified";}
internal static class CurrentBuildPlayerNameSampleCommand
{
 internal static async Task<int> RunAsync(IReadOnlyDictionary<string,string> options,TextWriter output,CancellationToken ct)
 {
  if(!options.TryGetValue("--pid",out var p)||!int.TryParse(p,NumberStyles.None,CultureInfo.InvariantCulture,out var pid)||pid<=0||!options.TryGetValue("--start-ticks",out var t)||!long.TryParse(t,NumberStyles.None,CultureInfo.InvariantCulture,out var ticks)||ticks<=0||!options.TryGetValue("--output",out var path)||string.IsNullOrWhiteSpace(path))throw new ArgumentException("--pid, --start-ticks and --output required.");
  if(File.Exists(path))throw new IOException("Output exists.");await using var session=await WindowsNativeMemorySession.OpenAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,ct);ct.ThrowIfCancellationRequested();var observation=Read(session);if(await session.RevalidateAsync(ct) is not null)throw new InvalidDataException("Process invalidated.");ct.ThrowIfCancellationRequested();await JsonReportWriter.WriteNewAsync(path,new{schemaVersion=1,contractVersion="native-current-player-name-candidate/1",status="complete",observation,limitations=new[]{"Raw self name seed does not establish API name or decoration.","Sequential reads cannot exclude ABA; loaded module bytes are not independently hashed.","No game getter, initializer, refcount or memory write is performed."}},ct);await output.WriteLineAsync(JsonSerializer.Serialize(new{recordType="native-current-player-name-summary/1",output=Path.GetFullPath(path)},new JsonSerializerOptions(JsonFormat.Options){WriteIndented=false}));return 0;
 }
 internal static PlayerNameObservation Read(IReadOnlyNativeMemorySession session)=>Read(session,CurrentBuildPlayerContextCandidateReader.Read,s=>{var l=CurrentBuildPlayerLookup.Resolve(s);return new(l.PlayerKey,l.EntityAddress,l.ResolveComponent(0x2F57850),l.VerifyUnchanged);});
 internal static PlayerNameObservation Read(IReadOnlyNativeMemorySession session,Func<IReadOnlyNativeMemorySession,CurrentBuildPlayerContextObservation> context,Func<IReadOnlyNativeMemorySession,PlayerContextOwner> resolve)
 {
  var start=DateTimeOffset.UtcNow;var id=session.Identity;var before=context(session);var lookup=resolve(session);
  if(before.Identity!=id||before.UnitKey!=lookup.Key||before.Entity!=lookup.Entity||before.HealthComponent!=lookup.Health)throw new InvalidDataException("Independent self binding mismatch.");
  var anchors=new Dictionary<(ulong,int),byte[]>();int budget=0;
  byte[] Take(ulong a,int n,bool save=true){budget=checked(budget+n);if(budget>2*1024*1024)throw new InvalidDataException("Name budget exceeded.");var b=CurrentBuildPlayerLookup.Exact(session,a,n);if(save){if(anchors.TryGetValue((a,n),out var old)&&!old.AsSpan().SequenceEqual(b))throw new InvalidDataException("Name bytes changed.");anchors[(a,n)]=b.ToArray();}return b;}
  var health=CurrentBuildPlayerLookup.Pointer(lookup.Health,0x48);var entity=CurrentBuildPlayerLookup.Pointer(lookup.Entity,128);
  if(BinaryPrimitives.ReadUInt64LittleEndian(Take(health+0x10,8))!=entity||BinaryPrimitives.ReadUInt64LittleEndian(Take(health+0x40,8))!=before.Owner)throw new InvalidDataException("Self health owner mismatch.");
  TargetNameSeed name;try{name=CurrentBuildNameSeedReader.Read(session,id,entity,Take,anchors);}catch(InvalidDataException){if(budget>2*1024*1024)throw;name=new("unavailable","name-read-or-type-failure");}
  foreach(var a in anchors)CurrentBuildPlayerLookup.RequireSame(Take(a.Key.Item1,a.Key.Item2,false),a.Value);lookup.Verify();var after=context(session);
  if(after.Identity!=id||after.UnitKey!=before.UnitKey||after.Entity!=entity||after.HealthComponent!=health||after.Owner!=before.Owner||session.Identity!=id)throw new InvalidDataException("Self owner or process changed.");
  return new(id,start,DateTimeOffset.UtcNow,lookup.Key,entity,health,name,name.RawDirect,name.RawDecoration);
 }
}
