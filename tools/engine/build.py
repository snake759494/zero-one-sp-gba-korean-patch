"""Deterministic Zero One SP Korean development build; no external translation service."""
from pathlib import Path
import struct,json,hashlib,re
from analyze import lz10,runs,iter_scripts
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'Zero One SP (Japan).gba'
OUTPUT=ROOT.parent/'Zero One SP (Korean).gba'
SOURCE_HASH='662c5efba869d9d37585eb635d36d68e950f54296c7c569c36381379bee410ba'

def bdf(path):
    out={};g=None;bitmap=False
    for l in path.read_text(encoding='utf-8').splitlines():
        if l.startswith('STARTCHAR '):g={'rows':[]};bitmap=False
        elif g is not None:
            if l.startswith('ENCODING '):g['cp']=int(l.split()[1])
            elif l.startswith('DWIDTH '):g['advance']=int(l.split()[1])
            elif l.startswith('BBX '):g['bbx']=tuple(map(int,l.split()[1:]))
            elif l=='BITMAP':bitmap=True
            elif l=='ENDCHAR':out[g['cp']]=g;g=None;bitmap=False
            elif bitmap:g['rows'].append(int(l,16))
    return out

def literal_lz(data):
    return b'\x10'+len(data).to_bytes(3,'little')+b''.join(b'\0'+data[i:i+8] for i in range(0,len(data),8))

def hook(base):
    # A000..CBFF are custom codes, outside original two-byte Shift-JIS.
    # r0 - 9000 yields appended glyph indices beginning at 1000.
    # The original function is replayed for every original code and control.
    words=[0x0a01,0x29a0,0xd308,0x29cc,0xd206,
           0x2100,0x3190,0x0209,0x1a40,0x4770,0x46c0,0x46c0,
           0xb580,0xb081,0x466f,0x1c39,0x4b00,0x4718]
    return struct.pack('<18H',*words)+struct.pack('<I',0x0800fc25)

