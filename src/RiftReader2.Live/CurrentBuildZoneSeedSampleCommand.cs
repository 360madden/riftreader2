using System.Buffers.Binary;
using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;
namespace RiftReader2.Live;
internal sealed record ZoneSeedObservation(object Identity,DateTimeOffset StartedAtUtc,DateTimeOffset CompletedAtUtc,ulong SelfKey,ulong SelfEntity,ulong Health,ulong Owner,uint RawZoneKey,string Status,ushort? Selector=null,uint? TlsIndex=null,ulong? Collection=null,ulong? RecordAddress=null,ulong? RecordVtable=null,ulong? RecordGetterRva=null,ulong? RawNameRef=null,string? ChildStatus=null,uint? ChildKey=null,string? ZoneIdCandidate=null)
{
 public string Qualification=>"zone ID candidate only; API correspondence, name, freshness and restart unverified";
 // Diagnostic duration only; excludes lease/session acquisition and command-level revalidation.
 // Null preserves honest absence for offline/legacy observations constructed without measurement.
 public double? AcquisitionElapsedMilliseconds {get;init;}
 public string? AcquisitionElapsedClock=>AcquisitionElapsedMilliseconds.HasValue?"monotonic-stopwatch":null;
 public string? AcquisitionElapsedKind=>AcquisitionElapsedMilliseconds.HasValue?"zone-read-including-final-validation":null;
}
internal static class CurrentBuildZoneSeedSampleCommand
{
 internal static Task<int> RunAsync(IReadOnlyDictionary<string,string> options,TextWriter output,CancellationToken ct)=>
  RunAsync(options,output,ct,
   static async (pid,ticks,token)=>await NativeReadFileLease.AcquireAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,TimeSpan.FromSeconds(1),token),
   static async (pid,ticks,token)=>await WindowsNativeMemorySession.OpenAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,token),
   static (session,pid)=>Read(session,CurrentBuildPlayerContextCandidateReader.Read,()=>WindowsThreadTlsSnapshot.Capture(pid)));
 // Explicit offline-only seam; production entry supplies the real lease.
 internal static async Task<int> RunAsync(IReadOnlyDictionary<string,string> options,TextWriter output,CancellationToken ct,
  Func<int,long,CancellationToken,Task<IAsyncDisposable>> acquireLease,
  Func<int,long,CancellationToken,Task<IReadOnlyNativeMemorySession>> open,
  Func<IReadOnlyNativeMemorySession,int,ZoneSeedObservation> read)
 {
  ArgumentNullException.ThrowIfNull(acquireLease);ArgumentNullException.ThrowIfNull(open);ArgumentNullException.ThrowIfNull(read);
  if(!options.TryGetValue("--pid",out var p)||!int.TryParse(p,NumberStyles.None,CultureInfo.InvariantCulture,out var pid)||pid<=0||!options.TryGetValue("--start-ticks",out var t)||!long.TryParse(t,NumberStyles.None,CultureInfo.InvariantCulture,out var ticks)||ticks<=0||!options.TryGetValue("--output",out var path)||string.IsNullOrWhiteSpace(path))throw new ArgumentException("--pid, --start-ticks, --output required.");
  if(File.Exists(path))throw new IOException("Output exists.");
  ZoneSeedObservation observation;
  await using (var lease=await acquireLease(pid,ticks,ct))
  {
   ct.ThrowIfCancellationRequested();
   await using var session=await open(pid,ticks,ct);ct.ThrowIfCancellationRequested();
   observation=read(session,pid);
   if(await session.RevalidateAsync(ct) is not null)throw new InvalidDataException("Process identity invalidated.");
   ct.ThrowIfCancellationRequested();
  }
  // Disk and output writes do not need the native lease or process session.
  ct.ThrowIfCancellationRequested();
  var report=new{schemaVersion=1,contractVersion="native-current-zone-seed-candidate/1",status="complete",observation,limitations=new[]{"Cache-only; misses do not establish a missing zone.","Sequential reads cannot exclude ABA; loaded module bytes are not independently hashed.","No getter, initialization, refcount or memory writes; zone ID or name and restart unverified."}};
  await JsonReportWriter.WriteNewAsync(path,report,ct);await output.WriteLineAsync(JsonSerializer.Serialize(new{recordType="native-current-zone-seed-summary/1",observation.Status,output=Path.GetFullPath(path)},new JsonSerializerOptions(JsonFormat.Options){WriteIndented=false}));return 0;
 }
 internal static ZoneSeedObservation Read(IReadOnlyNativeMemorySession session,Func<IReadOnlyNativeMemorySession,CurrentBuildPlayerContextObservation> context,Func<IReadOnlyList<NativeThreadEpoch>> threads)
 {
  var startedTimestamp=Stopwatch.GetTimestamp();var start=DateTimeOffset.UtcNow;var id=session.Identity;
  if(id.ProcessId<=0||id.ProcessStartUtcTicks<=0||id.ModuleSize<0x34731B8||!string.Equals(id.ExecutableSha256,CurrentBuildPlayerLookup.GameSha256,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("Unsupported build or process.");
  var before=context(session);if(before.Identity!=id)throw new InvalidDataException("Self context identity mismatch.");
  var anchors=new Dictionary<(ulong,int),byte[]>();int budget=0;byte[] Take(ulong a,int n,bool save=true){budget=checked(budget+n);if(budget>2*1024*1024)throw new InvalidDataException("Zone budget exceeded.");var b=CurrentBuildPlayerLookup.Exact(session,a,n);if(save){if(anchors.TryGetValue((a,n),out var old)&&!old.AsSpan().SequenceEqual(b))throw new InvalidDataException("Zone bytes changed.");anchors[(a,n)]=b.ToArray();}return b;}
  ulong Ptr(ulong a,int n=8)=>CurrentBuildPlayerLookup.Pointer(a,n);ulong Q(ulong a)=>U64(Take(a,8));
  var health=Ptr(before.HealthComponent,0x48);var entity=Ptr(before.Entity,128);var selfOwner=Ptr(Q(health+0x40),0x154);
  if(Q(health+0x10)!=entity||selfOwner!=before.Owner||Q(selfOwner)!=id.ModuleBaseAddress+0x2927448||Q(id.ModuleBaseAddress+0x2927488)!=id.ModuleBaseAddress+0x19D21E0||Q(id.ModuleBaseAddress+0x34731B0)!=id.ModuleBaseAddress+0x2929BD0||Q(id.ModuleBaseAddress+0x2929BD8)!=id.ModuleBaseAddress+0x19F4D60)throw new InvalidDataException("Self owner binding/type mismatch.");
  var system=Ptr(Q(id.ModuleBaseAddress+0x33623E0),0x400);if(Q(system+0x3F8)!=entity||Q(system+0x360)!=before.UnitKey)throw new InvalidDataException("Self cache mismatch.");
  var zoneKey=BinaryPrimitives.ReadUInt32LittleEndian(Take(selfOwner+0x150,4));
  IReadOnlyList<NativeThreadEpoch>? epochs=null;
  ZoneSeedObservation Finish(string status,ushort? selector=null,uint? index=null,ulong? collection=null,ulong? record=null,ulong? vt=null,ulong? getter=null,ulong? nameRef=null,string? childStatus=null,uint? childKey=null,string? zoneId=null)
  {
   foreach(var x in anchors)CurrentBuildPlayerLookup.RequireSame(Take(x.Key.Item1,x.Key.Item2,false),x.Value);
   var final=context(session);if(final.Identity!=id||final.UnitKey!=before.UnitKey||final.Entity!=entity||final.HealthComponent!=health||final.Owner!=selfOwner||session.Identity!=id)throw new InvalidDataException("Self owner or epoch changed.");
   if(epochs is not null&&!epochs.OrderBy(x=>x.Id).SequenceEqual(threads().OrderBy(x=>x.Id)))throw new InvalidDataException("Thread epoch changed.");
   if(session.Identity!=id)throw new InvalidDataException("Process identity changed.");
   return new(id,start,DateTimeOffset.UtcNow,before.UnitKey,entity,health,selfOwner,zoneKey,status,selector,index,collection,record,vt,getter,nameRef,childStatus,childKey,zoneId){AcquisitionElapsedMilliseconds=Stopwatch.GetElapsedTime(startedTimestamp).TotalMilliseconds};
  }
  var provider=Q(id.ModuleBaseAddress+0x336EBF8);if(provider==0)return Finish("null-provider");Ptr(provider,0x42);
  var selector=BinaryPrimitives.ReadUInt16LittleEndian(Take(provider+0x40,2));var wrapperRaw=Q(id.ModuleBaseAddress+0x3372C18);if(wrapperRaw==0)return Finish("null-registry",selector);var wrapper=Ptr(wrapperRaw);var registryRaw=Q(wrapper);if(registryRaw==0)return Finish("null-registry",selector);var owner=Ptr(registryRaw,0x278);var index=BinaryPrimitives.ReadUInt32LittleEndian(Take(owner+0x274,4));if(index>1087)throw new InvalidDataException("Invalid TLS index.");
  epochs=threads();if(epochs.Count is <1 or >256||epochs.Select(x=>x.Id).Distinct().Count()!=epochs.Count||epochs.Select(x=>x.Teb).Distinct().Count()!=epochs.Count)throw new InvalidDataException("Invalid thread set.");ulong? collection=null;
  foreach(var t in epochs){Ptr(t.Teb,0x1788);var ti=Take(t.Teb+0x30,32);if(t.Id<=0||t.Created<=0||U64(ti)!=t.Teb||U64(ti.AsSpan(16))!=(ulong)id.ProcessId||U64(ti.AsSpan(24))!=(ulong)t.Id)throw new InvalidDataException("Invalid TEB identity.");ulong v;if(index<64)v=Q(t.Teb+0x1480+index*8UL);else{var expansion=Q(t.Teb+0x1780);v=expansion==0?0:Q(checked(Ptr(expansion)+(index-64)*8UL));}var c=v==0?checked(owner+0x200):Ptr(v);if(collection.HasValue&&collection!=c)throw new InvalidDataException("Thread collections disagree.");collection=c;}
  var ch=Take(collection!.Value+0x20,32);var cb=Ptr(U64(ch));var cs=U64(ch.AsSpan(8));var cc=U64(ch.AsSpan(16));if(cs!=24||cc is <1 or >4096)throw new InvalidDataException("Invalid cache header.");Ptr(cb,checked((int)(cc*24)));
  var hash=CurrentBuildAbilityRecordsCandidateReader.Hash(zoneKey);var a=checked(cb+CurrentBuildAbilityRecordsCandidateReader.Hash(hash)%cc*24);var seen=new HashSet<ulong>();var head=true;byte[]? found=null;
  for(int i=0;i<=128;i++){if(!seen.Add(a))throw new InvalidDataException("Cache cycle.");var n=Take(a,24);var link=U64(n);if((!head||(link&1)==0)&&BinaryPrimitives.ReadUInt16LittleEndian(n.AsSpan(8))==selector&&BinaryPrimitives.ReadUInt32LittleEndian(n.AsSpan(12))==zoneKey){found=n;break;}var next=link&~1UL;if(next==0)break;if(i==128)throw new InvalidDataException("Cache chain budget.");a=Ptr(next,24);head=false;}
  string status="cache-miss";ulong? record=null,vt=null,getter=null,nameRef=null;string? childStatus=null;uint? childKey=null;string? zoneId=null;
  if(found is not null)
  {
   var holder=U64(found.AsSpan(16));if(holder==0)status="null-holder";else{var obj=Q(Ptr(holder,0x20)+0x18);if(obj==0)status="null-record";else
   {
    record=Ptr(obj,0x1F8);status="unqualified-cache-record";vt=Q(obj);
    if(vt>=id.ModuleBaseAddress&&vt<=id.ModuleBaseAddress+id.ModuleSize-0x48){var target=Q(vt.Value+0x40);if(target>=id.ModuleBaseAddress&&target<id.ModuleBaseAddress+id.ModuleSize)getter=target-id.ModuleBaseAddress;}
    var outerVerified=vt==id.ModuleBaseAddress+0x2B254A8&&Q(id.ModuleBaseAddress+0x2B254E8)==id.ModuleBaseAddress+0x1E772C0&&Q(id.ModuleBaseAddress+0x35109E0)==id.ModuleBaseAddress+0x2B2FEE0&&Q(id.ModuleBaseAddress+0x2B2FEE8)==id.ModuleBaseAddress+0x1E9FD50;
    if(outerVerified)status="type-0073-candidate";
    nameRef=Q(obj+0x1F0);if(nameRef==0)childStatus="null";else{var child=Ptr(nameRef.Value,0x1C);if(Q(child)==id.ModuleBaseAddress+0x27F24F8&&Q(id.ModuleBaseAddress+0x27F2538)==id.ModuleBaseAddress+0x170C5D0&&Q(id.ModuleBaseAddress+0x3417970)==id.ModuleBaseAddress+0x2802E40&&Q(id.ModuleBaseAddress+0x2802E48)==id.ModuleBaseAddress+0x17361E0){childStatus="type-1e17-raw-candidate";childKey=BinaryPrimitives.ReadUInt32LittleEndian(Take(child+0x18,4));}else childStatus="unverified-type";}
   }}
  }
  if(status=="type-0073-candidate"&&(childStatus=="null"||childStatus=="type-1e17-raw-candidate"))
  {
   var term=childStatus=="null"?0U:CurrentBuildAbilityRecordsCandidateReader.Hash(childKey!.Value);
   var sum=unchecked(term+0x7A6F656EU);var low=unchecked(CurrentBuildAbilityRecordsCandidateReader.Hash(sum)+sum);
   zoneId=$"z{(((ulong)zoneKey<<32)|low):X16}";
  }
  return Finish(status,selector,index,collection,record,vt,getter,nameRef,childStatus,childKey,zoneId);
 }
 static ulong U64(ReadOnlySpan<byte>b)=>BinaryPrimitives.ReadUInt64LittleEndian(b);
}
