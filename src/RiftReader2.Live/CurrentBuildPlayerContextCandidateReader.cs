using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live;
internal sealed record PlayerContextOwner(ulong Key,ulong Entity,ulong Health,Action Verify);
internal sealed record CurrentBuildPlayerContextObservation(NativeProcessIdentity Identity,DateTimeOffset StartedAtUtc,DateTimeOffset CompletedAtUtc,ulong UnitKey,ulong Entity,ulong HealthComponent,ulong Owner,ulong CachedContext,ulong RawFallbackKey,string TargetStatus,ulong? TargetKeyCandidate,string? TargetUnitIdCandidate,int RawLevel,string LevelStatus,byte RawCombat,string CombatStatus,bool CombatCandidate,uint? RawCalling = null,string? CallingCandidate = null)
{
 public string Qualification=>"candidate-only; changed-state, API correspondence and restart unverified";
}
internal static class CurrentBuildPlayerContextCandidateReader
{
 internal static CurrentBuildPlayerContextObservation Read(IReadOnlyNativeMemorySession session)=>Read(session,s=>{var l=CurrentBuildPlayerLookup.Resolve(s);return new(l.PlayerKey,l.EntityAddress,l.ResolveComponent(0x2F57850),l.VerifyUnchanged);});
 internal static CurrentBuildPlayerContextObservation Read(IReadOnlyNativeMemorySession session,Func<IReadOnlyNativeMemorySession,PlayerContextOwner> resolve)
 {
  var started=DateTimeOffset.UtcNow;var id=session.Identity;
  if(id.ProcessId<=0||id.ProcessStartUtcTicks<=0||id.ModuleSize<0x34731B8||!string.Equals(id.ExecutableSha256,CurrentBuildPlayerLookup.GameSha256,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("Invalid player context build or epoch.");
  var lookup=resolve(session);if(lookup.Key==0)throw new InvalidDataException("Missing self key.");
  var anchors=new Dictionary<(ulong,int),byte[]>();int budget=0;
  byte[] Take(ulong a,int n,bool remember=true){budget=checked(budget+n);if(budget>2*1024*1024)throw new InvalidDataException("Read budget exceeded.");var raw=CurrentBuildPlayerLookup.Exact(session,a,n);if(remember){if(anchors.TryGetValue((a,n),out var old)&&!old.AsSpan().SequenceEqual(raw))throw new InvalidDataException("Player context changed.");anchors[(a,n)]=raw.ToArray();}return raw;}
  ulong Ptr(ulong a,int n=8)=>CurrentBuildPlayerLookup.Pointer(a,n);ulong Q(ulong a)=>U64(Take(a,8));
  var entity=Ptr(lookup.Entity,128);var health=Ptr(lookup.Health,0x328);var system=Ptr(Q(id.ModuleBaseAddress+0x33623E0),0x408);
  if(Q(system+0x360)!=lookup.Key||Q(system+0x3F8)!=entity||Q(health+0x10)!=entity)throw new InvalidDataException("Cached self identity mismatch.");
  var cachedContext=Q(system+0x400);var owner=Ptr(Q(health+0x40),0x19E);
  if(Q(owner)!=id.ModuleBaseAddress+0x2927448||Q(id.ModuleBaseAddress+0x2927488)!=id.ModuleBaseAddress+0x19D21E0||Q(id.ModuleBaseAddress+0x34731B0)!=id.ModuleBaseAddress+0x2929BD0||Q(id.ModuleBaseAddress+0x2929BD8)!=id.ModuleBaseAddress+0x19F4D60)throw new InvalidDataException("Player owner type fingerprint mismatch.");
  var fallback=Q(owner+0x20);var level=BinaryPrimitives.ReadInt32LittleEndian(Take(owner+0x100,4));var combat=Take(owner+0x19D,1)[0];var calling=BinaryPrimitives.ReadUInt32LittleEndian(Take(owner+0x168,4));
  byte Selector(ulong rva){var index=BinaryPrimitives.ReadInt32LittleEndian(Take(id.ModuleBaseAddress+rva,4));if(index is <0 or >=0x60)throw new InvalidDataException("Invalid component selector.");return Take(entity+0x18+(ulong)index,1)[0];}
  ulong Component(byte slot){if(slot==0xFF)return 0;var table=Ptr(Q(entity+0x78));return Q(checked(table+slot*8UL));}
  string levelStatus;
  var levelSlot=Selector(0x2F58270);var alternate=Component(levelSlot);
  if(alternate!=0)levelStatus="alternate-component-unavailable";
  else levelStatus=cachedContext==health?"numeric-getter-and-presentation-candidate":"numeric-getter-candidate-presentation-unqualified";
  var targetStatus="override-unavailable";ulong? target=null;
  try
  {
   bool useFallback=false;var targetSlot=Selector(0x2F582E0);
   if(targetSlot!=0xFF)useFallback=true;
   else
   {
    var selectionSlot=Selector(0x2F57260);var selection=Component(selectionSlot);
    if(selection==0)useFallback=true;
    else
    {
     Ptr(selection,0x2B0);var first=Take(selection+0x280,16);var second=Take(selection+0x290,16);
     if(U64(first)==0&&U64(first.AsSpan(8))==0&&U64(second)==0&&U64(second.AsSpan(8))==0)
     {
      var state=Ptr(Q(health+0x320),0x44);var stateValue=BinaryPrimitives.ReadInt32LittleEndian(Take(state+0x40,4));
      if(stateValue is <6 or >11)useFallback=true;
      else {var third=Take(selection+0x2A0,16);if(U64(third)==0&&U64(third.AsSpan(8))==0)useFallback=true;}
     }
    }
   }
   if(useFallback){target=fallback;targetStatus=fallback==0?"raw-getter-zero-candidate":"fallback-key-candidate";}
  }
  catch(InvalidDataException){if(budget>2*1024*1024)throw;targetStatus="guard-unreadable-or-invalid";target=null;}
  foreach(var a in anchors)CurrentBuildPlayerLookup.RequireSame(Take(a.Key.Item1,a.Key.Item2,false),a.Value);
  lookup.Verify();if(session.Identity!=id)throw new InvalidDataException("Player context epoch changed.");
  return new(id,started,DateTimeOffset.UtcNow,lookup.Key,entity,health,owner,cachedContext,fallback,targetStatus,target,target.HasValue&&target.Value!=0?$"u{target.Value:X16}":null,level,levelStatus,combat,"raw-byte-candidate",combat!=0,calling,calling switch {1=>"warrior",2=>"cleric",3=>"mage",4=>"rogue",7=>"primalist",_=>null});
 }
 static ulong U64(ReadOnlySpan<byte>b)=>BinaryPrimitives.ReadUInt64LittleEndian(b);
}
