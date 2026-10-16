"""사건·인물·용어 사전의 네 구역과 상대 포인터를 보존하며 재배치한다."""
from pathlib import Path
import json,struct,hashlib
from analyze import runs
ROOT=Path(__file__).resolve().parent
BASES=(0x62f3a4,0x632efc,0x635d0c)
def prepare(source,base,encode):
    translations=json.loads((ROOT/'additional_text_translations.json').read_text('utf-8'))
    names=json.loads((ROOT/'name_translations.json').read_text('utf-8'))
    h=struct.unpack_from('<8I',source,base)
    assert h[0]==32 and all(h[i]+h[i+1]==h[i+2] for i in (0,2,4))
    old=[source[base+h[i]:base+h[i]+h[i+1]] for i in (0,2,4,6)]
    sections=list(old);maps={};records=[]
    for section in (0,3):
        block=old[section];out=bytearray();last=0;edits=[]
        start=4+struct.unpack_from('<I',block)[0]*4 if section==0 else 0
        for e in runs(block):
            p=e['offset'];jp=e['japanese']
            if p<start:continue
            assert jp in translations,(hex(base),jp)
            ko=names.get(jp,translations[jp]) if section==0 else translations[jp]
            out+=block[last:p];newp=len(out);replacement=encode(ko)
            out+=replacement;last=p+e['size']
            edits.append((p,last,newp,len(out)))
            records.append({'section':section,'original_offset':p,'new_offset':newp,'japanese':jp,'korean':ko})
        out+=block[last:]
        def mapper(p,edits=edits):
            delta=0
            for a,z,b,w in edits:
                if p<a:break
                if p==a:return b
                assert p>=z,('pointer inside text',p,a,z)
                delta=w-z
            return p+delta
        maps[section]=mapper
        if section==0:
            n=struct.unpack_from('<I',block)[0]
            for i in range(n):
                p=4+i*4;target=struct.unpack_from('<I',block,p)[0]
                struct.pack_into('<I',out,p,mapper(target))
        while len(out)%4:out.append(0)
        sections[section]=bytes(out)
        # Every command, line break, and terminator outside translated fields is copied.
        last_old=last_new=0
        for a,z,b,w in edits:
            if section==3:assert block[last_old:a]==out[last_new:b]
            last_old,last_new=z,w
        if section==3:assert block[last_old:]==out[last_new:last_new+len(block)-last_old]
    table=bytearray(old[1]);n=struct.unpack_from('<I',table)[0]
    for i in range(n):
        p=struct.unpack_from('<I',table,4+i*4)[0];count=struct.unpack_from('<I',table,p)[0]
        assert p+4+count*4<=len(table)
        for j in range(count):
            ref=p+4+j*4;target=struct.unpack_from('<I',table,ref)[0]
            struct.pack_into('<I',table,ref,maps[3](target))
    sections[1]=bytes(table);assert sections[2]==old[2]
    header=[];out=bytearray(32)
    for block in sections:header.extend((len(out),len(block)));out+=block
    struct.pack_into('<8I',out,0,*header)
    return bytes(out),records
def apply(source,rom,alloc,encode):
    result=[]
    for base in BASES:
        data,records=prepare(source,base,encode);dest=alloc(data)
        needle=struct.pack('<I',base+0x08000000)
        refs=[p for p in range(0,len(source),4) if source[p:p+4]==needle]
        assert len(refs)==7,(hex(base),refs)
        for p in refs:struct.pack_into('<I',rom,p,dest+0x08000000)
        result.append({'original':base,'new':dest,'references':refs,'size':len(data),'translated_fields':len(records),'records':records,'sha256':hashlib.sha256(data).hexdigest()})
    return result
def verify(source,rom,records,encode):
    allowed=set()
    assert len(records)==3
    for r in records:
        expected,fields=prepare(source,r['original'],encode)
        assert fields==r['records'] and rom[r['new']:r['new']+r['size']]==expected
        for p in r['references']:
            assert struct.unpack_from('<I',rom,p)[0]==r['new']+0x08000000
            allowed.update(range(p,p+4))
    return allowed
