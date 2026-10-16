"""선택 화면 썸네일의 8bpp 원본 타일·팔레트 크기를 보존해 번역한다."""
from pathlib import Path
import struct,json
from graphics_patch import unpack,ui_text,UI_STYLES,render_mapped,mapped_pixels,huffman_fixed4,literal_lz
ROOT=Path(__file__).resolve().parent
def prepare(source,bdf):
    font=bdf(ROOT/'폰트/Galmuri7.bdf');out=[]
    for key,rows in json.loads((ROOT/'extra8_ui_translations.json').read_text('utf-8')).items():
        off=int(key,16);old,_=unpack(source,off);a,n,po,ps,mo,ms,_,_=struct.unpack_from('<8I',old)
        assert a==32 and ms==0 and len(old)==po+ps and po==a+n
        tw,th=struct.unpack_from('<HH',old,a);assert n-4==tw*th*64
        tm=struct.pack('<HH',tw,th)+struct.pack('<'+'H'*(tw*th),*range(tw*th))
        container=struct.pack('<8I',a,n,po,ps,len(old),len(tm),0,0)+old[32:]+tm
        labels=[]
        for i,(rect,ko,jp) in enumerate(rows):
            labels.append((rect,ko,7));UI_STYLES[off,i]={'fg':(31,31,31),'solid_bg':True,'no_shadow':True}
        new,changed,native,oc,nc=ui_text(container,labels,{7:font},off)
        pix=mapped_pixels(new);original=mapped_pixels(container);patched=bytearray(old)
        for y in range(th*8):
            for x in range(tw*8):
                q=a+4+(y//8*tw+x//8)*64+y%8*8+x%8;patched[q]=pix[y][x]
                if pix[y][x]!=original[y][x]:assert any(l<=x<r and t<=y<b for (l,t,r,b),_,_ in rows)
        assert patched[:a+4]==old[:a+4] and patched[po:]==old[po:] and len(patched)==len(old)
        render_mapped(container,ROOT/f'graphics_review/extra8_original_{key}.png');render_mapped(new,ROOT/f'graphics_review/extra8_korean_{key}.png')
        out.append({'resource':key,'data':bytes(patched),'canvas':[tw*8,th*8],'tile_count':oc,'scale':[1,1],'palette_unchanged':True,'outside_text_rectangles_unchanged':True,'text_rectangles':[r[0] for r in rows],'translations':[{'japanese':r[2],'korean':r[1]} for r in rows],'native_labels':native,'changed_pixels':changed})
    return out
def apply(source,rom,alloc,bdf):
    records=[]
    for item in prepare(source,bdf):
        data=item.pop('data');off=int(item['resource'],16);needle=struct.pack('<I',off+0x08000000);refs=[];start=0
        while (ref:=source.find(needle,start))>=0:
            start=ref+1
            if ref%4==0:refs.append(ref)
        assert refs,hex(off);dest=alloc(huffman_fixed4(literal_lz(data)))
        for ref in refs:
            assert rom[ref:ref+4]==needle
            struct.pack_into('<I',rom,ref,dest+0x08000000)
        item['original']=off;item['new']=dest;item['references']=refs;item['decoded_size']=len(data);records.append(item)
    return records
def verify(source,rom,records,bdf):
    expected={x['resource']:x for x in prepare(source,bdf)};assert len(records)==len(expected);allowed=set()
    for item in records:
        want=expected.pop(item['resource']);actual,_=unpack(rom,item['new']);old,_=unpack(source,item['original'])
        assert actual==want['data'] and len(actual)==len(old)==item['decoded_size']
        for ref in item['references']:
            assert struct.unpack_from('<I',source,ref)[0]==item['original']+0x08000000
            assert struct.unpack_from('<I',rom,ref)[0]==item['new']+0x08000000;allowed.update(range(ref,ref+4))
    assert not expected
    return allowed
if __name__=='__main__':
    from build import bdf
    records=prepare((ROOT.parent/'Zero One SP (Japan).gba').read_bytes(),bdf)
    print('선택 화면 이미지',len(records),'직접 번역 이름',sum(len(r['translations']) for r in records))
