using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildCooldownModifierSampleCommandTests
{
 const ulong M=0x140000000,E=0x20000000,H=0x20010000,O=0x20020000,C=0x20030000,B=0x20040000,P=0x20050000;
 [Fact] public void EmptyAndOtherModeProduceNegativeCensus(){var s=Fixture();Assert.Equal("no-mode-4-observed",Read(s).CensusStatus);SetupRow(s,3);Assert.Equal("no-mode-4-observed",Read(s).CensusStatus);}
 [Fact] public void ModeFourCapturesInputsAndLists(){var s=Fixture();SetupRow(s,4);var r=Read(s);Assert.Equal("mode-4-present",r.CensusStatus);var row=Assert.Single(r.Rows);Assert.Equal(1.5f,row.Float18);Assert.Equal(2U,row.Operation);Assert.Equal(12345U,row.RawScaleKey);Assert.Empty(row.DirectKeys!.Values);}
 [Theory]
 [InlineData((byte)0,true)]
 [InlineData((byte)1,false)]
 public void ModeZeroCapturesRangePayloadAndHonorsScaleBranch(byte flag33,bool useDirectScale)
 {
  var s=Fixture();SetupRow(s,0);SetupScale(s);
  s.Put(P+0x33,[flag33]);s.Put(P+0x178,[..Q(B+0x100),..Q(B+0x104)]);s.Put(B+0x100,BitConverter.GetBytes(999U));
  var observation=ReadScale(s);var row=Assert.Single(observation.Rows);
  Assert.Equal("no-mode-4-observed",observation.CensusStatus);Assert.Equal(1U,observation.RawContextKey);
  Assert.Equal("mode-0-raw-candidate",row.Status);Assert.Equal(0,row.Mode);
  Assert.Equal(1.5f,row.Float18);Assert.Equal(2.5f,row.Float24);Assert.Equal(2U,row.Operation);
  Assert.Equal(flag33,row.Flag33);Assert.Equal(999U,Assert.Single(row.DirectKeys!.Values));Assert.Equal(12345U,row.RawScaleKey);
  if(useDirectScale)Assert.Equal(37,row.DirectScale!.RawMultiplier);else Assert.Null(row.DirectScale);
 }
 [Fact] public void MissingRangePayloadKeepsKnownModeForCooldownCensus()
 {
  var s=Fixture();SetupRow(s,0);s.Put(P+0x18,[]);
  var observation=Read(s);var row=Assert.Single(observation.Rows);
  Assert.Equal("no-mode-4-observed",observation.CensusStatus);Assert.Equal("mode-0-payload-unavailable",row.Status);
  Assert.Equal(0,row.Mode);Assert.Null(row.Float18Bits);Assert.Null(row.DirectKeys);
 }
 [Theory]
 [InlineData(-3,4,"typed-073c-direct-branch")]
 [InlineData(0,4,"typed-073c-fallback-branch")]
 [InlineData(3,-1,"typed-073c-fallback-branch")]
 public void Flag33UsesComparedEntityFieldAndTypedReference(int key,int slot,string status)
 {
  const ulong source=0x20140000;
  var s=Fixture();SetupRow(s,0);s.Put(P+0x33,[1]);
  var entry=new byte[32];Q(P).CopyTo(entry,0);Q(88).CopyTo(entry,0x10);s.Put(B,entry);
  s.Put(E+0x10,Q(88));s.Put(P+0xA0,Q(source));Type(s,source,0x2A062F8,0x1BF3DD0,0x34BD9D0,0x2A1F988,0x1C29690);
  byte[] fields=[..BitConverter.GetBytes(key),..BitConverter.GetBytes(slot)];s.Put(source+0x18,fields);
  var seed=Assert.Single(Read(s).Rows).Flag33Seed!;
  Assert.Equal(status,seed.Status);Assert.Equal(E,seed.Entity);Assert.Equal(88UL,seed.EntrySourceKey);
  Assert.Equal(88UL,seed.EntitySourceKey);Assert.True(seed.SourceMatches);Assert.Equal(source,seed.Address);
  Assert.Equal(key,seed.Key18);Assert.Equal(slot,seed.Slot1C);
  s.Change(source+0x18,BitConverter.GetBytes(70L));Assert.Throws<InvalidDataException>(()=>Read(s));
 }
 [Fact] public void Flag33DistinguishesOtherSourceNullAndUnverifiedReference()
 {
  var s=Fixture();SetupRow(s,0);s.Put(P+0x33,[1]);
  Flag33Seed Seed()=>Assert.Single(Read(s).Rows).Flag33Seed!;
  var seed=Seed();Assert.Equal("read-unavailable",seed.Status);Assert.Null(seed.SourceMatches);
  s.Put(E+0x10,Q(44));seed=Seed();Assert.Equal("entry-count-branch",seed.Status);Assert.False(seed.SourceMatches);Assert.Null(seed.Address);
  s.Put(E+0x10,Q(0));s.Put(P+0xA0,Q(0));seed=Seed();Assert.Equal("null-073c-reference",seed.Status);Assert.Equal(0UL,seed.Address);
  const ulong source=0x20140000;s.Put(P+0xA0,Q(source));s.Put(source,Q(M));seed=Seed();
  Assert.Equal("unverified-073c-type",seed.Status);Assert.Equal(source,seed.Address);Assert.Null(seed.Key18);Assert.Null(seed.Slot1C);
  s.Put(P+0x33,[0]);Assert.Null(Assert.Single(Read(s).Rows).Flag33Seed);
 }
 const ulong Alt=0x20100000, AltOwner=0x20101000, Role=0x20104000, Node=0x20105000, Container=0x20106000, Child=0x20107000, RoleRefs=0x20109000, ChildRefs=0x2010A000;
 static Fake RoleFixture(bool special)
 {
  const ulong seed=0x20120000;
  var s=Fixture();SetupRow(s,0);s.Put(P+0x33,[1]);s.Put(E+0x10,Q(0));s.Put(P+0xA0,Q(seed));
  Type(s,seed,0x2A062F8,0x1BF3DD0,0x34BD9D0,0x2A1F988,0x1C29690);
  s.Put(seed+0x18,[..BitConverter.GetBytes(-36),..BitConverter.GetBytes(1)]);
  s.Put(Alt+0x10,Q(E));s.Put(Alt+0x48,Q(AltOwner));Type(s,AltOwner,0x2A46738,0x1C48CC0,0x34C9670,0x2A4B760,0x1C84130);
  s.Put(AltOwner+0x24F,[special?(byte)1:(byte)0]);
  if(special)s.Put(AltOwner+0x7D8,[..Q(RoleRefs+8),..Q(RoleRefs+16)]);
  else{s.Put(AltOwner+0xDE0,[..Q(RoleRefs),..Q(RoleRefs+16)]);s.Put(AltOwner+0x1D8,BitConverter.GetBytes(1U));}
  s.Put(RoleRefs+8,Q(Role));Type(s,Role,0x2BD4388,0x201A050,0x3548720,0x2BE0EF8,0x20482A0);
  s.Put(Role+0x188,Q(Node));s.Put(Node+0x20,BitConverter.GetBytes(2));s.Put(Node+0x10,Q(Node+0x100));
  s.Put(Node+0x100+0x20,BitConverter.GetBytes(-36));s.Put(Node+0x100+0x28,Q(Container));
  Type(s,Container,0x2868CD8,0x1821880,0x343A3D0,0x2875988,0x184BD10);s.Put(Container+0x20,[..Q(ChildRefs),..Q(ChildRefs+16)]);s.Put(ChildRefs,Q(Child));s.Put(ChildRefs+8,Q(Child+0x100));
  Type(s,Child,0x2AB13A8,0x1D5DF30,0x34E9BC0,0x2AB32D8,0x1D7CEC0);
  s.Put(Child+0x18,BitConverter.GetBytes(1));s.Put(Child+0x1C,BitConverter.GetBytes(-7));
  return s;
 }
 static RoleFactorObservation Factor(Fake s)=>Assert.Single(ReadScale(s).Rows).Flag33Seed!.RoleFactor!;
 [Theory]
 [InlineData(true)]
 [InlineData(false)]
 public void DirectRoleReadsFirstMatchingSignedFactorFromSelectedReference(bool special)
 {
  var s=RoleFixture(special);var result=Factor(s);
  Assert.Equal("raw-factor-candidate",result.Status);Assert.Equal(-7,result.RawMultiplier);Assert.Equal(Role,result.RoleAddress);
  Assert.Equal(Node+0x100,result.NodeAddress);Assert.Equal(Container,result.ContainerAddress);Assert.Equal(Child,result.ChildAddress);
  s.Change(Child+0x1C,BitConverter.GetBytes(8));Assert.Throws<InvalidDataException>(()=>ReadScale(s));
 }
 [Fact] public void DirectRoleDistinguishesMissingSlotUnknownChildAndTreeCycle()
 {
  var s=RoleFixture(false);s.Put(Child+0x18,BitConverter.GetBytes(2));s.Put(ChildRefs+8,Q(0));
  var miss=Factor(s);Assert.Equal("slot-miss-zero-candidate",miss.Status);Assert.Equal(0,miss.RawMultiplier);
  s.Put(Child,Q(M));var unknown=Factor(s);Assert.Equal("child-type-unavailable",unknown.Status);Assert.Null(unknown.RawMultiplier);
  s.Put(Node+0x10,Q(Node));var cycle=Factor(s);Assert.Equal("tree-path-unavailable",cycle.Status);Assert.Null(cycle.RawMultiplier);
 }
 [Fact] public void ModeTwoCapturesPayloadWhileKeepingModeFourCensus()
 {
  var s=Fixture();SetupRow(s,2);SetupScale(s);var observation=ReadScale(s);var row=Assert.Single(observation.Rows);
  Assert.Equal("no-mode-4-observed",observation.CensusStatus);Assert.Equal("mode-2-raw-candidate",row.Status);
  Assert.Equal(2U,row.Operation);Assert.Equal(37,row.DirectScale!.RawMultiplier);Assert.Null(row.Flag33Seed);
  s.Put(P+0x33,[1]);Assert.Null(Assert.Single(ReadScale(s).Rows).DirectScale);
  s.Put(P+0x18,[]);var partial=ReadScale(s);Assert.Equal("mode-2-payload-unavailable",Assert.Single(partial.Rows).Status);
  Assert.Equal("no-mode-4-observed",partial.CensusStatus);
 }
 [Fact] public void ModeTwoUsesFlag33RoleFactorForItsFractionalRow()
 {
  var s=RoleFixture(false);s.Put(P+0x28,BitConverter.GetBytes(2));
  s.Put(P+0x24,BitConverter.GetBytes(-0.165f));s.Put(P+0x18,BitConverter.GetBytes(0f));
  var observation=ReadScale(s);var row=Assert.Single(observation.Rows);
  Assert.Equal("no-mode-4-observed",observation.CensusStatus);Assert.Equal("mode-2-raw-candidate",row.Status);
  Assert.Equal(2U,row.Operation);Assert.Equal(-0.165f,row.Float24);Assert.Null(row.DirectScale);
  Assert.Equal("typed-073c-direct-branch",row.Flag33Seed!.Status);
  Assert.Equal("raw-factor-candidate",row.Flag33Seed.RoleFactor!.Status);Assert.Equal(-7,row.Flag33Seed.RoleFactor.RawMultiplier);
 }
 [Fact] public void NullReferenceIsIncomplete(){var s=Fixture();SetupRow(s,4);s.Put(B,new byte[32]);Assert.Equal("incomplete",Read(s).CensusStatus);}
 [Fact] public void RangeConfigRequiresInitializedTypedReference()
 {
  const ulong root=0x20140000, config=0x20150000, slot=M+0x33E0AB0;
  var s=Fixture();Assert.Equal("read-unavailable",Read(s).RangeConfig.Status);
  s.Put(slot,Q(0));Assert.Equal("null-root",Read(s).RangeConfig.Status);
  s.Put(slot,Q(root));s.Put(root+0x848,Q(0));Assert.Equal("null-config",Read(s).RangeConfig.Status);
  s.Put(root+0x848,Q(config));s.Put(config,Q(M+0x1000));var unknown=Read(s).RangeConfig;
  Assert.Equal("unverified-type",unknown.Status);Assert.Null(unknown.SpecialKey);
  Type(s,config,0x2ADB030,0x1DD2CD0,0x34FC1D0,0x2AEB9E8,0x1DFCAF0);
  s.Put(config+0x64,BitConverter.GetBytes(2.5f));s.Put(config+0x7C,BitConverter.GetBytes(50f));s.Put(config+0x88,BitConverter.GetBytes(99U));
  var result=Read(s).RangeConfig;
  Assert.Equal("typed-0e29-candidate",result.Status);Assert.Equal(root,result.Root);Assert.Equal(config,result.Address);
  Assert.Equal(2.5f,result.Min);Assert.Equal(BitConverter.SingleToUInt32Bits(50f),result.MaxBits);Assert.Equal(99U,result.SpecialKey);
  s.Put(config+0x7C,BitConverter.GetBytes(0x7fc00001U));var nonfinite=Read(s).RangeConfig;
  Assert.Equal(0x7fc00001U,nonfinite.MaxBits);Assert.Null(nonfinite.Max);
  s.Change(config+0x88,BitConverter.GetBytes(100U));Assert.Throws<InvalidDataException>(()=>Read(s));
 }
 [Fact] public void ChangedScaleKeyRejects(){var s=Fixture();SetupRow(s,4);s.Change(P+0x20,BitConverter.GetBytes(12346U));Assert.Throws<InvalidDataException>(()=>Read(s));}
 [Fact] public void DirectScaleHitNullAndMutation()
 {
  var s=Fixture();SetupRow(s,4);SetupScale(s);var r=ReadScale(s);var row=Assert.Single(r.Rows);
  Assert.Equal("raw-factor-candidate",row.DirectScale!.Status);Assert.Equal(37,row.DirectScale.RawMultiplier);
  s=Fixture();SetupRow(s,4);SetupScale(s);s.Put(0x20110000+0x28,Q(0));r=ReadScale(s);Assert.Equal("null-row-zero-candidate",Assert.Single(r.Rows).DirectScale!.Status);
  s=Fixture();SetupRow(s,4);SetupScale(s);s.Put(0x20110000+0x20,BitConverter.GetBytes(12346));s.Put(0x20110000+0x10,Q(0));r=ReadScale(s);Assert.Equal("null-link-zero-candidate",Assert.Single(r.Rows).DirectScale!.Status);
  s=Fixture();SetupRow(s,4);SetupScale(s);s.Change(0x20120000+0x18,BitConverter.GetBytes(38));Assert.Throws<InvalidDataException>(()=>ReadScale(s));
 }
 static CooldownModifierObservation ReadScale(Fake s)=>CurrentBuildCooldownModifierSampleCommand.Read(s,_=>new(s.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,44,E,H,O,H,0,"x",null,null,0,"x",0,"x",false),_=>new(44,E,C,()=>{}),_=>new(44,E,0x20100000,()=>{}));
 static void Type(Fake s,ulong a,ulong vt,ulong g,ulong d,ulong dv,ulong dg){s.Put(a,Q(M+vt));s.Put(M+vt+0x40,Q(M+g));s.Put(M+d,Q(M+dv));s.Put(M+dv+8,Q(M+dg));}
 static void SetupScale(Fake s)
 {
  const ulong alt=0x20100000, owner=0x20101000,tree=0x20102000,node=0x20110000,row=0x20120000;
  s.Put(P+0x36,[1]);s.Put(alt+0x10,Q(E));s.Put(alt+0x48,Q(owner));Type(s,owner,0x2A46738,0x1C48CC0,0x34C9670,0x2A4B760,0x1C84130);
  s.Put(owner+0xDD0,Q(tree));Type(s,tree,0x2996D90,0x1ACE0B0,0x34940A0,0x29977A8,0x1AF0010);
  s.Put(tree+0x50,Q(node));s.Put(node+0x20,BitConverter.GetBytes(12345));s.Put(node+0x28,Q(row));Type(s,row,0x2D224F0,0x2348300,0x35B4B40,0x2D2E858,0x2368AB0);s.Put(row+0x18,BitConverter.GetBytes(37));
 }
 [Fact] public void ChangedModeRejects(){var s=Fixture();SetupRow(s,4);s.Change(P+0x28,BitConverter.GetBytes(3));Assert.Throws<InvalidDataException>(()=>Read(s));}
 static CooldownModifierObservation Read(Fake s)=>CurrentBuildCooldownModifierSampleCommand.Read(s,_=>new(s.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,44,E,H,O,H,0,"x",null,null,0,"x",0,"x",false),_=>new(44,E,C,()=>{}));
 static Fake Fixture(){var s=new Fake();s.Put(C+0x10,Q(E));s.Put(C+0x3F8,new byte[16]);return s;}
 static void SetupRow(Fake s,int mode){var h=new byte[16];Q(B).CopyTo(h,0);Q(B+32).CopyTo(h,8);s.Put(C+0x3F8,h);var e=new byte[32];Q(P).CopyTo(e,0);s.Put(B,e);s.Put(P+0x28,BitConverter.GetBytes(mode));s.Put(P,Q(M+0x1000));s.Put(M+0x1040,Q(M+0x2000));s.Put(C+0x2F0,BitConverter.GetBytes(1U));s.Put(P+0x18,BitConverter.GetBytes(1.5f));s.Put(P+0x24,BitConverter.GetBytes(2.5f));s.Put(P+0x20,BitConverter.GetBytes(12345U));s.Put(P+0x2C,BitConverter.GetBytes(2U));foreach(ulong off in new ulong[]{0x30,0x33,0x34,0x36})s.Put(P+off,[0]);foreach(ulong off in new ulong[]{0x110,0x178,0x1E0,0x248,0x2B0})s.Put(P+off,new byte[16]);}
 static byte[] Q(ulong v){var b=new byte[8];BinaryPrimitives.WriteUInt64LittleEndian(b,v);return b;}
 sealed class Fake:IReadOnlyNativeMemorySession{readonly Dictionary<ulong,byte[]> data=[];readonly Dictionary<ulong,byte[]> changed=[];readonly HashSet<ulong> seen=[];public NativeProcessIdentity Identity{get;}=new(123,456,@"C:\RIFT\rift_x64.exe",CurrentBuildPlayerLookup.GameSha256,M,0x4000000);public void Put(ulong a,byte[] b)=>data[a]=b;public void Change(ulong a,byte[] b){seen.Remove(a);changed[a]=b;}public NativeReadResult Read(ulong a,int n){var b=!seen.Add(a)&&changed.TryGetValue(a,out var c)?c:data.GetValueOrDefault(a);return b is not null&&b.Length==n?new("success",b.ToArray(),null,null):new("unavailable",[],null,null);}public ValueTask<string?> RevalidateAsync(CancellationToken c)=>ValueTask.FromResult<string?>(null);public ValueTask DisposeAsync()=>ValueTask.CompletedTask;}
}
