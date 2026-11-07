using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live;
internal sealed record WorldCastRow(ulong UnitKey, ulong Entity, ulong Component, ulong FirstChild, ulong FirstControl, uint? FirstRawId, ulong SecondChild, ulong SecondControl, uint? SecondRawId, uint RawDword2B8, string DurationStatus, int? SelectedBranch, float? Begin, ulong? DurationObject, ulong? Vtable, ulong? GetterRva, float? Duration, ulong? DurationInput = null, int? DurationMillisecondsRaw = null);
internal sealed record WorldCastObservation(NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc, int Examined, int Unavailable, int BucketsExamined, ulong StartBucket, ulong BucketCount, bool UnitLimitReached, float ClockBefore, float ClockAfter, IReadOnlyList<WorldCastRow> Rows)
{
    public string Qualification => "candidate-only; incomplete-world, cast semantics and freshness unverified";
}
internal static class CurrentBuildWorldCastCandidateReader
{
    internal static WorldCastObservation Read(IReadOnlyNativeMemorySession session, ulong startBucket = 0)
    {
        var started=DateTimeOffset.UtcNow; var id=session.Identity;
        if (id.ProcessId<=0 || id.ProcessStartUtcTicks<=0 || id.ModuleSize<0x33DC2B8 || !string.Equals(id.ExecutableSha256,CurrentBuildPlayerLookup.GameSha256,StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("World casts require exact build and process identity.");
        var budget=0; byte[] ReadBytes(ulong a,int n) { budget=checked(budget+n); if(budget>2*1024*1024) throw new InvalidDataException("World cast read budget exceeded."); return CurrentBuildPlayerLookup.Exact(session,a,n); }
        var global=new List<(ulong,byte[])>(); byte[] G(ulong a,int n) {var b=ReadBytes(a,n); global.Add((a,b.ToArray())); return b;}
        ulong Ptr(ulong p,int n=8)=>CurrentBuildPlayerLookup.Pointer(p,n);
        var manager=Ptr(U64(G(id.ModuleBaseAddress+0x33624A8,8))); var table=Ptr(U64(G(manager+0x50,8)));
        var header=G(table,24); var buckets=Ptr(U64(header)); var stride=U64(header.AsSpan(8)); var count=U64(header.AsSpan(16));
        if(stride is <24 or >4096 || stride%8!=0 || count is <1 or >4096) throw new InvalidDataException("Invalid unit table header.");
        Ptr(buckets,checked((int)((count-1)*stride+24)));
        var selector=BinaryPrimitives.ReadInt32LittleEndian(G(id.ModuleBaseAddress+0x2F57260,4)); if(selector is <0 or >=0x60) throw new InvalidDataException("Invalid component selector.");
        var clock=Ptr(U64(G(id.ModuleBaseAddress+0x33DC2B0,8)),0x1C); var before=F(ReadBytes(clock+0x18,4)); if(!float.IsFinite(before)) throw new InvalidDataException("Invalid clock.");
        var rows=new List<WorldCastRow>(); int examined=0, unavailable=0, visitedBuckets=0; bool limited=false;
        startBucket %= count;
        for(ulong step=0;step<count;step++)
        {
            if(examined>=256) {limited=true;break;} visitedBuckets++; var i=(startBucket+step)%count; var address=checked(buckets+i*stride); var seen=new HashSet<ulong>(); var path=new List<(ulong,byte[])>(); bool head=true;
            for(int chain=0;chain<256;chain++)
            {
                if(examined>=256) {limited=true;break;}
                byte[] node;
                try { if(!seen.Add(address)) throw new InvalidDataException("Cyclic unit chain."); node=ReadBytes(address,24); path.Add((address,node.ToArray())); }
                catch(InvalidDataException) {if(budget>2*1024*1024) throw; unavailable++;break;}
                var link=U64(node); var occupied=!head || (link&1)==0;
                if(occupied)
                {
                    examined++;
                    try
                    {
                        var anchors=new List<(ulong,byte[])>(path); byte[] A(ulong a,int n) {var raw=ReadBytes(a,n);anchors.Add((a,raw.ToArray()));return raw;}
                        var key=U64(node.AsSpan(8)); if(key==0) throw new InvalidDataException("Invalid unit key.");
                        var entity=Ptr(U64(node.AsSpan(16)),128); var slot=A(entity+0x18+(ulong)selector,1)[0];
                        if(slot!=0xFF)
                        {
                            var components=Ptr(U64(A(entity+0x78,8))); var component=Ptr(U64(A(components+slot*8UL,8)),0x2BC);
                            var first=U64(A(component+0x280,8)); var firstControl=U64(A(component+0x288,8)); var second=U64(A(component+0x290,8)); var secondControl=U64(A(component+0x298,8));
                            uint? f=first==0?null:BinaryPrimitives.ReadUInt32LittleEndian(A(Ptr(first,12)+8,4)); uint? s=second==0?null:BinaryPrimitives.ReadUInt32LittleEndian(A(Ptr(second,12)+8,4));
                            var unknown=BinaryPrimitives.ReadUInt32LittleEndian(A(component+0x2B8,4));
                            string status=(f.GetValueOrDefault()!=0 || s.GetValueOrDefault()!=0)?"no-selected-child":"no-nonzero-child-id"; int? branch=null; float? begin=null,duration=null; ulong? obj=null,vt=null,getter=null;
                            ulong? durationInput = null;
                            int? durationMilliseconds = null;
                            var selected=firstControl!=0&&first!=0?first:secondControl!=0&&second!=0?second:0;
                            if(selected!=0 && (f.GetValueOrDefault()!=0 || s.GetValueOrDefault()!=0))
                            {
                                branch=selected==first&&firstControl!=0?0:1; var guardRaw=U64(A(selected+0x10,8));
                                if(guardRaw==0) status="guard-object-absent";
                                else if(A(Ptr(guardRaw,0xC9)+0xC8,1)[0]!=0) status="guard-set";
                                else
                                {
                                    var start=F(A(selected+(branch==0?0x30UL:0x34UL),4)); begin=float.IsFinite(start)?start:null;
                                    var rawObj=U64(A(selected+(branch==0?0x20UL:0x28UL),8)); obj=rawObj;
                                    if(rawObj==0) status="duration-object-absent";
                                    else
                                    {
                                        Ptr(rawObj,0x1C); var v=U64(A(rawObj,8)); vt=v;
                                        if(v>=id.ModuleBaseAddress && v<=id.ModuleBaseAddress+id.ModuleSize-16) {var target=U64(A(v+8,8)); getter=target>=id.ModuleBaseAddress&&target<id.ModuleBaseAddress+id.ModuleSize?target-id.ModuleBaseAddress:null;}
                                        if(v==id.ModuleBaseAddress+0x26AA0E0 && getter==0x09D680)
                                        {var d=F(A(rawObj+0x18,4)); duration=float.IsFinite(d)?d:null; status=duration.HasValue&&begin.HasValue?"raw-fingerprint-candidate":"nonfinite";}
                                        else if (branch == 0 && v == id.ModuleBaseAddress + 0x26AA020 && getter == 0x537270)
                                        {
                                            // This wrapper retains the selected runtime input at +0x10.
                                            // Its +8 backlink must identify the child from which we reached it.
                                            if (U64(A(rawObj + 8, 8)) != selected)
                                                status = "duration-wrapper-owner-mismatch";
                                            else
                                            {
                                                var input = U64(A(rawObj + 0x10, 8));
                                                durationInput = input;
                                                if (input == 0)
                                                    status = "duration-input-absent";
                                                else if (id.ModuleSize < 0x3448E58 ||
                                                    U64(A(Ptr(input, 0x24), 8)) != id.ModuleBaseAddress + 0x28940E0 ||
                                                    U64(A(id.ModuleBaseAddress + 0x2894120, 8)) != id.ModuleBaseAddress + 0x188FAC0 ||
                                                    U64(A(id.ModuleBaseAddress + 0x3448E50, 8)) != id.ModuleBaseAddress + 0x28A7EF8 ||
                                                    U64(A(id.ModuleBaseAddress + 0x28A7F00, 8)) != id.ModuleBaseAddress + 0x18C0680)
                                                    status = "duration-input-type-unverified";
                                                else
                                                {
                                                    var milliseconds = BinaryPrimitives.ReadInt32LittleEndian(A(input + 0x20, 4));
                                                    durationMilliseconds = milliseconds;
                                                    duration = (float)milliseconds * 0.001f;
                                                    status = !begin.HasValue ? "nonfinite" :
                                                        milliseconds > 0 ? "raw-fingerprint-candidate" : "nonpositive-primary-duration";
                                                }
                                            }
                                        }
                                        else status="unsupported-type";
                                    }
                                }
                            }
                            foreach(var anchor in anchors) CurrentBuildPlayerLookup.RequireSame(ReadBytes(anchor.Item1,anchor.Item2.Length),anchor.Item2);
                            if(first!=0 || second!=0 || unknown!=0) rows.Add(new(key,entity,component,first,firstControl,f,second,secondControl,s,unknown,status,branch,begin,obj,vt,getter,duration,durationInput,durationMilliseconds));
                        }
                        else foreach(var anchor in anchors) CurrentBuildPlayerLookup.RequireSame(ReadBytes(anchor.Item1,anchor.Item2.Length),anchor.Item2);
                    }
                    catch(InvalidDataException) {if(budget>2*1024*1024) throw; unavailable++;}
                }
                var next=link&~1UL; if(next==0) break;
                try {address=Ptr(next,24);} catch(InvalidDataException) {if(budget>2*1024*1024) throw; unavailable++;break;}
                if(chain==255) unavailable++;
                head=false;
            }
        }
        foreach(var a in global) CurrentBuildPlayerLookup.RequireSame(ReadBytes(a.Item1,a.Item2.Length),a.Item2);
        var after=F(ReadBytes(clock+0x18,4)); if(!float.IsFinite(after)||after<before||session.Identity!=id) throw new InvalidDataException("Clock or process identity invalidated.");
        return new(id,started,DateTimeOffset.UtcNow,examined,unavailable,visitedBuckets,startBucket,count,limited,before,after,rows);
    }
    private static ulong U64(ReadOnlySpan<byte> b)=>BinaryPrimitives.ReadUInt64LittleEndian(b);
    private static float F(ReadOnlySpan<byte> b)=>BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32LittleEndian(b));
}
