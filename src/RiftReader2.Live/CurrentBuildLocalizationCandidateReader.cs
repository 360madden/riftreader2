using System.Buffers.Binary;
using System.Text;
using RiftReader2.Application;
using RiftReader2.Domain;
namespace RiftReader2.Live;
internal sealed record LocalizationCandidate(uint Key,string Status,ulong? NodeAddress=null,string? RawNode=null,ulong? HolderAddress=null,ulong? ResultAddress=null,string? RawResult=null,int? LocaleFound=null,ulong? ChildAddress=null,ulong? TextPointer=null,string? CandidateText=null);
internal sealed record CurrentBuildLocalizationObservation(NativeProcessIdentity Identity,DateTimeOffset StartedAtUtc,DateTimeOffset CompletedAtUtc,byte Mode,int Locale,ulong Manager,ulong Wrapper,ulong Inner,ulong BucketCount,ulong EntryCount,IReadOnlyList<LocalizationCandidate> Records)
{
 public string Qualification=>"raw typed candidates only; cache miss does not establish translation absence or freshness";
}
internal static class CurrentBuildLocalizationCandidateReader
{
 internal static CurrentBuildLocalizationObservation Read(IReadOnlyNativeMemorySession session,IReadOnlyList<uint> keys)
 {
  var started=DateTimeOffset.UtcNow;var id=session.Identity;
  if(id.ProcessId<=0||id.ProcessStartUtcTicks<=0||id.ModuleSize<=0x3484007||!string.Equals(id.ExecutableSha256,CurrentBuildPlayerLookup.GameSha256,StringComparison.OrdinalIgnoreCase)||keys.Count is <1 or >128||keys.Distinct().Count()!=keys.Count)throw new InvalidDataException("Invalid localization build, identity or keys.");
  var anchors=new Dictionary<(ulong,int),byte[]>();int budget=0;
  byte[] Take(ulong a,int n,bool anchor=true) {budget=checked(budget+n);if(budget>2*1024*1024)throw new InvalidDataException("Localization read budget exceeded.");var raw=CurrentBuildPlayerLookup.Exact(session,a,n);if(anchor){if(anchors.TryGetValue((a,n),out var old)&&!old.AsSpan().SequenceEqual(raw))throw new InvalidDataException("Localization bytes changed.");anchors[(a,n)]=raw.ToArray();}return raw;}
  ulong Ptr(ulong a,int n=8)=>CurrentBuildPlayerLookup.Pointer(a,n); ulong Q(ulong a)=>U64(Take(a,8));
  var manager=Ptr(Q(id.ModuleBaseAddress+0x33623E8),0xA0);var state=Take(manager,8);var mode=state[0];var locale=BinaryPrimitives.ReadInt32LittleEndian(state.AsSpan(4));
  var wrapper=Ptr(Q(manager+0x98),16);var provider=Take(wrapper,16);var vt=U64(provider);var inner=Ptr(U64(provider.AsSpan(8)),0x48);
  if(vt!=id.ModuleBaseAddress+0x26C1EA8||Q(vt)!=id.ModuleBaseAddress+0x7D3230)throw new InvalidDataException("Localization provider fingerprint mismatch.");
  var header=Take(inner+0x28,32);var b=U64(header);var stride=U64(header.AsSpan(8));var count=U64(header.AsSpan(16));var entries=U64(header.AsSpan(24));
  if(stride!=24||count>4096||entries>64||(count==0&&(b!=0||entries!=0)))throw new InvalidDataException("Invalid localization cache header.");if(count>0)Ptr(b,checked((int)(count*24)));
  void Type(ulong obj,ulong objectVt,ulong getter,ulong descriptor,ulong descVt,ulong descGetter,ulong? known=null)
  {if((known??Q(obj))!=id.ModuleBaseAddress+objectVt||Q(id.ModuleBaseAddress+objectVt+0x40)!=id.ModuleBaseAddress+getter||Q(id.ModuleBaseAddress+descriptor)!=id.ModuleBaseAddress+descVt||Q(id.ModuleBaseAddress+descVt+8)!=id.ModuleBaseAddress+descGetter)throw new InvalidDataException("Localization type fingerprint or initialized descriptor mismatch.");}
  string Text(ulong a)
  {
   if(a<0x10000||a%2!=0||a>0x7FFFFFFFFFFFUL-2)throw new InvalidDataException("Invalid text pointer.");var length=(int)Math.Min(256UL,4096-(a&4095))&~1;
   var raw=Take(a,length,false);int end=-1;for(int i=0;i<length;i+=2)if(raw[i]==0&&raw[i+1]==0){end=i;break;}
   if(end<0)throw new InvalidDataException("Unterminated localization text.");var exact=raw[..(end+2)];if(anchors.TryGetValue((a,exact.Length),out var old)&&!old.AsSpan().SequenceEqual(exact))throw new InvalidDataException("Localization text changed.");anchors[(a,exact.Length)]=exact;
   try{return new UnicodeEncoding(false,false,true).GetString(raw,0,end);}catch(DecoderFallbackException){throw new InvalidDataException("Invalid UTF-16 text.");}
  }
  var rows=new List<LocalizationCandidate>();
  foreach(var key in keys)
  {
   if(count==0){rows.Add(new(key,"cache-miss"));continue;}
   var address=checked(b+CurrentBuildAbilityRecordsCandidateReader.Hash(key)%count*24);var seen=new HashSet<ulong>();bool head=true;byte[]? node=null;
   for(int i=0;i<=128;i++) {if(!seen.Add(address))throw new InvalidDataException("Localization cache cycle.");node=Take(address,24);var link=U64(node);if((!head||(link&1)==0)&&BinaryPrimitives.ReadUInt32LittleEndian(node.AsSpan(8))==key)break;var next=link&~1UL;if(next==0){node=null;break;}if(i==128)throw new InvalidDataException("Localization chain budget exceeded.");address=Ptr(next,24);head=false;}
   if(node is null){rows.Add(new(key,"cache-miss"));continue;}
   var rawNode=Convert.ToHexString(node).ToLowerInvariant();var holder=U64(node.AsSpan(16));if(holder==0){rows.Add(new(key,"null-holder",address,rawNode,0));continue;}
   var result=Q(checked(Ptr(holder,0x20)+0x18));if(result==0){rows.Add(new(key,"null-result",address,rawNode,holder,0));continue;}
   Ptr(result,0x48);var raw=Take(result,0x48);Type(result,0x295DC10,0x1A4FAF0,0x3484000,0x2963030,0x1A779E0,U64(raw));
   var root=U64(raw.AsSpan(0x28));var treeCount=U64(raw.AsSpan(0x40));if(treeCount==0)throw new InvalidDataException("Localization locale tree unavailable.");Ptr(root,48);
   ulong foundChild=0;int? foundLocale=null;
   foreach(var target in new[]{locale,1}.Distinct())
   {
    var current=root;var treeSeen=new HashSet<ulong>();while(current!=0){Ptr(current,48);if(!treeSeen.Add(current)||treeSeen.Count>64)throw new InvalidDataException("Localization tree invalid or cyclic.");var n=Take(current,48);var left=U64(n.AsSpan(16));var right=U64(n.AsSpan(24));var nodeKey=BinaryPrimitives.ReadInt32LittleEndian(n.AsSpan(32));if(nodeKey==target){foundChild=U64(n.AsSpan(40));foundLocale=target;break;}current=target<nodeKey?left:right;}if(foundLocale.HasValue)break;
   }
   var rawResult=Convert.ToHexString(raw).ToLowerInvariant();
   if(!foundLocale.HasValue){rows.Add(new(key,"locale-miss",address,rawNode,holder,result,rawResult));continue;}
   Ptr(foundChild,0x40);Type(foundChild,0x2804120,0x173C790,0x3420930,0x2820340,0x177CE30);var fields=Take(foundChild+0x30,16);var first=U64(fields);var second=U64(fields.AsSpan(8));var textPtr=mode!=0?first:second;var text=Text(textPtr);if(text.Length==0&&textPtr!=first){textPtr=first;text=Text(first);}
   rows.Add(new(key,"typed-candidate",address,rawNode,holder,result,rawResult,foundLocale,foundChild,textPtr,text));
  }
  foreach(var a in anchors)CurrentBuildPlayerLookup.RequireSame(Take(a.Key.Item1,a.Key.Item2,false),a.Value);
  if(session.Identity!=id)throw new InvalidDataException("Localization process identity changed.");
  return new(id,started,DateTimeOffset.UtcNow,mode,locale,manager,wrapper,inner,count,entries,rows);
 }
 static ulong U64(ReadOnlySpan<byte>b)=>BinaryPrimitives.ReadUInt64LittleEndian(b);
}
