using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildPlayerDecorationSampleCommandTests
{
 const ulong M=0x140000000,E=0x20000000,H=0x20010000,O=0x20020000,Manager=0x20030000,T=0x20040000,C=0x20050000,P=0x20060000,B=0x20070000,Obj=0x20080000,Text=0x20090000;
 [Fact] public void FindsDecorationText(){var s=Fixture();var r=Read(s);Assert.Equal("text-candidate",r.Status);Assert.Equal("Example",r.DecorationTextCandidate);}
 [Fact] public void EqualAndMissAreDistinct(){var s=Fixture();s.Put(Manager+0x46C,BitConverter.GetBytes(1704U));Assert.Equal("no-decoration-equal",Read(s).Status);s=Fixture();var n=new byte[24];n[0]=1;s.Put(B,n);Assert.Equal("cache-miss",Read(s).Status);}
 [Fact] public void ChangedTextRejects(){var s=Fixture();s.Change(Text,System.Text.Encoding.Unicode.GetBytes("Changed\0"));Assert.Throws<InvalidDataException>(()=>Read(s));}
 static PlayerDecorationObservation Read(Fake s)=>CurrentBuildPlayerDecorationSampleCommand.Read(s,_=>new(s.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,44,E,H,O,H,0,"x",null,null,0,"x",0,"x",false),_=>new(44,E,H,()=>{}));
 static Fake Fixture(){var s=new Fake();s.Put(M+0x33623E0,Q(Manager));s.Put(Manager+0x360,Q(44));s.Put(Manager+0x3F8,Q(E));s.Put(H+0x10,Q(E));s.Put(H+0x40,Q(O));s.Put(M+0x2F582E0,BitConverter.GetBytes(1));s.Put(E+0x19,[0]);s.Put(E+0x78,Q(T));s.Put(T,Q(C));s.Put(E+0x1D0,Q(0));s.Put(C+0x48,Q(P));s.Put(P+0x20C,BitConverter.GetBytes(1704U));s.Put(Manager+0x46C,BitConverter.GetBytes(99U));var h=new byte[24];Q(B).CopyTo(h,0);Q(24).CopyTo(h,8);Q(1).CopyTo(h,16);s.Put(Manager+0x4B8,h);var n=new byte[24];BinaryPrimitives.WriteUInt32LittleEndian(n.AsSpan(8),1704);Q(Obj).CopyTo(n,16);s.Put(B,n);s.Put(Obj+0xD8,Q(Text));var txt=new byte[256];System.Text.Encoding.Unicode.GetBytes("Example\0").CopyTo(txt,0);s.Put(Text,txt);return s;}
 static byte[] Q(ulong v){var b=new byte[8];BinaryPrimitives.WriteUInt64LittleEndian(b,v);return b;}
 sealed class Fake:IReadOnlyNativeMemorySession{readonly Dictionary<ulong,byte[]> data=[];readonly Dictionary<ulong,byte[]> changed=[];readonly HashSet<ulong> seen=[];public NativeProcessIdentity Identity{get;}=new(123,456,@"C:\RIFT\rift_x64.exe",CurrentBuildPlayerLookup.GameSha256,M,0x4000000);public void Put(ulong a,byte[] b)=>data[a]=b;public void Change(ulong a,byte[] b)=>changed[a]=b;public NativeReadResult Read(ulong a,int n){var b=!seen.Add(a)&&changed.TryGetValue(a,out var c)?c:data.GetValueOrDefault(a);return b is not null&&b.Length>=n?new("success",b[..n],null,null):new("unavailable",[],null,null);}public ValueTask<string?> RevalidateAsync(CancellationToken c)=>ValueTask.FromResult<string?>(null);public ValueTask DisposeAsync()=>ValueTask.CompletedTask;}
}
