using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildWorldCastCandidateReaderTests
{
 const ulong M=0x140000000, Manager=0x20000000,Table=0x20010000,Bucket=0x20020000,Entity=0x20030000,Slots=0x20040000,Component=0x20050000,Child=0x20060000,Guard=0x20070000,Duration=0x20080000,Clock=0x20090000;
 [Fact] public void KnownTypePreservesNegativeDuration() {var s=Fixture();var o=CurrentBuildWorldCastCandidateReader.Read(s);var r=Assert.Single(o.Rows);Assert.Equal("raw-fingerprint-candidate",r.DurationStatus);Assert.Equal(-2,r.Duration);Assert.Equal(1,o.Examined);}
 const ulong Input0650 = 0x200A0000;

 static Fake Primary0650(int milliseconds)
 {
     var session = Fixture();
     session.Put(Duration, Q(M + 0x26AA020));
     session.Put(M + 0x26AA028, Q(M + 0x537270));
     session.Put(Duration + 8, Q(Child));
     session.Put(Duration + 0x10, Q(Input0650));
     session.Put(Input0650, Q(M + 0x28940E0));
     session.Put(M + 0x2894120, Q(M + 0x188FAC0));
     session.Put(M + 0x3448E50, Q(M + 0x28A7EF8));
     session.Put(M + 0x28A7F00, Q(M + 0x18C0680));
     session.Put(Input0650 + 0x20, BitConverter.GetBytes(milliseconds));
     return session;
 }

 [Theory]
 [InlineData(2501, "raw-fingerprint-candidate")]
 [InlineData(0, "nonpositive-primary-duration")]
 [InlineData(-1, "nonpositive-primary-duration")]
 public void Primary0650ReadsSavedInputMilliseconds(int milliseconds, string status)
 {
     var row = Assert.Single(CurrentBuildWorldCastCandidateReader.Read(Primary0650(milliseconds)).Rows);
     Assert.Equal(0, row.SelectedBranch);
     Assert.Equal(Input0650, row.DurationInput);
     Assert.Equal(milliseconds, row.DurationMillisecondsRaw);
     Assert.Equal((float)milliseconds * 0.001f, row.Duration);
     Assert.Equal(status, row.DurationStatus);
 }

 [Theory]
 [InlineData(Duration + 8, "duration-wrapper-owner-mismatch")]
 [InlineData(Duration + 0x10, "duration-input-absent")]
 [InlineData(M + 0x3448E50, "duration-input-type-unverified")]
 public void InvalidPrimary0650BindingLeavesDurationUnavailable(ulong address, string status)
 {
     var session = Primary0650(2501);
     session.Put(address, Q(0));
     var row = Assert.Single(CurrentBuildWorldCastCandidateReader.Read(session).Rows);
     Assert.Equal(status, row.DurationStatus);
     Assert.Null(row.Duration);
     Assert.Null(row.DurationMillisecondsRaw);
 }

 [Fact]
 public void ChangingPrimary0650PayloadInvalidatesTheObservedRow()
 {
     var session = Primary0650(2501);
     session.Change(Input0650 + 0x20, BitConverter.GetBytes(3000));
     var observation = CurrentBuildWorldCastCandidateReader.Read(session);
     Assert.Empty(observation.Rows);
     Assert.Equal(1, observation.Unavailable);
 }

 [Fact]
 public void FallbackBranchDoesNotUsePrimary0650Decoder()
 {
     var session = Primary0650(2501);
     session.Put(Component + 0x280, Q(0));
     session.Put(Component + 0x288, Q(0));
     session.Put(Component + 0x290, Q(Child));
     session.Put(Component + 0x298, Q(1));
     session.Put(Child + 0x34, BitConverter.GetBytes(5f));
     session.Put(Child + 0x28, Q(Duration));
     var row = Assert.Single(CurrentBuildWorldCastCandidateReader.Read(session).Rows);
     Assert.Equal(1, row.SelectedBranch);
     Assert.Equal("unsupported-type", row.DurationStatus);
     Assert.Null(row.Duration);
     Assert.Null(row.DurationMillisecondsRaw);
 }
 [Fact] public void WrongTypeIsSeedOnly() {var s=Fixture();s.Put(Duration,Q(M+0x26AA0E8));s.Put(M+0x26AA0F0,Q(M+0x100));var r=Assert.Single(CurrentBuildWorldCastCandidateReader.Read(s).Rows);Assert.Equal("unsupported-type",r.DurationStatus);Assert.Null(r.Duration);}
 [Fact] public void ChangedEntityBindingIsUnavailable() {var s=Fixture();var x=Node();Q(Entity+8).CopyTo(x,16);s.Change(Bucket,x);var o=CurrentBuildWorldCastCandidateReader.Read(s);Assert.Empty(o.Rows);Assert.Equal(1,o.Unavailable);}
 [Fact] public void NoControlDoesNotSelectChild() {var s=Fixture();s.Put(Component+0x288,Q(0));var r=Assert.Single(CurrentBuildWorldCastCandidateReader.Read(s).Rows);Assert.Equal("no-selected-child",r.DurationStatus);Assert.Null(r.Duration);}
 [Fact] public void ZeroIdAndNullGuardPreserveRawRow() {var s=Fixture();s.Put(Child+8,BitConverter.GetBytes(0U));var r=Assert.Single(CurrentBuildWorldCastCandidateReader.Read(s).Rows);Assert.Equal("no-nonzero-child-id",r.DurationStatus);s=Fixture();s.Put(Child+0x10,Q(0));r=Assert.Single(CurrentBuildWorldCastCandidateReader.Read(s).Rows);Assert.Equal("guard-object-absent",r.DurationStatus);Assert.Equal(123U,r.FirstRawId);}
 [Fact] public void StartsAtRequestedBucket() {var s=Fixture();var h=new byte[24];Q(Bucket).CopyTo(h,0);Q(24).CopyTo(h,8);Q(2).CopyTo(h,16);s.Put(Table,h);var empty=new byte[24];empty[0]=1;s.Put(Bucket,empty);s.Put(Bucket+24,Node());var o=CurrentBuildWorldCastCandidateReader.Read(s,1);Assert.Equal(1UL,o.StartBucket);Assert.Equal(2UL,o.BucketCount);Assert.Single(o.Rows);}
 [Fact] public void BackwardClockRejectsFrame() {var s=Fixture();s.Change(Clock+0x18,BitConverter.GetBytes(99f));Assert.Throws<InvalidDataException>(()=>CurrentBuildWorldCastCandidateReader.Read(s));}
 [Fact] public void ChangedGlobalRootRejectsFrame() {var s=Fixture();s.Change(Manager+0x50,Q(Table+8));Assert.Throws<InvalidDataException>(()=>CurrentBuildWorldCastCandidateReader.Read(s));}
 static Fake Fixture() {var s=new Fake();s.Put(M+0x33624A8,Q(Manager));s.Put(Manager+0x50,Q(Table));var h=new byte[24];Q(Bucket).CopyTo(h,0);Q(24).CopyTo(h,8);Q(1).CopyTo(h,16);s.Put(Table,h);s.Put(M+0x2F57260,BitConverter.GetBytes(0));s.Put(M+0x33DC2B0,Q(Clock));s.Put(Clock+0x18,BitConverter.GetBytes(100f));s.Put(Bucket,Node());s.Put(Entity+0x18,[0]);s.Put(Entity+0x78,Q(Slots));s.Put(Slots,Q(Component));s.Put(Component+0x280,Q(Child));s.Put(Component+0x288,Q(1));s.Put(Component+0x290,Q(0));s.Put(Component+0x298,Q(0));s.Put(Component+0x2B8,BitConverter.GetBytes(0U));s.Put(Child+8,BitConverter.GetBytes(123U));s.Put(Child+0x10,Q(Guard));s.Put(Guard+0xC8,[0]);s.Put(Child+0x30,BitConverter.GetBytes(5f));s.Put(Child+0x20,Q(Duration));s.Put(Duration,Q(M+0x26AA0E0));s.Put(M+0x26AA0E8,Q(M+0x09D680));s.Put(Duration+0x18,BitConverter.GetBytes(-2f));return s;}
 static byte[] Node(){var n=new byte[24];Q(42).CopyTo(n,8);Q(Entity).CopyTo(n,16);return n;}
 static byte[] Q(ulong v){var b=new byte[8];BinaryPrimitives.WriteUInt64LittleEndian(b,v);return b;}
 sealed class Fake:IReadOnlyNativeMemorySession {readonly Dictionary<ulong,byte[]> data=[];readonly Dictionary<ulong,byte[]> changed=[];readonly HashSet<ulong> seen=[];public NativeProcessIdentity Identity {get;}=new(123,456,@"C:\RIFT\rift_x64.exe",CurrentBuildPlayerLookup.GameSha256,M,0x4000000);public void Put(ulong a,byte[] b)=>data[a]=b;public void Change(ulong a,byte[] b)=>changed[a]=b;public NativeReadResult Read(ulong a,int n){var b=!seen.Add(a)&&changed.TryGetValue(a,out var c)?c:data.GetValueOrDefault(a);return b is not null&&b.Length==n?new("success",b.ToArray(),null,null):new("unavailable",[],null,null);}public ValueTask<string?> RevalidateAsync(CancellationToken c)=>ValueTask.FromResult<string?>(null);public ValueTask DisposeAsync()=>ValueTask.CompletedTask;}
}
