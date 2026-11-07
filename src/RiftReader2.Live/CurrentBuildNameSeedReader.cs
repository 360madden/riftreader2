using System.Buffers.Binary;
using System.Text;
using RiftReader2.Application;
namespace RiftReader2.Live;
internal static class CurrentBuildNameSeedReader
{
 internal static TargetNameSeed Read(IReadOnlyNativeMemorySession session, RiftReader2.Domain.NativeProcessIdentity id, ulong entity, Func<ulong,int,bool,byte[]> Take, Dictionary<(ulong,int),byte[]> anchors)
  {
   byte[] Read(ulong address,int size)=>Take(address,size,true);
   ulong Ptr(ulong p,int n=8)=>CurrentBuildPlayerLookup.Pointer(p,n);
   ulong Q(ulong a)=>BinaryPrimitives.ReadUInt64LittleEndian(Read(a,8));
   byte Selector(ulong rva) {var index=BinaryPrimitives.ReadInt32LittleEndian(Read(id.ModuleBaseAddress+rva,4));if(index is <0 or >=0x60)throw new InvalidDataException("Invalid name selector.");return Read(entity+0x18+(ulong)index,1)[0];}
   ulong Component(ulong rva) {var slot=Selector(rva);if(slot==0xFF)return 0;var table=Ptr(Q(entity+0x78));return Q(checked(table+slot*8UL));}
   string Text(ulong a) {if(a<0x10000||a%2!=0||a>0x7FFFFFFFFFFFUL-2)throw new InvalidDataException("Invalid name text pointer.");var n=(int)Math.Min(256UL,4096-(a&4095))&~1;var raw=Take(a,n,false);int end=-1;for(int i=0;i<n;i+=2)if(raw[i]==0&&raw[i+1]==0){end=i;break;}if(end<0)throw new InvalidDataException("Unterminated name.");var exact=raw[..(end+2)];if(anchors.TryGetValue((a,exact.Length),out var old)&&!old.AsSpan().SequenceEqual(exact))throw new InvalidDataException("Name text changed.");anchors[(a,exact.Length)]=exact;try{return new UnicodeEncoding(false,false,true).GetString(raw,0,end);}catch(DecoderFallbackException){throw new InvalidDataException("Invalid name UTF-16.");}}
   var direct=Component(0x2F582E0);
   if(direct!=0 && Q(entity+0x1D0)==0) {var p=Ptr(Q(Ptr(direct,0x50)+0x48),0xB68);var text=Text(Q(p+0xB60));var decoration=BinaryPrimitives.ReadUInt32LittleEndian(Read(p+0x20C,4));return new(text.Length==0?"empty":"raw-candidate","direct",RawDirect:text,RawDecoration:decoration);}
   var localized=Component(0x2F579F0);
   if(localized!=0)
   {
    var reference=Ptr(Q(Ptr(localized,0x28)+0x20),0x68);var child=Ptr(Q(reference+0x60),0x28);
    if(Q(child)!=id.ModuleBaseAddress+0x27F24F8||Q(id.ModuleBaseAddress+0x27F2538)!=id.ModuleBaseAddress+0x170C5D0||Q(id.ModuleBaseAddress+0x3417970)!=id.ModuleBaseAddress+0x2802E40||Q(id.ModuleBaseAddress+0x2802E48)!=id.ModuleBaseAddress+0x17361E0)throw new InvalidDataException("Name child type mismatch.");
    var key=BinaryPrimitives.ReadUInt32LittleEndian(Read(child+0x18,4));var fallback=Text(Q(child+0x20));var dictionary=key==0?null:CurrentBuildLocalizationDictionaryCandidateReader.Read(session,[key]);
    return new("raw-candidate","localized",RawFallback:fallback,LocalizationKey:key,Dictionary:dictionary);
   }
   var alternate=Component(0x2F58270);
   if(alternate!=0){var p=Ptr(Q(Ptr(alternate,0x30)+0x28),0x110);var text=Text(Q(p+0x108));return new(text.Length==0?"empty-unresolved-fallback":"raw-candidate","alternate",RawDirect:text);}
   var vt=Q(entity);ulong? getter=null;if(vt>=id.ModuleBaseAddress&&vt<=id.ModuleBaseAddress+id.ModuleSize-0x20){var v=Q(vt+0x18);if(v>=id.ModuleBaseAddress&&v<id.ModuleBaseAddress+id.ModuleSize)getter=v-id.ModuleBaseAddress;}
   return new("unresolved","entity-virtual",EntityVtable:vt,GetterRva:getter);
  }
}
