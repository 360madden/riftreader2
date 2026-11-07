using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildExperienceValuesTests
{
 const ulong M=0x140000000,O=0x20000000,R=0x20010000,G=0x20020000,CV=0x20030000,C=0x20040000,BV=0x20050000,P=0x20060000,W=0x20070000,REG=0x20080000,TEB=0x20090000,TABLE=0x200A0000,HOLDER=0x200B0000,DATA=0x200C0000;
 [Fact] public void ReadsTypedDatasetAndCalculatesCandidate()
 {
  var f=Fixture();var result=Run(f);Assert.Equal("raw-values-candidate",result.ValueStatus);Assert.Equal(43,result.Level);Assert.Equal(1000L,result.Baseline);Assert.Equal(200,result.Needed);Assert.Equal(3506622L,result.AccumulatedCandidate);
 }
 [Fact] public void RejectsThreadEpochChangeDuringFinalSeedRead()
 {
  var f=Fixture();var seedReads=0;
  Assert.Throws<InvalidDataException>(()=>CurrentBuildExperienceValuesCandidateReader.Read(f,
   _=>{seedReads++;return Seed(f);},()=>[new(7,seedReads>=2?9:8,TEB)]));
  Assert.Equal(2,seedReads);
 }
 [Fact] public void RestedSelectsFlaggedSourceAndRejectsNonfinite()
 {
  var f=Fixture();f.Q(M+0x33E0B08,0x200D0000);f.B(0x200D0087,1);f.D(R+0x20,BitConverter.SingleToInt32Bits(12.9f));
  var x=Run(f);Assert.Equal("raw-rested-candidate",x.RestedStatus);Assert.Equal(12L,x.RestedCandidate);
  f=Fixture();f.Q(M+0x33E0B08,0x200D0000);f.B(0x200D0087,0);f.D(O+0x138,BitConverter.SingleToInt32Bits(float.NaN));
  x=Run(f);Assert.Equal("nonfinite-or-out-of-range",x.RestedStatus);Assert.Null(x.RestedCandidate);
 }
 [Fact] public void CapAndColdCacheAreExplicit()
 {
  var f=Fixture();f.D(C+0x34,43);Assert.Equal("native-minus-one-level-cap",Run(f).ValueStatus);
  f=Fixture();f.Q(M+0x33E0D88,0);Assert.Equal("provider-uninitialized",Run(f).ValueStatus);
  f=Fixture();f.Changed=(DATA+0x20,4);Assert.Throws<InvalidDataException>(()=>Run(f));
 }
 static ExperienceValuesObservation Run(Fake f)=>CurrentBuildExperienceValuesCandidateReader.Read(f,_=>Seed(f),()=>[new(7,8,TEB)]);
 static ExperienceSeedObservation Seed(Fake f)=>new(f.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,1,0x21000000,0x21010000,O,0x2A46738,0x1C48CC0,0,0,0,0x21020000,0x21020008,[R],"indexed-raw-candidate",new(R,0x2BD4388,0x201A050,3507422,43,0,0),null,null);
 static Fake Fixture()
 {
  var f=new Fake();f.Type(O,0x2A46738,0x1C48CC0,0x34C9670,0x2A4B760,0x1C84130);f.Type(R,0x2BD4388,0x201A050,0x3548720,0x2BE0EF8,0x20482A0);
  f.Q(M+0x33E0B08,0);f.Q(R+0x18,3507422);f.D(R+0x24,43);f.Q(M+0x33E0AB0,G);f.Q(G+0x870,CV);f.Q(G+0x878,CV+8);f.Q(CV,C);
  f.Type(C,0x2BA1608,0x1FA64F0,0x3538760,0x2BADC68,0x1FCBC00);f.D(C+0x34,51);f.Q(M+0x33E0C98,BV);f.Q(M+0x33E0CA0,BV+52*8);f.Q(BV+43*8,1000);
  f.Q(M+0x33E0D88,P);f.U16(P+0x40,83);f.Q(M+0x3372C18,W);f.Q(W,REG);f.D(REG+0x274,1);
  var ti=new byte[32];BinaryPrimitives.WriteUInt64LittleEndian(ti,TEB);BinaryPrimitives.WriteUInt64LittleEndian(ti.AsSpan(16),1);BinaryPrimitives.WriteUInt64LittleEndian(ti.AsSpan(24),7);f.Put(TEB+0x30,ti);f.Q(TEB+0x1488,0);
  var header=new byte[32];BinaryPrimitives.WriteUInt64LittleEndian(header,TABLE);BinaryPrimitives.WriteUInt64LittleEndian(header.AsSpan(8),24);BinaryPrimitives.WriteUInt64LittleEndian(header.AsSpan(16),1);f.Put(REG+0x220,header);
  var node=new byte[24];BinaryPrimitives.WriteUInt16LittleEndian(node.AsSpan(8),83);BinaryPrimitives.WriteUInt32LittleEndian(node.AsSpan(12),43);BinaryPrimitives.WriteUInt64LittleEndian(node.AsSpan(16),HOLDER);f.Put(TABLE,node);f.Q(HOLDER+0x18,DATA);
  f.Type(DATA,0x2C04110,0x208AF40,0x3557780,0x2C0DC80,0x20AFB30);f.D(M+0x2F95CF4,2);f.D(DATA+0x20,200);return f;
 }
 sealed class Fake:IReadOnlyNativeMemorySession
 {
  readonly Dictionary<(ulong,int),byte[]> data=[];readonly Dictionary<(ulong,int),int> reads=[];public (ulong,int)? Changed{get;set;}
  public NativeProcessIdentity Identity{get;}=new(1,2,"rift.exe",CurrentBuildPlayerLookup.GameSha256,M,64*1024*1024);
  public void Put(ulong a,byte[] b)=>data[(a,b.Length)]=b;public void Q(ulong a,ulong v){var b=new byte[8];BinaryPrimitives.WriteUInt64LittleEndian(b,v);Put(a,b);}public void D(ulong a,int v){var b=new byte[4];BinaryPrimitives.WriteInt32LittleEndian(b,v);Put(a,b);}public void B(ulong a,byte v)=>Put(a,[v]);public void U16(ulong a,ushort v){var b=new byte[2];BinaryPrimitives.WriteUInt16LittleEndian(b,v);Put(a,b);}
  public void Type(ulong a,ulong vt,ulong getter,ulong desc,ulong dvt,ulong dg){Q(a,M+vt);Q(M+vt+0x40,M+getter);Q(M+desc,M+dvt);Q(M+dvt+8,M+dg);}
  public NativeReadResult Read(ulong a,int n){var k=(a,n);var old=reads.GetValueOrDefault(k);reads[k]=old+1;if(!data.TryGetValue(k,out var b))return new("unavailable",[],null,"missing");var copy=b.ToArray();if(Changed==k&&old>0)copy[0]^=1;return new("success",copy,null,null);}
  public ValueTask<string?> RevalidateAsync(CancellationToken _)=>ValueTask.FromResult<string?>(null);public ValueTask DisposeAsync()=>ValueTask.CompletedTask;
 }
}
