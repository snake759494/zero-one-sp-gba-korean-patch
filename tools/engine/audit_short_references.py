"""짧은 한자 표기도 놓치지 않도록 직접 참조된 원문을 양쪽 순서로 검색한다."""
from pathlib import Path
import json,re,struct,collections,hashlib
from analyze import iter_scripts,swapped
ROOT=Path(__file__).resolve().parent
def main():
    s=(ROOT.parent/'Zero One SP (Japan).gba').read_bytes();p=(ROOT.parent/'Zero One SP (Korean).gba').read_bytes();m=bytearray(s)
    spans=[(x['rom_offset'],x['rom_offset']+x['compressed_size']) for x in iter_scripts()]
    spans += [(x['offset'],x['offset']+x['compressed_size']) for x in json.loads((ROOT/'nested_graphics_inventory.json').read_text('utf-8'))]
    spans += [(0x62f3a4,0x638b80),(0x5e7f7c,0x627f80),(0x10f6c4,0x114fc0)]
    for a,z in spans:m[a:z]=bytes(z-a)
    refs=collections.defaultdict(list)
    for i,(w,) in enumerate(struct.iter_unpack('<I',s)):
        if 0x8000000<=w<0x9000000:refs[w-0x8000000].append(i*4)
    rows=[]
    for endian,data in [('big',m),('little',swapped(m))]:
        for x in re.finditer(rb'(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc])+',data):
            a=x.start();z=x.end()
            if endian=='little' and a%2:continue
            if a not in refs or s[a:z]!=p[a:z]:continue
            try:t=x.group().decode('cp932')
            except UnicodeDecodeError:continue
            if not re.search('[ぁ-ゖァ-ヶ一-鿿]',t):continue
            rows.append({'offset':f'{a:08X}','endian':endian,'source':t,'references':[f'{v:08X}' for v in refs[a]]})
    found={0xf9688:'終　了',0xf969c:'特殊演出　　＃０００',0xf96b4:'ミニゲーム　＃０００',0xf96cc:'ＭＡＰ　　　＃０００',0xf96e4:'連続起動　　＃０００'}
    for a,jp in found.items():assert s[a:a+len(jp)*2]!=p[a:a+len(jp)*2]
    report={'rom_sha256':hashlib.sha256(p).hexdigest(),'newly_translated_menu_fields':5,'remaining_raw_candidates':len(rows),'multiple_character_binary_candidates':[x for x in rows if len(x['source'])>1],'candidates':rows,'note':'원시 포인터 패턴에는 압축·정수·코드의 우연한 값도 포함된다. 번역 문구 여부는 원문 판독 및 자원 구조와 함께 판단한다.'}
    (ROOT/'재점검/직접참조_짧은문구_검색.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('candidates','multiple_character_binary_candidates')},ensure_ascii=False))
if __name__=='__main__':main()
