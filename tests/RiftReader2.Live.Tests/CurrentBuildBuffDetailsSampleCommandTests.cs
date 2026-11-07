using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildBuffDetailsSampleCommandTests
{
 const ulong M=0x140000000,Obj=0x20000000,State=0x20010000,Timer=0x20020000,Ref=0x20030000;
 [Fact] public void ZeroCasterAndStateSentinel(){var s=Fixture();s.Put(Obj+0x28,Q(0));s.Put(State+0x88,BitConverter.GetBytes(5U));var r=Assert.Single(Read(s).Rows);Assert.Equal("u0000000000000000",r.CasterUnitIdCandidate);Assert.Equal("sentinel",r.Stack.Status);Assert.Equal(0xAB9AACF9U,r.Stack.GetterRawBits);}
 [Fact] public void TypedGateReturnsRawStack(){var s=Fixture();ConfigureTyped(s);var r=Assert.Single(Read(s).Rows);Assert.Equal("raw-getter-candidate",r.Stack.Status);Assert.Equal(3,r.Stack.ReferenceGate);Assert.Equal(7,r.Stack.TimerValue);}
 [Fact] public void BelowThresholdUsesSentinel(){var s=Fixture();ConfigureTyped(s);s.Put(Ref+0x30,BitConverter.GetBytes(1));Assert.Equal("sentinel",Assert.Single(Read(s).Rows).Stack.Status);}
 [Fact] public void ChangedValueOrListRejects(){var s=Fixture();ConfigureTyped(s);s.Change(Timer+0x1C,BitConverter.GetBytes(8));Assert.Throws<InvalidDataException>(()=>Read(s));s=Fixture();int i=0;Assert.Throws<InvalidDataException>(()=>CurrentBuildBuffDetailsSampleCommand.Read(s,_=>Seed(s,++i==1?Obj:Obj+8)));}
 static BuffDetailSeedObservation Read(Fake s)=>CurrentBuildBuffDetailsSampleCommand.Read(s,_=>Seed(s,Obj));
 static CurrentBuildBuffSeedObservation Seed(Fake s,ulong obj)=>new(s.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,44,0x20040000,0x20050000,[new(0x20060000,0x20050000,obj,0,new("raw-candidate"))]);
 static Fake Fixture(){var s=new Fake();s.Put(Obj+0x28,Q(44));s.Put(Obj+0x20,Q(State));s.Put(State+0x88,BitConverter.GetBytes(1U));s.Put(Obj+0x68,Q(Timer));s.Put(Timer,Q(M+0x26BCE50));s.Put(M+0x26BCE90,Q(M+0x72B4C0));return s;}
 static void ConfigureTyped(Fake s){s.Put(Timer,Q(M+0x26BC950));s.Put(M+0x26BC990,Q(M+0x72B610));s.Put(Timer+0x10,Q(Ref));s.Put(Ref,Q(M+0x286CDC8));s.Put(M+0x286CE08,Q(M+0x18254A0));s.Put(M+0x343B3C0,Q(M+0x2876CA8));s.Put(M+0x2876CB0,Q(M+0x184B530));s.Put(Ref+0x30,BitConverter.GetBytes(3));s.Put(Timer+0x1C,BitConverter.GetBytes(7));}
 static byte[] Q(ulong v){var b=new byte[8];BinaryPrimitives.WriteUInt64LittleEndian(b,v);return b;}
 sealed class Fake:IReadOnlyNativeMemorySession{readonly Dictionary<ulong,byte[]> data=[];readonly Dictionary<ulong,byte[]> changed=[];readonly HashSet<ulong> seen=[];public NativeProcessIdentity Identity{get;}=new(123,456,@"C:\RIFT\rift_x64.exe",CurrentBuildPlayerLookup.GameSha256,M,0x4000000);public void Put(ulong a,byte[] b)=>data[a]=b;public void Change(ulong a,byte[] b)=>changed[a]=b;public NativeReadResult Read(ulong a,int n){var b=!seen.Add(a)&&changed.TryGetValue(a,out var c)?c:data.GetValueOrDefault(a);return b is not null&&b.Length==n?new("success",b.ToArray(),null,null):new("unavailable",[],null,null);}public ValueTask<string?> RevalidateAsync(CancellationToken c)=>ValueTask.FromResult<string?>(null);public ValueTask DisposeAsync()=>ValueTask.CompletedTask;}
}
