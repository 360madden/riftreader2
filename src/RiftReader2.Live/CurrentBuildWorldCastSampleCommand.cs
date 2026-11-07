using System.Globalization;
using System.Text.Json;
using RiftReader2.Infrastructure;
namespace RiftReader2.Live;
internal static class CurrentBuildWorldCastSampleCommand
{
    internal static async Task<int> RunAsync(IReadOnlyDictionary<string,string> options, TextWriter output,CancellationToken cancellationToken)
    {
        if(!options.TryGetValue("--pid",out var p)||!int.TryParse(p,NumberStyles.None,CultureInfo.InvariantCulture,out var pid)||pid<=0||!options.TryGetValue("--start-ticks",out var t)||!long.TryParse(t,NumberStyles.None,CultureInfo.InvariantCulture,out var ticks)||ticks<=0||!options.TryGetValue("--output",out var path)||string.IsNullOrWhiteSpace(path)) throw new ArgumentException("--pid, --start-ticks and --output required.");
        int Parse(string key,int fallback,int min,int max) {if(!options.TryGetValue(key,out var v))return fallback; if(!int.TryParse(v,NumberStyles.None,CultureInfo.InvariantCulture,out var n)||n<min||n>max)throw new ArgumentException($"{key} must be {min}..{max}.");return n;}
        var samples=Parse("--samples",10,1,30);var interval=Parse("--interval-ms",100,0,500); if((samples-1)*interval>15000)throw new ArgumentException("Sampling delays exceed 15 seconds.");
        if(File.Exists(path))throw new IOException("Output exists; never overwrite an earlier observation.");
        await using var session=await WindowsNativeMemorySession.OpenAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,cancellationToken);
        var observations=new List<WorldCastObservation>(); ulong startBucket=0;
        for(var i=0;i<samples;i++)
        {
            cancellationToken.ThrowIfCancellationRequested(); var observation=CurrentBuildWorldCastCandidateReader.Read(session,startBucket); observations.Add(observation);
            startBucket=(observation.StartBucket+(ulong)observation.BucketsExamined)%observation.BucketCount;
            if(await session.RevalidateAsync(cancellationToken) is not null)throw new InvalidDataException("Process identity invalidated; no report published.");
            if(i+1<samples)await Task.Delay(interval,cancellationToken);
        }
        cancellationToken.ThrowIfCancellationRequested();
        var report=new {schemaVersion=1,contractVersion="native-current-world-casts-candidate-samples/1",status="complete",qualification="candidate-only; bounded world subset, cast semantics and freshness unverified",observations,limitations=new[]{"On-disk executable SHA does not hash loaded module bytes.","Sequential reads and byte anchors are not atomic and cannot exclude ABA.","The bounded unit scan is not a complete world inventory or proof of casting.","No getter, initialization, refcount or memory write is performed."}};
        await JsonReportWriter.WriteNewAsync(path,report,cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(new {recordType="native-current-world-casts-candidate-summary/1",report.status,report.qualification,completedSamples=observations.Count,output=Path.GetFullPath(path)},new JsonSerializerOptions(JsonFormat.Options){WriteIndented=false}));return 0;
    }
}
