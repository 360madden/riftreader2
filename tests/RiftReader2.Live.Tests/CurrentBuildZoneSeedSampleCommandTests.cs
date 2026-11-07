using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildZoneSeedSampleCommandTests
{
 const ulong M=0x140000000,E=0x20000000,H=0x20010000,O=0x20020000,S=0x20030000,P=0x20040000,W=0x20050000,R=0x20060000,T=0x20070000,B=0x20080000,Holder=0x20090000,Obj=0x200A0000;
 static readonly NativeThreadEpoch Epoch=new(77,123,T);
 [Fact] public void NullProviderPreservesRawKey(){var s=Fixture();s.Put(M+0x336EBF8,Q(0));var r=Read(s);Assert.Equal("null-provider",r.Status);Assert.Equal(1234U,r.RawZoneKey);}
 [Fact] public void CacheHitIsUnqualified(){var s=Fixture();var r=Read(s);Assert.Equal("unqualified-cache-record",r.Status);Assert.Equal(Obj,r.RecordAddress);Assert.Equal("null",r.ChildStatus);}
 [Fact] public void CacheMissPreservesRawKey(){var s=Fixture();var n=new byte[24];n[0]=1;s.Put(B,n);var r=Read(s);Assert.Equal("cache-miss",r.Status);Assert.Equal(1234U,r.RawZoneKey);}
 [Fact] public void ChangedKeyOrThreadRejects(){var s=Fixture();s.Change(O+0x150,BitConverter.GetBytes(1235U));Assert.Throws<InvalidDataException>(()=>Read(s));s=Fixture();int i=0;Assert.Throws<InvalidDataException>(()=>CurrentBuildZoneSeedSampleCommand.Read(s,_=>Context(s),()=>[++i==1?Epoch:Epoch with {Created=124}]));}
 static ZoneSeedObservation Read(Fake s)=>CurrentBuildZoneSeedSampleCommand.Read(s,_=>Context(s),()=>[Epoch]);
 static CurrentBuildPlayerContextObservation Context(Fake s)=>new(s.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,44,E,H,O,H,0,"x",null,null,0,"x",0,"x",false);
 static Fake Fixture(){var s=new Fake();s.Put(H+0x40,Q(O));s.Put(H+0x10,Q(E));s.Put(O,Q(M+0x2927448));s.Put(M+0x2927488,Q(M+0x19D21E0));s.Put(M+0x34731B0,Q(M+0x2929BD0));s.Put(M+0x2929BD8,Q(M+0x19F4D60));s.Put(M+0x33623E0,Q(S));s.Put(S+0x3F8,Q(E));s.Put(S+0x360,Q(44));s.Put(O+0x150,BitConverter.GetBytes(1234U));s.Put(M+0x336EBF8,Q(P));s.Put(P+0x40,BitConverter.GetBytes((ushort)55));s.Put(M+0x3372C18,Q(W));s.Put(W,Q(R));s.Put(R+0x274,new byte[4]);var ti=new byte[32];Q(T).CopyTo(ti,0);Q(123).CopyTo(ti,16);Q(77).CopyTo(ti,24);s.Put(T+0x30,ti);s.Put(T+0x1480,Q(0));var h=new byte[32];Q(B).CopyTo(h,0);Q(24).CopyTo(h,8);Q(1).CopyTo(h,16);Q(1).CopyTo(h,24);s.Put(R+0x220,h);var n=new byte[24];BinaryPrimitives.WriteUInt16LittleEndian(n.AsSpan(8),55);BinaryPrimitives.WriteUInt32LittleEndian(n.AsSpan(12),1234);Q(Holder).CopyTo(n,16);s.Put(B,n);s.Put(Holder+0x18,Q(Obj));s.Put(Obj,Q(M+0x1000));s.Put(M+0x1040,Q(M+0x2000));s.Put(Obj+0x1F0,Q(0));return s;}
 static byte[] Q(ulong v){var b=new byte[8];BinaryPrimitives.WriteUInt64LittleEndian(b,v);return b;}
 sealed class Fake:IReadOnlyNativeMemorySession{readonly Dictionary<ulong,byte[]> data=[];readonly Dictionary<ulong,byte[]> changed=[];readonly HashSet<ulong> seen=[];public NativeProcessIdentity Identity{get;}=new(123,456,@"C:\RIFT\rift_x64.exe",CurrentBuildPlayerLookup.GameSha256,M,0x4000000);public void Put(ulong a,byte[] b)=>data[a]=b;public void Change(ulong a,byte[] b)=>changed[a]=b;public NativeReadResult Read(ulong a,int n){var b=!seen.Add(a)&&changed.TryGetValue(a,out var c)?c:data.GetValueOrDefault(a);return b is not null&&b.Length==n?new("success",b.ToArray(),null,null):new("unavailable",[],null,null);}public ValueTask<string?> RevalidateAsync(CancellationToken c)=>ValueTask.FromResult<string?>(null);public ValueTask DisposeAsync()=>ValueTask.CompletedTask;}
}
