using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildUnitTemplateNamesTests
{
 const ulong M=0x140000000,Manager=0x20000000,Table=0x20010000,Unit=0x20020000,Entity=0x20030000,Provider=0x20040000,Wrapper=0x20050000,Owner=0x20060000,Teb=0x20070000,Bucket=0x20080000,Holder=0x20090000,Record=0x200A0000,Child=0x200B0000,Text=0x200C0000,Key=0x80000002CD0034D1;
 static readonly NativeThreadEpoch Thread=new(77,123,Teb);
 [Fact] public void KeysAreBoundedCanonicalUniqueAndLossless()
 {
  Assert.Equal(new ulong[]{1,ulong.MaxValue},CurrentBuildUnitTemplateNamesSampleCommand.ParseKeys("1,18446744073709551615"));
  foreach(var raw in new[]{"","0","01","1,1","-1"," 1","18446744073709551616",string.Join(',',Enumerable.Range(1,33))})
   Assert.Throws<ArgumentException>(()=>CurrentBuildUnitTemplateNamesSampleCommand.ParseKeys(raw));
 }
 static UnitTemplateNamesObservation Read(Fake s,params ulong[] keys)=>CurrentBuildUnitTemplateNamesSampleCommand.Read(s,keys,()=>[Thread],default,_=>Context(s,null));
 [Fact] public void ExplicitKeyWorksWithoutSelectedTargetAndKeepsOrderedRows()
 {
  var s=Fixture();var r=Read(s,Key,Key+1);
  Assert.Equal("Wolf",r.Rows[0].FallbackText);Assert.Equal(Key.ToString(),r.Rows[0].UnitKey);
  Assert.Equal("raw-candidate",r.Rows[0].Status);Assert.Equal("unit-missing",r.Rows[1].Status);
  Assert.Null(r.Rows[1].EntityAddressDecimal);Assert.Null(r.Rows[1].TemplateKey);
  Assert.Equal("123",r.SelfKey);Assert.True(r.Rows[0].CompletedAtUtc<=r.Rows[1].StartedAtUtc);
 }
 [Fact] public void ChangingSelectedTargetDoesNotAffectExplicitKeysOrAcquireDictionary()
 {
  var s=Fixture();s.Put(Child+0x18,BitConverter.GetBytes(42U));int calls=0;
  var r=CurrentBuildUnitTemplateNamesSampleCommand.Read(s,[Key],()=>[Thread],default,_=>Context(s,Key+(ulong)++calls));
  Assert.Equal("Wolf",r.Rows[0].FallbackText);Assert.Equal(42U,r.Rows[0].LocalizationKey);
 }
 [Fact] public void UnsupportedEntityIsRowButGlobalFingerprintFailureIsFatal()
 {
  var s=Fixture();s.Put(Entity,Q(M+1));Assert.Equal("unsupported-template-entity",Read(s,Key).Rows[0].Status);
  s=Fixture();s.Put(M+0x26AE608,Q(M+1));Assert.Throws<InvalidDataException>(()=>Read(s,Key));
 }
 [Fact] public void CacheMissIsRowAndChangedConsumedBytesFailBatch()
 {
  var s=Fixture();var n=new byte[24];n[0]=1;s.Put(Bucket,n);Assert.Equal("cache-miss",Read(s,Key).Rows[0].Status);
  s=Fixture();s.Change(Bucket,new byte[24]);Assert.Throws<InvalidDataException>(()=>Read(s,Key));
 }
 [Fact] public void ThreadAndPlayerChangesFailInsteadOfPublishingUnavailable()
 {
  var s=Fixture();int calls=0;
  Assert.Throws<InvalidDataException>(()=>CurrentBuildUnitTemplateNamesSampleCommand.Read(s,[Key],()=>[++calls==1?Thread:Thread with {Created=124}],default,_=>Context(s,null)));
  s=Fixture();calls=0;
  Assert.Throws<InvalidDataException>(()=>CurrentBuildUnitTemplateNamesSampleCommand.Read(s,[Key],()=>[Thread],default,_=>Context(s,null) with {UnitKey=++calls==1?123UL:124UL}));
 }
 [Fact] public void AggregateReadAndCooperativeTimeBudgetsAreFatal()
 {
  var s=Fixture();var bounded=new CurrentBuildUnitTemplateNamesSampleCommand.BoundedSession(s,default);
  bounded.Read(Unit,1024*1024);bounded.Read(Unit,1024*1024);
  Assert.Throws<InvalidDataException>(()=>bounded.Read(Unit,1));
  bounded=new(s,default,()=>TimeSpan.FromSeconds(3.001));Assert.Throws<InvalidDataException>(()=>bounded.Check());
 }
 [Fact] public void OldSelectedTargetStillRequiresTargetAndRejectsChanges()
 {
  var s=Fixture();Assert.Throws<InvalidDataException>(()=>CurrentBuildTargetTemplateNameSampleCommand.Read(s,_=>Context(s,null),()=>[Thread]));
  int calls=0;Assert.Throws<InvalidDataException>(()=>CurrentBuildTargetTemplateNameSampleCommand.Read(s,_=>Context(s,++calls==1?Key:Key+1),()=>[Thread]));
 }
 static CurrentBuildPlayerContextObservation Context(Fake s,ulong? k)=>new(s.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,123,Entity,0,0,0,k ?? 0,"fallback-key-candidate",k,null,0,"x",0,"x",false);
 static Fake Fixture(){var s=new Fake();s.Put(M+0x33623E8,Q(0x200D0000));s.Put(0x200D0004,BitConverter.GetBytes(1));s.Put(M+0x3373784,new byte[4]);s.Put(M+0x33624A8,Q(Manager));s.Put(Manager+0x50,Q(Table));var h=new byte[24];Q(Unit).CopyTo(h,0);Q(24).CopyTo(h,8);Q(1).CopyTo(h,16);s.Put(Table,h);var n=new byte[24];Q(Key).CopyTo(n,8);Q(Entity).CopyTo(n,16);s.Put(Unit,n);s.Put(Entity,Q(M+0x26AE5F0));s.Put(M+0x26AE608,Q(M+0x59E940));s.Put(Entity+0x1D0,Q(0));s.Put(Entity+0x1B8,BitConverter.GetBytes(1847420318U));s.Put(M+0x33E3A98,Q(Provider));s.Put(Provider+0x40,BitConverter.GetBytes((ushort)623));s.Put(M+0x3372C18,Q(Wrapper));s.Put(Wrapper,Q(Owner));s.Put(Owner+0x274,new byte[4]);var ti=new byte[32];Q(Teb).CopyTo(ti,0);Q(123).CopyTo(ti,16);Q(77).CopyTo(ti,24);s.Put(Teb+0x30,ti);s.Put(Teb+0x1480,Q(0));var ch=new byte[32];Q(Bucket).CopyTo(ch,0);Q(24).CopyTo(ch,8);Q(1).CopyTo(ch,16);Q(1).CopyTo(ch,24);s.Put(Owner+0x220,ch);n=new byte[24];BinaryPrimitives.WriteUInt16LittleEndian(n.AsSpan(8),623);BinaryPrimitives.WriteUInt32LittleEndian(n.AsSpan(12),1847420318);Q(Holder).CopyTo(n,16);s.Put(Bucket,n);s.Put(Holder+0x18,Q(Record));s.Put(Record,Q(M+0x29DB058));s.Put(M+0x29DB098,Q(M+0x1B81C10));s.Put(M+0x34AD250,Q(M+0x29E8E00));s.Put(M+0x29E8E08,Q(M+0x1BADFA0));s.Put(Record+0xA8,Q(Child));s.Put(Child,Q(M+0x27F24F8));s.Put(M+0x27F2538,Q(M+0x170C5D0));s.Put(M+0x3417970,Q(M+0x2802E40));s.Put(M+0x2802E48,Q(M+0x17361E0));s.Put(Child+0x18,new byte[4]);s.Put(Child+0x20,Q(Text));var txt=new byte[256];System.Text.Encoding.Unicode.GetBytes("Wolf\0").CopyTo(txt,0);s.Put(Text,txt);return s;}
 static byte[] Q(ulong v){var b=new byte[8];BinaryPrimitives.WriteUInt64LittleEndian(b,v);return b;}
 sealed class Fake:IReadOnlyNativeMemorySession{readonly Dictionary<ulong,byte[]> data=[];readonly Dictionary<ulong,byte[]> changed=[];readonly HashSet<ulong> seen=[];public NativeProcessIdentity Identity{get;}=new(123,456,@"C:\RIFT\rift_x64.exe",CurrentBuildPlayerLookup.GameSha256,M,0x4000000);public void Put(ulong a,byte[] b)=>data[a]=b;public void Change(ulong a,byte[] b)=>changed[a]=b;public NativeReadResult Read(ulong a,int n){var b=!seen.Add(a)&&changed.TryGetValue(a,out var c)?c:data.GetValueOrDefault(a);return b is not null&&b.Length>=n?new("success",b[..n],null,null):new("unavailable",[],null,null);}public ValueTask<string?> RevalidateAsync(CancellationToken c)=>ValueTask.FromResult<string?>(null);public ValueTask DisposeAsync()=>ValueTask.CompletedTask;}
}
