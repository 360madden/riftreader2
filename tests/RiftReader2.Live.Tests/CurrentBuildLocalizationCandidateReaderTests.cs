using System.Buffers.Binary;
using System.Text;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildLocalizationCandidateReaderTests
{
 const ulong M=0x140000000,Manager=0x20000000,Wrapper=0x20010000,Inner=0x20020000,Bucket=0x20030000,Holder=0x20040000,Result=0x20050000,Tree=0x20060000,Child=0x20070000,Text=0x20080000;
 [Fact] public void ReadsTypedTextAndLocaleFallback(){var r=Read(Fixture()).Records[0];Assert.Equal("typed-candidate",r.Status);Assert.Equal("Ability",r.CandidateText);Assert.Equal(1,r.LocaleFound);}
 [Fact] public void MissingKeyIsCacheMiss(){var s=Fixture();var n=new byte[24];n[0]=1;s.Put(Bucket,n);Assert.Equal("cache-miss",Read(s).Records[0].Status);}
 [Fact] public void DescriptorMismatchRejects(){var s=Fixture();s.Put(M+0x3484000,Q(0));Assert.Throws<InvalidDataException>(()=>Read(s));}
 [Fact] public void ChangedNodeRejects(){var s=Fixture();var n=Node();n[8]=2;s.Change(Bucket,n);Assert.Throws<InvalidDataException>(()=>Read(s));}
 [Fact] public void ChangedTextRejects(){var s=Fixture();s.Change(Text,Encoding.Unicode.GetBytes("Changed\0"));Assert.Throws<InvalidDataException>(()=>Read(s));}
 static CurrentBuildLocalizationObservation Read(Fake s)=>CurrentBuildLocalizationCandidateReader.Read(s,[1]);
 static Fake Fixture(){var s=new Fake();s.Put(M+0x33623E8,Q(Manager));var state=new byte[8];BinaryPrimitives.WriteInt32LittleEndian(state.AsSpan(4),2);s.Put(Manager,state);s.Put(Manager+0x98,Q(Wrapper));var w=new byte[16];Q(M+0x26C1EA8).CopyTo(w,0);Q(Inner).CopyTo(w,8);s.Put(Wrapper,w);s.Put(M+0x26C1EA8,Q(M+0x7D3230));var h=new byte[32];Q(Bucket).CopyTo(h,0);Q(24).CopyTo(h,8);Q(1).CopyTo(h,16);Q(1).CopyTo(h,24);s.Put(Inner+0x28,h);s.Put(Bucket,Node());s.Put(Holder+0x18,Q(Result));var r=new byte[0x48];Q(M+0x295DC10).CopyTo(r,0);Q(Tree).CopyTo(r,0x28);Q(1).CopyTo(r,0x40);s.Put(Result,r);s.Put(M+0x295DC50,Q(M+0x1A4FAF0));s.Put(M+0x3484000,Q(M+0x2963030));s.Put(M+0x2963038,Q(M+0x1A779E0));var tree=new byte[48];BinaryPrimitives.WriteInt32LittleEndian(tree.AsSpan(32),1);Q(Child).CopyTo(tree,40);s.Put(Tree,tree);s.Put(Child,Q(M+0x2804120));s.Put(M+0x2804160,Q(M+0x173C790));s.Put(M+0x3420930,Q(M+0x2820340));s.Put(M+0x2820348,Q(M+0x177CE30));var fields=new byte[16];Q(Text).CopyTo(fields,0);Q(Text).CopyTo(fields,8);s.Put(Child+0x30,fields);var bytes=new byte[256];Encoding.Unicode.GetBytes("Ability\0").CopyTo(bytes,0);s.Put(Text,bytes);return s;}
 static byte[] Node(){var n=new byte[24];n[8]=1;Q(Holder).CopyTo(n,16);return n;}static byte[] Q(ulong v){var b=new byte[8];BinaryPrimitives.WriteUInt64LittleEndian(b,v);return b;}
 sealed class Fake:IReadOnlyNativeMemorySession {readonly Dictionary<ulong,byte[]> data=[];readonly Dictionary<ulong,byte[]> changed=[];readonly HashSet<ulong> seen=[];public NativeProcessIdentity Identity{get;}=new(123,456,@"C:\RIFT\rift_x64.exe",CurrentBuildPlayerLookup.GameSha256,M,0x4000000);public void Put(ulong a,byte[] b)=>data[a]=b;public void Change(ulong a,byte[] b)=>changed[a]=b;public NativeReadResult Read(ulong a,int n){var b=!seen.Add(a)&&changed.TryGetValue(a,out var c)?c:data.GetValueOrDefault(a);return b is not null&&b.Length>=n?new("success",b[..n],null,null):new("unavailable",[],null,null);}public ValueTask<string?> RevalidateAsync(CancellationToken c)=>ValueTask.FromResult<string?>(null);public ValueTask DisposeAsync()=>ValueTask.CompletedTask;}
}
