using System.Buffers.Binary;
using System.Globalization;
using System.Text;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;
namespace RiftReader2.Live;
internal sealed record PlayerDecorationObservation(object Identity,DateTimeOffset StartedAtUtc,DateTimeOffset CompletedAtUtc,ulong SelfKey,ulong SelfEntity,string Status,uint? RawDecorationKey,uint? RawManagerComparison,string? DecorationTextCandidate)
{public string Qualification=>"raw name-decoration candidate; shard identity, API name, freshness and restart unverified";}
internal static class CurrentBuildPlayerDecorationSampleCommand
{
 internal static async Task<int> RunAsync(IReadOnlyDictionary<string,string> options,TextWriter output,CancellationToken ct)
 {
  if(!options.TryGetValue("--pid",out var p)||!int.TryParse(p,NumberStyles.None,CultureInfo.InvariantCulture,out var pid)||pid<=0||!options.TryGetValue("--start-ticks",out var t)||!long.TryParse(t,NumberStyles.None,CultureInfo.InvariantCulture,out var ticks)||ticks<=0||!options.TryGetValue("--output",out var path)||string.IsNullOrWhiteSpace(path))throw new ArgumentException("--pid, --start-ticks and --output required.");
  if(File.Exists(path))throw new IOException("Output exists.");await using var session=await WindowsNativeMemorySession.OpenAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,ct);ct.ThrowIfCancellationRequested();var observation=Read(session);if(await session.RevalidateAsync(ct) is not null)throw new InvalidDataException("Process invalidated.");ct.ThrowIfCancellationRequested();await JsonReportWriter.WriteNewAsync(path,new{schemaVersion=1,contractVersion="native-current-player-decoration-candidate/1",status="complete",observation,limitations=new[]{"Decoration text is not a shard identity or verified API name.","Sequential reads cannot exclude ABA; loaded module bytes are not independently hashed.","No game getter, initializer, refcount or memory write is performed."}},ct);await output.WriteLineAsync(JsonSerializer.Serialize(new{recordType="native-current-player-decoration-summary/1",output=Path.GetFullPath(path)},new JsonSerializerOptions(JsonFormat.Options){WriteIndented=false}));return 0;
 }
 internal static PlayerDecorationObservation Read(IReadOnlyNativeMemorySession session)=>Read(session,CurrentBuildPlayerContextCandidateReader.Read,s=>{var l=CurrentBuildPlayerLookup.Resolve(s);return new(l.PlayerKey,l.EntityAddress,l.ResolveComponent(0x2F57850),l.VerifyUnchanged);});
 internal static PlayerDecorationObservation Read(IReadOnlyNativeMemorySession session,Func<IReadOnlyNativeMemorySession,CurrentBuildPlayerContextObservation> context,Func<IReadOnlyNativeMemorySession,PlayerContextOwner> resolve)
 {
  var started=DateTimeOffset.UtcNow;var id=session.Identity;var before=context(session);var lookup=resolve(session);
  if(before.Identity!=id||before.UnitKey!=lookup.Key||before.Entity!=lookup.Entity||before.HealthComponent!=lookup.Health)throw new InvalidDataException("Self identity mismatch.");
  var anchors=new Dictionary<(ulong,int),byte[]>();int budget=0;byte[] Take(ulong a,int n,bool save=true){budget=checked(budget+n);if(budget>2*1024*1024)throw new InvalidDataException("Decoration budget exceeded.");var b=CurrentBuildPlayerLookup.Exact(session,a,n);if(save){if(anchors.TryGetValue((a,n),out var old)&&!old.AsSpan().SequenceEqual(b))throw new InvalidDataException("Decoration bytes changed.");anchors[(a,n)]=b.ToArray();}return b;}
  ulong Ptr(ulong a,int n=8)=>CurrentBuildPlayerLookup.Pointer(a,n);ulong Q(ulong a)=>BinaryPrimitives.ReadUInt64LittleEndian(Take(a,8));uint D(ulong a)=>BinaryPrimitives.ReadUInt32LittleEndian(Take(a,4));
  var entity=Ptr(lookup.Entity,0x1D8);var health=Ptr(lookup.Health,0x48);var manager=Ptr(Q(id.ModuleBaseAddress+0x33623E0),0x4D0);
  if(Q(health+0x10)!=entity||Q(health+0x40)!=before.Owner||Q(manager+0x360)!=lookup.Key||Q(manager+0x3F8)!=entity)throw new InvalidDataException("Self owner mismatch.");
  string status="unavailable";uint? decoration=null,comparison=null;string? text=null;
  try
  {
   var selector=BinaryPrimitives.ReadInt32LittleEndian(Take(id.ModuleBaseAddress+0x2F582E0,4));if(selector is <0 or >=0x60)throw new InvalidDataException("Invalid selector.");var slot=Take(entity+0x18+(ulong)selector,1)[0];
   if(slot==0xFF)status="direct-component-absent";
   else
   {
    var table=Ptr(Q(entity+0x78));var component=Q(checked(table+slot*8UL));
    if(component==0)status="direct-component-absent";
    else if(Q(entity+0x1D0)!=0)status="direct-branch-not-selected";
    else
    {
     var p=Ptr(Q(Ptr(component,0x50)+0x48),0x210);decoration=D(p+0x20C);comparison=D(manager+0x46C);
     if(decoration==0)status="no-decoration-zero";
     else if(decoration==comparison)status="no-decoration-equal";
     else
     {
      var header=Take(manager+0x4B8,24);var b=Ptr(BinaryPrimitives.ReadUInt64LittleEndian(header));var stride=BinaryPrimitives.ReadUInt64LittleEndian(header.AsSpan(8));var count=BinaryPrimitives.ReadUInt64LittleEndian(header.AsSpan(16));if(stride is <24 or >4096||stride%8!=0||count is <1 or >4096)throw new InvalidDataException("Invalid decoration map.");
      var address=Ptr(checked(b+CurrentBuildAbilityRecordsCandidateReader.Hash(decoration.Value)%count*stride),24);var seen=new HashSet<ulong>();bool head=true;byte[]? node=null;
      for(int i=0;i<128;i++){if(!seen.Add(address))throw new InvalidDataException("Decoration chain cycle.");node=Take(address,24);var link=BinaryPrimitives.ReadUInt64LittleEndian(node);if((!head||(link&1)==0)&&BinaryPrimitives.ReadUInt32LittleEndian(node.AsSpan(8))==decoration.Value)break;var next=link&~1UL;if(next==0){node=null;break;}if(i==127)throw new InvalidDataException("Decoration chain budget.");address=Ptr(next,24);head=false;}
      if(node is null)status="cache-miss";
      else
      {
       var obj=Ptr(BinaryPrimitives.ReadUInt64LittleEndian(node.AsSpan(16)),0xE0);var pointer=Q(obj+0xD8);if(pointer<0x10000||pointer%2!=0||pointer>0x7FFFFFFFFFFFUL-2)throw new InvalidDataException("Invalid decoration text pointer.");var n=(int)Math.Min(256UL,4096-(pointer&4095))&~1;var raw=Take(pointer,n,false);int end=-1;for(int i=0;i<n;i+=2)if(raw[i]==0&&raw[i+1]==0){end=i;break;}if(end<0)throw new InvalidDataException("Unterminated decoration text.");anchors[(pointer,end+2)]=raw[..(end+2)];try{text=new UnicodeEncoding(false,false,true).GetString(raw,0,end);}catch(DecoderFallbackException){throw new InvalidDataException("Invalid UTF-16 decoration.");}status=text.Length==0?"empty-text-candidate":"text-candidate";
      }
     }
    }
   }
  }
  catch(InvalidDataException ex){if(budget>2*1024*1024)throw;status=ex.Message=="Unterminated decoration text."?"unterminated-text":ex.Message is "Invalid decoration text pointer." or "Invalid UTF-16 decoration."?"invalid-text":"unavailable";text=null;}
  foreach(var a in anchors)CurrentBuildPlayerLookup.RequireSame(Take(a.Key.Item1,a.Key.Item2,false),a.Value);lookup.Verify();var after=context(session);if(after.Identity!=id||after.UnitKey!=lookup.Key||after.Entity!=entity||after.HealthComponent!=health||after.Owner!=before.Owner||session.Identity!=id)throw new InvalidDataException("Self or process epoch changed.");
  return new(id,started,DateTimeOffset.UtcNow,lookup.Key,entity,status,decoration,comparison,text);
 }
}
