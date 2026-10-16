"""등록된 압축 자원 밖을 양쪽 바이트 순서로 독립 재검색한다."""
from pathlib import Path
import json,re,hashlib
from analyze import iter_scripts,swapped
ROOT=Path(__file__).resolve().parent
def main():
    source=(ROOT.parent/'Zero One SP (Japan).gba').read_bytes()
    patched=(ROOT.parent/'Zero One SP (Korean).gba').read_bytes()
    spans=[(r['rom_offset'],r['rom_offset']+r['compressed_size']) for r in iter_scripts()]
    graphics=json.loads((ROOT/'nested_graphics_inventory.json').read_text('utf-8'))
    spans += [(r['offset'],r['offset']+r['compressed_size']) for r in graphics]
    spans += [(0x10f6c4,0x114fc0)]
    build=json.loads((ROOT/'build_report.json').read_text('utf-8'))
    relocated=build.get('glossary_changes',[])
    for item in relocated:
        base=item['original'];h=__import__('struct').unpack_from('<8I',source,base)
        spans.append((base,base+h[6]+h[7]))
        assert all(int.from_bytes(patched[p:p+4],'little')==item['new']+0x8000000 for p in item['references'])
    masked=bytearray(source)
    for lo,hi in spans:masked[lo:hi]=bytes(hi-lo)
    pattern=rb'(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]){3,}'
    rows=[]
    for endian,data in [('big',bytes(masked)),('little',swapped(masked))]:
        for m in re.finditer(pattern,data):
            if endian=='little' and m.start()%2:continue
            try:text=m.group().decode('cp932')
            except UnicodeDecodeError:continue
            if len(re.findall('[ぁ-ゖァ-ヶ]',text))<2:continue
            p=m.start();size=len(m.group())
            rows.append({'offset':f'{p:08X}','endian':endian,'text':text,'unchanged':source[p:p+size]==patched[p:p+size]})
    report={'source_sha256':hashlib.sha256(source).hexdigest(),'rom_sha256':hashlib.sha256(patched).hexdigest(),'excluded_compressed_and_verified_relocated_spans':len(spans),'candidate_count':len(rows),'relocated_glossary_containers':len(relocated),'candidates':rows}
    (ROOT/'재점검/목록외_문자열_재검색.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    unchanged=[r for r in rows if r['unchanged']]
    print(json.dumps({'candidates':len(rows),'unchanged':len(unchanged),'unchanged_candidates':unchanged},ensure_ascii=False))
if __name__=='__main__':main()
