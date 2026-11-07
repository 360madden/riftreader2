using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live;
internal sealed record SelectedTargetObservation(NativeProcessIdentity Identity,DateTimeOffset StartedAtUtc,DateTimeOffset CompletedAtUtc,ulong SelfKey,string Status,string BeforeGuardStatus,string? AfterGuardStatus,ulong? TargetKey,string? TargetUnitId,ulong? TargetEntity,CurrentBuildVitalsObservation? TargetVitals)
{
 public string Qualification=>"candidate-only; target and vitals semantics, freshness and restart unverified";
}
internal static class CurrentBuildSelectedTargetCandidateReader
{
 internal static SelectedTargetObservation Read(IReadOnlyNativeMemorySession session)=>Read(session,CurrentBuildPlayerContextCandidateReader.Read,(s,owner)=>CurrentBuildVitalsCandidateReader.Read(s,_=>owner));
 internal static SelectedTargetObservation Read(IReadOnlyNativeMemorySession session,Func<IReadOnlyNativeMemorySession,CurrentBuildPlayerContextObservation> context,Func<IReadOnlyNativeMemorySession,CurrentBuildVitalsOwnerSnapshot,CurrentBuildVitalsObservation> vitals)
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
  string? afterStatus=null;
  void Verify()
  {
   foreach(var a in anchors)CurrentBuildPlayerLookup.RequireSame(Take(a.Key.Item1,a.Key.Item2,false),a.Value);
   var now=context(session);afterStatus=now.TargetStatus;
   if(now.Identity!=id||now.UnitKey!=before.UnitKey||now.TargetKeyCandidate!=key||session.Identity!=id)throw new InvalidDataException("Self or gated target changed during capture.");
  }
  var observation=vitals(session,new(key,health,Verify));Verify();
  return new(id,start,DateTimeOffset.UtcNow,before.UnitKey,"candidate",before.TargetStatus,afterStatus,key,$"u{key:X16}",entity,observation);
 }
 static ulong U64(ReadOnlySpan<byte>b)=>BinaryPrimitives.ReadUInt64LittleEndian(b);
}
