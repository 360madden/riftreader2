using System.Buffers.Binary;
using System.Text;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live;
internal sealed record TargetNameSeed(string Status, string Branch, string? RawDirect = null, string? RawFallback = null, uint? LocalizationKey = null, uint? RawDecoration = null, ulong? EntityVtable = null, ulong? GetterRva = null, CurrentBuildLocalizationDictionaryObservation? Dictionary = null);
internal sealed record TargetPositionCandidate(string Status, ulong UnitKey, ulong? ComponentAddress = null, DateTimeOffset? StartedAtUtc = null, DateTimeOffset? CompletedAtUtc = null, CurrentBuildXyz? Position = null)
{
 public string Qualification => "cached position candidate; freshness and target semantics unverified";
}
internal sealed record TargetRawContext(string Status, ulong? Owner = null, int? RawLevel = null, byte? RawCombat = null, bool? CombatCandidate = null, string? LevelStatus = null, string? LevelBranch = null, int? NumericLevelCandidate = null)
{
 public string Qualification => "typed owner raw inputs; target level presentation, combat semantics and freshness unverified";
}
internal sealed record SelectedTargetObservation(NativeProcessIdentity Identity,DateTimeOffset StartedAtUtc,DateTimeOffset CompletedAtUtc,ulong SelfKey,string Status,string BeforeGuardStatus,string? AfterGuardStatus,ulong? TargetKey,string? TargetUnitId,ulong? TargetEntity,CurrentBuildVitalsObservation? TargetVitals, TargetNameSeed? NameSeed = null, TargetPositionCandidate? TargetPosition = null, TargetRawContext? TargetContext = null)
{
 public string Qualification=>"candidate-only; target and vitals semantics, freshness and restart unverified";
}
internal static class CurrentBuildSelectedTargetCandidateReader
{
 internal static SelectedTargetObservation Read(IReadOnlyNativeMemorySession session, bool includeNameSeed = false, bool includePosition = false, bool includeContext = false)=>Read(session,CurrentBuildPlayerContextCandidateReader.Read,(s,owner)=>CurrentBuildVitalsCandidateReader.Read(s,_=>owner), includeNameSeed, includePosition, includeContext);
 internal static SelectedTargetObservation Read(IReadOnlyNativeMemorySession session,Func<IReadOnlyNativeMemorySession,CurrentBuildPlayerContextObservation> context,Func<IReadOnlyNativeMemorySession,CurrentBuildVitalsOwnerSnapshot,CurrentBuildVitalsObservation> vitals, bool includeNameSeed = false, bool includePosition = false, bool includeContext = false)
 {
  var start=DateTimeOffset.UtcNow;var id=session.Identity;var before=context(session);
  if(before.Identity!=id)throw new InvalidDataException("Self context identity mismatch.");
  if(!before.TargetKeyCandidate.HasValue||before.TargetKeyCandidate.Value==0)return new(id,start,DateTimeOffset.UtcNow,before.UnitKey,"unavailable",before.TargetStatus,null,null,null,null,null);
  var key=before.TargetKeyCandidate.Value;var anchors=new Dictionary<(ulong,int),byte[]>();var budget=0;
  byte[] Take(ulong a,int n,bool remember=true){budget=checked(budget+n);if(budget>2*1024*1024)throw new InvalidDataException("Target lookup budget exceeded.");var b=CurrentBuildPlayerLookup.Exact(session,a,n);if(remember){if(anchors.TryGetValue((a,n),out var old)&&!old.AsSpan().SequenceEqual(b))throw new InvalidDataException("Target lookup changed.");anchors[(a,n)]=b.ToArray();}return b;}
  ulong Ptr(ulong v,int n=8)=>CurrentBuildPlayerLookup.Pointer(v,n);ulong Q(ulong a)=>U64(Take(a,8));
  var manager=Ptr(Q(id.ModuleBaseAddress+0x33624A8));var table=Ptr(Q(manager+0x50));var header=Take(table,24);
  var buckets=Ptr(U64(header));var stride=U64(header.AsSpan(8));var count=U64(header.AsSpan(16));
  if(stride is <24 or >4096||stride%8!=0||count is <1 or >(1<<24))throw new InvalidDataException("Invalid target unit table.");
  var address=Ptr(checked(buckets+CurrentBuildPlayerLookup.BucketIndex(key,count)*stride),24);var seen=new HashSet<ulong>();ulong entity=0;bool head=true;
  for(var i=0;i<128;i++)
  {
   if(!seen.Add(address))throw new InvalidDataException("Cyclic target lookup.");var node=Take(address,24);var link=U64(node);
   if((!head||(link&1)==0)&&U64(node.AsSpan(8))==key){entity=Ptr(U64(node.AsSpan(16)),128);break;}
   var next=link&~1UL;if(next==0)break;address=Ptr(next,24);head=false;
  }
  if(entity==0)throw new InvalidDataException("Target key absent or lookup bound exceeded.");
  var selector=BinaryPrimitives.ReadInt32LittleEndian(Take(id.ModuleBaseAddress+0x2F57850,4));if(selector is <0 or >=0x60)throw new InvalidDataException("Invalid target health selector.");
  var slot=Take(entity+0x18+(ulong)selector,1)[0];if(slot==0xFF)throw new InvalidDataException("Target health component absent.");
  var components=Ptr(Q(entity+0x78));var health=Ptr(Q(checked(components+slot*8UL)),0x18);if(Q(health+0x10)!=entity)throw new InvalidDataException("Target health entity mismatch.");
  TargetNameSeed? name=null;
  if(includeNameSeed) {try{name=CurrentBuildNameSeedReader.Read(session,id,entity,Take,anchors);}catch(InvalidDataException){if(budget>2*1024*1024)throw;name=new("unavailable","name-read-or-type-failure");}}
  string? afterStatus=null;
  void Verify()
  {
   foreach(var a in anchors)CurrentBuildPlayerLookup.RequireSame(Take(a.Key.Item1,a.Key.Item2,false),a.Value);
   var now=context(session);afterStatus=now.TargetStatus;
   if(now.Identity!=id||now.UnitKey!=before.UnitKey||now.TargetKeyCandidate!=key||session.Identity!=id)throw new InvalidDataException("Self or gated target changed during capture.");
  }
  var observation=vitals(session,new(key,health,Verify));
  TargetPositionCandidate? position=null;
  if(includePosition)
  {
   var posIndex=BinaryPrimitives.ReadInt32LittleEndian(Take(id.ModuleBaseAddress+0x2F588A0,4));
   if(posIndex is <0 or >=0x60)throw new InvalidDataException("Invalid target position selector.");
   var posSlot=Take(entity+0x18+(ulong)posIndex,1)[0];
   var pos=posSlot==0xFF?0:Q(checked(components+posSlot*8UL));
   if(pos==0) position=new("component-unavailable",key);
   else
   {
    Ptr(pos,0x110);if(Q(pos+0x10)!=entity)throw new InvalidDataException("Target position entity mismatch.");
    var positionStart=DateTimeOffset.UtcNow;
    var xyz=CurrentBuildPositionCandidateReader.Read(session,_=>new(key,pos,Verify));
    position=new("candidate",key,pos,positionStart,DateTimeOffset.UtcNow,xyz);
   }
  }
  TargetRawContext? targetContext=null;
  if(includeContext)
  {
   try
   {
    var rawOwner=Q(health+0x40);
    if(rawOwner==0) targetContext=new("owner-unavailable");
    else
    {
     var owner=Ptr(rawOwner,0x19E);
     if(Q(owner)!=id.ModuleBaseAddress+0x2927448||Q(id.ModuleBaseAddress+0x2927488)!=id.ModuleBaseAddress+0x19D21E0||Q(id.ModuleBaseAddress+0x34731B0)!=id.ModuleBaseAddress+0x2929BD0||Q(id.ModuleBaseAddress+0x2929BD8)!=id.ModuleBaseAddress+0x19F4D60) targetContext=new("unverified-type",owner);
     else
     {
      var level=BinaryPrimitives.ReadInt32LittleEndian(Take(owner+0x100,4));var combat=Take(owner+0x19D,1)[0];
      string levelStatus="numeric-getter-candidate", levelBranch="owner"; int? numeric=level;
      try
      {
       var index=BinaryPrimitives.ReadInt32LittleEndian(Take(id.ModuleBaseAddress+0x2F58270,4));
       if(index is <0 or >=0x60) throw new InvalidDataException("Invalid target level selector.");
       var levelSlot=Take(entity+0x18+(ulong)index,1)[0]; var alt=levelSlot==0xFF?0:Q(checked(components+levelSlot*8UL));
       if(alt!=0)
       {
        Ptr(alt,0x38);var first=Ptr(Q(alt+0x28),0x68);var value=BinaryPrimitives.ReadInt32LittleEndian(Take(first+0x64,4));
        levelBranch="alternate-primary";
        if(value==-1){var second=Ptr(Q(alt+0x30),0x68);value=BinaryPrimitives.ReadInt32LittleEndian(Take(second+0x64,4));levelBranch="alternate-secondary";}
        numeric=value;
       }
      }
      catch(InvalidDataException){if(budget>2*1024*1024)throw;levelStatus="unavailable";levelBranch="unreadable-or-invalid";numeric=null;}
      targetContext=new("raw-typed-candidate",owner,level,combat,combat!=0,levelStatus,levelBranch,numeric);
     }
    }
   }
   catch(InvalidDataException){if(budget>2*1024*1024)throw;targetContext=new("owner-or-fields-unavailable");}
  }
  Verify();
  return new(id,start,DateTimeOffset.UtcNow,before.UnitKey,"candidate",before.TargetStatus,afterStatus,key,$"u{key:X16}",entity,observation,name,position,targetContext);
 }
 static ulong U64(ReadOnlySpan<byte>b)=>BinaryPrimitives.ReadUInt64LittleEndian(b);
}
