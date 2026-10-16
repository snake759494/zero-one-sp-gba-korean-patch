from pathlib import Path
import re, json, hashlib, struct, collections
ROOT=Path(__file__).resolve().parent
ROM=ROOT.parent/'Zero One SP (Japan).gba'

def iter_scripts():
    """Read one resource at a time from our indented inventory format."""
    with (ROOT/'source_inventory.json').open(encoding='utf-8') as f:
        for line in f:
            if line.strip()=='"compressed_scripts": [':break
        else:raise ValueError('Missing compressed script array')
        lines=[];count=0
        for line in f:
            if line.startswith('  ],'):
                if lines:raise ValueError('Incomplete script inventory object')
                if not count:raise ValueError('Empty script inventory')
                return
            if not lines and not line.strip():continue
            lines.append(line)
            if line.startswith('    }'):
                text=''.join(lines).strip().removesuffix(',')
                resource=json.loads(text)
                assert {'rom_offset','entries','compressed_size'}<=resource.keys()
                count+=1;yield resource;lines=[]
        raise ValueError('Missing script array end')

def lz10(b,off):
    n=int.from_bytes(b[off+1:off+4],'little'); p=off+4; out=bytearray()
    if not 32<=n<=0x100000: raise ValueError('size')
    while len(out)<n:
        flags=b[p];p+=1
        for bit in range(7,-1,-1):
            if flags>>bit&1:
                x,y=b[p:p+2];p+=2; count=(x>>4)+3;distance=((x&15)<<8|y)+1
                if distance>len(out):raise ValueError('distance')
                for _ in range(count):out.append(out[-distance])
            else:out.append(b[p]);p+=1
            if len(out)>=n:break
        if len(out)>n or p-off>n*2+32:raise ValueError('length')
    return bytes(out),p-off

def swapped(b):
    n=len(b)&~1;s=bytearray(b[:n]);s[0::2],s[1::2]=b[1:n:2],b[0:n:2];return bytes(s)

def runs(b):
    s=swapped(b); result=[]
    for m in re.finditer(rb'(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc])+',s):
        if m.start()%2:continue
        try:t=m.group().decode('cp932')
        except UnicodeDecodeError:continue
        result.append({'offset':m.start(),'size':len(m.group()),'japanese':t,'korean':''})
    return result

def main():
    b=ROM.read_bytes();resources=[];addresses=set()
    # Follow both real pointer tables. Greedy scanning can mistake interior bytes
    # for a long LZ stream and skip real resources, including short branch scripts.
    for lo,hi in [(0x3afb00,0x3b0000),(0xfd3500,0xfd4000)]:
        for ref in range(lo,hi,4):
            off=struct.unpack_from('<I',b,ref)[0]-0x08000000
            if 0<=off<len(b)-4 and b[off]==0x10:addresses.add(off)
    for off in sorted(addresses):
        try:
            data,size=lz10(b,off);a,z,p,s=struct.unpack_from('<4I',data)
        except (ValueError,IndexError,struct.error):continue
        if a!=16 or a+z!=p or p+s!=len(data) or z%4:continue
        rr=runs(data)
        if not any(any('ぁ'<=c<='ヶ' for c in r['japanese']) for r in rr):continue
        resources.append({'rom_offset':off,'compressed_size':size,'decoded_size':len(data),'commands':data.count(b'\x06\x40'),'entries':rr})
        print(f'{off:08X}: {size} -> {len(data)}, {len(rr)} entries')
    raw=[]
    for st,en in [(0x105058,0x10ffff),(0x620000,0x670000)]:
        for r in runs(b[st:en]):r['offset']+=st;raw.append(r)
    result={'sha256':hashlib.sha256(b).hexdigest(),'size':len(b),'compressed_scripts':resources,'raw_candidates':raw}
    (ROOT/'source_inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Scripts:',len(resources),'Entries:',sum(len(r['entries']) for r in resources),'Raw candidates:',len(raw))

if __name__=='__main__':main()
