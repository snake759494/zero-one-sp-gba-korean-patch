"""VBA의 실제 이름창 타일을 원본 ROM과 대조한다. 에뮬레이터를 실행하지 않는다."""
from pathlib import Path
import json,struct
from PIL import Image

ROOT=Path(__file__).resolve().parent

def main():
    report=json.loads((ROOT/'build_report.json').read_text('utf-8'))
    prefix=report['output_sha256'][:8];evidence=ROOT/'analysis_evidence'
    io=(evidence/f'name_probe_{prefix}_region4.bin').read_bytes()
    palette=(evidence/f'name_probe_{prefix}_region5.bin').read_bytes()
    vram=(evidence/f'name_probe_{prefix}_region6.bin').read_bytes()
    source=(ROOT.parent/'Zero One SP (Japan).gba').read_bytes()
    colors=[tuple(((c>>s)&31)*255//31 for s in (0,5,10)) for c in struct.unpack('<512H',palette)]
    records=[]
    for bg in range(4):
        control=struct.unpack_from('<H',io,8+bg*2)[0]
        cb=((control>>2)&3)*0x4000;sb=((control>>8)&31)*0x800
        depth=64 if control&128 else 32;size=control>>14
        width=64 if size&1 else 32;height=64 if size&2 else 32
        sx,sy=struct.unpack_from('<HH',io,0x10+bg*4)
        def entry_at(x,y):
            xx=(x+sx)%(width*8);yy=(y+sy)%(height*8);tx=xx//8;ty=yy//8
            pos=sb+((ty//32)*(width//32)+tx//32)*0x800+((ty%32)*32+tx%32)*2
            return struct.unpack_from('<H',vram,pos)[0],xx%8,yy%8
        im=Image.new('RGB',(240,160))
        for y in range(160):
            for x in range(240):
                entry,xx,yy=entry_at(x,y)
                if entry&0x400:xx=7-xx
                if entry&0x800:yy=7-yy
                start=cb+(entry&1023)*depth
                q=start+yy*(8 if depth==64 else 4)+(xx if depth==64 else xx//2)
                value=vram[q] if depth==64 else (vram[q]>>(xx%2*4)&15)
                color=value if depth==64 else (entry>>12)*16+value
                im.putpixel((x,y),colors[color])
        im.save(evidence/f'name_probe_{prefix}_bg{bg}.png')
        tiles=[]
        for x in range(8,65,8):
            entry,_,_=entry_at(x,104);start=cb+(entry&1023)*depth;tile=vram[start:start+depth]
            hits=[];position=0
            if len(set(tile))>2:
                while (position:=source.find(tile,position))>=0 and len(hits)<16:
                    hits.append(position);position+=1
            tiles.append({'screen_x':x,'map_entry':hex(entry),'vram_tile':hex(start),'rom_matches':[hex(p) for p in hits]})
        records.append({'bg':bg,'control':hex(control),'scroll':[sx,sy],'name_row_tiles':tiles})
    (evidence/f'name_probe_{prefix}_tiles.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    oam=(evidence/f'name_probe_{prefix}_region7.bin').read_bytes()
    sprites={}
    for index in range(128):
        a,c,d,_=struct.unpack_from('<4H',oam,index*8)
        if (a&0xff)==100 and (c&0x1ff) in (0,32) and a&0x0c00==0 and a&0x300!=0x200:
            sprites[c&0x1ff]=(a,c,d)
    assert set(sprites)=={0,32},sprites
    assert not (struct.unpack_from('<H',io)[0]&64),'이 분석은 2D OBJ 배치 전용입니다.'
    actual=[]
    for y in range(16):
        for x in range(64):
            a,c,d=sprites[x//32*32];assert not a&0x2000
            tile=(d&1023)+(x%32)//8+(y//8)*32
            q=0x10000+tile*32+y%8*4+(x%8)//2
            actual.append((vram[q]>>(x%2*4))&15)
    patched=(ROOT.parent/'Zero One SP (Korean).gba').read_bytes()
    matches=[]
    for slot in range(60):
        expected=[]
        for y in range(16):
            for x in range(64):
                yy=slot*16+y;q=0x63bcc0+(yy//8*8+x//8)*32+yy%8*4+x%8//2
                expected.append((patched[q]>>(x%2*4))&15)
        if expected==actual:matches.append(slot)
    proof={'rom_sha256':report['output_sha256'],'matching_nameplate_slots':matches,
           'pixels_verified':1024,'pixel_differences':0 if matches else None}
    (evidence/f'name_probe_{prefix}_obj_match.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert matches,'현재 이름판과 OBJ VRAM이 일치하지 않습니다.'
    print(json.dumps(proof,ensure_ascii=False))

if __name__=='__main__':main()
