using System.Buffers.Binary;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;
namespace RiftReader2.Live;
internal sealed record BuffStackSeed(string Status,uint? StateRaw=null,ulong? TimerAddress=null,ulong? TimerVtableRva=null,ulong? TimerSlot40Rva=null,ulong? ReferenceAddress=null,int? ReferenceGate=null,int? TimerValue=null,uint? GetterRawBits=null);
internal sealed record BuffDetailSeedRow(ulong NodeAddress,ulong ObjectAddress,ulong? RawCasterKey,string? CasterUnitIdCandidate,BuffStackSeed Stack);
internal sealed record BuffDetailSeedObservation(object Identity,DateTimeOffset StartedAtUtc,DateTimeOffset CompletedAtUtc,ulong UnitKey,ulong Context,ulong Sentinel,IReadOnlyList<BuffDetailSeedRow> Rows)
{public string Qualification=>"raw caster and stack getter candidates; visibility, grouping, API correspondence, freshness and restart unverified";}
internal static class CurrentBuildBuffDetailsSampleCommand
{
 internal static async Task<int> RunAsync(IReadOnlyDictionary<string,string> options,TextWriter output,CancellationToken ct)
 {
  if(!options.TryGetValue("--pid",out var p)||!int.TryParse(p,NumberStyles.None,CultureInfo.InvariantCulture,out var pid)||pid<=0||!options.TryGetValue("--start-ticks",out var t)||!long.TryParse(t,NumberStyles.None,CultureInfo.InvariantCulture,out var ticks)||ticks<=0||!options.TryGetValue("--output",out var path)||string.IsNullOrWhiteSpace(path))throw new ArgumentException("--pid, --start-ticks and --output required.");
  if(File.Exists(path))throw new IOException("Output exists.");await using var session=await WindowsNativeMemorySession.OpenAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,ct);ct.ThrowIfCancellationRequested();var observation=Read(session);if(await session.RevalidateAsync(ct) is not null)throw new InvalidDataException("Process invalidated.");ct.ThrowIfCancellationRequested();await JsonReportWriter.WriteNewAsync(path,new{schemaVersion=1,contractVersion="native-current-buff-details-candidate/1",status="complete",observation,limitations=new[]{"Caster and stack are raw getter candidates; visibility and grouping are unverified.","Sentinel does not establish API stack omission or an aggregate count.","Sequential reads cannot exclude ABA; loaded module bytes are not independently hashed.","No game getter, initializer, refcount or memory write is performed."}},ct);await output.WriteLineAsync(JsonSerializer.Serialize(new{recordType="native-current-buff-details-summary/1",output=Path.GetFullPath(path)},new JsonSerializerOptions(JsonFormat.Options){WriteIndented=false}));return 0;
 }
 internal static BuffDetailSeedObservation Read(IReadOnlyNativeMemorySession session)=>Read(session,s=>CurrentBuildBuffSeedCandidateReader.Read(s));
 internal static BuffDetailSeedObservation Read(IReadOnlyNativeMemorySession session,Func<IReadOnlyNativeMemorySession,CurrentBuildBuffSeedObservation> seed)
 {
  var start=DateTimeOffset.UtcNow;var id=session.Identity;var before=seed(session);if(before.Identity!=id)throw new InvalidDataException("Buff seed identity mismatch.");
  var anchors=new Dictionary<(ulong,int),byte[]>();int budget=0;byte[] Take(ulong a,int n,bool save=true){budget=checked(budget+n);if(budget>2*1024*1024)throw new InvalidDataException("Buff detail budget exceeded.");var b=CurrentBuildPlayerLookup.Exact(session,a,n);if(save){if(anchors.TryGetValue((a,n),out var old)&&!old.AsSpan().SequenceEqual(b))throw new InvalidDataException("Buff detail changed.");anchors[(a,n)]=b.ToArray();}return b;}
  ulong Ptr(ulong v,int n=8)=>CurrentBuildPlayerLookup.Pointer(v,n);ulong Q(ulong a)=>BinaryPrimitives.ReadUInt64LittleEndian(Take(a,8));uint D(ulong a)=>BinaryPrimitives.ReadUInt32LittleEndian(Take(a,4));
  bool Type(ulong a,ulong vt,ulong getter,ulong descriptor,ulong descVt,ulong descGetter)=>Q(a)==id.ModuleBaseAddress+vt&&Q(id.ModuleBaseAddress+vt+0x40)==id.ModuleBaseAddress+getter&&Q(id.ModuleBaseAddress+descriptor)==id.ModuleBaseAddress+descVt&&Q(id.ModuleBaseAddress+descVt+8)==id.ModuleBaseAddress+descGetter;
  var rows=new List<BuffDetailSeedRow>();
  foreach(var node in before.Nodes)
  {
   ulong? caster=null;BuffStackSeed stack=new("unavailable");
   try
   {
    var obj=Ptr(node.Object,0x70);caster=Q(obj+0x28);var state=Ptr(Q(obj+0x20),0x8C);var stateRaw=D(state+0x88);
    if(stateRaw==5)stack=new("sentinel",stateRaw,GetterRawBits:0xAB9AACF9);
    else
    {
     var timer=Ptr(Q(obj+0x68),0x20);var vt=Q(timer);ulong? vtRva=vt>=id.ModuleBaseAddress&&vt<id.ModuleBaseAddress+id.ModuleSize?vt-id.ModuleBaseAddress:null;ulong? method=null;
     if(vtRva.HasValue&&vtRva.Value<=id.ModuleSize-0x48){var m=Q(vt+0x40);if(m>=id.ModuleBaseAddress&&m<id.ModuleBaseAddress+id.ModuleSize)method=m-id.ModuleBaseAddress;}
     stack=new("unsupported-timer-type",stateRaw,timer,vtRva,method);
     if(vtRva==0x26BCE50&&method==0x72B4C0)stack=stack with{Status="sentinel",GetterRawBits=0xAB9AACF9};
     else if((vtRva==0x26BC950&&method==0x72B610)||(vtRva==0x26BC9A0&&method==0x72B660))
     {
      var reference=Q(timer+0x10);stack=stack with{Status="unverified-reference-type",ReferenceAddress=reference};
      if(reference!=0)
      {
       Ptr(reference,0x48);var first=vtRva==0x26BC950;
       if(first?Type(reference,0x286CDC8,0x18254A0,0x343B3C0,0x2876CA8,0x184B530):Type(reference,0x2CC0618,0x225CA20,0x3598870,0x2CD1DE8,0x22892E0))
       {
        var gate=BinaryPrimitives.ReadInt32LittleEndian(Take(reference+(first?0x30UL:0x44UL),4));
        if(gate<2)stack=stack with{Status="sentinel",ReferenceGate=gate,GetterRawBits=0xAB9AACF9};
        else{var value=BinaryPrimitives.ReadInt32LittleEndian(Take(timer+0x1C,4));stack=stack with{Status="raw-getter-candidate",ReferenceGate=gate,TimerValue=value,GetterRawBits=unchecked((uint)value)};}
       }
      }
     }
    }
   }
   catch(InvalidDataException){if(budget>2*1024*1024)throw;stack=new("unavailable");}
   rows.Add(new(node.Address,node.Object,caster,caster.HasValue?$"u{caster.Value:X16}":null,stack));
  }
  foreach(var a in anchors)CurrentBuildPlayerLookup.RequireSame(Take(a.Key.Item1,a.Key.Item2,false),a.Value);var after=seed(session);
  if(after.Identity!=id||before.UnitKey!=after.UnitKey||before.Context!=after.Context||before.Sentinel!=after.Sentinel||!before.Nodes.SequenceEqual(after.Nodes)||session.Identity!=id)throw new InvalidDataException("Buff list or process changed.");
  return new(id,start,DateTimeOffset.UtcNow,before.UnitKey,before.Context,before.Sentinel,rows);
 }
}
