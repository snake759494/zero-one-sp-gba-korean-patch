"""옵션 화면의 원본 칸·테두리·팔레트 및 원래 크기 글꼴을 검사한다."""
from pathlib import Path
import json,hashlib,struct,collections
from PIL import Image
from graphics_patch import unpack,mapped_pixels
from build import bdf
ROOT=Path(__file__).resolve().parent
def main():
    report=json.loads((ROOT/'build_report.json').read_text('utf-8'))
    source=(ROOT.parent/'Zero One SP (Japan).gba').read_bytes();rom=(ROOT.parent/'Zero One SP (Korean).gba').read_bytes()
    assert hashlib.sha256(rom).hexdigest()==report['output_sha256']
    item=next(i for i in report['image_changes'] if i['original']==0xbc117c)
    old,_=unpack(source,0xbc117c);new,_=unpack(rom,item['new']);a=mapped_pixels(old);b=mapped_pixels(new)
    rects=item['text_rectangles'];unchanged=changed=0
    for y,row in enumerate(a):
        for x,c in enumerate(row):
            if not any(l<=x<r and t<=y<bot for l,t,r,bot in rects):assert c==b[y][x];unchanged+=1
            if c!=b[y][x]:changed+=1
    labels=item['native_labels'];assert labels[0]['font_size']==11
    for i,label in enumerate(labels[2:6]):
        assert label['origin']==[112+32*i,36]
        assert rects[2+i]==[110+32*i,34,130+32*i,46]
    assert all(l['font_size']==7 and l['foreground_rgb5']==[31,31,31] for l in labels[1:])
    assert item['original_tile_count']==item['new_tile_count'] and item['palette_unchanged']
    po,ps=struct.unpack_from('<2I',old,8);palette=struct.unpack_from('<'+'H'*(ps//2),old,po)
    def rgb(c):return tuple(palette[c]>>shift&31 for shift in (0,5,10))
    fonts={7:bdf(ROOT/'폰트/Galmuri7.bdf'),11:bdf(ROOT/'폰트/Galmuri11-Condensed.bdf')}
    blank_pixels=0
    for i,(rect,label) in enumerate(zip(rects,labels)):
        size=label['font_size'];font=fonts[size];xx,top=label['origin'];points=set()
        for ch in label['text']:
            if ch==' ':xx+=4;continue
            glyph=font[ord(ch)];w,h,xo,yo=glyph['bbx']
            for sy,row in enumerate(glyph['rows']):
                for sx in range(w):
                    if row>>(8*((w+7)//8)-1-sx)&1:points.add((xx+max(xo,0)+sx,top+size-h-yo+sy))
            xx+=glyph['advance']
        if i==0:points|={(x+1,y+1) for x,y in points}
        l,t,r,bot=rect;solid=collections.Counter(rgb(c) for row in a[t:bot] for c in row[l:r]).most_common(1)[0][0]
        for y in range(t,bot):
            for x in range(l,r):
                if (x,y) not in points:
                    expected=rgb(a[y][114]) if i==0 else solid
                    assert rgb(b[y][x])==expected,('잔여 획 또는 줄무늬',i,x,y,rgb(b[y][x]),expected)
                    blank_pixels+=1
    shots=json.loads((ROOT/'qa_current_capture_report.json').read_text('utf-8'))
    assert shots['rom_sha256']==report['output_sha256'] and shots['emulator_closed']
    selected=[x for x in shots['screenshots'] if x['file'].startswith('qa_option_selection_')];assert len(selected)==5
    speeds=[x for x in shots['screenshots'] if x['file'].startswith('qa_option_speed_')];assert len(speeds)==6
    states=set()
    for shot in speeds:
        path=ROOT/shot['file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==shot['sha256']
        im=Image.open(path).convert('RGB');counts=[]
        for i in range(4):
            counts.append(sum(r>180 and 90<g<200 and b<120 for r,g,b in im.crop((110+32*i,34,130+32*i,46)).getdata()))
        assert max(counts)>80;states.add(counts.index(max(counts)))
        for label in labels[2:6]:
            x,y=label['origin']
            for ch in label['text']:
                glyph=fonts[7][ord(ch)];w,h,xo,yo=glyph['bbx']
                for sy,row in enumerate(glyph['rows']):
                    for sx in range(w):
                        if row>>(8*((w+7)//8)-1-sx)&1:
                            assert min(im.getpixel((x+max(xo,0)+sx,y+7-h-yo+sy)))>=240
                x+=glyph['advance']
    assert states=={0,1,2,3},states
    result={'rom_sha256':report['output_sha256'],'user_reference_images':['Zero One SP (Japan)_02.png','Zero One SP (Korean)_01.png'],'body_font_native_size':7,'title_font_native_size':11,'scale':[1,1],'outside_text_pixels_unchanged':unchanged,'changed_pixels':changed,'original_palette_preserved':True,'original_tile_capacity_preserved':True,'selected_rows_captured':5,'emulator_closed':True}
    result.update(non_glyph_background_pixels_verified=blank_pixels,no_source_text_residue_or_erasure_stripes=True)
    result.update(speed_cell_centers=[120,152,184,216],speed_label_origins=[112,144,176,208],all_four_speed_highlights_verified=True,speed_runtime_glyph_pixels_verified=True)
    (ROOT/'재점검/옵션_레이아웃_검증.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
