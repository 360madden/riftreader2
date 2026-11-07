using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildExperienceSeedTests
{
 const ulong M=0x140000000,S=0x20000000,E=0x20010000,H=0x20020000,X=0x20030000,O=0x20040000,V=0x20050000,R=0x20060000;
 [Fact] public void IndexedRawCandidateAndOwnerVerification()
 {
  var f=Fixture();bool verified=false;var x=Read(f,()=>verified=true);Assert.True(verified);Assert.Equal("indexed-raw-candidate",x.Branch);
  Assert.Equal(42L,x.Selected!.RawInt64_18);Assert.Equal(19U,x.Selected.RawDword24);Assert.Equal(2.5f,x.Selected.RawFloat20);
 }
 [Fact] public void SpecialBranchAndChangedAnchors()
 {
  var f=Fixture();f.D(O+0x1D8,unchecked((uint)-1));f.B(O+0x24F,1);f.Q(O+0x7D8,3);f.Q(O+0x7E0,4);
  var x=Read(f,()=>{});Assert.Equal("special-index-minus-one",x.Branch);Assert.Equal(3UL,x.Special7D8);
  f=Fixture();f.Changed=(R+0x18,8);Assert.Throws<InvalidDataException>(()=>Read(f,()=>{}));
  f=Fixture();Assert.Throws<InvalidDataException>(()=>Read(f,()=>throw new InvalidDataException()));
 }
 static ExperienceSeedObservation Read(Fake f,Action verify)=>CurrentBuildExperienceSeedCandidateReader.ReadResolved(f,f.Identity,DateTimeOffset.UtcNow,1,E,H,X,verify);
 static Fake Fixture()
 {
  var f=new Fake();f.Q(M+0x33623E0,S);f.Q(S+0x3F8,E);f.Q(H+0x10,E);f.Q(X+0x10,E);f.Q(X+0x48,O);
  f.Q(O,M+0x1000);f.Q(M+0x1040,M+0x2000);f.D(O+0x1D8,0);f.D(O+0x160,5);f.B(O+0x24F,0);
  f.Q(O+0xDE0,V);f.Q(O+0xDE8,V+8);f.Q(V,R);f.Q(R,M+0x3000);f.Q(M+0x3040,M+0x4000);
  f.Q(R+0x18,42);f.D(R+0x20,(uint)BitConverter.SingleToInt32Bits(2.5f));f.D(R+0x24,19);return f;
 }
 sealed class Fake:IReadOnlyNativeMemorySession
 {
  readonly Dictionary<(ulong,int),byte[]> data=[];readonly Dictionary<(ulong,int),int> reads=[];public (ulong,int)? Changed{get;set;}
  public NativeProcessIdentity Identity{get;}=new(1,2,"rift.exe",CurrentBuildPlayerLookup.GameSha256,M,64*1024*1024);
  public void Q(ulong a,ulong v){var b=new byte[8];BinaryPrimitives.WriteUInt64LittleEndian(b,v);data[(a,8)]=b;}
  public void D(ulong a,uint v){var b=new byte[4];BinaryPrimitives.WriteUInt32LittleEndian(b,v);data[(a,4)]=b;}
  public void B(ulong a,byte v)=>data[(a,1)]=[v];
  public NativeReadResult Read(ulong a,int n){var k=(a,n);var old=reads.GetValueOrDefault(k);reads[k]=old+1;if(!data.TryGetValue(k,out var b))return new("unavailable",[],null,"missing");var copy=b.ToArray();if(Changed==k&&old>0)copy[0]^=1;return new("success",copy,null,null);}
  public ValueTask<string?> RevalidateAsync(CancellationToken _)=>ValueTask.FromResult<string?>(null);
  public ValueTask DisposeAsync()=>ValueTask.CompletedTask;
 }
}
