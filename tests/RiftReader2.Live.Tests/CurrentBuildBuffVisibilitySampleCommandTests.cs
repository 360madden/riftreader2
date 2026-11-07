using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildBuffVisibilitySampleCommandTests
{
 const ulong M=0x140000000,E=0x20000000,H=0x20010000,S=0x20020000,Obj=0x20030000,Desc=0x20040000;
 [Fact] public void AbsentViewerAcceptsTypedOrdinary(){var s=Fixture();var o=Read(s);var r=Assert.Single(o.Rows);Assert.Equal("predicate-pass-candidate",r.Status);Assert.Equal(123UL,r.RawListIdCandidate);}
 [Fact] public void KindOneIsExcluded(){var s=Fixture();s.Put(Desc+0x38,BitConverter.GetBytes(1U));Assert.Equal("excluded-first-guard",Assert.Single(Read(s).Rows).Status);}
 [Fact] public void DescriptorChangeRejects(){var s=Fixture();s.Change(Desc+0x38,BitConverter.GetBytes(1U));Assert.Throws<InvalidDataException>(()=>Read(s));}
 [Fact] public void SeedChangeRejects(){var s=Fixture();int i=0;Assert.Throws<InvalidDataException>(()=>CurrentBuildBuffVisibilitySampleCommand.Read(s,_=>Seed(s,++i==1?Obj:Obj+8),_=>new(44,E,H,()=>{})));}
 static BuffVisibilityObservation Read(Fake s)=>CurrentBuildBuffVisibilitySampleCommand.Read(s,_=>Seed(s,Obj),_=>new(44,E,H,()=>{}));
 static CurrentBuildBuffSeedObservation Seed(Fake s,ulong obj)=>new(s.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,44,0x20050000,0x20060000,[new(0x20070000,0x20060000,obj,0,new("raw-candidate"))]);
 static Fake Fixture(){var s=new Fake();s.Put(M+0x33623E0,Q(S));s.Put(S+0x3F8,Q(E));s.Put(S+0x360,Q(44));s.Put(M+0x2F582E0,BitConverter.GetBytes(1));s.Put(E+0x19,[255]);s.Put(Obj+0x10,Q(Desc));s.Put(Desc,Q(M+0x28DC6A8));s.Put(M+0x28DC6E8,Q(M+0x193DF00));s.Put(M+0x34623E0,Q(M+0x28F5188));s.Put(M+0x28F5190,Q(M+0x1978690));s.Put(Desc+0x38,BitConverter.GetBytes(2U));s.Put(Obj+0x3C,BitConverter.GetBytes(8U));s.Put(Obj+0x48,Q(123));return s;}
 static byte[] Q(ulong v){var b=new byte[8];BinaryPrimitives.WriteUInt64LittleEndian(b,v);return b;}
 sealed class Fake:IReadOnlyNativeMemorySession{readonly Dictionary<ulong,byte[]> data=[];readonly Dictionary<ulong,byte[]> changed=[];readonly HashSet<ulong> seen=[];public NativeProcessIdentity Identity{get;}=new(123,456,@"C:\RIFT\rift_x64.exe",CurrentBuildPlayerLookup.GameSha256,M,0x4000000);public void Put(ulong a,byte[] b)=>data[a]=b;public void Change(ulong a,byte[] b)=>changed[a]=b;public NativeReadResult Read(ulong a,int n){var b=!seen.Add(a)&&changed.TryGetValue(a,out var c)?c:data.GetValueOrDefault(a);return b is not null&&b.Length==n?new("success",b.ToArray(),null,null):new("unavailable",[],null,null);}public ValueTask<string?> RevalidateAsync(CancellationToken c)=>ValueTask.FromResult<string?>(null);public ValueTask DisposeAsync()=>ValueTask.CompletedTask;}
}