def build():
    source=SOURCE.read_bytes();assert hashlib.sha256(source).hexdigest()==SOURCE_HASH
    input_paths=[ROOT/name for name in ['translations.json','name_translations.json','context_translations.json','preserved_resources.json','source_inventory.json','split_ui_translations.json','extra8_ui_translations.json','additional_text_translations.json'] if (ROOT/name).exists()]
    input_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in input_paths}
    tr=json.loads((ROOT/'translations.json').read_text(encoding='utf-8'))
    name_tr=json.loads((ROOT/'name_translations.json').read_text(encoding='utf-8'))
    override_path=ROOT/'context_translations.json'
    overrides=json.loads(override_path.read_text(encoding='utf-8')) if override_path.exists() else {}
    preserve_path=ROOT/'preserved_resources.json'
    preserved=json.loads(preserve_path.read_text(encoding='utf-8')) if preserve_path.exists() else {}
    for key,value in overrides.items():
        assert len(value['korean'])<=len(value['japanese']),(key,value)
    for jp,ko in tr.items():
        if len(ko)>len(jp):raise ValueError(f'Translation overflow: {jp} -> {ko}')
    additional=json.loads((ROOT/'additional_text_translations.json').read_text('utf-8'))
    hangul=sorted({ch for s in [*tr.values(),*name_tr.values(),*additional.values(),*(v['korean'] for v in overrides.values())] for ch in s if '가'<=ch<='힣'})
    codes={ch:0xa000+i for i,ch in enumerate(hangul)}
    def encode(t,endian='little'):
        out=bytearray()
        for ch in t:
            if ch in codes:c=codes[ch]
            else:
                # Korean middle dot uses the original CP932 middle-dot glyph.
                if ch=='·':ch='・'
                if ord(ch)<128:ch=chr(ord(ch)+0xfee0) if ch!=' ' else '　'
                c=int.from_bytes(ch.encode('cp932'),'big')
            out+=c.to_bytes(2,endian)
        return bytes(out)
    rom=bytearray(source); changes=[];ref_changes=[]
    def alloc(data):
        while len(rom)%4:rom.append(0xff)
        off=len(rom);rom.extend(data);return off
    def replace_entries(data,entries,context,endian='little'):
        patched=bytearray(data)
        for r in entries:
            jp=r['japanese'];ko=tr.get(jp)
            override=overrides.get(f"{context}:{r['offset']}")
            if override is not None:
                assert override['japanese']==jp,(context,r['offset'])
                ko=override['korean']
            if ko is None:continue
            a=r['offset'];n=r['size'];expected=jp.encode('cp932')
            if endian=='little':expected=b''.join(expected[i:i+2][::-1] for i in range(0,len(expected),2))
            assert data[a:a+n]==expected,(context,a)
            replacement=encode(ko+'　'*(len(jp)-len(ko)),endian)
            assert len(replacement)==n
            patched[a:a+n]=replacement
            changes.append({'resource':context,'offset':a,'japanese':jp,'korean':ko,'size':n})
        assert len(patched)==len(data)
        return bytes(patched)
    source_candidate_count=0
    for r in iter_scripts():
        source_candidate_count+=len(r['entries'])
        off=r['rom_offset'];data,n=lz10(source,off);assert n==r['compressed_size']
        if f'{off:08X}' in preserved:continue
        table_off,table_size,body_off,body_size=struct.unpack_from('<4I',data)
        assert table_off==16 and table_off+table_size==body_off and body_off+body_size==len(data)
        entries=[e for e in r['entries'] if body_off<=e['offset']<body_off+body_size]
        new=replace_entries(data,entries,f'{off:08X}')
        assert new[:body_off]==data[:body_off]
        if new==data:continue
        packed=literal_lz(new);dest=alloc(packed)
        assert lz10(rom,dest)[0]==new
        refs=[];p=0;needle=struct.pack('<I',off+0x08000000)
        while True:
            p=source.find(needle,p)
            if p<0:break
            if p%4==0:refs.append(p)
            p+=1
        assert refs,hex(off)
        for p in refs:
            assert 0x3afb00<=p<0x3b0000 or 0xfd3500<=p<0xfd4000,hex(p)
            struct.pack_into('<I',rom,p,0x08000000+dest)
            ref_changes.append({'reference':p,'original':off,'new':dest})
    # Verified uncompressed room examination dialogue.
    a,z=0x105058,0x10ffff
    rom[a:z]=replace_entries(source[a:z],runs(source[a:z]),'room_dialogue')
    # Name table: relative pointers let Korean full names retain proper spacing.
    # The original 50 entry IDs remain intact; 0x0100 remains the terminator.
    base=0x632f1c;assert struct.unpack_from('<I',source,base)[0]==50
    name_changes=[]
    for idx in range(50):
        ref=base+4+idx*4;off=base+struct.unpack_from('<I',source,ref)[0];end=off
        while source[end:end+2]!=b'\x00\x01':end+=2
        raw=source[off:end];jp=b''.join(raw[i:i+2][::-1] for i in range(0,len(raw),2)).decode('cp932')
        if jp not in name_tr:continue
        ko=name_tr[jp];dest=alloc(encode(ko)+b'\x00\x01')
        struct.pack_into('<I',rom,ref,dest-base)
        name_changes.append({'index':idx,'reference':ref,'original':off,'new':dest,'japanese':jp,'korean':ko})
    # Verified UI range; two-byte big-endian CP932 separated by control bytes.
    a,z=0xf9848,0xfc790;entries=[]
    for m in re.finditer(rb'(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc])+',source[a:z]):
        try:t=m.group().decode('cp932')
        except UnicodeDecodeError:continue
        entries.append({'offset':m.start(),'size':len(m.group()),'japanese':t})
    rom[a:z]=replace_entries(source[a:z],entries,'system_ui','big')
    for p,jp in [(0xf9688,'終　了'),(0xf969c,'特殊演出　　＃０００'),(0xf96b4,'ミニゲーム　＃０００'),(0xf96cc,'ＭＡＰ　　　＃０００'),(0xf96e4,'連続起動　　＃０００')]:
        ko=additional[jp]
        assert source[p:p+len(jp)*2]==jp.encode('cp932') and len(ko)<=len(jp)
        rom[p:p+len(jp)*2]=encode(ko+'　'*(len(jp)-len(ko)),'big')
        changes.append({'resource':'additional_ui','offset':p,'japanese':jp,'korean':ko,'size':len(jp)*2})
    from glossary_text_patch import apply as apply_glossary
    glossary_changes=apply_glossary(source,rom,alloc,encode)
    from graphics_patch import apply_graphics,apply_chapters,apply_ui,apply_raw_ui
    image_changes=apply_graphics(source,rom,alloc,bdf)
    image_changes+=apply_chapters(source,rom,alloc,bdf)
    image_changes+=apply_ui(source,rom,alloc,bdf)
    image_changes+=apply_raw_ui(source,rom,alloc,bdf)
    from split_ui_patch import apply as apply_split_ui
    split_image_changes=apply_split_ui(source,rom,alloc,bdf)
    from extra4_ui_patch import apply as apply_extra4_ui
    extra4_image_changes=apply_extra4_ui(source,rom,alloc,bdf)
    from extra8_ui_patch import apply as apply_extra8_ui
    extra8_image_changes=apply_extra8_ui(source,rom,alloc,bdf)
    glyphs=bdf(ROOT/'폰트/Galmuri11-Condensed.bdf')
    count=(4096+len(codes)+15)//16*16
    height=count//16*2
    font=bytearray(struct.pack('<HH',16,height)+source[0x5e7f80:0x627f80]+b'\x11'*((count-4096)*64))
    for ch,c in codes.items():
        g=glyphs[ord(ch)];w,h,xo,yo=g['bbx'];assert w<=8 and h<=16,(ch,g)
        top=11-h-yo;left=max(0,xo);assert top>=0 and top+h<=16 and left+w<=8,(ch,g)
        index=c-0x9000
        for sy,row in enumerate(g['rows']):
            for sx in range(w):
                if row>>(8*((w+7)//8)-1-sx)&1:
                    x=left+sx;y=top+sy
                    p=4+((index//16)*32+(y//8)*16+(index%16))*32+(y%8)*4+x//2
                    font[p]=(font[p]&~(15<<(4*(x%2))))|(4<<(4*(x%2)))
    fontoff=alloc(font)
    for p in [0x10684,0x2fae8,0xf9610,0xfc10c,0x644040]:
        assert struct.unpack_from('<I',rom,p)[0]==0x085e7f7c
        struct.pack_into('<I',rom,p,0x08000000+fontoff)
    assert rom[0xfc1c:0xfc24]==bytes.fromhex('80 b5 81 b0 6f 46 39 1c')
    hookoff=alloc(hook(len(rom)+0x08000000))
    rom[0xfc1c:0xfc24]=bytes.fromhex('00 4b 18 47')+struct.pack('<I',0x08000000+hookoff+1)
    assert len(rom)<=0x2000000
    used=len(rom);rom.extend(b'\xff'*(0x2000000-len(rom)))
    assert rom[:0xc0]==source[:0xc0]
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==input_hashes[p.name] for p in input_paths),'번역 또는 추출 자료가 빌드 중 변경되었습니다.'
    OUTPUT.write_bytes(rom)
    report={'status':'release_candidate','source_sha256':SOURCE_HASH,'output_sha256':hashlib.sha256(rom).hexdigest(),
            'output_size':len(rom),'used_size':used,'font':'Galmuri11-Condensed v2.40.4 native bitmap','glyph_count':len(codes),
            'font_offset':fontoff,'hook_offset':hookoff,'translated_occurrences':len(changes),
            'source_candidate_segments':source_candidate_count,
            'translation_dictionary_entries':len(tr),'context_translation_entries':len(overrides),'pointer_changes':ref_changes,'name_pointer_changes':name_changes,'text_changes':changes,'image_changes':image_changes,
            'preserved_diagnostic_resources':preserved,'script_resource_count':sum(1 for _ in iter_scripts()),'translation_inputs_sha256':input_hashes,
            'split_image_changes':split_image_changes,'extra4_image_changes':extra4_image_changes,'extra8_image_changes':extra8_image_changes,'glossary_changes':glossary_changes,'additional_text_fields':sum(r['translated_fields'] for r in glossary_changes),'full_translation_complete':False,'runtime_verified':False}
    (ROOT/'build_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'glyph_codes.json').write_text(json.dumps(codes,ensure_ascii=False,indent=2),encoding='utf-8')
    print(OUTPUT);print('Translated occurrences:',len(changes),'Hangul glyphs:',len(codes))

if __name__=='__main__':build()
