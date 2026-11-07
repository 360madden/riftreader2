using System.Buffers.Binary;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;
namespace RiftReader2.Live;
internal sealed record VariantGuardObservation(object Identity,DateTimeOffset StartedAtUtc,DateTimeOffset CompletedAtUtc,ulong SelfKey,string SpecialKeyStatus,uint? SpecialKey,string EffectiveLevelStatus,int? EffectiveLevel,string? LevelBranch,byte? PStatus,ulong? RegularBegin,ulong? RegularEnd,ulong? SpecialBegin,ulong? SpecialEnd,int? SelectionIndex,bool? RoleExceptionBypassed,uint? RawGuard,IReadOnlyList<uint>? RawGuardKeys,string RawKeyRestrictionStatus,IReadOnlyList<uint>? RawKeyRestrictionKeys)
{
 public string Qualification=>"raw candidate inputs; guard initialization and variant winner unverified";
}
internal static class CurrentBuildVariantGuardSampleCommand
{
 internal static async Task<int> RunAsync(IReadOnlyDictionary<string,string> options,TextWriter output,CancellationToken ct)
 {
  if(!options.TryGetValue("--pid",out var p)||!int.TryParse(p,NumberStyles.None,CultureInfo.InvariantCulture,out var pid)||pid<=0||!options.TryGetValue("--start-ticks",out var t)||!long.TryParse(t,NumberStyles.None,CultureInfo.InvariantCulture,out var ticks)||ticks<=0||!options.TryGetValue("--output",out var path)||string.IsNullOrWhiteSpace(path))throw new ArgumentException("--pid, --start-ticks and --output required.");
  if(File.Exists(path))throw new IOException("Output exists.");await using var session=await WindowsNativeMemorySession.OpenAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,ct);ct.ThrowIfCancellationRequested();var observation=Read(session);if(await session.RevalidateAsync(ct) is not null)throw new InvalidDataException("Process invalidated.");ct.ThrowIfCancellationRequested();await JsonReportWriter.WriteNewAsync(path,new{schemaVersion=1,contractVersion="native-current-variant-guards-candidate/1",status="complete",observation},ct);await output.WriteLineAsync(JsonSerializer.Serialize(new{recordType="native-current-variant-guards-summary/1",output=Path.GetFullPath(path)},new JsonSerializerOptions(JsonFormat.Options){WriteIndented=false}));return 0;
 }
 internal static VariantGuardObservation Read(IReadOnlyNativeMemorySession session)=>Read(session,CurrentBuildPlayerContextCandidateReader.Read,s=>{var l=CurrentBuildPlayerLookup.Resolve(s);return new(l.PlayerKey,l.EntityAddress,l.ResolveComponent(0x2F57850),l.VerifyUnchanged);});
 internal static VariantGuardObservation Read(IReadOnlyNativeMemorySession session,Func<IReadOnlyNativeMemorySession,CurrentBuildPlayerContextObservation> context,Func<IReadOnlyNativeMemorySession,PlayerContextOwner> resolve)
 {
  var start=DateTimeOffset.UtcNow;var id=session.Identity;if(id.ProcessId<=0||id.ProcessStartUtcTicks<=0||id.ModuleSize<0x3548728||!string.Equals(id.ExecutableSha256,CurrentBuildPlayerLookup.GameSha256,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("Invalid build or process.");
  var self=context(session);var lookup=resolve(session);if(self.Identity!=id||self.UnitKey!=lookup.Key||self.Entity!=lookup.Entity||self.HealthComponent!=lookup.Health||self.CachedContext!=lookup.Health)throw new InvalidDataException("Self health owner mismatch.");
  var anchors=new Dictionary<(ulong,int),byte[]>();var budget=0;byte[] Take(ulong a,int n,bool remember=true){budget=checked(budget+n);if(budget>2*1024*1024)throw new InvalidDataException("Read budget exceeded.");var b=CurrentBuildPlayerLookup.Exact(session,a,n);if(remember){if(anchors.TryGetValue((a,n),out var old)&&!old.AsSpan().SequenceEqual(b))throw new InvalidDataException("Bytes changed.");anchors[(a,n)]=b.ToArray();}return b;}
  ulong Ptr(ulong a,int n=8)=>CurrentBuildPlayerLookup.Pointer(a,n);ulong Q(ulong a)=>U64(Take(a,8));bool Type(ulong a,ulong vt,ulong getter,ulong desc,ulong descVt,ulong descGetter)=>Q(a)==id.ModuleBaseAddress+vt&&Q(id.ModuleBaseAddress+vt+0x40)==id.ModuleBaseAddress+getter&&Q(id.ModuleBaseAddress+desc)==id.ModuleBaseAddress+descVt&&Q(id.ModuleBaseAddress+descVt+8)==id.ModuleBaseAddress+descGetter;
  var health=Ptr(lookup.Health,0x48);if(Q(health+0x10)!=lookup.Entity)throw new InvalidDataException("Health self mismatch.");var owner=Ptr(Q(health+0x40),0x140);if(!Type(owner,0x2927448,0x19D21E0,0x34731B0,0x2929BD0,0x19F4D60))throw new InvalidDataException("Self owner fingerprint mismatch.");
  uint? specialKey=null;string specialStatus="unavailable";try{var root=Ptr(Q(id.ModuleBaseAddress+0x33E0AB0),0x870);var config=Q(root+0x868);if(config==0)specialStatus="null-config";else if(Type(Ptr(config,0x4C),0x29ABD08,0x1B064A0,0x349E980,0x29B8660,0x1B35A50)){specialKey=BinaryPrimitives.ReadUInt32LittleEndian(Take(config+0x48,4));specialStatus="typed-candidate";}else specialStatus="unverified-type";}catch(InvalidDataException){if(budget>2*1024*1024)throw;}
  int? effective=null,index=null;string levelStatus="unavailable";string? branch=null;byte? pStatus=null;ulong? rb=null,re=null,sb=null,se=null;bool? role=null;uint? guard=null;List<uint>? keys=null;
  try
  {
   var selector=BinaryPrimitives.ReadInt32LittleEndian(Take(id.ModuleBaseAddress+0x2F582E0,4));if(selector is <0 or >=0x60)throw new InvalidDataException("Invalid selector.");var slot=Take(lookup.Entity+0x18+(ulong)selector,1)[0];var alternate=slot==0xFF?0:Q(Ptr(Q(lookup.Entity+0x78))+slot*8UL);
   if(alternate==0){effective=BinaryPrimitives.ReadInt32LittleEndian(Take(owner+0x138,4));levelStatus="candidate";branch="owner";role=true;}
   else
   {
    var p=Ptr(Q(Ptr(alternate,0x50)+0x48),0xDF0);index=BinaryPrimitives.ReadInt32LittleEndian(Take(p+0x1D8,4));pStatus=Take(p+0x24F,1)[0];var regular=Take(p+0xDE0,16);rb=U64(regular);re=U64(regular.AsSpan(8));var special=Take(p+0x7D8,16);sb=U64(special);se=U64(special.AsSpan(8));
    ulong Count(ulong b,ulong e,int cap){if((b==0)!=(e==0)||e<b||(e-b)%8!=0||(e-b)/8>(ulong)cap)throw new InvalidDataException("Invalid ref span.");if(b!=0)Ptr(b,e==b?8:checked((int)(e-b)));return(e-b)/8;}
    var rn=Count(rb.Value,re.Value,512);var sn=Count(sb.Value,se.Value,512);role=pStatus!=0&&sn>0?true:null;ulong row=0;
    if(index>=0&&(ulong)index<rn)row=Q(rb.Value+(ulong)index*8);else if(index==-1&&pStatus!=0&&sn>0)row=Q(sb.Value);
    if(row==0){effective=BinaryPrimitives.ReadInt32LittleEndian(Take(owner+0x138,4));levelStatus="candidate";branch="owner-no-row";}
    else if(Type(Ptr(row,0x28),0x2BD4388,0x201A050,0x3548720,0x2BE0EF8,0x20482A0)){effective=BinaryPrimitives.ReadInt32LittleEndian(Take(row+0x24,4));levelStatus="candidate";branch="typed-0736-row";}
    else {levelStatus="unverified-row";branch="typed-row-required";}
    if(pStatus==0)try{guard=BinaryPrimitives.ReadUInt32LittleEndian(Take(id.ModuleBaseAddress+0x336EE90,4));var list=Take(id.ModuleBaseAddress+0x336EDD0,16);var b=U64(list);var e=U64(list.AsSpan(8));if((b==0)!=(e==0)||e<b||(e-b)%4!=0||(e-b)/4>512||(b!=0&&(b<0x10000||b%4!=0||e>0x7FFFFFFFFFFFUL)))throw new InvalidDataException("Invalid guard list.");keys=[];for(var at=b;at<e;at+=4)keys.Add(BinaryPrimitives.ReadUInt32LittleEndian(Take(at,4)));}catch(InvalidDataException){if(budget>2*1024*1024)throw;guard=null;keys=null;}
   }
  }
  catch(InvalidDataException){if(budget>2*1024*1024)throw;effective=null;levelStatus="unavailable";branch="unreadable-or-invalid";role=null;guard=null;keys=null;}
  string restrictionStatus="unavailable";List<uint>? restrictionKeys=null;
  try
  {
   var system=Ptr(Q(id.ModuleBaseAddress+0x33623E0),0x400);if(Q(system+0x3F8)!=lookup.Entity)throw new InvalidDataException("Cached self entity mismatch.");
   var selector=BinaryPrimitives.ReadInt32LittleEndian(Take(id.ModuleBaseAddress+0x2F57260,4));if(selector is <0 or >=0x60)throw new InvalidDataException("Invalid restriction selector.");
   var slot=Take(lookup.Entity+0x18+(ulong)selector,1)[0];if(slot==0xFF)throw new InvalidDataException("Restriction component absent.");
   var table=Ptr(Q(lookup.Entity+0x78));var component=Ptr(Q(checked(table+slot*8UL)),0x1B8);if(Q(component+0x10)!=lookup.Entity)throw new InvalidDataException("Restriction component owner mismatch.");
   var v=Ptr(Q(component+0x1B0),0x3E8);var span=Take(v+0x3D8,16);var b=U64(span);var e=U64(span.AsSpan(8));
   if((b==0)!=(e==0)||e<b||(e-b)%4!=0||(e-b)/4>512||(b!=0&&(b<0x10000||b%4!=0||e>0x7FFFFFFFFFFFUL)))throw new InvalidDataException("Invalid restriction span.");
   restrictionKeys=[];for(var at=b;at<e;at+=4)restrictionKeys.Add(BinaryPrimitives.ReadUInt32LittleEndian(Take(at,4)));restrictionStatus=restrictionKeys.Count==0?"empty":"available";
  }
  catch(InvalidDataException){if(budget>2*1024*1024)throw;restrictionStatus="unavailable";restrictionKeys=null;}
  foreach(var a in anchors)CurrentBuildPlayerLookup.RequireSame(Take(a.Key.Item1,a.Key.Item2,false),a.Value);lookup.Verify();var after=context(session);if(after.Identity!=id||after.UnitKey!=self.UnitKey||after.Entity!=self.Entity||after.HealthComponent!=health||after.CachedContext!=health||session.Identity!=id)throw new InvalidDataException("Self epoch changed.");
  return new(id,start,DateTimeOffset.UtcNow,self.UnitKey,specialStatus,specialKey,levelStatus,effective,branch,pStatus,rb,re,sb,se,index,role,guard,keys,restrictionStatus,restrictionKeys);
 }
 static ulong U64(ReadOnlySpan<byte>b)=>BinaryPrimitives.ReadUInt64LittleEndian(b);
}
