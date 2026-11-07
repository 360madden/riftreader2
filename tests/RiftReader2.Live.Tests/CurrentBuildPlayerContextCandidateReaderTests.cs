using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildPlayerContextCandidateReaderTests
{
 const ulong M=0x140000000,E=0x20000000,H=0x20010000,O=0x20020000,S=0x20030000,T=0x20040000,C=0x20050000,State=0x20060000;
 [Fact] public void DirectFallbackAndLevelCombat(){var x=Fixture();var o=Read(x);Assert.Equal(42UL,o.TargetKeyCandidate);Assert.Equal("u000000000000002A",o.TargetUnitIdCandidate);Assert.Equal(65,o.RawLevel);Assert.True(o.CombatCandidate);Assert.Equal("numeric-getter-and-presentation-candidate",o.LevelStatus);}
 [Fact] public void AlternateLevelAndPresentationAreIndependent(){var x=Fixture();x.Put(E+0x19,[1]);x.Put(T+8,Q(C));x.Put(S+0x400,Q(0));Assert.Equal("alternate-component-unavailable",Read(x).LevelStatus);x=Fixture();x.Put(S+0x400,Q(0));Assert.Equal("numeric-getter-candidate-presentation-unqualified",Read(x).LevelStatus);}
 [Theory][InlineData(3,true)][InlineData(6,true)][InlineData(11,true)][InlineData(12,true)] public void EmptyOverrideFallback(int state,bool expected){var x=Selection(state);Assert.Equal(expected,Read(x).TargetKeyCandidate.HasValue);}
 [Fact] public void ActiveOrIncoherentReferenceIsUnavailable(){var x=Selection(3);var pair=new byte[16]; Q(1).CopyTo(pair,8); x.Put(C+0x280,pair);var o=Read(x);Assert.Null(o.TargetKeyCandidate);Assert.Equal(42UL,o.RawFallbackKey);}
 [Fact] public void NullStateIsUnavailable(){var x=Selection(3);x.Put(H+0x320,Q(0));Assert.Equal("guard-unreadable-or-invalid",Read(x).TargetStatus);}
 [Fact] public void CachedEntityOrPayloadChangeFails(){var x=Fixture();x.Put(S+0x3F8,Q(E+8));Assert.Throws<InvalidDataException>(()=>Read(x));x=Fixture();x.Change(O+0x100,BitConverter.GetBytes(66));Assert.Throws<InvalidDataException>(()=>Read(x));}
 static CurrentBuildPlayerContextObservation Read(Fake s)=>CurrentBuildPlayerContextCandidateReader.Read(s,_=>new(123,E,H,()=>{}));
 static Fake Selection(int state){var x=Fixture();x.Put(E+0x1A,[255]);x.Put(E+0x1B,[2]);x.Put(T+16,Q(C));x.Put(C+0x280,new byte[16]);x.Put(C+0x290,new byte[16]);x.Put(C+0x2A0,new byte[16]);x.Put(H+0x320,Q(State));x.Put(State+0x40,BitConverter.GetBytes(state));return x;}
 static Fake Fixture(){var x=new Fake();x.Put(M+0x33623E0,Q(S));x.Put(S+0x360,Q(123));x.Put(S+0x3F8,Q(E));x.Put(S+0x400,Q(H));x.Put(H+0x10,Q(E));x.Put(H+0x40,Q(O));x.Put(O,Q(M+0x2927448));x.Put(M+0x2927488,Q(M+0x19D21E0));x.Put(M+0x34731B0,Q(M+0x2929BD0));x.Put(M+0x2929BD8,Q(M+0x19F4D60));x.Put(O+0x20,Q(42));x.Put(O+0x100,BitConverter.GetBytes(65));x.Put(O+0x19D,[1]);x.Put(M+0x2F58270,BitConverter.GetBytes(1));x.Put(M+0x2F582E0,BitConverter.GetBytes(2));x.Put(M+0x2F57260,BitConverter.GetBytes(3));x.Put(E+0x19,[255]);x.Put(E+0x1A,[4]);x.Put(E+0x78,Q(T));return x;}
 static byte[] Q(ulong v){var b=new byte[8];BinaryPrimitives.WriteUInt64LittleEndian(b,v);return b;}
 sealed class Fake:IReadOnlyNativeMemorySession{readonly Dictionary<ulong,byte[]> data=[];readonly Dictionary<ulong,byte[]> changed=[];readonly HashSet<ulong> seen=[];public NativeProcessIdentity Identity{get;}=new(123,456,@"C:\RIFT\rift_x64.exe",CurrentBuildPlayerLookup.GameSha256,M,0x4000000);public void Put(ulong a,byte[] b)=>data[a]=b;public void Change(ulong a,byte[] b)=>changed[a]=b;public NativeReadResult Read(ulong a,int n){var b=!seen.Add(a)&&changed.TryGetValue(a,out var c)?c:data.GetValueOrDefault(a);return b is not null&&b.Length==n?new("success",b.ToArray(),null,null):new("unavailable",[],null,null);}public ValueTask<string?> RevalidateAsync(CancellationToken c)=>ValueTask.FromResult<string?>(null);public ValueTask DisposeAsync()=>ValueTask.CompletedTask;}
}
