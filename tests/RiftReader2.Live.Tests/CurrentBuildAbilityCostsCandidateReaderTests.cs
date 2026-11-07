using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildAbilityCostsCandidateReaderTests
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
    [Fact] public void EmptyAndNullCostVector() { var s=Fixture(); s.Put(R+0x6D0,new byte[16]); var r=ReadCosts(s).Records[0]; Assert.Equal("empty",r.RawCosts!.Status); }
    [Fact] public void KnownManaCostIsRawAndAnchored() { var s=Fixture(); ConfigureCost(s); var c=Assert.Single(ReadCosts(s).Records[0].RawCosts!.Children); Assert.Equal("mana-raw-candidate",c.Status); Assert.Equal(12.5f,c.Float18); Assert.Equal((byte)1,c.Flag1C); }
    [Fact] public void UnknownAndNullChildrenStayUnclassified() { var s=Fixture(); ConfigureCost(s); s.Put(C+0x1000,Q(0)); var c=Assert.Single(ReadCosts(s).Records[0].RawCosts!.Children); Assert.Equal("null",c.Status); s=Fixture(); ConfigureCost(s); s.Put(C+0x2000,Q(M+0x1000)); s.Put(M+0x1040,Q(M+0x2000)); c=Assert.Single(ReadCosts(s).Records[0].RawCosts!.Children); Assert.Equal("unknown-type",c.Status); Assert.Null(c.RawPayloadHex); }
    [Fact] public void ChangedVectorOrCostPayloadRejects() { var s=Fixture(); ConfigureCost(s); s.Change(R+0x6D0,new byte[16]); Assert.Throws<InvalidDataException>(()=>ReadCosts(s)); s=Fixture(); ConfigureCost(s); s.Change(C+0x2018,new byte[8]); Assert.Throws<InvalidDataException>(()=>ReadCosts(s)); }
    [Fact] public void CombinedManaChargeFingerprintAndPayload() { var s=Fixture(); ConfigureCombined(s); var c=Assert.Single(ReadCosts(s).Records[0].RawCosts!.Children); Assert.Equal("mana-charge-raw-candidate",c.Status); Assert.Equal(1.5f,c.Float1C); Assert.Equal(42,c.Int20); Assert.Equal(34,c.RawPayloadHex!.Length); Assert.Equal(77,c.Int24); Assert.Equal((byte)3,c.Flag28); }
    [Fact] public void CombinedWrongDescriptorRemainsUnverified() { var s=Fixture(); ConfigureCombined(s); s.Put(M+0x34B4B20,Q(0)); var c=Assert.Single(ReadCosts(s).Records[0].RawCosts!.Children); Assert.Equal("unverified-type",c.Status); Assert.Null(c.RawPayloadHex); }
    [Fact] public void EnergyFlagIsVerifiedAndAnchored() { var s=Fixture(); ConfigureCost(s); s.Put(C+0x2000,Q(M+0x2800660)); s.Put(M+0x28006A0,Q(M+0x171A0B0)); s.Put(M+0x3416390,Q(M+0x2801400)); s.Put(M+0x2801408,Q(M+0x1735BE0)); s.Put(C+0x2020,[7]); var c=Assert.Single(ReadCosts(s).Records[0].RawCosts!.Children); Assert.Equal("energy-raw-candidate",c.Status); Assert.Equal((byte)7,c.Flag20); Assert.Equal(16,c.RawPayloadHex!.Length); s=Fixture(); ConfigureCost(s); s.Put(C+0x2000,Q(M+0x2800660)); s.Put(M+0x28006A0,Q(M+0x171A0B0)); s.Put(M+0x3416390,Q(M+0x2801400)); s.Put(M+0x2801408,Q(M+0x1735BE0)); s.Put(C+0x2020,[7]); s.Change(C+0x2020,[8]); Assert.Throws<InvalidDataException>(()=>ReadCosts(s)); }
    [Fact] public void KnownUnhandledTypeKeepsNoPayload() { var s=Fixture(); ConfigureCost(s); s.Put(C+0x2000,Q(M+0x2CEF3D8)); s.Put(M+0x2CEF418,Q(M+0x22CCCF0)); s.Put(M+0x35A8330,Q(M+0x2D060C0)); s.Put(M+0x2D060C8,Q(M+0x2303720)); var c=Assert.Single(ReadCosts(s).Records[0].RawCosts!.Children); Assert.Equal("typed-unhandled-1e2d",c.Status); Assert.Null(c.RawPayloadHex); }
    static void ConfigureCombined(Fake s) { ConfigureCost(s); s.Put(C+0x2000,Q(M+0x29F7628)); s.Put(M+0x29F7668,Q(M+0x1BBF8B0)); s.Put(M+0x34B4B20,Q(M+0x2A04450)); s.Put(M+0x2A04458,Q(M+0x1BED910)); var raw=new byte[17]; BitConverter.GetBytes(1.5f).CopyTo(raw,4); BitConverter.GetBytes(42).CopyTo(raw,8); BitConverter.GetBytes(77).CopyTo(raw,12); raw[16]=3; s.Put(C+0x2018,raw); }
    static CurrentBuildAbilityRecordsObservation ReadCosts(Fake s)=>CurrentBuildAbilityRecordsCandidateReader.Read(s,[1],()=>[Epoch],true);
    static void ConfigureCost(Fake s) {var v=new byte[16];Q(C+0x1000).CopyTo(v,0);Q(C+0x1008).CopyTo(v,8);s.Put(R+0x6D0,v);s.Put(C+0x1000,Q(C+0x2000));s.Put(C+0x2000,Q(M+0x29DFB00));s.Put(M+0x29DFB40,Q(M+0x1B86480));s.Put(M+0x34AD5C0,Q(M+0x29E9220));s.Put(M+0x29E9228,Q(M+0x1BAD860));var raw=new byte[8];BitConverter.GetBytes(12.5f).CopyTo(raw,0);raw[4]=1;s.Put(C+0x2018,raw);}
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
