using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildStatsSampleCommandTests
{
 const ulong M=0x140000000,E=0x20000000,H=0x20010000,O=0x20020000,S=0x20030000,R=0x20040000,Map=0x20050000,A=0x20060000,U=0x20070000;
 [Fact] public void ReadsKnownIndexAndPreservesMissing(){var s=Fixture();var r=Read(s);Assert.Equal(123L,r.Stats[0].Ordinary.RawSigned64);Assert.Equal(-7L,r.Stats[0].Unbuffed.RawSigned64);Assert.Equal("index-unavailable",r.Stats[1].Ordinary.Status);Assert.Null(r.Stats[1].Ordinary.RawSigned64);}
 [Fact] public void AllTwentyVerifiedSelectorsAreCaptured(){var s=Fixture();var rows=Read(s).Stats;Assert.Equal(20,rows.Count);Assert.Contains(rows,r=>r.Name=="strength"&&r.Selector==5);Assert.Contains(rows,r=>r.Name=="critPower"&&r.Selector==83);Assert.Contains(rows,r=>r.Name=="resistAir"&&r.Selector==41);}
 [Fact] public void CachedReceiverMismatchFails(){var s=Fixture();s.Put(S+0x400,Q(H+8));Assert.Throws<InvalidDataException>(()=>Read(s));}
 [Fact] public void MappingAndValueMutationFail(){var s=Fixture();s.Change(Map+37*4,BitConverter.GetBytes(1));Assert.Throws<InvalidDataException>(()=>Read(s));s=Fixture();s.Change(A,Q(124));Assert.Throws<InvalidDataException>(()=>Read(s));}
 [Fact] public void WrongRecordTypeFails(){var s=Fixture();s.Put(R,Q(M+0x1234));Assert.Throws<InvalidDataException>(()=>Read(s));}
 static StatsObservation Read(Fake s)=>CurrentBuildStatsSampleCommand.Read(s,_=>new(s.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,44,E,H,O,H,0,"x",null,null,0,"x",0,"x",false),_=>new(44,E,H,()=>{}));
 static Fake Fixture(){var s=new Fake();s.Put(M+0x33623E0,Q(S));s.Put(S+0x360,Q(44));s.Put(S+0x3F8,Q(E));s.Put(S+0x400,Q(H));s.Put(H+0x10,Q(E));s.Put(H+0x40,Q(O));s.Put(O,Q(M+0x2927448));s.Put(M+0x2927488,Q(M+0x19D21E0));s.Put(M+0x34731B0,Q(M+0x2929BD0));s.Put(M+0x2929BD8,Q(M+0x19F4D60));s.Put(O+0x640,Q(R));s.Put(R,Q(M+0x2C0EE88));s.Put(M+0x2C0EEC8,Q(M+0x20CCC60));s.Put(M+0x355F430,Q(M+0x2C281B0));s.Put(M+0x2C281B8,Q(M+0x20F2480));s.Put(M+0x33E3AE8,Q(Map));foreach(var i in new[]{37,24,32,26,33,5,1,3,4,2,35,36,38,39,40,41,31,83,27,30})s.Put(Map+(ulong)i*4,BitConverter.GetBytes(i==37?0:-1));s.Put(R+0x78,Header(A));s.Put(R+0x148,Header(U));s.Put(A,Q(123));s.Put(U,BitConverter.GetBytes(-7L));return s;}
 static byte[] Header(ulong a){var b=new byte[16];Q(a).CopyTo(b,0);Q(a+8).CopyTo(b,8);return b;}static byte[] Q(ulong v){var b=new byte[8];BinaryPrimitives.WriteUInt64LittleEndian(b,v);return b;}
 sealed class Fake:IReadOnlyNativeMemorySession{readonly Dictionary<ulong,byte[]> data=[];readonly Dictionary<ulong,byte[]> changed=[];readonly HashSet<ulong> seen=[];public NativeProcessIdentity Identity{get;}=new(123,456,@"C:\RIFT\rift_x64.exe",CurrentBuildPlayerLookup.GameSha256,M,0x4000000);public void Put(ulong a,byte[] b)=>data[a]=b;public void Change(ulong a,byte[] b)=>changed[a]=b;public NativeReadResult Read(ulong a,int n){var b=!seen.Add(a)&&changed.TryGetValue(a,out var c)?c:data.GetValueOrDefault(a);return b is not null&&b.Length==n?new("success",b.ToArray(),null,null):new("unavailable",[],null,null);}public ValueTask<string?> RevalidateAsync(CancellationToken c)=>ValueTask.FromResult<string?>(null);public ValueTask DisposeAsync()=>ValueTask.CompletedTask;}
}
