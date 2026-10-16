"""최종 화면에서 이름판의 네이티브 갈무리 글자 픽셀을 독립 대조한다."""
from pathlib import Path
import json,struct,hashlib
from PIL import Image
from build import bdf

ROOT=Path(__file__).resolve().parent

def main():
    report=json.loads((ROOT/'build_report.json').read_text('utf-8'))
    atlas=next(i for i in report['image_changes'] if i['original']==0x63bcbc)
    label=next(l for l in atlas['native_labels'] if l['text']=='나고무')
    font=bdf(ROOT/'폰트/Galmuri7.bdf')
    source=(ROOT.parent/'Zero One SP (Japan).gba').read_bytes()
    color=struct.unpack_from('<H',source,0x63bbfc+12)[0]
    expected=tuple(((color>>s)&31)<<3 for s in (0,5,10));found=[]
    captures=json.loads((ROOT/'qa_current_capture_report.json').read_text('utf-8'))
    assert captures['rom_sha256']==report['output_sha256']
    for record in captures['screenshots']:
        path=ROOT/record['file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
        im=Image.open(path);x,top=label['origin'];top=top-32+100;count=0;ok=True
        for ch in label['text']:
            g=font[ord(ch)];gw,gh,xo,yo=g['bbx']
            for sy,row in enumerate(g['rows']):
                for sx in range(gw):
                    if row>>(8*((gw+7)//8)-1-sx)&1:
                        actual=im.getpixel((x+max(xo,0)+sx,top+7-gh-yo+sy))
                        ok&=actual==expected;count+=1
            x+=g['advance']
        if ok:found.append({'file':path.name,'sha256':record['sha256'],'native_glyph_pixels_verified':count})
    assert found,'한글 이름판의 실제 글자 픽셀이 일치하는 화면이 없습니다.'
    result={'rom_sha256':report['output_sha256'],'atlas_offset':'0063BCBC','slot':2,'text':'나고무',
            'font':'Galmuri7','scale':[1,1],'foreground_rgb':expected,'verified_screenshots':found,
            'all_58_nameplates_runtime_verified':False}
    (ROOT/'nameplate_runtime_pixel_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'nameplate_runtime_verified':True,'screenshots':len(found),'native_pixels_per_screen':found[0]['native_glyph_pixels_verified']},ensure_ascii=False))

if __name__=='__main__':main()
