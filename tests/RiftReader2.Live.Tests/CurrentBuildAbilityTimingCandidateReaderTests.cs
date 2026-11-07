using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildAbilityTimingCandidateReaderTests
{
    const ulong M=0x140000000, S=0x20000000, W=0x20010000, O=0x20020000, T=0x20030000, B=0x20040000, H=0x20050000, R=0x20060000, C=0x20070000;
    static readonly NativeThreadEpoch Epoch = new(77, 123, T);
    [Fact] public void ReadsTypedRecordAndFullId() { var s=Fixture(); var r=Read(s).Records[0]; Assert.Equal("type-verified-candidate",r.Status); Assert.Equal("A0000000100020D38",r.FullIdCandidate); Assert.Equal((byte)1,r.ApiListFilterNonzeroRaw); }
    [Fact] public void CacheMissIsExplicit() { var s=Fixture(); var node=new byte[24]; node[0]=1; s.Put(B,node); Assert.Equal("cache-miss",Read(s).Records[0].Status); }
    [Fact] public void WrongDescriptorIsUnverified() { var s=Fixture(); s.Put(M+0x344A6B0,Q(0)); Assert.Null(Read(s).Records[0].FullIdCandidate); Assert.Equal("unverified-type",Read(s).Records[0].Status); }
    [Fact] public void WrongPidInTebRejects() { var s=Fixture(); var teb=Identity(99); s.Put(T+0x30,teb); Assert.Throws<InvalidDataException>(()=>Read(s)); }
    [Fact] public void ThreadEpochChangeRejects() { var s=Fixture(); int n=0; Assert.Throws<InvalidDataException>(()=>CurrentBuildAbilityRecordsCandidateReader.Read(s,[1],()=> [++n == 1 ? Epoch : Epoch with { Created=124 }])); }
    [Fact] public void ReferenceChangeRejects() { var s=Fixture(); s.Change(R+0x8E0,Q(0)); Assert.Throws<InvalidDataException>(()=>Read(s)); }
    [Fact] public void HashUsesSignedInput() { Assert.Equal(16807U,CurrentBuildAbilityRecordsCandidateReader.Hash(1)); Assert.Equal(2147466840U,CurrentBuildAbilityRecordsCandidateReader.Hash(uint.MaxValue)); }
    [Fact] public void KnownTimingAndSeparateFallback() { var s=Fixture(); ConfigureTiming(s); var t=ReadTiming(s).Records[0].RawTiming!; Assert.Equal(1200,t.BaseCooldownMilliseconds); Assert.Equal("type-0650-raw-candidate",t.Primary.Status); Assert.Equal(1500,t.Primary.RawMilliseconds); Assert.Equal("empty",t.Secondary.Status); }
    [Fact] public void CorruptTypeAndChangedHeaderRejectOrStayUnverified() { var s=Fixture(); ConfigureTiming(s); s.Put(M+0x3448E50,Q(0)); Assert.Equal("unverified-type",ReadTiming(s).Records[0].RawTiming!.Primary.Status); s=Fixture(); ConfigureTiming(s); s.Change(R+0x5F0,new byte[16]); Assert.Throws<InvalidDataException>(()=>ReadTiming(s)); }
    [Fact] public void MultipleAndUnknownAreNotZero() { var s=Fixture(); ConfigureTiming(s); var h=new byte[16]; Q(C+0x1000).CopyTo(h,0);Q(C+0x1010).CopyTo(h,8);s.Put(R+0x5F0,h);var v=ReadTiming(s).Records[0].RawTiming!.Primary;Assert.Equal("not-single",v.Status);Assert.Null(v.RawMilliseconds); s=Fixture();ConfigureTiming(s);s.Put(C+0x2000,Q(M+0x1000));s.Put(M+0x1040,Q(M+0x2000));v=ReadTiming(s).Records[0].RawTiming!.Primary;Assert.Equal("unknown-type",v.Status);Assert.Null(v.RawMilliseconds); }
    [Fact] public void FixedTypeAndGateChange() { var s=Fixture(); ConfigureTiming(s); s.Put(C+0x2000,Q(M+0x2A40918)); s.Put(M+0x2A40958,Q(M+0x1C4C940)); s.Put(M+0x34C8FE0,Q(M+0x2A4AF80)); s.Put(M+0x2A4AF88,Q(M+0x1C83A10)); var t=ReadTiming(s).Records[0].RawTiming!; Assert.Equal(7,t.RawGate88); Assert.Equal("typed-0759-fixed-input",t.Primary.Status); Assert.Null(t.Primary.RawMilliseconds); s=Fixture(); ConfigureTiming(s); s.Change(R+0x88,BitConverter.GetBytes(8)); Assert.Throws<InvalidDataException>(()=>ReadTiming(s)); }
    static CurrentBuildAbilityRecordsObservation ReadTiming(Fake s)=>CurrentBuildAbilityRecordsCandidateReader.Read(s,[1],()=>[Epoch],false,true);
    static void ConfigureTiming(Fake s) { s.Put(R+0x88,BitConverter.GetBytes(7)); s.Put(R+0x94,BitConverter.GetBytes(1200));var h=new byte[16];Q(C+0x1000).CopyTo(h,0);Q(C+0x1008).CopyTo(h,8);s.Put(R+0x5F0,h);s.Put(R+0x8E8,new byte[16]);s.Put(C+0x1000,Q(C+0x2000));s.Put(C+0x2000,Q(M+0x28940E0));s.Put(M+0x2894120,Q(M+0x188FAC0));s.Put(M+0x3448E50,Q(M+0x28A7EF8));s.Put(M+0x28A7F00,Q(M+0x18C0680));s.Put(C+0x2020,BitConverter.GetBytes(1500)); }
    static CurrentBuildAbilityRecordsObservation Read(Fake s)=>CurrentBuildAbilityRecordsCandidateReader.Read(s,[1],()=>[Epoch]);
    static Fake Fixture()
    {
        var s=new Fake(); s.Put(M+0x33624C8,Q(S)); s.Put(S+0x40,new byte[]{83,0}); s.Put(M+0x3372C18,Q(W)); s.Put(W,Q(O)); s.Put(O+0x274,new byte[4]);
        s.Put(T+0x30,Identity(123)); s.Put(T+0x1480,Q(0)); var hdr=new byte[32]; Q(B).CopyTo(hdr,0); Q(24).CopyTo(hdr,8); Q(1).CopyTo(hdr,16); Q(1).CopyTo(hdr,24); s.Put(O+0x220,hdr);
        var node=new byte[24]; node[8]=83; node[12]=1; Q(H).CopyTo(node,16); s.Put(B,node); s.Put(H+0x18,Q(R));
        s.Put(R,Q(M+0x28A08C0)); s.Put(M+0x28A0900,Q(M+0x1899BF0)); s.Put(M+0x344A6B0,Q(M+0x28A9C38)); s.Put(M+0x28A9C40,Q(M+0x18C06C0));
        s.Put(R+0xC9,[1]); s.Put(R+0x8E0,Q(C)); s.Put(R+0x958,Q(0)); s.Put(C,Q(M+0x27F24F8)); s.Put(M+0x27F2538,Q(M+0x170C5D0)); s.Put(M+0x3417970,Q(M+0x2802E40)); s.Put(M+0x2802E48,Q(M+0x17361E0)); s.Put(C+0x18,BitConverter.GetBytes(8U)); return s;
    }
    static byte[] Identity(ulong pid) { var x=new byte[32]; Q(T).CopyTo(x,0); Q(pid).CopyTo(x,16); Q(77).CopyTo(x,24); return x; }
    static byte[] Q(ulong v) { var x=new byte[8]; BinaryPrimitives.WriteUInt64LittleEndian(x,v); return x; }
    sealed class Fake:IReadOnlyNativeMemorySession
    {
        readonly Dictionary<ulong,byte[]> data=[]; readonly Dictionary<ulong,byte[]> changed=[]; readonly HashSet<ulong> seen=[];
        public NativeProcessIdentity Identity {get;}=new(123,456,@"C:\RIFT\rift_x64.exe",CurrentBuildPlayerLookup.GameSha256,M,0x4000000);
        public void Put(ulong a,byte[] b)=>data[a]=b; public void Change(ulong a,byte[] b)=>changed[a]=b;
        public NativeReadResult Read(ulong a,int n) { var b=!seen.Add(a)&&changed.TryGetValue(a,out var c)?c:data.GetValueOrDefault(a); return b is not null&&b.Length==n?new("success",b.ToArray(),null,null):new("unavailable",[],null,null); }
        public ValueTask<string?> RevalidateAsync(CancellationToken c)=>ValueTask.FromResult<string?>(null); public ValueTask DisposeAsync()=>ValueTask.CompletedTask;
    }
}
