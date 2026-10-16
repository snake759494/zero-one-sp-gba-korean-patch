"""분리형 8bpp 조작 안내. 원본 타일 용량/맵/팔레트 보존 검사."""
import json,struct
from pathlib import Path
from graphics_patch import unpack,ui_text,render_mapped,mapped_pixels,UI_STYLES
ROOT=Path(__file__).resolve().parent

def container(tiles,tilemap,palette):
 assert len(tiles)%64==0 and len(palette)==512
 n=4+len(tiles);po=32+n;mo=po+512
 return struct.pack('<8I',32,n,po,512,mo,len(tilemap),0,0)+struct.pack('<HH',len(tiles)//64,1)+tiles+palette+tilemap

def prepare(source,bdf_reader):
 pairs=json.loads((ROOT/'재점검/이미지검토/분리타일맵_전체목록.json').read_text('utf-8'))['pairs'];pair_index={}
 for entry in pairs:pair_index.setdefault(entry['tiles'],entry)
 all_pairs=pairs; pairs=pair_index
 texts=json.loads((ROOT/'split_ui_translations.json').read_text('utf-8'));fonts={11:bdf_reader(ROOT/'폰트/Galmuri11-Condensed.bdf'),7:bdf_reader(ROOT/'폰트/Galmuri7.bdf')};out=[]
 palette=bytearray(512);palette[256:288]=source[0x52f944:0x52f964]
 for key,lines in texts.items():
  a=int(key,16);ma=int(pairs[key]['map'],16);tiles,_=unpack(source,a);tm,_=unpack(source,ma);w,h=struct.unpack_from('<HH',tm);w*=8;h*=8
  assert set(tiles)<=set(range(128,135))|{0},key
  size=11 if h>=64 else 7;font=fonts[size];rect=[7,12,w-7,h-10] if h>=64 else [4,3,w-4,h-3]
  widths=[sum(font[ord(ch)]['advance'] if ch!=' ' else 4 for ch in line) for line in lines]
  assert max(widths)<=rect[2]-rect[0],(key,widths,w)
  top=rect[1]+(rect[3]-rect[1]-(len(lines)*(size+3)-3))//2;assert top>=rect[1],key
  labels=[]
  for i,line in enumerate(lines):
   labels.append((rect,line,size));UI_STYLES[a,i]={'fg':(31,31,31),'no_shadow':True,'solid_bg':True,'bg':(6,4,10),'origin_y':top+i*(size+3),'preserve_background':i>0}
  reserved=set()
  for other in all_pairs:
   if other['tiles']==key and int(other['map'],16)!=ma:
    extra,_=unpack(source,int(other['map'],16));ew,eh=struct.unpack_from('<HH',extra);reserved.update(v&1023 for v in struct.unpack_from('<'+'H'*(ew*eh),extra,4))
  old=container(tiles,tm,bytes(palette));new,changed,native,oc,nc=ui_text(old,labels,fonts,a,reserved);po=36+len(tiles);mo=po+512
  assert all(tiles[i*64:(i+1)*64]==new[36+i*64:36+(i+1)*64] for i in reserved)
  assert oc==nc and old[po:mo]==new[po:mo]
  render_mapped(old,ROOT/f'graphics_review/split_original_{key}.png');render_mapped(new,ROOT/f'graphics_review/split_korean_{key}.png')
  out.append({'resource':key,'map_resource':f'{ma:08X}','changed_pixels':changed,'native_labels':native,'tiles':new[36:po],'map':new[mo:],'tile_count':oc,'text_rectangles':[rect],'canvas':[w,h]})
 # 암호 장치의 닫기/열기 버튼. 배경과 숫자 키는 그대로 보존한다.
 a=0xb62f90;ma=0xb660b8;tiles,_=unpack(source,a);tm,_=unpack(source,ma);palette=source[0x5306f4:0x5308f4]
 labels=[([64,103,111,121],'닫기',11),([128,103,176,121],'열기',11)]
 for i in range(2):UI_STYLES[a,i]={'fg':(0,0,0) if i==0 else (31,0,0),'no_shadow':True,'solid_bg':True,'bg':(24,24,23)}
 old=container(tiles,tm,palette);new,changed,native,oc,nc=ui_text(old,labels,fonts,a);po=36+len(tiles);mo=po+512
 render_mapped(old,ROOT/'graphics_review/split_original_00B62F90.png');render_mapped(new,ROOT/'graphics_review/split_korean_00B62F90.png')
 out.append({'resource':'00B62F90','map_resource':'00B660B8','changed_pixels':changed,'native_labels':native,'tiles':new[36:po],'map':new[mo:],'tile_count':oc,'text_rectangles':[x[0] for x in labels],'canvas':[240,160],'palette_source':0x5306f4})
 return out
if __name__=='__main__':
 from build import bdf
 data=prepare((ROOT.parent/'Zero One SP (Japan).gba').read_bytes(),bdf)
 print('검사 통과',len(data))
 (ROOT/'재점검/분리형_배치검증.json').write_text(json.dumps([{k:v for k,v in r.items() if k not in ['tiles','map']} for r in data],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def apply(source,rom,alloc,bdf_reader):
 from graphics_patch import huffman_fixed4,literal_lz
 records=[]
 for entry in prepare(source,bdf_reader):
  record={k:v for k,v in entry.items() if k not in ('tiles','map')};components=[]
  for name,original in [('tiles',int(entry['resource'],16)),('map',int(entry['map_resource'],16))]:
   data=entry[name];packed=huffman_fixed4(literal_lz(data));assert unpack(packed,0)[0]==data
   refs=[];needle=struct.pack('<I',0x08000000+original);start=0
   while (ref:=source.find(needle,start))>=0:
    start=ref+1
    if ref%4==0:refs.append(ref)
   assert refs,(name,hex(original));dest=alloc(packed)
   for ref in refs:
    assert struct.unpack_from('<I',rom,ref)[0]==original+0x08000000
    struct.pack_into('<I',rom,ref,dest+0x08000000)
   components.append({'kind':name,'original':original,'new':dest,'references':refs,'decoded_size':len(data)})
  record['components']=components;record['palette_source']=entry.get('palette_source',0x52f944);record['palette_unchanged']=True;record['scale']=[1,1];record['shared_map_tiles_preserved']=True;records.append(record)
 return records

def verify(source,patched,records,bdf_reader):
 expected={x['resource']:x for x in prepare(source,bdf_reader)};assert len(records)==len(expected);allowed=set()
 for record in records:
  item=expected.pop(record['resource']);assert record['canvas']==item['canvas'] and record['tile_count']==item['tile_count']
  for part in record['components']:
   data,_=unpack(patched,part['new']);original,_=unpack(source,part['original'])
   assert data==item[part['kind']] and len(data)==len(original)==part['decoded_size']
   for ref in part['references']:
    assert struct.unpack_from('<I',source,ref)[0]==0x08000000+part['original']
    assert struct.unpack_from('<I',patched,ref)[0]==0x08000000+part['new'];allowed.update(range(ref,ref+4))
  assert source[record['palette_source']:record['palette_source']+32]==patched[record['palette_source']:record['palette_source']+32]
 assert not expected
 return allowed
