using System.Buffers.Binary;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
namespace RiftReader2.Live;

internal sealed record ExperienceValuesObservation(NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc,
    ExperienceSeedObservation Seed, string ValueStatus, int? Level = null, int? Limit = null,
    int? Mode = null, long? Baseline = null, int? Needed = null, long? AccumulatedCandidate = null, string RestedStatus = "unavailable", byte? RestedFlag = null, uint? RestedRawBits = null, long? RestedCandidate = null)
{
    public string Qualification => "candidate-only; API agreement, freshness and restart unverified";
}
internal static class CurrentBuildExperienceValuesCandidateReader
{
    internal static ExperienceValuesObservation Read(IReadOnlyNativeMemorySession session) =>
        Read(session,CurrentBuildExperienceSeedCandidateReader.Read,()=>WindowsThreadTlsSnapshot.Capture(session.Identity.ProcessId));
    internal static ExperienceValuesObservation Read(IReadOnlyNativeMemorySession session,
        Func<IReadOnlyNativeMemorySession,ExperienceSeedObservation> seedReader,Func<IReadOnlyList<NativeThreadEpoch>> threads)
    {
        var start=DateTimeOffset.UtcNow;var id=session.Identity;var seed=seedReader(session);
        if(seed.Identity!=id || id.ProcessId<=0 || id.ProcessStartUtcTicks<=0 || id.ModuleSize<0x3590000 ||
            !string.Equals(id.ExecutableSha256,CurrentBuildPlayerLookup.GameSha256,StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Invalid experience identity.");
        var anchors=new Dictionary<(ulong,int),byte[]>();var budget=0;
        byte[] ReadBytes(ulong a,int n,bool remember=true)
        {
            budget=checked(budget+n);if(budget>2*1024*1024)throw new InvalidDataException("Experience value budget exceeded.");
            var b=CurrentBuildPlayerLookup.Exact(session,a,n);
            if(remember){if(anchors.TryGetValue((a,n),out var old)&&!old.AsSpan().SequenceEqual(b))throw new InvalidDataException("Experience data changed.");anchors[(a,n)]=b.ToArray();}return b;
        }
        ulong Q(ulong a)=>BinaryPrimitives.ReadUInt64LittleEndian(ReadBytes(a,8));
        int I(ulong a)=>BinaryPrimitives.ReadInt32LittleEndian(ReadBytes(a,4));
        ulong Ptr(ulong v,int n=8)=>CurrentBuildPlayerLookup.Pointer(v,n);
        bool Type(ulong a,ulong vt,ulong getter,ulong desc,ulong descVt,ulong descGetter)=>
            Q(a)==id.ModuleBaseAddress+vt && Q(id.ModuleBaseAddress+vt+0x40)==id.ModuleBaseAddress+getter &&
            Q(id.ModuleBaseAddress+desc)==id.ModuleBaseAddress+descVt && Q(id.ModuleBaseAddress+descVt+8)==id.ModuleBaseAddress+descGetter;
        string status="seed-unavailable";int? level=null,limit=null,mode=null,needed=null;long? baseline=null,accumulated=null;
        IReadOnlyList<NativeThreadEpoch>? epochs=null;
        string restedStatus="unavailable";byte? restedFlag=null;uint? restedBits=null;long? rested=null;
        if(seed.Branch=="indexed-raw-candidate" && seed.Selected is not null &&
           !Type(Ptr(seed.Owner,0x168),0x2A46738,0x1C48CC0,0x34C9670,0x2A4B760,0x1C84130))
            status="owner-type-unavailable";
        else if(seed.Branch=="indexed-raw-candidate" && seed.Selected is not null)
        {
            var selected=seed.Selected;var r=Ptr(selected.Address,0x28);
            if(!Type(r,0x2BD4388,0x201A050,0x3548720,0x2BE0EF8,0x20482A0))status="progress-type-unavailable";
            else
            {
                var raw=BinaryPrimitives.ReadInt64LittleEndian(ReadBytes(r+0x18,8));var l=I(r+0x24);level=l;
                var restedRoot=Q(id.ModuleBaseAddress+0x33E0B08);
                if(restedRoot!=0)
                {
                    restedRoot=Ptr(restedRoot,0x88);restedFlag=ReadBytes(restedRoot+0x87,1)[0];
                    restedBits=BinaryPrimitives.ReadUInt32LittleEndian(ReadBytes(restedFlag!=0?r+0x20:seed.Owner+0x138,4));
                    var restedFloat=BitConverter.Int32BitsToSingle(unchecked((int)restedBits.Value));
                    if(float.IsFinite(restedFloat) && (double)restedFloat >= -9223372036854775808.0 && (double)restedFloat < 9223372036854775808.0)
                    {rested=(long)restedFloat;restedStatus="raw-rested-candidate";}
                    else restedStatus="nonfinite-or-out-of-range";
                }
                else restedStatus="provider-uninitialized";
                if(raw!=selected.RawInt64_18 || unchecked((uint)l)!=selected.RawDword24)throw new InvalidDataException("Progress seed changed.");
                var g=Ptr(Q(id.ModuleBaseAddress+0x33E0AB0),0x880);var cb=Q(g+0x870);var ce=Q(g+0x878);
                if(ce<cb || (ce-cb)%8!=0 || (ce-cb)/8>4096 || cb==0 || ce==cb)throw new InvalidDataException("Cap vector unavailable.");
                Ptr(cb,checked((int)(ce-cb)));var count=(ce-cb)/8;
                var mi=unchecked((int)seed.RawDword160);var which=mi<0?0UL:(ulong)mi>=count?count-1:(ulong)mi;
                var cap=Ptr(Q(checked(cb+which*8)),0x38);
                if(!Type(cap,0x2BA1608,0x1FA64F0,0x3538760,0x2BADC68,0x1FCBC00))status="cap-type-unavailable";
                else
                {
                    var capValue=I(cap+0x34);var vb=Q(id.ModuleBaseAddress+0x33E0C98);var ve=Q(id.ModuleBaseAddress+0x33E0CA0);
                    if(ve<vb || (ve-vb)%8!=0 || (ve-vb)/8>65536 || (vb==0)!=(ve==0))throw new InvalidDataException("Invalid baseline vector.");
                    var n=(ve-vb)/8;if(n>0)Ptr(vb,checked((int)(n*8)));
                    var lim=n==0?capValue:Math.Min(capValue,checked((int)n-1));limit=lim;
                    if(l>=lim)status="native-minus-one-level-cap";
                    else if(l<1 || (ulong)l>=n)status="baseline-unavailable";
                    else
                    {
                        baseline=BinaryPrimitives.ReadInt64LittleEndian(ReadBytes(checked(vb+(ulong)l*8),8));
                        var provider=Q(id.ModuleBaseAddress+0x33E0D88);
                        if(provider==0)status="provider-uninitialized";
                        else
                        {
                            provider=Ptr(provider,0x42);var selector=BinaryPrimitives.ReadUInt16LittleEndian(ReadBytes(provider+0x40,2));
                            var wrapper=Ptr(Q(id.ModuleBaseAddress+0x3372C18));var owner=Ptr(Q(wrapper),0x278);
                            var tls=BinaryPrimitives.ReadUInt32LittleEndian(ReadBytes(owner+0x274,4));if(tls>1087)throw new InvalidDataException("Invalid TLS index.");
                            epochs=threads();if(epochs.Count is <1 or >256 || epochs.Select(t=>t.Id).Distinct().Count()!=epochs.Count || epochs.Select(t=>t.Teb).Distinct().Count()!=epochs.Count)throw new InvalidDataException("Invalid thread set.");
                            ulong? collection=null;
                            foreach(var t in epochs)
                            {
                                Ptr(t.Teb,0x1788);var identity=ReadBytes(t.Teb+0x30,32);
                                if(t.Id<=0||t.Created<=0||BinaryPrimitives.ReadUInt64LittleEndian(identity)!=t.Teb||BinaryPrimitives.ReadUInt64LittleEndian(identity.AsSpan(16))!=(ulong)id.ProcessId||BinaryPrimitives.ReadUInt64LittleEndian(identity.AsSpan(24))!=(ulong)t.Id)throw new InvalidDataException("TEB identity mismatch.");
                                ulong value;if(tls<64)value=Q(t.Teb+0x1480+tls*8UL);else {var expansion=Q(t.Teb+0x1780);value=expansion==0?0:Q(checked(Ptr(expansion)+(tls-64)*8UL));}
                                var c=value==0?checked(owner+0x200):Ptr(value);if(collection.HasValue&&collection!=c)throw new InvalidDataException("TLS collections disagree.");collection=c;
                            }
                            var header=ReadBytes(checked(collection!.Value+0x20),32);var bucket=Ptr(BinaryPrimitives.ReadUInt64LittleEndian(header));var stride=BinaryPrimitives.ReadUInt64LittleEndian(header.AsSpan(8));var countBuckets=BinaryPrimitives.ReadUInt64LittleEndian(header.AsSpan(16));
                            if(stride!=24||countBuckets is <1 or >4096)throw new InvalidDataException("Invalid cache header.");Ptr(bucket,checked((int)(countBuckets*24)));
                            var address=checked(bucket+CurrentBuildAbilityRecordsCandidateReader.Hash(CurrentBuildAbilityRecordsCandidateReader.Hash(unchecked((uint)l)))%countBuckets*24);
                            var seen=new HashSet<ulong>();bool head=true;ulong record=0;
                            for(var i=0;i<=128;i++)
                            {
                                Ptr(address,24);if(!seen.Add(address))throw new InvalidDataException("Cache cycle.");var node=ReadBytes(address,24);var link=BinaryPrimitives.ReadUInt64LittleEndian(node);
                                if((!head||(link&1)==0)&&BinaryPrimitives.ReadUInt16LittleEndian(node.AsSpan(8))==selector&&BinaryPrimitives.ReadUInt32LittleEndian(node.AsSpan(12))==unchecked((uint)l))
                                {var holder=BinaryPrimitives.ReadUInt64LittleEndian(node.AsSpan(16));if(holder!=0)record=Q(checked(Ptr(holder,0x20)+0x18));break;}
                                var next=link&~1UL;if(next==0)break;if(i==128)throw new InvalidDataException("Cache chain budget exceeded.");address=next;head=false;
                            }
                            if(record==0)status="cold-cache-or-null";
                            else if(!Type(Ptr(record,0x2C),0x2C04110,0x208AF40,0x3557780,0x2C0DC80,0x20AFB30))status="needed-type-unavailable";
                            else
                            {
                                var m=I(id.ModuleBaseAddress+0x2F95CF4);mode=m;var offset=m switch {1=>0x28UL,2=>0x20UL,3=>0x18UL,4=>0x1CUL,_=>0x24UL};var nval=I(record+offset);needed=nval;
                                if(nval==-1)status="native-minus-one-needed";
                                else {try{accumulated=checked(checked(raw-baseline.Value)+nval);status="raw-values-candidate";}catch(OverflowException){status="arithmetic-overflow";}}
                            }
                        }
                    }
                }
            }
        }
        foreach(var a in anchors)CurrentBuildPlayerLookup.RequireSame(ReadBytes(a.Key.Item1,a.Key.Item2,false),a.Value);
        var after=seedReader(session);
        static string Stable(ExperienceSeedObservation x)=>JsonSerializer.Serialize(new{x.Identity,x.UnitKey,x.Entity,x.Component,x.Owner,x.OwnerVtableRva,x.OwnerGetterRva,x.Index,x.RawDword160,x.RawByte24F,x.VectorBegin,x.VectorEnd,x.References,x.Branch,x.Selected,x.Special7D8,x.Special7E0});
        if(Stable(seed)!=Stable(after)||session.Identity!=id)throw new InvalidDataException("Experience seed changed.");
        if(epochs is not null&&!epochs.OrderBy(t=>t.Id).SequenceEqual(threads().OrderBy(t=>t.Id)))throw new InvalidDataException("Thread epochs changed.");
        if(session.Identity!=id)throw new InvalidDataException("Experience process epoch changed.");
        return new(id,start,DateTimeOffset.UtcNow,seed,status,level,limit,mode,baseline,needed,accumulated,restedStatus,restedFlag,restedBits,rested);
    }
}
internal static class CurrentBuildExperienceValuesSampleCommand
{
    internal static Task<int> RunAsync(IReadOnlyDictionary<string,string> options,TextWriter output,CancellationToken ct) =>
        RunAsync(options,output,ct,
            static async (pid,ticks,token) => await NativeReadFileLease.AcquireAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,TimeSpan.FromSeconds(1),token),
            static async (pid,ticks,token) => await WindowsNativeMemorySession.OpenAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,token),
            CurrentBuildExperienceValuesCandidateReader.Read);

