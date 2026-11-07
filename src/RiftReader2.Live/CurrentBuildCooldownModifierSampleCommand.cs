using System.Buffers.Binary;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;
namespace RiftReader2.Live;
internal sealed record RawModifierSpan(ulong Begin,ulong End,IReadOnlyList<uint> Values);
internal sealed record DirectScaleObservation(string Status, uint Key, int? RawMultiplier=null);
internal sealed record RawRangeConfig(string Status, ulong? Root, ulong? Address = null, uint? MinBits = null, float? Min = null, uint? MaxBits = null, float? Max = null, uint? SpecialKey = null);
internal sealed record RawCooldownModifier(ulong EntryAddress,string RawEntryHex,ulong Pointer,string Status,int? Mode=null,ulong? Vtable=null,ulong? GetterRva=null,uint? Float18Bits=null,float? Float18=null,uint? Float24Bits=null,float? Float24=null,uint? Operation=null,byte? Flag30=null,byte? Flag33=null,byte? Flag34=null,byte? Flag36=null,RawModifierSpan? Exclusions=null,RawModifierSpan? DirectKeys=null,RawModifierSpan? Tags1=null,RawModifierSpan? Tags2=null,RawModifierSpan? Tags3=null,uint? RawScaleKey=null,DirectScaleObservation? DirectScale=null);
internal sealed record CooldownModifierObservation(object Identity,DateTimeOffset StartedAtUtc,DateTimeOffset CompletedAtUtc,ulong SelfKey,ulong Component,ulong Begin,ulong End,string CensusStatus,uint? RawContextKey,IReadOnlyList<RawCooldownModifier> Rows,RawRangeConfig RangeConfig)
{public string Qualification=>"raw modifier census only; eligibility, adjusted cooldown, freshness and restart unverified";}
internal static class CurrentBuildCooldownModifierSampleCommand
{
 internal static async Task<int> RunAsync(IReadOnlyDictionary<string,string> options,TextWriter output,CancellationToken ct)
 {
  if(!options.TryGetValue("--pid",out var p)||!int.TryParse(p,NumberStyles.None,CultureInfo.InvariantCulture,out var pid)||pid<=0||!options.TryGetValue("--start-ticks",out var t)||!long.TryParse(t,NumberStyles.None,CultureInfo.InvariantCulture,out var ticks)||ticks<=0||!options.TryGetValue("--output",out var path)||string.IsNullOrWhiteSpace(path))throw new ArgumentException("--pid, --start-ticks and --output required.");
  if(File.Exists(path))throw new IOException("Output exists.");await using var session=await WindowsNativeMemorySession.OpenAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,ct);ct.ThrowIfCancellationRequested();var observation=Read(session);if(await session.RevalidateAsync(ct) is not null)throw new InvalidDataException("Process invalidated.");ct.ThrowIfCancellationRequested();await JsonReportWriter.WriteNewAsync(path,new{schemaVersion=1,contractVersion="native-current-cooldown-modifiers-candidate/1",status="complete",observation,limitations=new[]{"Raw modifier inputs do not establish applicability or adjusted cooldown.","Sequential reads cannot exclude ABA; loaded module bytes are not independently hashed.","No game getter, initializer, refcount or memory write is performed."}},ct);await output.WriteLineAsync(JsonSerializer.Serialize(new{recordType="native-current-cooldown-modifiers-summary/1",output=Path.GetFullPath(path)},new JsonSerializerOptions(JsonFormat.Options){WriteIndented=false}));return 0;
 }
 internal static CooldownModifierObservation Read(IReadOnlyNativeMemorySession session)=>Read(session,CurrentBuildPlayerContextCandidateReader.Read,s=>{var l=CurrentBuildPlayerLookup.Resolve(s);return new(l.PlayerKey,l.EntityAddress,l.ResolveComponent(0x2F57260),l.VerifyUnchanged);});
 internal static CooldownModifierObservation Read(IReadOnlyNativeMemorySession session,Func<IReadOnlyNativeMemorySession,CurrentBuildPlayerContextObservation> context,Func<IReadOnlyNativeMemorySession,PlayerContextOwner> resolve, Func<IReadOnlyNativeMemorySession,PlayerContextOwner>? resolveAlternate=null)
 {
  var started=DateTimeOffset.UtcNow;var id=session.Identity;var before=context(session);var lookup=resolve(session);if(before.Identity!=id||before.UnitKey!=lookup.Key||before.Entity!=lookup.Entity)throw new InvalidDataException("Self identity mismatch.");
  var anchors=new Dictionary<(ulong,int),byte[]>();int budget=0;byte[] Take(ulong a,int n,bool save=true){budget=checked(budget+n);if(budget>2*1024*1024)throw new InvalidDataException("Modifier budget exceeded.");var b=CurrentBuildPlayerLookup.Exact(session,a,n);if(save){if(anchors.TryGetValue((a,n),out var old)&&!old.AsSpan().SequenceEqual(b))throw new InvalidDataException("Modifier bytes changed.");anchors[(a,n)]=b.ToArray();}return b;}
  ulong Ptr(ulong a,int n=8)=>CurrentBuildPlayerLookup.Pointer(a,n);ulong Q(ulong a)=>BinaryPrimitives.ReadUInt64LittleEndian(Take(a,8));uint D(ulong a)=>BinaryPrimitives.ReadUInt32LittleEndian(Take(a,4));
  var component=Ptr(lookup.Health,0x408);if(Q(component+0x10)!=lookup.Entity)throw new InvalidDataException("Modifier component owner mismatch.");var h=Take(component+0x3F8,16);var begin=U64(h);var end=U64(h.AsSpan(8));
  if((begin==0)!=(end==0)||end<begin||(end-begin)%32!=0||(end-begin)/32>256)throw new InvalidDataException("Invalid modifier vector.");if(begin!=0)Ptr(begin,end==begin?8:checked((int)(end-begin)));
  RawModifierSpan Span(ulong address){var raw=Take(address,16);var b=U64(raw);var e=U64(raw.AsSpan(8));if((b==0)!=(e==0)||e<b||(e-b)%4!=0||(e-b)/4>512||(b!=0&&(b<0x10000||b%4!=0||e>0x7FFFFFFFFFFFUL)))throw new InvalidDataException("Invalid modifier filter span.");var values=new List<uint>();for(var a=b;a<e;a+=4)values.Add(D(a));return new(b,e,values);}
  PlayerContextOwner? alternateOwner=null;
  bool Type(ulong a,ulong vt,ulong getter,ulong descriptor,ulong descVt,ulong descGetter)=>Q(a)==id.ModuleBaseAddress+vt && Q(id.ModuleBaseAddress+vt+0x40)==id.ModuleBaseAddress+getter && Q(id.ModuleBaseAddress+descriptor)==id.ModuleBaseAddress+descVt && Q(id.ModuleBaseAddress+descVt+8)==id.ModuleBaseAddress+descGetter;
  RawRangeConfig ReadRangeConfig()
  {
   ulong? root=null, address=null;
   try
   {
    root=Q(id.ModuleBaseAddress+0x33E0AB0);
    if(root==0)return new("null-root",root);
    address=Q(Ptr(root.Value,0x850)+0x848);
    if(address==0)return new("null-config",root,address);
    var config=Ptr(address.Value,0x8C);
    if(!Type(config,0x2ADB030,0x1DD2CD0,0x34FC1D0,0x2AEB9E8,0x1DFCAF0))
     return new("unverified-type",root,address);
    var minBits=D(config+0x64);var maxBits=D(config+0x7C);
    var min=BitConverter.UInt32BitsToSingle(minBits);var max=BitConverter.UInt32BitsToSingle(maxBits);
    return new("typed-0e29-candidate",root,address,minBits,float.IsFinite(min)?min:null,maxBits,float.IsFinite(max)?max:null,D(config+0x88));
   }
   catch(InvalidDataException){if(budget>2*1024*1024)throw;return new("read-unavailable",root,address);}
  }
  DirectScaleObservation Scale(uint key)
  {
   if(key==0)return new("zero-key-unresolved",key);
   if(key==1)return new("caller-bypass",key);
   try
   {
    alternateOwner??=resolveAlternate is null ? ResolveAlternate(session) : resolveAlternate(session);
    if(alternateOwner.Key!=lookup.Key||alternateOwner.Entity!=lookup.Entity)throw new InvalidDataException("Scale owner identity mismatch.");
    var alt=Ptr(alternateOwner.Health,0x50);if(Q(alt+0x10)!=lookup.Entity)throw new InvalidDataException("Scale owner backref mismatch.");
    var owner=Ptr(Q(alt+0x48),0xDD8);
    if(!Type(owner,0x2A46738,0x1C48CC0,0x34C9670,0x2A4B760,0x1C84130))return new("owner-type-unavailable",key);
    var tree=Q(owner+0xDD0);if(tree==0)return new("tree-unavailable",key);
    tree=Ptr(tree,0x58);if(!Type(tree,0x2996D90,0x1ACE0B0,0x34940A0,0x29977A8,0x1AF0010))return new("tree-type-unavailable",key);
    var sentinel=checked(tree+0x48);var node=Q(tree+0x50);var visited=new HashSet<ulong>();
    for(int i=0;i<128;i++)
    {
     if(node==0)return new("null-link-zero-candidate",key,0);
     if(node==sentinel)return new("unmatched-header-unavailable",key);
     node=Ptr(node,0x30);if(!visited.Add(node))return new("cycle-unavailable",key);
     var nodeKey=unchecked((int)D(node+0x20));var signedKey=unchecked((int)key);
     if(nodeKey==signedKey)
     {
      var row=Q(node+0x28);if(row==0)return new("null-row-zero-candidate",key,0);
      row=Ptr(row,0x1C);if(!Type(row,0x2D224F0,0x2348300,0x35B4B40,0x2D2E858,0x2368AB0))return new("row-type-unavailable",key);
      return new("raw-factor-candidate",key,unchecked((int)D(row+0x18)));
     }
     node=Q(node+(signedKey<nodeKey?0x10UL:0x18UL));
    }
    return new("node-budget-unavailable",key);
   }
   catch(InvalidDataException){if(budget>2*1024*1024)throw;return new("read-or-binding-unavailable",key);}
  }
  var rows=new List<RawCooldownModifier>();bool incomplete=false;uint? contextKey=null;
  for(var at=begin;at<end;at+=32)
  {
   var entry=Take(at,32);var p=U64(entry);var raw=Convert.ToHexString(entry).ToLowerInvariant();
   if(p==0){rows.Add(new(at,raw,0,"null-reference"));incomplete=true;continue;}
   RawCooldownModifier? rangeSeed=null;
   try
   {
    Ptr(p,0x38);var mode=BinaryPrimitives.ReadInt32LittleEndian(Take(p+0x28,4));var vt=Q(p);ulong? getter=null;if(vt>=id.ModuleBaseAddress&&vt<=id.ModuleBaseAddress+id.ModuleSize-0x48){var target=Q(vt+0x40);if(target>=id.ModuleBaseAddress&&target<id.ModuleBaseAddress+id.ModuleSize)getter=target-id.ModuleBaseAddress;}
    if(mode is not (0 or 4)){rows.Add(new(at,raw,p,"mode-candidate",mode,vt,getter));continue;}
    if(mode==0)rangeSeed=new(at,raw,p,"mode-0-payload-unavailable",mode,vt,getter);
    contextKey??=D(component+0x2F0);var bits18=D(p+0x18);var bits24=D(p+0x24);var f18=BitConverter.Int32BitsToSingle(unchecked((int)bits18));var f24=BitConverter.Int32BitsToSingle(unchecked((int)bits24));
    var operation=D(p+0x2C);var flag30=Take(p+0x30,1)[0];var flag33=Take(p+0x33,1)[0];var flag34=Take(p+0x34,1)[0];var flag36=Take(p+0x36,1)[0];
    var ex=Span(p+0x110);var direct=Span(p+0x178);var tag1=Span(p+0x1E0);var tag2=Span(p+0x248);var tag3=Span(p+0x2B0);var scaleKey=D(p+0x20);
    var status=mode==0?"mode-0-raw-candidate":"mode-4-raw-candidate";
    var directScale=flag36==1 && (mode==4 || flag33==0) ? Scale(scaleKey) : null;
    rows.Add(new(at,raw,p,status,mode,vt,getter,bits18,float.IsFinite(f18)?f18:null,bits24,float.IsFinite(f24)?f24:null,operation,flag30,flag33,flag34,flag36,ex,direct,tag1,tag2,tag3,scaleKey,directScale));
   }
   catch(InvalidDataException)
   {
    if(budget>2*1024*1024)throw;
    if(rangeSeed is not null){rows.Add(rangeSeed);continue;}
    rows.Add(new(at,raw,p,"unavailable"));incomplete=true;
   }
  }
  var rangeConfig=ReadRangeConfig();
  alternateOwner?.Verify();lookup.Verify();var after=context(session);if(after.Identity!=id||after.UnitKey!=before.UnitKey||after.Entity!=lookup.Entity||after.HealthComponent!=before.HealthComponent||after.Owner!=before.Owner||session.Identity!=id)throw new InvalidDataException("Self or process changed.");foreach(var a in anchors)CurrentBuildPlayerLookup.RequireSame(Take(a.Key.Item1,a.Key.Item2,false),a.Value);if(session.Identity!=id)throw new InvalidDataException("Process changed.");
  return new(id,started,DateTimeOffset.UtcNow,lookup.Key,component,begin,end,incomplete?"incomplete":rows.Any(r=>r.Mode==4)?"mode-4-present":"no-mode-4-observed",contextKey,rows,rangeConfig);
 }
 static PlayerContextOwner ResolveAlternate(IReadOnlyNativeMemorySession session){var owner=CurrentBuildPlayerLookup.Resolve(session);return new(owner.PlayerKey,owner.EntityAddress,owner.ResolveComponent(0x2F582E0),owner.VerifyUnchanged);}
 static ulong U64(ReadOnlySpan<byte>b)=>BinaryPrimitives.ReadUInt64LittleEndian(b);
}
