"""재배치 생성기와 독립적으로 최종 ROM의 사전 문구와 상대 포인터를 읽는다."""
from pathlib import Path
import json,struct,hashlib,re
ROOT=Path(__file__).resolve().parent
def main():
    source=(ROOT.parent/'Zero One SP (Japan).gba').read_bytes();rom=(ROOT.parent/'Zero One SP (Korean).gba').read_bytes()
    build=json.loads((ROOT/'build_report.json').read_text('utf-8'));codes=json.loads((ROOT/'glyph_codes.json').read_text('utf-8'));glyphs={v:k for k,v in codes.items()}
    assert hashlib.sha256(rom).hexdigest()==build['output_sha256']
    def decode(raw,endian='little'):
        out=''
        for i in range(0,len(raw),2):
            c=int.from_bytes(raw[i:i+2],endian)
            if c in glyphs:out+=glyphs[c]
            else:
                ch=c.to_bytes(2,'big').decode('cp932')
                if 0xff01<=ord(ch)<=0xff5e:ch=chr(ord(ch)-0xfee0)
                if ch=='　':ch=' '
                if ch=='・':ch='·'
                out+=ch
        return out
    fields=variants=titles=references=0;resources=[]
    for item in build['glossary_changes']:
        a=item['original'];b=item['new'];h=struct.unpack_from('<8I',rom,b);oh=struct.unpack_from('<8I',source,a)
        assert h[0]==32 and all(h[i]+h[i+1]==h[i+2] for i in (0,2,4))
        assert source[a+oh[4]:a+oh[4]+oh[5]]==rom[b+h[4]:b+h[4]+h[5]]
        n=struct.unpack_from('<I',rom,b+h[0])[0];titles+=n
        assert n==struct.unpack_from('<I',source,a+oh[0])[0]
        body_targets=[]
        for i in range(n):
            s=struct.unpack_from('<I',rom,b+h[2]+4+i*4)[0]
            old_s=struct.unpack_from('<I',source,a+oh[2]+4+i*4)[0]
            count=struct.unpack_from('<I',rom,b+h[2]+s)[0]
            assert count==struct.unpack_from('<I',source,a+oh[2]+old_s)[0]
            for j in range(count):
                new_t=struct.unpack_from('<I',rom,b+h[2]+s+4+j*4)[0]
                old_t=struct.unpack_from('<I',source,a+oh[2]+old_s+4+j*4)[0]
                assert 0<=new_t<h[7] and rom[b+h[6]+new_t:b+h[6]+new_t+2]==source[a+oh[6]+old_t:a+oh[6]+old_t+2]
                body_targets.append(new_t);variants+=1
        for record in item['records']:
            section=record['section'];p=b+h[section*2]+record['new_offset'];ko=record['korean']
            assert decode(rom[p:p+len(ko)*2])==ko,(hex(a),record)
            assert not re.search('[ぁ-ゖァ-ヶ]',ko)
            fields+=1
        for p in item['references']:
            assert struct.unpack_from('<I',rom,p)[0]==b+0x8000000;references+=1
        resources.append({'original':f'{a:08X}','new':f'{b:08X}','titles':n,'variants':len(body_targets),'fields':len(item['records'])})
    headers=[e for e in build['text_changes'] if e['resource']=='additional_ui']
    assert len(headers)==5
    for e in headers:
        p=e['offset'];assert decode(rom[p:p+e['size']],'big').rstrip()==e['korean']
    assert fields==1540 and titles==198 and references==21
    report={'rom_sha256':build['output_sha256'],'containers':resources,'title_ids_verified':titles,'variant_links_verified':variants,'absolute_references_verified':references,'translated_fields_verified':fields,'developer_menu_fields_verified':len(headers),'remaining_kana_fields':0,'readback_matches':True,'runtime_display_verified':False}
    (ROOT/'재점검/추가본문_최종바이트검증.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
