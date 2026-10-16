"""원본·현재 ROM을 독립 대조하여 미번역 위치와 추출 누락을 재점검한다."""
from pathlib import Path
import collections,csv,hashlib,json,re,struct
from analyze import iter_scripts,lz10,runs
from graphics_patch import unpack

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'재점검'
JP=re.compile('[ぁ-ゖゝ-ゟァ-ヶヷ-ヺヽ-ヿ㐀-䶿一-鿿豈-﫿々〆]')
KANA=re.compile('[ぁ-ゖゝ-ゟァ-ヶヷ-ヺヽ-ヿ]')
CORE=re.compile('[ぁ-ゖゝ-ゟァ-ヶヷ-ヺヽ-ヿ㐀-䶿一-鿿豈-﫿]')

def read(name):return json.loads((ROOT/name).read_text('utf-8'))
def digest(data):return hashlib.sha256(data).hexdigest()

def aligned_runs(data,start):
    begin=None;letters=[];result=[]
    for off in range(start,len(data)-1,2):
        pair=data[off:off+2][::-1];ch=''
        if 0x81<=pair[0]<=0x9f or 0xe0<=pair[0]<=0xef:
            try:ch=pair.decode('cp932')
            except UnicodeDecodeError:pass
        if len(ch)==1:
            if begin is None:begin=off
            letters.append(ch)
        elif begin is not None:
            result.append((begin,''.join(letters)));begin=None;letters=[]
    if begin is not None:result.append((begin,''.join(letters)))
    return result

def peek_header(rom,off):
    total=int.from_bytes(rom[off+1:off+4],'little')
    if not 32<=total<=0x100000:return None
    out=bytearray();p=off+4
    try:
        while len(out)<16:
            flags=rom[p];p+=1
            for bit in range(7,-1,-1):
                if flags>>bit&1:
                    x,y=rom[p:p+2];p+=2;n=(x>>4)+3;d=((x&15)<<8|y)+1
                    if d>len(out):return None
                    for _ in range(n):
                        out.append(out[-d])
                        if len(out)==16:break
                else:out.append(rom[p]);p+=1
                if len(out)>=16:break
        a,z,b,s=struct.unpack('<4I',out)
        if a==16 and not z%4 and a+z==b and b+s==total and s>0:return total
    except (ValueError,IndexError,struct.error):pass
    return None

