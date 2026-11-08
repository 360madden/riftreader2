using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class PlayerContextStatsNativeLeaseTests
{
    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public async Task RefusedLeaseNeverOpens(int kind)
    {
        var path=TempPath();var opened=false;
        await Assert.ThrowsAsync<TimeoutException>(()=>Run(kind,path,(_,_,_)=>throw new TimeoutException(),
            (_,_,_)=>{opened=true;throw new Exception();},default));
        Assert.False(opened);Assert.False(File.Exists(path));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public async Task SuccessHoldsLeaseThroughRevalidateAndDispose(int kind)
    {
        var path=TempPath();var lease=new Lease();var session=new Session(lease);
        try
        {
            Assert.Equal(0,await Run(kind,path,(_,_,_)=>Task.FromResult<IAsyncDisposable>(lease),
                (_,_,_)=>Task.FromResult<IReadOnlyNativeMemorySession>(session),default));
            Assert.True(session.Revalidated && session.Disposed && lease.Disposed);
            Assert.True(File.Exists(path));
        }
        finally { if(File.Exists(path))File.Delete(path); }
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public async Task CancellationAfterLeaseReleasesWithoutOpening(int kind)
    {
        var path=TempPath();var lease=new Lease();var opened=false;using var cts=new CancellationTokenSource();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(()=>Run(kind,path,
            (_,_,_)=>{cts.Cancel();return Task.FromResult<IAsyncDisposable>(lease);},
            (_,_,_)=>{opened=true;throw new Exception();},cts.Token));
        Assert.False(opened);Assert.True(lease.Disposed);Assert.False(File.Exists(path));
    }

    static string TempPath()=>Path.Combine(Path.GetTempPath(),Guid.NewGuid().ToString("N")+".json");
    static Task<int> Run(int kind,string path,Func<int,long,CancellationToken,Task<IAsyncDisposable>> acquire,
        Func<int,long,CancellationToken,Task<IReadOnlyNativeMemorySession>> open,CancellationToken token)
    {
        var options=new Dictionary<string,string>{{"--pid","123"},{"--start-ticks","456"},{"--output",path}};
        return kind switch
        {
            0=>CurrentBuildPlayerContextSampleCommand.RunAsync(options,TextWriter.Null,token,acquire,open,
                s=>new(s.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,1,1,1,1,1,0,"none",null,null,1,"candidate",0,"candidate",false)),
            1=>CurrentBuildTargetTemplateNameSampleCommand.RunAsync(options,TextWriter.Null,token,acquire,open,
                (s,_)=>new(s.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,1,2,3,4,5,6,7,0,0,"cache-miss")),
            _=>CurrentBuildStatsSampleCommand.RunAsync(options,TextWriter.Null,token,acquire,open,
                (s,_)=>new(s.Identity,DateTimeOffset.UtcNow,DateTimeOffset.UtcNow,1,1,1,1,1,1,[]))
        };
    }
    sealed class Lease:IAsyncDisposable
    {
        public bool Disposed {get;private set;}
        public ValueTask DisposeAsync(){Disposed=true;return ValueTask.CompletedTask;}
    }
    sealed class Session(Lease lease):IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity {get;}=new(123,456,@"C:\RIFT\rift_x64.exe",CurrentBuildPlayerLookup.GameSha256,0x140000000,0x4000000);
        public bool Revalidated {get;private set;}
        public bool Disposed {get;private set;}
        public NativeReadResult Read(ulong address,int length)=>throw new InvalidOperationException();
        public ValueTask<string?> RevalidateAsync(CancellationToken token){Assert.False(lease.Disposed);Revalidated=true;return ValueTask.FromResult<string?>(null);}
        public ValueTask DisposeAsync(){Assert.False(lease.Disposed);Disposed=true;return ValueTask.CompletedTask;}
    }
}
