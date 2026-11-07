using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildAbilityVariantsCandidateReaderTests
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
    [Fact] public void ReadsVerifiedVariantKeysAndNulls(){var s=Fixture();ConfigureVariants(s);var v=ReadVariants(s).Records[0].RawVariants!;Assert.Equal("raw-candidates",v.Status);Assert.Equal(2,v.Entries!.Count);Assert.Equal(987U,v.Entries[0].Key);Assert.Equal("null",v.Entries[1].Status);}
    [Fact] public void RejectsChangedVariantKeyAndPreservesUnknown(){var s=Fixture();ConfigureVariants(s);s.Change(C+0x3018,BitConverter.GetBytes(988U));Assert.Throws<InvalidDataException>(()=>ReadVariants(s));s=Fixture();ConfigureVariants(s);s.Put(C+0x3000,Q(M+0x1000));s.Put(M+0x1040,Q(M+0x2000));Assert.Equal("unknown-type",ReadVariants(s).Records[0].RawVariants!.Entries![0].Status);}
    static CurrentBuildAbilityRecordsObservation ReadVariants(Fake s)=>CurrentBuildAbilityRecordsCandidateReader.Read(s,[1],()=>[Epoch],false,false,false,true);
    static void ConfigureVariants(Fake s){s.Put(R+0x20,BitConverter.GetBytes(41));var h=new byte[16];Q(C+0x1000).CopyTo(h,0);Q(C+0x1008).CopyTo(h,8);s.Put(R+0x5F0,h);s.Put(C+0x1000,Q(C+0x2000));s.Put(C+0x2000,Q(M+0x283E6C0));s.Put(M+0x283E700,Q(M+0x17BD530));s.Put(M+0x342C310,Q(M+0x2845BD0));s.Put(M+0x2845BD8,Q(M+0x17DBA60));h=new byte[16];Q(C+0x4000).CopyTo(h,0);Q(C+0x4010).CopyTo(h,8);s.Put(C+0x2018,h);s.Put(C+0x4000,Q(C+0x3000));s.Put(C+0x4008,Q(0));s.Put(C+0x3000,Q(M+0x2CDE8F0));s.Put(M+0x2CDE930,Q(M+0x229B4B0));s.Put(M+0x359F390,Q(M+0x2CE8820));s.Put(M+0x2CE8828,Q(M+0x22C1850));s.Put(C+0x3018,BitConverter.GetBytes(987U));}
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
