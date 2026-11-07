using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildCooldownModifierSampleCommandTests
{
 const ulong M=0x140000000,E=0x20000000,H=0x20010000,O=0x20020000,C=0x20030000,B=0x20040000,P=0x20050000;
 [Fact] public void EmptyAndOtherModeProduceNegativeCensus(){var s=Fixture();Assert.Equal("no-mode-4-observed",Read(s).CensusStatus);SetupRow(s,3);Assert.Equal("no-mode-4-observed",Read(s).CensusStatus);}
 [Fact] public void ModeFourCapturesInputsAndLists(){var s=Fixture();SetupRow(s,4);var r=Read(s);Assert.Equal("mode-4-present",r.CensusStatus);var row=Assert.Single(r.Rows);Assert.Equal(1.5f,row.Float18);Assert.Equal(2U,row.Operation);Assert.Empty(row.DirectKeys!.Values);}
 [Fact] public void NullReferenceIsIncomplete(){var s=Fixture();SetupRow(s,4);s.Put(B,new byte[32]);Assert.Equal("incomplete",Read(s).CensusStatus);}
 [Fact] public void ChangedModeRejects(){var s=Fixture();SetupRow(s,4);s.Change(P+0x28,BitConverter.GetBytes(3));Assert.Throws<InvalidDataException>(()=>Read(s));}
 static CooldownModifierObservation Read(Fake s)=>CurrentBuildCooldownModifierSampleCommand.Read(s,_=>new(s.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,44,E,H,O,H,0,"x",null,null,0,"x",0,"x",false),_=>new(44,E,C,()=>{}));
 static Fake Fixture(){var s=new Fake();s.Put(C+0x10,Q(E));s.Put(C+0x3F8,new byte[16]);return s;}
 static void SetupRow(Fake s,int mode){var h=new byte[16];Q(B).CopyTo(h,0);Q(B+32).CopyTo(h,8);s.Put(C+0x3F8,h);var e=new byte[32];Q(P).CopyTo(e,0);s.Put(B,e);s.Put(P+0x28,BitConverter.GetBytes(mode));s.Put(P,Q(M+0x1000));s.Put(M+0x1040,Q(M+0x2000));s.Put(C+0x2F0,BitConverter.GetBytes(1U));s.Put(P+0x18,BitConverter.GetBytes(1.5f));s.Put(P+0x24,BitConverter.GetBytes(2.5f));s.Put(P+0x2C,BitConverter.GetBytes(2U));foreach(ulong off in new ulong[]{0x30,0x33,0x34,0x36})s.Put(P+off,[0]);foreach(ulong off in new ulong[]{0x110,0x178,0x1E0,0x248,0x2B0})s.Put(P+off,new byte[16]);}
 static byte[] Q(ulong v){var b=new byte[8];BinaryPrimitives.WriteUInt64LittleEndian(b,v);return b;}
 sealed class Fake:IReadOnlyNativeMemorySession{readonly Dictionary<ulong,byte[]> data=[];readonly Dictionary<ulong,byte[]> changed=[];readonly HashSet<ulong> seen=[];public NativeProcessIdentity Identity{get;}=new(123,456,@"C:\RIFT\rift_x64.exe",CurrentBuildPlayerLookup.GameSha256,M,0x4000000);public void Put(ulong a,byte[] b)=>data[a]=b;public void Change(ulong a,byte[] b)=>changed[a]=b;public NativeReadResult Read(ulong a,int n){var b=!seen.Add(a)&&changed.TryGetValue(a,out var c)?c:data.GetValueOrDefault(a);return b is not null&&b.Length==n?new("success",b.ToArray(),null,null):new("unavailable",[],null,null);}public ValueTask<string?> RevalidateAsync(CancellationToken c)=>ValueTask.FromResult<string?>(null);public ValueTask DisposeAsync()=>ValueTask.CompletedTask;}
}
