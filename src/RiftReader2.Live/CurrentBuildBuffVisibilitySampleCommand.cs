using System.Buffers.Binary;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;
namespace RiftReader2.Live;
internal sealed record BuffVisibilityRow(ulong NodeAddress,string Status,ulong? RawListIdCandidate,string NameBranchCandidate);
internal sealed record BuffVisibilityObservation(object Identity,DateTimeOffset StartedAtUtc,DateTimeOffset CompletedAtUtc,ulong UnitKey,string ViewerStatus,uint? NameSpecialKey,IReadOnlyList<BuffVisibilityRow> Rows)
{public string Qualification=>"candidate predicate inputs; API membership, grouping, names, freshness and restart unverified";}
internal static class CurrentBuildBuffVisibilitySampleCommand
{
 internal static async Task<int> RunAsync(IReadOnlyDictionary<string,string> options,TextWriter output,CancellationToken ct)
 {
  if(!options.TryGetValue("--pid",out var p)||!int.TryParse(p,NumberStyles.None,CultureInfo.InvariantCulture,out var pid)||pid<=0||!options.TryGetValue("--start-ticks",out var t)||!long.TryParse(t,NumberStyles.None,CultureInfo.InvariantCulture,out var ticks)||ticks<=0||!options.TryGetValue("--output",out var path)||string.IsNullOrWhiteSpace(path))throw new ArgumentException("--pid, --start-ticks and --output required.");
  if(File.Exists(path))throw new IOException("Output exists.");await using var session=await WindowsNativeMemorySession.OpenAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,ct);ct.ThrowIfCancellationRequested();var observation=Read(session);if(await session.RevalidateAsync(ct) is not null)throw new InvalidDataException("Process invalidated.");ct.ThrowIfCancellationRequested();await JsonReportWriter.WriteNewAsync(path,new{schemaVersion=1,contractVersion="native-current-buff-visibility-candidate/1",status="complete",observation,limitations=new[]{"Candidate predicate paths do not establish API membership, grouping or displayed names.","Sequential reads cannot exclude ABA; loaded module bytes are not independently hashed.","No game getter, initializer, refcount operation or memory write is performed."}},ct);await output.WriteLineAsync(JsonSerializer.Serialize(new{recordType="native-current-buff-visibility-summary/1",output=Path.GetFullPath(path)},new JsonSerializerOptions(JsonFormat.Options){WriteIndented=false}));return 0;
 }
 internal static BuffVisibilityObservation Read(IReadOnlyNativeMemorySession session)=>Read(session,s=>CurrentBuildBuffSeedCandidateReader.Read(s),s=>{var l=CurrentBuildPlayerLookup.Resolve(s);return new(l.PlayerKey,l.EntityAddress,l.ResolveComponent(0x2F57850),l.VerifyUnchanged);});
 internal static BuffVisibilityObservation Read(IReadOnlyNativeMemorySession session,Func<IReadOnlyNativeMemorySession,CurrentBuildBuffSeedObservation> seed,Func<IReadOnlyNativeMemorySession,PlayerContextOwner> resolve)
 {
  var start=DateTimeOffset.UtcNow;var id=session.Identity;if(id.ProcessId<=0||id.ProcessStartUtcTicks<=0||id.ModuleSize<0x35AF088||!string.Equals(id.ExecutableSha256,CurrentBuildPlayerLookup.GameSha256,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("Unsupported build or identity.");
  var before=seed(session);var owner=resolve(session);if(before.Identity!=id||before.UnitKey!=owner.Key)throw new InvalidDataException("Viewer seed identity mismatch.");
  var anchors=new Dictionary<(ulong,int),byte[]>();int budget=0;byte[] Take(ulong a,int n,bool save=true){budget=checked(budget+n);if(budget>2*1024*1024)throw new InvalidDataException("Visibility budget exceeded.");var b=CurrentBuildPlayerLookup.Exact(session,a,n);if(save){if(anchors.TryGetValue((a,n),out var old)&&!old.AsSpan().SequenceEqual(b))throw new InvalidDataException("Visibility bytes changed.");anchors[(a,n)]=b.ToArray();}return b;}
  ulong Ptr(ulong p,int n=8)=>CurrentBuildPlayerLookup.Pointer(p,n);ulong Q(ulong a)=>U64(Take(a,8));uint D(ulong a)=>BinaryPrimitives.ReadUInt32LittleEndian(Take(a,4));
  bool Type(ulong a,ulong vt,ulong getter,ulong desc,ulong descVt,ulong descGetter)=>Q(a)==id.ModuleBaseAddress+vt&&Q(id.ModuleBaseAddress+vt+0x40)==id.ModuleBaseAddress+getter&&Q(id.ModuleBaseAddress+desc)==id.ModuleBaseAddress+descVt&&Q(id.ModuleBaseAddress+descVt+8)==id.ModuleBaseAddress+descGetter;
  var system=Ptr(Q(id.ModuleBaseAddress+0x33623E0),0x400);if(Q(system+0x3F8)!=owner.Entity||Q(system+0x360)!=owner.Key)throw new InvalidDataException("Viewer cache mismatch.");
  bool? viewerAbsent=null;
  try{var index=BinaryPrimitives.ReadInt32LittleEndian(Take(id.ModuleBaseAddress+0x2F582E0,4));if(index is <0 or >=0x60)throw new InvalidDataException("Invalid viewer selector.");var slot=Take(owner.Entity+0x18+(ulong)index,1)[0];viewerAbsent=slot==0xFF||Q(Ptr(Q(owner.Entity+0x78))+slot*8UL)==0;}
  catch(InvalidDataException){if(budget>2*1024*1024)throw;}
  uint? a=null,b=null,c=null,nameKey=null;
  try
  {
   var root=Ptr(Q(id.ModuleBaseAddress+0x33E0AB0),0x870);
   uint? Config(ulong off,ulong field,ulong vt,ulong getter,ulong desc,ulong descVt,ulong method){try{var ptr=Q(root+off);if(ptr==0)return null;Ptr(ptr,checked((int)field+4));return Type(ptr,vt,getter,desc,descVt,method)?D(ptr+field):null;}catch(InvalidDataException){if(budget>2*1024*1024)throw;return null;}}
   a=Config(0x7C0,0x88,0x29430F0,0x1A0EF30,0x347C480,0x2947E08,0x1A366C0);
   b=Config(0x5C0,0x78,0x2D12220,0x2314920,0x35AF080,0x2D1DA20,0x233EC50);
   var config=Q(root+0x868);if(config!=0&&Type(Ptr(config,0x114),0x29ABD08,0x1B064A0,0x349E980,0x29B8660,0x1B35A50)){c=D(config+0x6C);nameKey=D(config+0x110);}
  }
  catch(InvalidDataException){if(budget>2*1024*1024)throw;}
  var rows=new List<BuffVisibilityRow>();
  foreach(var row in before.Nodes)
  {
   var status="unresolved";ulong? listId=null;string name="unresolved";
   try
   {
    var obj=Ptr(row.Object,0x50);var descriptor=Ptr(Q(obj+0x10),0x140);
    if(Type(descriptor,0x28DC6A8,0x193DF00,0x34623E0,0x28F5188,0x1978690))
    {
     var kind=D(descriptor+0x38);var category=D(obj+0x3C);var rawId=Q(obj+0x48);
     if(nameKey.HasValue)name=category==nameKey.Value?"special":"ordinary";
     if(kind==1)status="excluded-first-guard";
     else if(viewerAbsent==true){status="predicate-pass-candidate";listId=rawId;}
     else if(viewerAbsent==false&&a.HasValue&&b.HasValue&&c.HasValue)
     {var h=Take(descriptor+0x130,16);var begin=U64(h);var end=U64(h.AsSpan(8));if(begin==end&&category!=a&&category!=b&&category!=c){status="predicate-pass-candidate";listId=rawId;}}
    }
   }
   catch(InvalidDataException){if(budget>2*1024*1024)throw;}
   rows.Add(new(row.Address,status,listId,name));
  }
  foreach(var x in anchors)CurrentBuildPlayerLookup.RequireSame(Take(x.Key.Item1,x.Key.Item2,false),x.Value);owner.Verify();var after=seed(session);
  if(session.Identity!=id||after.Identity!=id||before.UnitKey!=after.UnitKey||before.Context!=after.Context||before.Sentinel!=after.Sentinel||!before.Nodes.SequenceEqual(after.Nodes))throw new InvalidDataException("Buff seed or identity changed.");
  return new(id,start,DateTimeOffset.UtcNow,owner.Key,viewerAbsent==true?"viewer-component-absent":viewerAbsent==false?"viewer-component-present":"unavailable",nameKey,rows);
 }
 static ulong U64(ReadOnlySpan<byte>b)=>BinaryPrimitives.ReadUInt64LittleEndian(b);
}