def main():
    OUT.mkdir(exist_ok=True)
    source=(ROOT.parent/'Zero One SP (Japan).gba').read_bytes()
    patched=(ROOT.parent/'Zero One SP (Korean).gba').read_bytes()
    build=read('build_report.json');tr=read('translations.json');overrides=read('context_translations.json')
    preserved=read('preserved_resources.json');codes=read('glyph_codes.json');glyphs={v:k for k,v in codes.items()}
    assert digest(source)==build['source_sha256'] and digest(patched)==build['output_sha256']
    for name,expected in build['translation_inputs_sha256'].items():assert digest((ROOT/name).read_bytes())==expected,name
    refs={r['original']:r['new'] for r in build['pointer_changes']}
    fields={(r['resource'],r['offset']):r for r in build['text_changes']}
    def decode(data,endian):
        result=[]
        for p in range(0,len(data),2):
            code=int.from_bytes(data[p:p+2],endian)
            if code in glyphs:result.append(glyphs[code])
            else:
                try:result.append(code.to_bytes(2,'big').decode('cp932'))
                except UnicodeDecodeError:result.append(f'{{{code:04X}}}')
        return ''.join(result)
    def encode(text,endian):
        result=bytearray()
        for ch in text:
            if ch in codes:code=codes[ch]
            else:
                if ch=='·':ch='・'
                if ord(ch)<128:ch=chr(ord(ch)+0xfee0) if ch!=' ' else '　'
                code=int.from_bytes(ch.encode('cp932'),'big')
            result+=code.to_bytes(2,endian)
        return bytes(result)
    remaining=[];resources=[];missed=[];mismatches=[];japanese_in_translations=[];known=set();frequency=collections.Counter();symbol_rows=[]
    for resource in iter_scripts():
        off=resource['rom_offset'];known.add(off);key=f'{off:08X}'
        old,_=lz10(source,off);new,_=lz10(patched,refs.get(off,off));base=struct.unpack_from('<I',old,8)[0]
        assert old[:base]==new[:base]
        original_entries={(e['offset'],e['japanese']) for e in resource['entries'] if e['offset']>=base}
        missed.extend({'resource':key,'offset':p,'japanese':s} for p,s in aligned_runs(old,base) if (p,s) not in original_entries and JP.search(s))
        count=0;examples=[];translated=0
        for entry in resource['entries']:
            p=entry['offset'];size=entry['size'];jp=entry['japanese']
            if p<base or key in preserved:continue
            ko=overrides.get(f'{key}:{p}',{}).get('korean',tr.get(jp))
            actual=decode(new[p:p+size],'little')
            if ko is not None:
                translated+=1;expected=encode(ko+'　'*(len(jp)-len(ko)),'little')
                if expected!=new[p:p+size]:mismatches.append({'resource':key,'offset':p,'japanese':jp,'korean':ko,'actual':actual})
                if JP.search(actual):japanese_in_translations.append({'resource':key,'offset':p,'japanese':jp,'actual':actual})
            elif JP.search(jp):
                if not CORE.search(jp):
                    symbol_rows.append(['기호열',key,f'{refs.get(off,off):08X}',f'{p:08X}',jp,actual,'기호열 보존 검토: 미번역 대사로 집계하지 않음'])
                    continue
                count+=1;frequency[jp]+=1
                row=['본편',key,f'{refs.get(off,off):08X}',f'{p:08X}',jp,actual,'본문 언어 후보']
                remaining.append(row)
                if len(examples)<5:examples.append({'offset':p,'japanese':jp})
        resources.append({'resource':key,'translated':translated,'remaining':count,'preserved_diagnostic':preserved.get(key),'examples':examples})
    # A full aligned ROM sweep, independent of the pointer table inventory.
    structural=[];unlisted=[]
    for off in range(0,len(source)-8,4):
        if source[off]!=0x10 or peek_header(source,off) is None:continue
        try:
            raw,size=lz10(source,off);a,z,base,n=struct.unpack_from('<4I',raw)
            entries=aligned_runs(raw,base);language=[(p,s) for p,s in entries if JP.search(s)]
            row={'resource':f'{off:08X}','compressed_size':size,'language_candidates':len(language),'dialogue_commands':raw.count(b'\x06\x40')}
            structural.append(row)
            if off not in known:
                needle=struct.pack('<I',off+0x08000000);positions=[];p=0
                while (p:=source.find(needle,p))>=0:
                    if not p%4:positions.append(f'{p:08X}')
                    p+=1
                row['references']=positions;row['examples']=[{'offset':p,'japanese':s} for p,s in language[:5]];unlisted.append(row)
        except (ValueError,IndexError,struct.error):pass
    raw_candidates=[];raw_counts={}
    for kind,lo,hi,endian in [('방 조사 대사',0x105058,0x10ffff,'little'),('시스템 문구',0xf9848,0xfc790,'big')]:
        block=source[lo:hi];entries=runs(block) if endian=='little' else []
        if endian=='big':
            for match in re.finditer(rb'(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc])+',block):
                try:jp=match.group().decode('cp932')
                except UnicodeDecodeError:continue
                entries.append({'offset':match.start(),'size':len(match.group()),'japanese':jp})
        counts=collections.Counter()
        for entry in entries:
            jp=entry['japanese'];p=entry['offset'];size=entry['size']
            if not JP.search(jp):continue
            context='room_dialogue' if endian=='little' else 'system_ui'
            field=fields.get((context,p))
            if field:
                expected=encode(field['korean']+'　'*(len(jp)-len(field['korean'])),endian)
                if patched[lo+p:lo+p+size]!=expected:mismatches.append({'resource':context,'offset':lo+p,'japanese':jp})
                continue
            confidence='언어 가능성 높음' if len(KANA.findall(jp))>=2 and len(jp)>=4 else '바이너리 오탐 검토 필요'
            counts[confidence]+=1;actual=decode(patched[lo+p:lo+p+size],endian)
            raw_candidates.append([kind,f'{lo+p:08X}',f'{lo+p:08X}','00000000',jp,actual,confidence])
        raw_counts[kind]=dict(counts)
    # Classify every nested graphics resource, including 8bpp omitted by the old image inventory.
    graphics=[];graphic_counts=collections.Counter();edited={i['original'] for i in build['image_changes']}
    edited.update(part['original'] for item in build.get('split_image_changes', []) for part in item['components'])
    edited.update(part['original'] for item in build.get('extra4_image_changes', []) for part in item['components'])
    edited.update(item['original'] for item in build.get('extra8_image_changes', []))
    supplemental_path=OUT/'이미지검토/추가형식_목록.json'
    supplemental={}
    if supplemental_path.exists():
        supplemental={int(item['resource'],16):item for item in json.loads(supplemental_path.read_text('utf-8'))['classifications']}
    for item in read('nested_graphics_inventory.json'):
        off=item['offset'];kind='미분류';details={}
        try:
            raw,_=unpack(source,off);a,n,p,z,m,ms,_,_=struct.unpack_from('<8I',raw)
            if a==32 and a+n<=len(raw) and p+z<=len(raw) and z%2==0:
                tw,th=struct.unpack_from('<HH',raw,a)
                depth=4 if n-4==tw*th*32 else (8 if n-4==tw*th*64 else None)
                if depth:
                    kind=f'{depth}bpp '+('맵 화면' if ms and m+ms<=len(raw) else '타일 이미지')
                    details={'tile_canvas':[tw*8,th*8],'palette_bytes':z,'map_size':ms}
        except (ValueError,IndexError,struct.error):kind='해제 재검토 필요'
        if kind=='미분류' and off in supplemental:
            extra=supplemental[off]
            assert len(raw)==extra['decoded_size']
            if extra['kind']!='연결 조사':kind=extra['kind']
        graphic_counts[kind]+=1
        graphics.append({'resource':f'{off:08X}','kind':kind,'patched':off in edited,**details})
    with (OUT/'미번역_전체목록.tsv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.writer(file,delimiter='\t');writer.writerow(['구분','원본 자원 또는 주소','현재 자원 또는 주소','자원 내부 위치','원문','현재 표시 문자열','판정']);writer.writerows(remaining);writer.writerows(raw_candidates);writer.writerows(symbol_rows)
    with (OUT/'그래픽_검토목록.tsv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.writer(file,delimiter='\t');writer.writerow(['원본 자원','분류','패치 여부','타일 캔버스','팔레트 바이트','맵 크기'])
        for g in graphics:writer.writerow([g['resource'],g['kind'],g['patched'],g.get('tile_canvas'),g.get('palette_bytes'),g.get('map_size')])
    result={'source_sha256':digest(source),'output_sha256':digest(patched),'script_resources':len(resources),
            'diagnostic_resources_preserved':len(preserved),'main_remaining_language_candidates':len(remaining),
            'main_unique_remaining_strings':len(frequency),'remaining_main_resources':sum(bool(r['remaining']) for r in resources),
            'translated_fields_with_japanese':japanese_in_translations,'translation_byte_mismatches':mismatches,
            'missed_aligned_runs':missed,'independent_structural_scan_count':len(structural),'unlisted_structural_resources':unlisted,
            'raw_candidate_counts':raw_counts,'raw_total_candidates':len(raw_candidates),
            'symbol_only_candidates':symbol_rows,
            'graphics_nested_resources':len(graphics),'graphics_classification':dict(graphic_counts),
            'graphics_unpatched_nested_resources':sum(not g['patched'] for g in graphics),
            'graphics_note':'패치하지 않은 자원이 모두 미번역 이미지를 뜻하지 않는다. 배경·인물 그림·브랜드 로고도 포함하며 시각적 전수 조사는 완료되지 않았다.',
            'resources':resources,'most_frequent_remaining':[{'japanese':s,'occurrences':n} for s,n in frequency.most_common(100)],
            'full_translation_complete':False,'rom_modified':False,'emulator_launched':False}
    confirmed_path=OUT/'확인된_미번역이미지.json'
    if confirmed_path.exists():
        confirmed=json.loads(confirmed_path.read_text('utf-8'))
        if confirmed['rom_sha256']==result['output_sha256']:
            for item in confirmed['resources']:
                off=int(item['resource'],16);_,size=unpack(source,off)
                assert source[off:off+size]==patched[off:off+size]
            result['confirmed_untranslated_image_resources']=len(confirmed['resources'])
            result['confirmed_untranslated_image_categories']=dict(collections.Counter(i['category'] for i in confirmed['resources']))
    review_path=OUT/'이미지검토/목록.json'
    if review_path.exists():
        review=json.loads(review_path.read_text('utf-8'))
        result['mapped_8bpp_screen_previews']=sum(len(p['resources']) for p in review['pages'])
        result['partial_palette_previews']=len(review['partial_palette_previews'])
    (OUT/'재점검_결과.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['resources','most_frequent_remaining']},ensure_ascii=False))

if __name__=='__main__':main()
