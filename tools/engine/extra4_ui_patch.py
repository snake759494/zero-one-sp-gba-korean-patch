"""추가 4bpp 안내창과 작은 표시를 네이티브 글리프로 직접 번역한다."""
from pathlib import Path
import struct,collections,json
from graphics_patch import unpack,ui_text,UI_STYLES,render_mapped,mapped_pixels,huffman_fixed4,literal_lz
ROOT=Path(__file__).resolve().parent
CONFIG={
0xb2b338:{'palette_source':0x4fd4b0,'labels':[([10,11,18,20],'이',7),([8,20,18,44],'런',7),([8,45,18,56],'것',7)],'origins':[12,29,47]},
0xb66e04:{'map':0xb66ee0,'labels':[([8,7,16,16],'기',7),([8,135,16,144],'힘',7)]},
0xb7259c:{'map':0xb72648,'labels':[([12,26,36,36],'힘',7)]},
0xb83c3c:{'map':0xb83d2c,'labels':[([8,7,16,16],'기',7),([8,135,16,144],'힘',7)]},
0xb7887c:{'map':0xb78c54,'labels':[([35,60,210,78],'조회할 번호를 입력하세요.',11),([37,226,209,246],'해제 코드를 입력하세요.',11)]},
0xb7941c:{'map':0xb7a048,'labels':[([13,19,150,39],'잠시 기다려 주세요.',11),([26,67,153,87],'해당 차량이 없습니다!',11),([9,115,153,135],'해당 차량을 찾았습니다!',11),([26,163,153,183],'유효하지 않은 코드!',11),([9,211,153,231],'해제 코드를 접수했습니다!',11)]},
0xb90b04:{'map':0xb90c18,'labels':[([18,33,45,47],'왼쪽',7),([193,33,221,47],'오른쪽',7)]},
0xb9dc90:{'labels':[([0,0,33,16],'신',11),([40,0,80,16],'나고무',11)]},
0xba42b0:{'labels':[([18,8,109,24],'흉기는 어디에?',11)]},
}
def prepare(source,bdf):
    fonts={7:bdf(ROOT/'폰트/Galmuri7.bdf'),11:bdf(ROOT/'폰트/Galmuri11-Condensed.bdf')};records=[]
    # 판독용 회색조를 색 번호에 일대일 대응시킨다. 실제 ROM 팔레트는 수정하지 않는다.
    palette=struct.pack('<256H',*[((i%16)*2)|((i%16)*2<<5)|((i%16)*2<<10) for i in range(256)])
    for off,config in CONFIG.items():
        current_palette=source[config['palette_source']:config['palette_source']+32]*16 if 'palette_source' in config else palette
        old,_=unpack(source,off);standalone='map' not in config
        if standalone:
            tw,th=struct.unpack_from('<HH',old);tiles=old[4:];tm=struct.pack('<HH',tw,th)+struct.pack('<'+'H'*(tw*th),*range(tw*th))
        else:
            tiles=old;tw=len(tiles)//32;th=1;tm,_=unpack(source,config['map'])
        n=4+len(tiles);po=32+n;mo=po+512
        container=struct.pack('<8I',32,n,po,512,mo,len(tm),0,0)+struct.pack('<HH',tw,th)+tiles+current_palette+tm
        pixels=mapped_pixels(container)
        for i,(rect,text,size) in enumerate(config['labels']):
            l,t,r,b=rect;counter=collections.Counter(c%16 for row in pixels[t:b] for c in row[l:r]);bg=counter.most_common(1)[0][0]
            fg=next(c for c,_ in counter.most_common() if c!=bg)
            if off==0xb7941c:fg=1
            if off==0xb90b04:fg=1
            if off==0xb9dc90:fg=2
            UI_STYLES[off,i]={'fg':(fg*2,)*3,'bg':(bg*2,)*3,'solid_bg':True,'no_shadow':True}
            if off==0xb2b338:
                color=struct.unpack_from('<H',current_palette,6)[0]
                UI_STYLES[off,i]={'fg':tuple((color>>s)&31 for s in (0,5,10)),'no_shadow':True,'origin_y':config['origins'][i]}
        new,changed,native,oc,nc=ui_text(container,config['labels'],fonts,off)
        if standalone:
            pix=mapped_pixels(new);data=bytearray(old)
            for y in range(th*8):
                for x in range(0,tw*8,2):
                    q=4+(y//8*tw+x//8)*32+y%8*4+x%8//2;data[q]=(pix[y][x]%16)|((pix[y][x+1]%16)<<4)
            parts=[('bitmap',off,bytes(data))]
        else:parts=[('tiles',off,new[36:po]),('map',config['map'],new[mo:])]
        key=f'{off:08X}';render_mapped(container,ROOT/f'graphics_review/extra4_original_{key}.png');render_mapped(new,ROOT/f'graphics_review/extra4_korean_{key}.png')
        records.append({'resource':key,'native_labels':native,'changed_pixels':changed,'tile_count':oc,'scale':[1,1],'palette_unchanged':True,'parts':parts,'palette_source':config.get('palette_source'),'text_rectangles':[row[0] for row in config['labels']]})
    return records
def apply(source,rom,alloc,bdf):
    records=[]
    for item in prepare(source,bdf):
        components=[]
        for kind,off,data in item.pop('parts'):
            needle=struct.pack('<I',0x08000000+off);refs=[];start=0
            while (ref:=source.find(needle,start))>=0:
                start=ref+1
                if ref%4==0:refs.append(ref)
            assert refs,hex(off);dest=alloc(huffman_fixed4(literal_lz(data)))
            for ref in refs:
                assert rom[ref:ref+4]==needle
                struct.pack_into('<I',rom,ref,0x08000000+dest)
            components.append({'kind':kind,'original':off,'new':dest,'references':refs,'decoded_size':len(data)})
        item['components']=components;records.append(item)
    return records
def verify(source,rom,records,bdf):
    expected={r['resource']:r for r in prepare(source,bdf)};assert len(records)==len(expected);allowed=set()
    for item in records:
        generated=expected.pop(item['resource']);parts={kind:(off,data) for kind,off,data in generated['parts']}
        for part in item['components']:
            off,data=parts[part['kind']];actual,_=unpack(rom,part['new']);original,_=unpack(source,off)
            assert actual==data and len(actual)==len(original)==part['decoded_size']
            for ref in part['references']:
                assert struct.unpack_from('<I',source,ref)[0]==off+0x08000000
                assert struct.unpack_from('<I',rom,ref)[0]==part['new']+0x08000000;allowed.update(range(ref,ref+4))
    assert not expected
    return allowed
if __name__=='__main__':
    from build import bdf
    data=prepare((ROOT.parent/'Zero One SP (Japan).gba').read_bytes(),bdf)
    print('추가 4bpp 직접 번역 렌더링 통과',len(data))
