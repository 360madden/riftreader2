using System.Buffers.Binary;
using System.Globalization;
using System.Text.Json;
using System.Text;
using RiftReader2.Application;
using RiftReader2.Infrastructure;
namespace RiftReader2.Live;
internal sealed record PlayerRaceSeedObservation(object Identity,DateTimeOffset StartedAtUtc,DateTimeOffset CompletedAtUtc,ulong SelfKey,ulong SelfEntity,ulong Health,string ReferentStatus,ulong? ReferentAddress,ulong? ReferentVtable,ulong? ReferentGetterRva,uint? RawRaceKey,string ProviderStatus,ulong? ProviderAddress,string? RaceRecordStatus=null,ulong? RaceRecordAddress=null,ushort? RaceSelector=null,uint? RaceTlsIndex=null,ulong? RaceCollection=null,string? RaceTextCandidate=null,RaceLocalizedNameSeed? LocalizedNameSeed=null)
{public string Qualification=>"raw referent seed; referent type, API correspondence, freshness and restart unverified";}
internal sealed record RaceLocalizedNameSeed(string Status,int? LocalizationMode=null,ulong? ChildAddress=null,uint? LocalizationKey=null,string? FallbackText=null,CurrentBuildLocalizationDictionaryObservation? Dictionary=null)
{public string Qualification=>"raw localized name seed; API raceName selection and freshness unverified";}
internal static class CurrentBuildPlayerRaceSampleCommand
{
 internal static async Task<int> RunAsync(IReadOnlyDictionary<string,string> options,TextWriter output,CancellationToken ct)
 {
  if(!options.TryGetValue("--pid",out var p)||!int.TryParse(p,NumberStyles.None,CultureInfo.InvariantCulture,out var pid)||pid<=0||!options.TryGetValue("--start-ticks",out var t)||!long.TryParse(t,NumberStyles.None,CultureInfo.InvariantCulture,out var ticks)||ticks<=0||!options.TryGetValue("--output",out var path)||string.IsNullOrWhiteSpace(path))throw new ArgumentException("--pid, --start-ticks and --output required.");
  if(File.Exists(path))throw new IOException("Output exists.");await using var session=await WindowsNativeMemorySession.OpenAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,ct);ct.ThrowIfCancellationRequested();var observation=Read(session);if(await session.RevalidateAsync(ct) is not null)throw new InvalidDataException("Process invalidated.");ct.ThrowIfCancellationRequested();await JsonReportWriter.WriteNewAsync(path,new{schemaVersion=1,contractVersion="native-current-player-race-seed/1",status="complete",observation,limitations=new[]{"Referent type and race semantics are not established; typed definition text is a candidate, not raceName or a provider fallback.","Sequential reads cannot exclude ABA; loaded module bytes are not independently hashed.","No native getter, initializer, refcount or memory write is performed."}},ct);await output.WriteLineAsync(JsonSerializer.Serialize(new{recordType="native-current-player-race-seed-summary/1",output=Path.GetFullPath(path)},new JsonSerializerOptions(JsonFormat.Options){WriteIndented=false}));return 0;
 }
 internal static PlayerRaceSeedObservation Read(IReadOnlyNativeMemorySession session)=>Read(session,CurrentBuildPlayerContextCandidateReader.Read,s=>{var l=CurrentBuildPlayerLookup.Resolve(s);return new(l.PlayerKey,l.EntityAddress,l.ResolveComponent(0x2F57850),l.VerifyUnchanged);},()=>WindowsThreadTlsSnapshot.Capture(session.Identity.ProcessId));
 internal static PlayerRaceSeedObservation Read(IReadOnlyNativeMemorySession session,Func<IReadOnlyNativeMemorySession,CurrentBuildPlayerContextObservation> context,Func<IReadOnlyNativeMemorySession,PlayerContextOwner> resolve,Func<IReadOnlyList<NativeThreadEpoch>>? threads=null)
 {
  var start=DateTimeOffset.UtcNow;var id=session.Identity;if(id.ProcessId<=0||id.ProcessStartUtcTicks<=0||id.ModuleSize<0x3576368||!string.Equals(id.ExecutableSha256,CurrentBuildPlayerLookup.GameSha256,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("Unsupported build or process.");var before=context(session);var lookup=resolve(session);
  if(before.Identity!=id||before.UnitKey!=lookup.Key||before.Entity!=lookup.Entity||before.HealthComponent!=lookup.Health)throw new InvalidDataException("Self identity mismatch.");
  var anchors=new Dictionary<(ulong,int),byte[]>();int budget=0;byte[] Take(ulong a,int n,bool save=true){budget=checked(budget+n);if(budget>2*1024*1024)throw new InvalidDataException("Race seed budget exceeded.");var b=CurrentBuildPlayerLookup.Exact(session,a,n);if(save){if(anchors.TryGetValue((a,n),out var old)&&!old.AsSpan().SequenceEqual(b))throw new InvalidDataException("Race seed changed.");anchors[(a,n)]=b.ToArray();}return b;}
  ulong Q(ulong a)=>BinaryPrimitives.ReadUInt64LittleEndian(Take(a,8));var health=CurrentBuildPlayerLookup.Pointer(lookup.Health,0x50);var entity=CurrentBuildPlayerLookup.Pointer(lookup.Entity,128);
  if(Q(health+0x10)!=entity||Q(health+0x40)!=before.Owner)throw new InvalidDataException("Self health binding changed.");
  string status="unavailable";ulong? referent=null,vt=null,getter=null;uint? key=null;
  try{var raw=Q(health+0x48);if(raw==0)status="null-referent";else{referent=CurrentBuildPlayerLookup.Pointer(raw,0x34);vt=Q(raw);key=BinaryPrimitives.ReadUInt32LittleEndian(Take(raw+0x30,4));if(vt>=id.ModuleBaseAddress&&vt<=id.ModuleBaseAddress+id.ModuleSize-0x48){try{var target=Q(vt.Value+0x40);if(target>=id.ModuleBaseAddress&&target<id.ModuleBaseAddress+id.ModuleSize)getter=target-id.ModuleBaseAddress;}catch(InvalidDataException){if(budget>2*1024*1024)throw;}}status="raw-candidate";}}catch(InvalidDataException){if(budget>2*1024*1024)throw;referent=null;vt=null;getter=null;key=null;}
  string providerStatus="unavailable";ulong? provider=null;try{var p=Q(id.ModuleBaseAddress+0x336F1F8);if(p==0)providerStatus="null-provider";else{provider=CurrentBuildPlayerLookup.Pointer(p,0x42);providerStatus="resident-unqueried";}}catch(InvalidDataException){if(budget>2*1024*1024)throw;}
  RaceLocalizedNameSeed? localizedName=null;string? raceStatus=null,raceText=null;ulong? raceRecord=null,collection=null;ushort? selector=null;uint? index=null;IReadOnlyList<NativeThreadEpoch>? epochs=null;
  if(providerStatus=="resident-unqueried"&&key.HasValue&&threads is not null)
  {
   raceStatus="unavailable";
   // Fail closed on unavailable memory; successfully consumed bytes remain anchored.
   try
   {
    selector=BinaryPrimitives.ReadUInt16LittleEndian(Take(provider!.Value+0x40,2));
    var wrapper=CurrentBuildPlayerLookup.Pointer(Q(id.ModuleBaseAddress+0x3372C18));var owner=CurrentBuildPlayerLookup.Pointer(Q(wrapper),0x278);
    index=BinaryPrimitives.ReadUInt32LittleEndian(Take(owner+0x274,4));if(index>1087)throw new InvalidDataException("Invalid TLS index.");
    epochs=threads();if(epochs.Count is <1 or >256||epochs.Select(x=>x.Id).Distinct().Count()!=epochs.Count||epochs.Select(x=>x.Teb).Distinct().Count()!=epochs.Count)throw new InvalidDataException("Invalid thread set.");
    foreach(var t in epochs){CurrentBuildPlayerLookup.Pointer(t.Teb,0x1788);var ti=Take(t.Teb+0x30,32);if(t.Id<=0||t.Created<=0||U64(ti)!=t.Teb||U64(ti.AsSpan(16))!=(ulong)id.ProcessId||U64(ti.AsSpan(24))!=(ulong)t.Id)throw new InvalidDataException("Invalid TEB identity.");ulong v;if(index<64)v=Q(t.Teb+0x1480+index.Value*8UL);else{var expansion=Q(t.Teb+0x1780);v=expansion==0?0:Q(checked(CurrentBuildPlayerLookup.Pointer(expansion)+(index.Value-64)*8UL));}var c=v==0?checked(owner+0x200):CurrentBuildPlayerLookup.Pointer(v);if(collection.HasValue&&collection!=c)throw new InvalidDataException("Thread collections disagree.");collection=c;}
    var header=Take(collection!.Value+0x20,32);var cb=CurrentBuildPlayerLookup.Pointer(U64(header));var stride=U64(header.AsSpan(8));var count=U64(header.AsSpan(16));if(stride!=24||count is <1 or >4096)throw new InvalidDataException("Invalid cache header.");CurrentBuildPlayerLookup.Pointer(cb,checked((int)(count*24)));
    var hash=CurrentBuildAbilityRecordsCandidateReader.Hash(key.Value);var address=checked(cb+CurrentBuildAbilityRecordsCandidateReader.Hash(hash)%count*24);var seen=new HashSet<ulong>();var head=true;byte[]? found=null;
    for(int i=0;i<=128;i++){if(!seen.Add(address))throw new InvalidDataException("Cache cycle.");var node=Take(address,24);var link=U64(node);if((!head||(link&1)==0)&&BinaryPrimitives.ReadUInt16LittleEndian(node.AsSpan(8))==selector&&BinaryPrimitives.ReadUInt32LittleEndian(node.AsSpan(12))==key){found=node;break;}var next=link&~1UL;if(next==0)break;if(i==128)throw new InvalidDataException("Cache chain budget.");address=CurrentBuildPlayerLookup.Pointer(next,24);head=false;}
    raceStatus="cache-miss";
    if(found is not null){var holder=U64(found.AsSpan(16));if(holder==0)raceStatus="null-holder";else{var obj=Q(CurrentBuildPlayerLookup.Pointer(holder,0x20)+0x18);if(obj==0)raceStatus="null-record";else{raceRecord=CurrentBuildPlayerLookup.Pointer(obj,0x120);raceStatus="unverified-type";
     if(Q(obj)==id.ModuleBaseAddress+0x2C68CA0&&Q(id.ModuleBaseAddress+0x2C68CE0)==id.ModuleBaseAddress+0x2173B90&&Q(id.ModuleBaseAddress+0x3576360)==id.ModuleBaseAddress+0x2C6B2C0&&Q(id.ModuleBaseAddress+0x2C6B2C8)==id.ModuleBaseAddress+0x2196D70){raceStatus="type-0718-text-unavailable";var text=Q(obj+0x118);if(text>=0x10000&&text<=0x7FFFFFFFFFFFUL-256){var bytes=new List<byte>();bool terminated=false;for(int i=0;i<256;i++){var b=Take(text+(ulong)i,1)[0];if(b==0){terminated=true;break;}bytes.Add(b);}if(terminated){try{raceText=new UTF8Encoding(false,true).GetString(bytes.ToArray());raceStatus="type-0718-text-candidate";}catch(DecoderFallbackException){}}}}
    }}}
    if(raceRecord.HasValue && raceStatus is "type-0718-text-candidate" or "type-0718-text-unavailable")
    {
     try
     {
      var manager=CurrentBuildPlayerLookup.Pointer(Q(id.ModuleBaseAddress+0x33623E8),8);var mode=BinaryPrimitives.ReadInt32LittleEndian(Take(manager+4,4));
      var child=Q(raceRecord.Value+0x280);
      if(child==0)localizedName=new("null-child",mode);
      else
      {
       CurrentBuildPlayerLookup.Pointer(child,0x28);
       if(Q(child)!=id.ModuleBaseAddress+0x27F24F8||Q(id.ModuleBaseAddress+0x27F2538)!=id.ModuleBaseAddress+0x170C5D0||Q(id.ModuleBaseAddress+0x3417970)!=id.ModuleBaseAddress+0x2802E40||Q(id.ModuleBaseAddress+0x2802E48)!=id.ModuleBaseAddress+0x17361E0)localizedName=new("unverified-type",mode,child);
       else
       {
        var loc=BinaryPrimitives.ReadUInt32LittleEndian(Take(child+0x18,4));var pointer=Q(child+0x20);
        if(pointer<0x10000||pointer%2!=0||pointer>0x7FFFFFFFFFFFUL-2)throw new InvalidDataException("Invalid race name pointer.");
        var length=(int)Math.Min(256UL,4096-(pointer&4095))&~1;var raw=Take(pointer,length,false);int end=-1;
        for(int i=0;i<length;i+=2)if(raw[i]==0&&raw[i+1]==0){end=i;break;}
        if(end<0)throw new InvalidDataException("Unterminated race name.");
        var exact=raw[..(end+2)];if(anchors.TryGetValue((pointer,exact.Length),out var old)&&!old.AsSpan().SequenceEqual(exact))throw new InvalidDataException("Race name changed.");anchors[(pointer,exact.Length)]=exact;
        string fallback;try{fallback=new UnicodeEncoding(false,false,true).GetString(raw,0,end);}catch(DecoderFallbackException){throw new InvalidDataException("Invalid race name UTF-16.");}
        CurrentBuildLocalizationDictionaryObservation? dict=null;string nameStatus="raw-candidate";
        if(loc!=0)try{dict=CurrentBuildLocalizationDictionaryCandidateReader.Read(session,[loc]);}catch(InvalidDataException){nameStatus="raw-candidate-dictionary-unavailable";}
        localizedName=new(nameStatus,mode,child,loc,fallback,dict);
       }
      }
     }
     catch(InvalidDataException){if(budget>2*1024*1024)throw;localizedName=new("unavailable");}
    }
   }
   catch(InvalidDataException){if(budget>2*1024*1024)throw;raceStatus="unavailable";raceText=null;}
  }
  lookup.Verify();var after=context(session);if(after.Identity!=id||after.UnitKey!=lookup.Key||after.Entity!=entity||after.HealthComponent!=health||after.Owner!=before.Owner||session.Identity!=id)throw new InvalidDataException("Self or process epoch changed.");
  foreach(var a in anchors)CurrentBuildPlayerLookup.RequireSame(Take(a.Key.Item1,a.Key.Item2,false),a.Value);
  if(epochs is not null&&!epochs.OrderBy(x=>x.Id).SequenceEqual(threads!().OrderBy(x=>x.Id)))throw new InvalidDataException("Thread epoch changed.");if(session.Identity!=id)throw new InvalidDataException("Process identity changed.");
  return new(id,start,DateTimeOffset.UtcNow,lookup.Key,entity,health,status,referent,vt,getter,key,providerStatus,provider,raceStatus,raceRecord,selector,index,collection,raceText,localizedName);
 }
 static ulong U64(ReadOnlySpan<byte> b)=>BinaryPrimitives.ReadUInt64LittleEndian(b);
}
