using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live.Tests;
public sealed class CurrentBuildPlayerNameSampleCommandTests
{
 [Fact] public void IndependentSelfEntityMismatchRejectsBeforeNameReads()
 {
  var s=new Fake();var ctx=new CurrentBuildPlayerContextObservation(s.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,44,0x20000000,0x20010000,0x20020000,0,0,"x",null,null,0,"x",0,"x",false);
  Assert.Throws<InvalidDataException>(()=>CurrentBuildPlayerNameSampleCommand.Read(s,_=>ctx,_=>new(44,0x20000008,0x20010000,()=>{})));Assert.Equal(0,s.Reads);
 }
 sealed class Fake:IReadOnlyNativeMemorySession
 {
  public int Reads{get;private set;}public NativeProcessIdentity Identity{get;}=new(123,456,@"C:\RIFT\rift_x64.exe",CurrentBuildPlayerLookup.GameSha256,0x140000000,0x4000000);
  public NativeReadResult Read(ulong a,int n){Reads++;return new("unavailable",[],null,null);}public ValueTask<string?> RevalidateAsync(CancellationToken c)=>ValueTask.FromResult<string?>(null);public ValueTask DisposeAsync()=>ValueTask.CompletedTask;
 }
}
