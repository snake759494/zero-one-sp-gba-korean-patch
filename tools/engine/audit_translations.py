from pathlib import Path
import sys,json,struct,hashlib
from analyze import iter_scripts,lz10
ROOT=Path(__file__).resolve().parent

def main():
    rom=(ROOT.parent/'Zero One SP (Japan).gba').read_bytes()
    tr=json.loads((ROOT/'translations.json').read_text(encoding='utf-8'))
    ov=json.loads((ROOT/'context_translations.json').read_text(encoding='utf-8'))
    preserve_path=ROOT/'preserved_resources.json'
    preserved_resources=json.loads(preserve_path.read_text(encoding='utf-8')) if preserve_path.exists() else {}
    records=[]
    for r in iter_scripts():
        raw,_=lz10(rom,r['rom_offset']);base=struct.unpack_from('<I',raw,8)[0]
        translated=0;preserved=0;headers=0;left=[];diagnostic=0
        reason=preserved_resources.get(f"{r['rom_offset']:08X}")
        for i,e in enumerate(r['entries']):
            if e['offset']<base:headers+=1;continue
            if reason:diagnostic+=1;continue
            key=f"{r['rom_offset']:08X}:{e['offset']}"
            if key in ov or e['japanese'] in tr:translated+=1
            elif any('ぁ'<=c<='ヶ' or '一'<=c<='龯' for c in e['japanese']):left.append({'index':i,'offset':e['offset'],'japanese':e['japanese']})
            else:preserved+=1
        records.append({'rom_offset':r['rom_offset'],'source_candidate_segments':len(r['entries']),'script_body_offset':base,
                        'translated_segments':translated,'preserved_header_candidates':headers,'preserved_symbols_and_numbers':preserved,
                        'remaining_language_candidates':len(left),'untranslated_examples':left[:5],
                        'preserved_diagnostic_candidates':diagnostic,'preserved_resource_reason':reason,
                        'all_language_candidates_translated':not left and not reason,
                        'all_candidates_accounted':not left,'runtime_full_branch_verified':False})
    report={'original_sha256':hashlib.sha256(rom).hexdigest(),'scripts':records,'fully_translated_candidate_resources':sum(r['all_language_candidates_translated'] for r in records),
            'remaining_candidate_segments':sum(r['remaining_language_candidates'] for r in records),
            'fully_preserved_resources':sum(bool(r['preserved_resource_reason']) for r in records),
            'remaining_language_resources':sum(bool(r['remaining_language_candidates']) for r in records),
            'full_translation_complete':False,'note':'후보에는 본문 중 미식별 매개변수도 포함될 수 있으므로 전체 실제 대사 수나 완성률과 다릅니다.'}
    (ROOT/'translation_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='scripts'},ensure_ascii=False))
    for r in records[:3]:print(json.dumps(r,ensure_ascii=False))
if __name__=='__main__':main()
