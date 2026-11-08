using System.Buffers.Binary;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;
namespace RiftReader2.Live;
internal sealed record StatValueCandidate(string Status,long? RawSigned64=null,double? DoubleCandidate=null,string? Precision=null);
internal sealed record StatCandidate(string Name,int Selector,int MappedIndex,StatValueCandidate Ordinary,StatValueCandidate Unbuffed);
internal sealed record StatsObservation(object Identity,DateTimeOffset StartedAtUtc,DateTimeOffset CompletedAtUtc,ulong UnitKey,ulong Entity,ulong Health,ulong Owner,ulong Record,ulong Mapping,IReadOnlyList<StatCandidate> Stats)
{public string Qualification=>"raw typed stat candidates; API availability, units, freshness and restart unverified";}
internal static class CurrentBuildStatsSampleCommand
{
 internal static Task<int> RunAsync(IReadOnlyDictionary<string,string> options,TextWriter output,CancellationToken ct) =>
  RunAsync(options,output,ct,
   async (pid,ticks,token)=>await NativeReadFileLease.AcquireAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,TimeSpan.FromSeconds(1),token),
   async (pid,ticks,token)=>await WindowsNativeMemorySession.OpenAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,token),
   (session,pid)=>Read(session));
 internal static async Task<int> RunAsync(IReadOnlyDictionary<string,string> options,TextWriter output,CancellationToken ct,
  Func<int,long,CancellationToken,Task<IAsyncDisposable>> acquire,
  Func<int,long,CancellationToken,Task<IReadOnlyNativeMemorySession>> open,
  Func<IReadOnlyNativeMemorySession,int,StatsObservation> read)
 {
  if(!options.TryGetValue("--pid",out var p)||!int.TryParse(p,NumberStyles.None,CultureInfo.InvariantCulture,out var pid)||pid<=0||!options.TryGetValue("--start-ticks",out var t)||!long.TryParse(t,NumberStyles.None,CultureInfo.InvariantCulture,out var ticks)||ticks<=0||!options.TryGetValue("--output",out var path)||string.IsNullOrWhiteSpace(path))throw new ArgumentException("--pid, --start-ticks and --output required.");
  if(File.Exists(path))throw new IOException("Output exists.");await using var lease=await acquire(pid,ticks,ct);ct.ThrowIfCancellationRequested();await using var session=await open(pid,ticks,ct);ct.ThrowIfCancellationRequested();var observation=read(session,pid);if(await session.RevalidateAsync(ct) is not null)throw new InvalidDataException("Process invalidated.");ct.ThrowIfCancellationRequested();await JsonReportWriter.WriteNewAsync(path,new{schemaVersion=1,contractVersion="native-current-stats-candidate/1",status="complete",observation,limitations=new[]{"Raw signed values and double conversions are candidates, not proven API presence, units or adjusted semantics.","Sequential reads cannot exclude ABA; loaded module bytes are not independently hashed.","No game getter, initializer, refcount or memory write is performed."}},ct);await output.WriteLineAsync(JsonSerializer.Serialize(new{recordType="native-current-stats-summary/1",output=Path.GetFullPath(path)},new JsonSerializerOptions(JsonFormat.Options){WriteIndented=false}));return 0;
 }
 internal static StatsObservation Read(IReadOnlyNativeMemorySession session)=>Read(session,CurrentBuildPlayerContextCandidateReader.Read,s=>{var l=CurrentBuildPlayerLookup.Resolve(s);return new(l.PlayerKey,l.EntityAddress,l.ResolveComponent(0x2F57850),l.VerifyUnchanged);});
 internal static StatsObservation Read(IReadOnlyNativeMemorySession session,Func<IReadOnlyNativeMemorySession,CurrentBuildPlayerContextObservation> context,Func<IReadOnlyNativeMemorySession,PlayerContextOwner> resolve)
 {
  var started=DateTimeOffset.UtcNow;var id=session.Identity;if(id.ProcessId<=0||id.ProcessStartUtcTicks<=0||id.ModuleSize<0x355F438||!string.Equals(id.ExecutableSha256,CurrentBuildPlayerLookup.GameSha256,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("Invalid stats build or epoch.");var before=context(session);var lookup=resolve(session);
  if(before.Identity!=id||before.UnitKey!=lookup.Key||before.Entity!=lookup.Entity||before.HealthComponent!=lookup.Health)throw new InvalidDataException("Stats self mismatch.");
  var anchors=new Dictionary<(ulong,int),byte[]>();int budget=0;byte[] Take(ulong a,int n,bool save=true){budget=checked(budget+n);if(budget>2*1024*1024)throw new InvalidDataException("Stats read budget exceeded.");var b=CurrentBuildPlayerLookup.Exact(session,a,n);if(save){if(anchors.TryGetValue((a,n),out var old)&&!old.AsSpan().SequenceEqual(b))throw new InvalidDataException("Stats bytes changed.");anchors[(a,n)]=b.ToArray();}return b;}
  ulong Ptr(ulong a,int n=8)=>CurrentBuildPlayerLookup.Pointer(a,n);ulong Q(ulong a)=>BinaryPrimitives.ReadUInt64LittleEndian(Take(a,8));
  bool Type(ulong a,ulong vt,ulong getter,ulong desc,ulong descVt,ulong method)=>Q(a)==id.ModuleBaseAddress+vt&&Q(id.ModuleBaseAddress+vt+0x40)==id.ModuleBaseAddress+getter&&Q(id.ModuleBaseAddress+desc)==id.ModuleBaseAddress+descVt&&Q(id.ModuleBaseAddress+descVt+8)==id.ModuleBaseAddress+method;
  var entity=Ptr(lookup.Entity,128);var health=Ptr(lookup.Health,0x48);var system=Ptr(Q(id.ModuleBaseAddress+0x33623E0),0x408);
  if(Q(system+0x360)!=lookup.Key||Q(system+0x3F8)!=entity||Q(system+0x400)!=health||Q(health+0x10)!=entity)throw new InvalidDataException("Cached stat receiver mismatch.");
  var owner=Ptr(Q(health+0x40),0x648);if(owner!=before.Owner||!Type(owner,0x2927448,0x19D21E0,0x34731B0,0x2929BD0,0x19F4D60))throw new InvalidDataException("Stat owner fingerprint mismatch.");
  var record=Ptr(Q(owner+0x640),0x158);if(!Type(record,0x2C0EE88,0x20CCC60,0x355F430,0x2C281B0,0x20F2480))throw new InvalidDataException("Stat record fingerprint mismatch.");
  var map=Ptr(Q(id.ModuleBaseAddress+0x33E3AE8),336);
  (ulong Begin,ulong Count) Span(ulong address){var h=Take(address,16);var b=U64(h);var e=U64(h.AsSpan(8));if((b==0)!=(e==0)||e<b||(e-b)%8!=0||(e-b)/8>4096)throw new InvalidDataException("Invalid stat vector.");if(b!=0)Ptr(b,e==b?8:checked((int)(e-b)));return(b,(e-b)/8);}
  var ordinary=Span(record+0x78);var unbuffed=Span(record+0x148);
  StatValueCandidate Value((ulong Begin,ulong Count) vector,int index)
  {
   if(index<0||(ulong)index>=vector.Count)return new("index-unavailable");
   var raw=BinaryPrimitives.ReadInt64LittleEndian(Take(checked(vector.Begin+(ulong)index*8),8));return new("raw-candidate",raw,(double)raw,raw is >= -9007199254740992L and <= 9007199254740992L?"exact-integer-range":"may-round");
  }
  var rows=new List<StatCandidate>();foreach(var (name,selector) in new[]{("armor",37),("powerAttack",24),("powerSpell",32),("critAttack",26),("critSpell",33),("strength",5),("dexterity",1),("intelligence",3),("wisdom",4),("endurance",2),("resistLife",35),("resistDeath",36),("resistFire",38),("resistWater",39),("resistEarth",40),("resistAir",41),("hit",31),("critPower",83),("block",27),("dodge",30)}){var index=BinaryPrimitives.ReadInt32LittleEndian(Take(checked(map+(ulong)selector*4),4));rows.Add(new(name,selector,index,Value(ordinary,index),Value(unbuffed,index)));}
  lookup.Verify();var after=context(session);if(after.Identity!=id||after.UnitKey!=lookup.Key||after.Entity!=entity||after.HealthComponent!=health||after.Owner!=owner||after.CachedContext!=health||session.Identity!=id)throw new InvalidDataException("Stats self changed.");foreach(var a in anchors)CurrentBuildPlayerLookup.RequireSame(Take(a.Key.Item1,a.Key.Item2,false),a.Value);if(session.Identity!=id)throw new InvalidDataException("Stats process changed.");
  return new(id,started,DateTimeOffset.UtcNow,lookup.Key,entity,health,owner,record,map,rows);
 }
 static ulong U64(ReadOnlySpan<byte>b)=>BinaryPrimitives.ReadUInt64LittleEndian(b);
}