    // Explicit offline test seam; production always supplies the real lease.
    internal static async Task<int> RunAsync(IReadOnlyDictionary<string,string> options,TextWriter output,CancellationToken ct,
        Func<int,long,CancellationToken,Task<IAsyncDisposable>> acquireLease,
        Func<int,long,CancellationToken,Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession,ExperienceValuesObservation> read)
    {
        if(!options.TryGetValue("--pid",out var p)||!int.TryParse(p,NumberStyles.None,CultureInfo.InvariantCulture,out var pid)||pid<=0||!options.TryGetValue("--start-ticks",out var t)||!long.TryParse(t,NumberStyles.None,CultureInfo.InvariantCulture,out var ticks)||ticks<=0||!options.TryGetValue("--output",out var path)||string.IsNullOrWhiteSpace(path))throw new ArgumentException("--pid, --start-ticks and --output required.");
        if(File.Exists(path))throw new IOException("Output exists.");await using var lease=await acquireLease(pid,ticks,ct);ct.ThrowIfCancellationRequested();await using var session=await open(pid,ticks,ct);ct.ThrowIfCancellationRequested();
        var observation=read(session);if(await session.RevalidateAsync(ct) is not null)throw new InvalidDataException("Process identity invalidated.");ct.ThrowIfCancellationRequested();
        var report=new{schemaVersion=1,contractVersion="native-current-experience-values-candidate/1",status="complete",observation,limitations=new[]{"Candidate values lack API agreement, freshness and restart proof.","Sequential reads are non-atomic and cannot exclude ABA.","Executable hash identifies on-disk bytes, not independently hashed loaded pages.","No getter, initializer, refcount operation or memory write."}};
        await JsonReportWriter.WriteNewAsync(path,report,ct);await output.WriteLineAsync(JsonSerializer.Serialize(new{status="complete",observation.ValueStatus,output=Path.GetFullPath(path)},new JsonSerializerOptions(JsonFormat.Options){WriteIndented=false}));return 0;
    }
}
