from pathlib import Path
import json,hashlib,struct
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_SP,UC_ARM_REG_LR
from analyze import lz10,iter_scripts
from build import ROOT,SOURCE,OUTPUT,SOURCE_HASH,bdf

def cpu(data):
    u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u.mem_map(0x08000000,0x2000000);u.mem_write(0x08000000,data)
    u.mem_map(0x02000000,0x40000);return u
def convert(u,c):
    u.reg_write(UC_ARM_REG_SP,0x0203f000);u.reg_write(UC_ARM_REG_LR,0x08001001);u.reg_write(UC_ARM_REG_R0,c)
    u.emu_start(0x0800fc1d,0x08001000,count=1500)
    assert u.reg_read(UC_ARM_REG_SP)==0x0203f000
    return u.reg_read(UC_ARM_REG_R0)

def main():
    original=SOURCE.read_bytes();patched=OUTPUT.read_bytes();report=json.loads((ROOT/'build_report.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(original).hexdigest()==SOURCE_HASH
    assert hashlib.sha256(patched).hexdigest()==report['output_sha256']
    assert original[:0xc0]==patched[:0xc0]
    a=cpu(original);b=cpu(patched)
    codes={0,1,0x100,0xcc00,0xe040,0xe141,0xe2a0,0xeaa4,0xffff,*range(0x4000,0x4100)}
    for r in iter_scripts():
        for e in r['entries']:
            for ch in e['japanese']:
                enc=ch.encode('cp932')
                if len(enc)==2:codes.add(int.from_bytes(enc,'big'))
    # Original supported character range must retain exactly the same mapping.
    checked=0
    for c in sorted(codes):
        if 0xa000<=c<0xcc00:continue
        assert convert(a,c)==convert(b,c),hex(c);checked+=1
    glyphs=json.loads((ROOT/'glyph_codes.json').read_text(encoding='utf-8'))
    for ch,c in glyphs.items():assert convert(b,c)==c-0x9000,(ch,c)
    # Decompressed resources differ only inside explicitly translated fields.
    changed_scripts=0
    by_resource={}
    for e in report['text_changes']:by_resource.setdefault(e['resource'],[]).append(e)
    refs={e['original']:e['new'] for e in report['pointer_changes']}
    for off,dest in refs.items():
        x,_=lz10(original,off);y,_=lz10(patched,dest);assert len(x)==len(y)
        body_off=struct.unpack_from('<I',x,8)[0]
        assert x[:body_off]==y[:body_off]
        allowed=set()
        for e in by_resource[f'{off:08X}']:allowed.update(range(e['offset'],e['offset']+e['size']))
        assert all(p in allowed for p,(s,t) in enumerate(zip(x,y)) if s!=t)
        changed_scripts+=1
    for e in report['pointer_changes']:
        assert struct.unpack_from('<I',patched,e['reference'])[0]==e['new']+0x08000000
    preserved=report.get('preserved_diagnostic_resources',{})
    for key in preserved:
        off=int(key,16);_,size=lz10(original,off)
        assert original[off:off+size]==patched[off:off+size]
    assert patched[0x632f1c:0x632f20]==original[0x632f1c:0x632f20]
    for e in report['name_pointer_changes']:
        assert struct.unpack_from('<I',patched,e['reference'])[0]+0x632f1c==e['new']
        end=e['new']+len(e['korean'])*2
        assert patched[end:end+2]==b'\x00\x01'
    allowed=set(range(0xfc1c,0xfc24))
    for ref in [0x10684,0x2fae8,0xf9610,0xfc10c,0x644040]:allowed.update(range(ref,ref+4))
    for e in [*report['pointer_changes'],*report['name_pointer_changes']]:allowed.update(range(e['reference'],e['reference']+4))
    from graphics_patch import unpack,mapped_pixels,standalone_container
    image_fonts={size:bdf(ROOT/f'폰트/Galmuri{size}.bdf') for size in (7,9,14)}
    image_fonts[11]=bdf(ROOT/'폰트/Galmuri11-Condensed.bdf')
    for image in report.get('image_changes',[]):
        if image.get('layout')=='standalone_bitmap':
            off=image['original'];palette_off=image['standalone_palette']
            x=standalone_container(original,off,palette_off);y=standalone_container(patched,off,palette_off)
            a,n,po,ps=struct.unpack_from('<4I',x)
            assert x[:a+4]==y[:a+4] and x[po:]==y[po:]
            allowed.update(range(off+4,off+n))
        elif image.get('layout')=='uncompressed_bitmap':
            off=image['original'];total=image['decoded_size'];x=original[off:off+total];y=patched[off:off+total]
            a,n,po,ps=struct.unpack_from('<4I',x)
            assert x[:a+4]==y[:a+4] and x[po:]==y[po:]
            allowed.update(range(off+a+4,off+a+n))
        else:x,_=unpack(original,image['original']);y,_=unpack(patched,image['new'])
        if image.get('native_labels'):
            ya,yn,yp,yz=struct.unpack_from('<4I',y)
            palette=struct.unpack_from('<'+'H'*(yz//2),y,yp)
            native_tw,native_th=struct.unpack_from('<HH',y,ya)
            native_bank_size=yz//2 if yn-4==native_tw*native_th*64 else 16
            if image.get('layout') in ('mapped_text','mapped_background'):screen=mapped_pixels(y)
            else:
                tw,th=struct.unpack_from('<HH',y,ya)
                screen=[[(y[ya+4+(yy//8*tw+xx//8)*32+yy%8*4+xx%8//2]>>(xx%2*4))&15 for xx in range(tw*8)] for yy in range(th*8)]
            for label in image['native_labels']:
                size=label['font_size'];font=image_fonts[size];xx,top=label['origin'];color=label['foreground_rgb5']
                for ch in label['text']:
                    if ch==' ':xx+=4 if size<14 else 8;continue
                    glyph=font[ord(ch)];gw,gh,xo,yo=glyph['bbx']
                    for sy,row in enumerate(glyph['rows']):
                        for sx in range(gw):
                            if not row>>(8*((gw+7)//8)-1-sx)&1:continue
                            px=xx+max(0,xo)+sx;py=top+size-gh-yo+sy
                            actual=screen[py][px];bank=actual//native_bank_size
                            if 'foreground_index' in label:
                                assert actual==label['foreground_index'],(image['resource'],label['text'],ch,px,py)
                                continue
                            def distance(index):
                                value=palette[index]
                                return sum((((value>>shift)&31)-target)**2 for shift,target in zip((0,5,10),color))
                            expected=bank*native_bank_size+min(range(native_bank_size),key=lambda c:distance(bank*native_bank_size+c))
                            assert actual==expected,(image['resource'],label['text'],ch,px,py)
                    if label.get('vertical'):top+=size+1
                    else:xx+=glyph['advance']
        if image.get('layout')=='mapped_text':
            assert len(y)==image['decoded_size'] and len(x)==image['original_decoded_size']
            xa,xn,xp,xz,xm,xs,_,_=struct.unpack_from('<8I',x)
            ya,yn,yp,yz,ym,ys,_,_=struct.unpack_from('<8I',y)
            assert x[xp:xp+xz]==y[yp:yp+yz] and xs==ys
            assert len(x)==len(y) and x[:xa+4]==y[:ya+4]
            assert image['original_tile_count']==image['new_tile_count']
            before=mapped_pixels(x);after=mapped_pixels(y);pixels=0
            for yy,row in enumerate(before):
                for xx,c in enumerate(row):
                    if c!=after[yy][xx]:
                        assert any(l<=xx<r and t<=yy<b for l,t,r,b in image['text_rectangles'])
                        pixels+=1
            assert pixels==image['changed_pixels']
            assert image['new_tile_count']<=512
            for ref in image['references']:
                assert struct.unpack_from('<I',patched,ref)[0]==0x08000000+image['new']
                allowed.update(range(ref,ref+4))
            continue
        assert len(x)==len(y)==image['decoded_size']
        a,n,p,z=struct.unpack_from('<4I',x)
        assert x[:a+4]==y[:a+4]
        if image.get('layout')=='mapped_background':
            assert x[p:p+z]==y[p:p+z]
            before=mapped_pixels(x);after=mapped_pixels(y)
            l,t,r,bottom=image['text_bounds_screen']
            for yy,row in enumerate(before):
                for xx,pixel in enumerate(row):
                    if pixel!=after[yy][xx]:assert l<=xx<r and t<=yy<bottom
            assert sum(c!=image['background_index'] for row in after for c in row)==image['foreground_pixels']
            for ref in image['references']:
                assert struct.unpack_from('<I',patched,ref)[0]==0x08000000+image['new']
                allowed.update(range(ref,ref+4))
            continue
        assert x[p:]==y[p:]
        width,height=struct.unpack_from('<HH',x,a)
        changed_pixels=0
        for yy in range(height*8):
            for xx in range(width*8):
                q=a+4+(yy//8*width+xx//8)*32+yy%8*4+xx%8//2
                shift=xx%2*4
                if (x[q]>>shift&15)!=(y[q]>>shift&15):
                    assert any(l<=xx<r and t<=yy<b for l,t,r,b in image['text_rectangles'])
                    changed_pixels+=1
        assert changed_pixels==image['changed_pixels']
        for ref in image['references']:
            assert struct.unpack_from('<I',patched,ref)[0]==0x08000000+image['new']
            allowed.update(range(ref,ref+4))
    for e in report['text_changes']:
        base={'room_dialogue':0x105058,'system_ui':0xf9848,'additional_ui':0}.get(e['resource'])
        if base is not None:allowed.update(range(base+e['offset'],base+e['offset']+e['size']))
    from split_ui_patch import verify as verify_split_ui
    allowed.update(verify_split_ui(original,patched,report.get('split_image_changes',[]),bdf))
    from extra4_ui_patch import verify as verify_extra4_ui
    allowed.update(verify_extra4_ui(original,patched,report.get('extra4_image_changes',[]),bdf))
    from extra8_ui_patch import verify as verify_extra8_ui
    allowed.update(verify_extra8_ui(original,patched,report.get('extra8_image_changes',[]),bdf))
    from glossary_text_patch import verify as verify_glossary
    def encode_additional(text):
        out=bytearray()
        for ch in text:
            if ch in glyphs:code=glyphs[ch]
            else:
                if ch=='·':ch='・'
                if ord(ch)<128:ch=chr(ord(ch)+0xfee0) if ch!=' ' else '　'
                code=int.from_bytes(ch.encode('cp932'),'big')
            out+=code.to_bytes(2,'little')
        return bytes(out)
    allowed.update(verify_glossary(original,patched,report.get('glossary_changes',[]),encode_additional))
    differences=[p for p,(s,t) in enumerate(zip(original,patched)) if s!=t]
    assert all(p in allowed for p in differences)
    font=report['font_offset']
    assert patched[font+4:font+4+0x40000]==original[0x5e7f80:0x627f80]
    # Every added pixel equals the BDF bitmap at native scale.
    bf=bdf(ROOT/'폰트/Galmuri11-Condensed.bdf')
    for ch,c in glyphs.items():
        g=bf[ord(ch)];w,h,xo,yo=g['bbx'];top=11-h-yo;idx=c-0x9000
        for yy in range(16):
            for xx in range(8):
                p=font+4+((idx//16)*32+(yy//8)*16+(idx%16))*32+(yy%8)*4+xx//2
                actual=patched[p]>>(4*(xx%2))&15
                sy=yy-top;sx=xx-max(xo,0)
                expected=4 if 0<=sy<h and 0<=sx<w and g['rows'][sy]>>(8*((w+7)//8)-1-sx)&1 else 1
                assert actual==expected,(ch,xx,yy)
    result={'source_sha256':SOURCE_HASH,'output_sha256':report['output_sha256'],'original_codes_checked':checked,
            'hangul_codes_checked':len(glyphs),'compressed_scripts_verified':changed_scripts,
            'native_bitmap_pixel_check':True,'header_unchanged':True,'control_and_branch_bytes_unchanged':True,
            'name_table_entries_verified':len(report['name_pointer_changes']),'name_ids_unchanged':True,
            'original_rom_changed_bytes':len(differences),'original_rom_changes_allowlisted':True,
            'image_resources_verified':len(report.get('image_changes',[])),
            'split_image_resources_verified':len(report.get('split_image_changes',[])),
            'extra4_image_resources_verified':len(report.get('extra4_image_changes',[])),
            'extra8_image_resources_verified':len(report.get('extra8_image_changes',[])),
            'preserved_diagnostic_resources_verified':len(preserved),
            'native_image_glyph_pixel_check':True,'script_headers_preserved':True,
            'glossary_containers_verified':len(report.get('glossary_changes',[])), 'glossary_fields_verified':report.get('additional_text_fields',0),
            'full_translation_complete':False,'runtime_coverage':'별도 runtime_report.json 참조'}
    (ROOT/'validation_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
