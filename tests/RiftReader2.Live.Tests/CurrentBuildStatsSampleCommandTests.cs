using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildStatsSampleCommandTests
{
 const ulong M=0x140000000,E=0x20000000,H=0x20010000,O=0x20020000,S=0x20030000,R=0x20040000,Map=0x20050000,A=0x20060000,U=0x20070000;
 [Fact] public void ReadsKnownIndexAndPreservesMissing(){var s=Fixture();var r=Read(s);Assert.Equal(123L,r.Stats[0].Ordinary.RawSigned64);Assert.Equal(-7L,r.Stats[0].Unbuffed.RawSigned64);Assert.Equal("index-unavailable",r.Stats[1].Ordinary.Status);Assert.Null(r.Stats[1].Ordinary.RawSigned64);}
 [Fact] public void AllTwentyVerifiedSelectorsAreCaptured(){var s=Fixture();var rows=Read(s).Stats;Assert.Equal(20,rows.Count);Assert.Contains(rows,r=>r.Name=="strength"&&r.Selector==5);Assert.Contains(rows,r=>r.Name=="critPower"&&r.Selector==83);Assert.Contains(rows,r=>r.Name=="resistAir"&&r.Selector==41);}
  [Fact] public void SelectorMappingUsesOneBracketedRead(){var s=Fixture();Read(s);Assert.Equal(2,s.ReadCount(Map));}
  [Fact] public void ExportsAllEightyFourSelectorMappingsWithoutExtraReads()
  {
   var s=Fixture();var map=s.Get(Map);
   BinaryPrimitives.WriteInt32LittleEndian(map.AsSpan(0,4),146);
   BinaryPrimitives.WriteInt32LittleEndian(map.AsSpan(82*4,4),-2);
   s.Put(Map,map);
   var result=Read(s);
   Assert.Equal(84,result.SelectorMapCandidate.Count);
   Assert.Equal(146,result.SelectorMapCandidate[0]);
   Assert.Equal(-2,result.SelectorMapCandidate[82]);
   Assert.Equal(0,result.SelectorMapCandidate[37]);
   Assert.Equal(-1,result.SelectorMapCandidate[81]);
   Assert.Equal(123L,result.Stats[0].Ordinary.RawSigned64);
   Assert.Equal(2,s.ReadCount(Map));
  }
 [Fact] public void AdjacentStatsShareOneValueReadPerVector()
 {
  var s=Fixture();var map=s.Get(Map);BinaryPrimitives.WriteInt32LittleEndian(map.AsSpan(24*4,4),1);s.Put(Map,map);
  s.Put(R+0x78,Header(A,2));s.Put(R+0x148,Header(U,2));
  var normal=new byte[16];Q(123).CopyTo(normal,0);Q(321).CopyTo(normal,8);s.Put(A,normal);
  var baseValues=new byte[16];BitConverter.GetBytes(-7L).CopyTo(baseValues,0);BitConverter.GetBytes(-9L).CopyTo(baseValues,8);s.Put(U,baseValues);
  var rows=Read(s).Stats;Assert.Equal(321L,rows[1].Ordinary.RawSigned64);Assert.Equal(-9L,rows[1].Unbuffed.RawSigned64);
  Assert.Equal(2,s.ReadCount(A));Assert.Equal(2,s.ReadCount(U));Assert.Equal(0,s.ReadCount(A+8));Assert.Equal(0,s.ReadCount(U+8));
 }
 [Fact] public void HistoricalTwentySelectorLayoutBatchesIntoFiveGroupsPerVector()
 {
  var s=Fixture();var map=s.Get(Map);
  var mappings=new (int Selector,int Index)[]{(37,20),(24,8),(32,14),(26,9),(33,15),
   (5,2),(1,3),(3,4),(4,5),(2,6),(35,18),(36,19),(38,21),(39,22),
   (40,23),(41,24),(31,13),(83,146),(27,10),(30,12)};
  foreach(var (selector,index) in mappings)
   BinaryPrimitives.WriteInt32LittleEndian(map.AsSpan(selector*4,4),index);
  s.Put(Map,map);s.Put(R+0x78,Header(A,147));s.Put(R+0x148,Header(U,147));
  var groups=new (int Start,int End)[]{(2,6),(8,10),(12,15),(18,24),(146,146)};
  foreach(var (start,end) in groups)
  {
   var ordinary=new byte[(end-start+1)*8];var unbuffed=new byte[ordinary.Length];
   for(var index=start;index<=end;index++)
   {
    BitConverter.GetBytes(1000L+index).CopyTo(ordinary,(index-start)*8);
    BitConverter.GetBytes(-1000L-index).CopyTo(unbuffed,(index-start)*8);
   }
   s.Put(A+(ulong)start*8,ordinary);s.Put(U+(ulong)start*8,unbuffed);
  }
  var rows=Read(s).Stats;Assert.Equal(20,rows.Count);
  foreach(var row in rows)
  {
   Assert.Equal(1000L+row.MappedIndex,row.Ordinary.RawSigned64);
   Assert.Equal(-1000L-row.MappedIndex,row.Unbuffed.RawSigned64);
  }
  foreach(var (start,_) in groups)
  {
   Assert.Equal(2,s.ReadCount(A+(ulong)start*8));
   Assert.Equal(2,s.ReadCount(U+(ulong)start*8));
  }
  Assert.Equal(0,s.ReadCount(A));Assert.Equal(0,s.ReadCount(U));
 }
  [Fact] public void ProductionStatsReaderReusesOneAnchoredLookup()
  {
   var s=Fixture();const ulong manager=0x20100000,table=0x20110000,buckets=0x20120000,components=0x20130000;
   s.Put(M+0x33624A8,Q(manager));s.Put(manager+0x50,Q(table));
   var header=new byte[24];Q(buckets).CopyTo(header,0);Q(24).CopyTo(header,8);Q(1).CopyTo(header,16);s.Put(table,header);
   var bucket=new byte[24];Q(44).CopyTo(bucket,8);Q(E).CopyTo(bucket,16);s.Put(buckets,bucket);
   var entity=new byte[128];entity[0x18]=0;Q(components).CopyTo(entity,0x78);s.Put(E,entity);
   s.Put(components,Q(H));s.Put(M+0x2F57850,BitConverter.GetBytes(0));
   var result=CurrentBuildStatsSampleCommand.Read(s);
   Assert.Equal(123L,result.Stats[0].Ordinary.RawSigned64);
   Assert.Equal(2,s.ReadCount(M+0x33624A8)); // One lookup plus its anchor recheck.
   Assert.Equal(0,s.ReadCount(O+0x100)); // Unrelated level field.
   Assert.Equal(0,s.ReadCount(M+0x2F58270)); // Unrelated target/level selector.
   s=Fixture();s.Put(M+0x33624A8,Q(manager));s.Put(manager+0x50,Q(table));
   s.Put(table,header);s.Put(buckets,bucket);s.Put(E,entity);
   s.Put(components,Q(H));s.Put(M+0x2F57850,BitConverter.GetBytes(0));
   s.Change(manager+0x50,Q(table+0x1000));
   Assert.Throws<InvalidDataException>(()=>CurrentBuildStatsSampleCommand.Read(s));
  }
 [Fact] public void CachedReceiverMismatchFails(){var s=Fixture();s.Put(S+0x400,Q(H+8));Assert.Throws<InvalidDataException>(()=>Read(s));}
 [Fact] public void MappingAndValueMutationFail(){var s=Fixture();var changedMap=s.Get(Map);BinaryPrimitives.WriteInt32LittleEndian(changedMap.AsSpan(37*4,4),1);s.Change(Map,changedMap);Assert.Throws<InvalidDataException>(()=>Read(s));s=Fixture();s.Change(A,Q(124));Assert.Throws<InvalidDataException>(()=>Read(s));}
 [Fact] public void WrongRecordTypeFails(){var s=Fixture();s.Put(R,Q(M+0x1234));Assert.Throws<InvalidDataException>(()=>Read(s));}
 static StatsObservation Read(Fake s)=>CurrentBuildStatsSampleCommand.Read(s,_=>new(s.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,44,E,H,O,H,0,"x",null,null,0,"x",0,"x",false),_=>new(44,E,H,()=>{}));
 static Fake Fixture(){var s=new Fake();s.Put(M+0x33623E0,Q(S));s.Put(S+0x360,Q(44));s.Put(S+0x3F8,Q(E));s.Put(S+0x400,Q(H));s.Put(H+0x10,Q(E));s.Put(H+0x40,Q(O));s.Put(O,Q(M+0x2927448));s.Put(M+0x2927488,Q(M+0x19D21E0));s.Put(M+0x34731B0,Q(M+0x2929BD0));s.Put(M+0x2929BD8,Q(M+0x19F4D60));s.Put(O+0x640,Q(R));s.Put(R,Q(M+0x2C0EE88));s.Put(M+0x2C0EEC8,Q(M+0x20CCC60));s.Put(M+0x355F430,Q(M+0x2C281B0));s.Put(M+0x2C281B8,Q(M+0x20F2480));s.Put(M+0x33E3AE8,Q(Map));var rawMap=new byte[336];for(var i=0;i<84;i++)BinaryPrimitives.WriteInt32LittleEndian(rawMap.AsSpan(i*4,4),-1);BinaryPrimitives.WriteInt32LittleEndian(rawMap.AsSpan(37*4,4),0);s.Put(Map,rawMap);s.Put(R+0x78,Header(A));s.Put(R+0x148,Header(U));s.Put(A,Q(123));s.Put(U,BitConverter.GetBytes(-7L));return s;}
 static byte[] Header(ulong a,int count=1){var b=new byte[16];Q(a).CopyTo(b,0);Q(a+(ulong)count*8).CopyTo(b,8);return b;}static byte[] Q(ulong v){var b=new byte[8];BinaryPrimitives.WriteUInt64LittleEndian(b,v);return b;}
 sealed class Fake:IReadOnlyNativeMemorySession{readonly Dictionary<ulong,byte[]> data=[];readonly Dictionary<ulong,byte[]> changed=[];readonly HashSet<ulong> seen=[];readonly Dictionary<ulong,int> counts=[];public NativeProcessIdentity Identity{get;}=new(123,456,@"C:\RIFT\rift_x64.exe",CurrentBuildPlayerLookup.GameSha256,M,0x4000000);public void Put(ulong a,byte[] b)=>data[a]=b;public byte[] Get(ulong a)=>data[a].ToArray();public int ReadCount(ulong a)=>counts.GetValueOrDefault(a);public void Change(ulong a,byte[] b)=>changed[a]=b;public NativeReadResult Read(ulong a,int n){counts[a]=ReadCount(a)+1;var b=!seen.Add(a)&&changed.TryGetValue(a,out var c)?c:data.GetValueOrDefault(a);return b is not null&&b.Length==n?new("success",b.ToArray(),null,null):new("unavailable",[],null,null);}public ValueTask<string?> RevalidateAsync(CancellationToken c)=>ValueTask.FromResult<string?>(null);public ValueTask DisposeAsync()=>ValueTask.CompletedTask;}
}
