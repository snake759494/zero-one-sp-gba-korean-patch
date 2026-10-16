"""Native Galmuri title graphics; BIOS Huffman then LZ10 container codec."""
from pathlib import Path
import json,struct,hashlib
from analyze import lz10
ROOT=Path(__file__).resolve().parent

def huffman(data,off=0,limit=None):
    bits=data[off]&15
    if data[off] not in (0x24,0x28):raise ValueError('Huffman header')
    total=int.from_bytes(data[off+1:off+4],'little')
    if not 1<=total<=0x100000:raise ValueError('Huffman output size')
    n=min(total,limit) if limit else total
    tree=off+4;size=(data[tree]+1)*2;stream=tree+size;node=1
    out=bytearray();acc=0;shift=0;word=0;left=0;steps=0
    while len(out)<n:
        steps+=1
        if steps>n*64+128:raise ValueError('Huffman depth')
        if not left:word=struct.unpack_from('<I',data,stream)[0];stream+=4;left=32
        direction=word>>31;word=word<<1&0xffffffff;left-=1
        desc=data[tree+node];child=(node&~1)+((desc&63)+1)*2+direction
        if child>=size:raise ValueError('Huffman tree')
        if desc&(0x80>>direction):
            val=data[tree+child]
            if bits==4:
                if val>15:raise ValueError('Huffman nibble')
                acc|=val<<shift;shift+=4
                if shift==8:out.append(acc);acc=0;shift=0
            else:out.append(val)
            node=1
        else:node=child
    return bytes(out),stream-off

def huffman_fixed4(data):
    # Balanced 16-symbol tree. Every original nibble is encoded at native width.
    data=bytes(data)
    assert len(data)%4==0
    tree=bytearray(32);tree[0]=15
    for i in range(1,16):tree[i]=((2*i-(i&~1)-2)//2)|(0xc0 if i>=8 else 0)
    tree[16:32]=bytes(range(16))
    bits=bytes((x>>4)|((x&15)<<4) for x in data)
    stream=b''.join(bits[i:i+4][::-1] for i in range(0,len(bits),4))
    result=b'\x24'+len(data).to_bytes(3,'little')+tree+stream
    assert huffman(result)[0]==data
    return result

def literal_lz(data):
    result=b'\x10'+len(data).to_bytes(3,'little')+b''.join(b'\0'+data[i:i+8] for i in range(0,len(data),8))
    return result+b'\0'*(-len(result)%4)

def unpack(rom,off):
    stage,n=huffman(rom,off)
    decoded,_=lz10(stage,0)
    return decoded,n

def render(data,path):
    from PIL import Image
    a,n,p,z=struct.unpack_from('<4I',data);w,h=struct.unpack_from('<HH',data,a)
    palette=[tuple(((c>>s)&31)*255//31 for s in (0,5,10)) for c in struct.unpack_from('<16H',data,p)]
    im=Image.new('RGB',(w*8,h*8))
    for y in range(h*8):
        for x in range(w*8):
            q=a+4+(y//8*w+x//8)*32+y%8*4+x%8//2
            im.putpixel((x,y),palette[data[q]>>(x%2*4)&15])
    im.save(path)

def title_menu(original,glyphs):
    data=bytearray(original);image_off,image_size,paloff,palsize=struct.unpack_from('<4I',data)
    w,h=struct.unpack_from('<HH',data,image_off);assert (w,h)==(16,14)
    def pixel(x,y,c=None):
        q=image_off+4+(y//8*w+x//8)*32+y%8*4+x%8//2;s=x%2*4
        if c is None:return data[q]>>s&15
        data[q]=(data[q]&~(15<<s))|(c<<s)
    def advance(ch):return 4 if ch==' ' else 8
    def text(t,x,y,shadow=None):
        points=[]
        for ch in t:
            if ch!=' ':
                g=glyphs[ord(ch)];gw,gh,xo,yo=g['bbx'];assert gw<=8 and gh<=7
                for sy,row in enumerate(g['rows']):
                    for sx in range(gw):
                        if row>>(8*((gw+7)//8)-1-sx)&1:points.append((x+max(0,xo)+sx,y+7-gh-yo+sy))
            x+=advance(ch)
        if shadow is not None:
            for xx,yy in points:pixel(xx+1,yy+1,shadow)
        for xx,yy in points:pixel(xx,yy,11)
    labels=[(0,0,'게임 시작',1),(64,0,'처음부터',1),(0,16,'설정',1),(64,16,'이어하기',1),
            (0,32,'보너스',1),(64,32,'처음부터',5),(0,48,'게임 시작',5),(64,48,'이어하기',5),
            (0,64,'설정',5),(0,80,'보너스',5)]
    rectangles=[];native=[]
    for x,y,t,bg in labels:
        rect=[x+7,y+4,x+57,y+12];rectangles.append(rect)
        for yy in range(rect[1],rect[3]):
            for xx in range(rect[0],rect[2]):pixel(xx,yy,bg)
        width=sum(advance(ch) for ch in t)
        origin=[x+(64-width)//2,y+4]
        text(t,*origin,4 if bg==1 else 9)
        native.append({'text':t,'font_size':7,'origin':origin,'foreground_rgb5':[31,31,31]})
    # Preserve A/B icons and their positions; replace only their label pixels.
    for rect,label in [([11,97,26,104],'확인'),([35,97,61,104],'취소')]:
        rectangles.append(rect)
        for yy in range(rect[1],rect[3]):
            for xx in range(rect[0],rect[2]):pixel(xx,yy,0)
        text(label,rect[0],rect[1])
        native.append({'text':label,'font_size':7,'origin':rect[:2],'foreground_rgb5':[31,31,31]})
    assert data[:image_off+4]==original[:image_off+4]
    assert data[paloff:]==original[paloff:]
    # Prove all frame, border, palette and unrelated atlas pixels remain exact.
    changed=0
    for y in range(h*8):
        for x in range(w*8):
            q=image_off+4+(y//8*w+x//8)*32+y%8*4+x%8//2
            before=original[q]>>(x%2*4)&15
            if before!=pixel(x,y):
                assert any(a<=x<c and b<=y<d for a,b,c,d in rectangles),(x,y)
                changed+=1
    return bytes(data),rectangles,changed,native

def apply_graphics(source,rom,alloc,bdf_reader):
    font=ROOT/'폰트/Galmuri7.bdf'
    assert hashlib.sha256(font.read_bytes()).hexdigest()=='0ec6b8707e8c47d85995b5b2b507180aed7bcc724792fe5477e998d41f8b075f'
    off=0xbc62d0;old,n=unpack(source,off);new,rectangles,pixels,native=title_menu(old,bdf_reader(font))
    packed=huffman_fixed4(literal_lz(new));assert unpack(packed,0)[0]==new
    dest=alloc(packed);refs=[0x15080,0x1762c,0xf9a14,0xbcb0c8]
    for ref in refs:
        assert struct.unpack_from('<I',source,ref)[0]==0x08000000+off
        assert struct.unpack_from('<I',rom,ref)[0]==0x08000000+off
        struct.pack_into('<I',rom,ref,0x08000000+dest)
    render(old,ROOT/'menu_atlas_original.png');render(new,ROOT/'menu_atlas_korean.png')
    return [{'resource':'title_menu','original':off,'new':dest,'references':refs,'original_compressed_size':n,'new_compressed_size':len(packed),
             'decoded_size':len(new),'tile_dimensions':[16,14],'font':'Galmuri7 native 7px bitmap','scale':[1,1],
             'palette_unchanged':True,'outside_text_rectangles_unchanged':True,'text_rectangles':rectangles,'changed_pixels':pixels,'native_labels':native,
             'codec':'Huffman4 followed by LZ10','runtime_verified':False}]

def mapped_pixels(data):
    from PIL import Image
    a,n,po,ps,mo,ms,_,_=struct.unpack_from('<8I',data)
    tw,th=struct.unpack_from('<HH',data,a)
    bytes_per_tile=64 if n-4==tw*th*64 else 32
    assert n-4==tw*th*bytes_per_tile
    mw,mh=struct.unpack_from('<HH',data,mo)
    assert 0<mw<=256 and 0<mh<=256 and ms==mw*mh*2+4
    out=[]
    for y in range(mh*8):
        row=[]
        for x in range(mw*8):
            entry=struct.unpack_from('<H',data,mo+4+(y//8*mw+x//8)*2)[0]
            xx=7-x%8 if entry&1024 else x%8;yy=7-y%8 if entry&2048 else y%8
            q=a+4+(entry&1023)*bytes_per_tile+(yy*8+xx if bytes_per_tile==64 else yy*4+xx//2)
            assert a+4<=q<a+n
            row.append(data[q] if bytes_per_tile==64 else (data[q]>>(xx%2*4)&15)+((entry>>12)*16))
        out.append(row)
    return out

def render_mapped(data,path):
    from PIL import Image
    pix=mapped_pixels(data);po=struct.unpack_from('<I',data,8)[0]
    count=struct.unpack_from('<I',data,12)[0]//2
    palette=[tuple(((c>>s)&31)*255//31 for s in (0,5,10)) for c in struct.unpack_from('<'+'H'*count,data,po)]
    im=Image.new('RGB',(len(pix[0]),len(pix)))
    im.putdata([palette[c] for row in pix for c in row]);im.save(path)

def chapter_title(original,text,glyphs):
    data=bytearray(original);pix=mapped_pixels(original)
    width=len(pix[0]);height=len(pix);assert (width,height)==(240,160)
    palette_off=struct.unpack_from('<I',original,8)[0]
    palette=struct.unpack_from('<16H',original,palette_off)
    bg=pix[0][0]
    coords=[(x,y) for y,row in enumerate(pix) for x,c in enumerate(row) if palette[c]!=palette[bg]]
    bbox=[min(x for x,y in coords),min(y for x,y in coords),max(x for x,y in coords)+1,max(y for x,y in coords)+1]
    x0=(bbox[0]+bbox[2]-sum(glyphs[ord(ch)]['advance'] for ch in text))//2;y0=(bbox[1]+bbox[3]-14)//2
    points=[];cursor=x0
    for ch in text:
        g=glyphs[ord(ch)];w,h,xo,yo=g['bbx'];assert w<=16 and h<=14
        for sy,row in enumerate(g['rows']):
            for sx in range(w):
                if row>>(8*((w+7)//8)-1-sx)&1:points.append((cursor+max(0,xo)+sx,y0+14-h-yo+sy))
        cursor+=g['advance']
    for x,y in points:assert bbox[0]<=x<bbox[2] and bbox[1]<=y<bbox[3]
    newpix=[[bg]*width for _ in range(height)]
    for x,y in points:newpix[y][x]=15
    a,n,po,ps,mo,ms,_,_=struct.unpack_from('<8I',data);capacity=(n-4)//32
    blank=struct.unpack_from('<H',original,mo+4)[0]&1023
    blank_data=bytes([bg|(bg<<4)])*32
    assert original[a+4+blank*32:a+4+(blank+1)*32]==blank_data
    tiles={blank_data:blank};used={blank};newtiles={blank:blank_data}
    for ty in range(height//8):
        for tx in range(width//8):
            tile=bytes(newpix[ty*8+yy][tx*8+xx]|newpix[ty*8+yy][tx*8+xx+1]<<4 for yy in range(8) for xx in range(0,8,2))
            if tile not in tiles:
                idx=next(i for i in range(capacity) if i not in used);tiles[tile]=idx;used.add(idx);newtiles[idx]=tile
            struct.pack_into('<H',data,mo+4+(ty*(width//8)+tx)*2,tiles[tile])
    data[a+4:a+n]=bytes(n-4)
    for idx,tile in newtiles.items():data[a+4+idx*32:a+4+(idx+1)*32]=tile
    assert data[:a+4]==original[:a+4] and data[po:po+ps]==original[po:po+ps]
    assert mapped_pixels(data)==newpix
    return bytes(data),bbox,len(points),[x0,y0],bg

CHAPTER_LABELS={0x644d00:('悪夢','악몽'),0x644ff8:('刺客','자객'),0x6452d4:('逃走','도주'),0x645614:('脱出','탈출'),
0x645898:('展開','전개'),0x645bac:('凶悪','흉악'),0x645e9c:('発展','발전'),0x646200:('不死','불사'),
0x6464b4:('狂犬','광견'),0x646774:('奪還','탈환'),0x646adc:('復讐','복수'),0x646e50:('暴走','폭주'),
0x647178:('転送','전송'),0x6474bc:('決戦','결전'),0x64783c:('顛末','전말'),0x647b18:('欠番','결번'),
0x647e5c:('精神','정신'),0x64816c:('破壊','파괴'),0x6484ec:('終結','종결'),0x6488a8:('転生','전생')}

def apply_chapters(source,rom,alloc,bdf_reader):
    font=ROOT/'폰트/Galmuri14.bdf'
    assert hashlib.sha256(font.read_bytes()).hexdigest()=='316afc1e7b48abf3bbd261b572148610a5fcad9da8e96a7c9de7e910af973bf4'
    glyphs=bdf_reader(font);records=[];review=ROOT/'graphics_review';review.mkdir(exist_ok=True)
    for off,(japanese,korean) in CHAPTER_LABELS.items():
        old,n=unpack(source,off);new,bbox,pixels,position,bg=chapter_title(old,korean,glyphs)
        packed=huffman_fixed4(literal_lz(new));assert unpack(packed,0)[0]==new
        needle=struct.pack('<I',0x08000000+off);refs=[];start=0
        while (r:=source.find(needle,start))>=0:
            start=r+1
            if r%4==0:refs.append(r)
        assert refs,(hex(off),'chapter references')
        dest=alloc(packed)
        for ref in refs:
            assert struct.unpack_from('<I',rom,ref)[0]==off+0x08000000
            struct.pack_into('<I',rom,ref,dest+0x08000000)
        render_mapped(old,review/f'chapter_screen_{off:08X}.png');render_mapped(new,review/f'chapter_korean_{off:08X}.png')
        records.append({'resource':'chapter_title','original':off,'new':dest,'references':refs,'japanese':japanese,'korean':korean,
                        'original_compressed_size':n,'new_compressed_size':len(packed),'decoded_size':len(new),'layout':'mapped_background',
                        'canvas':[240,160],'text_bounds_screen':bbox,'font_origin':position,'foreground_pixels':pixels,'background_index':bg,
                        'font':'Galmuri14 native 14px bitmap','scale':[1,1],'palette_unchanged':True,
                        'native_labels':[{'text':korean,'font_size':14,'origin':position,'foreground_rgb5':[31,31,31]}],
                        'outside_text_bounds_unchanged':True,'runtime_verified':False})
    return records

# Rectangles use the decoded original screen's coordinate system, before any game placement.
UI_LABELS={
0x648b88:[([150,8,214,21],'힌트',9)],
0x649038:[([11,10,127,24],'게임 오버 횟수',9),([11,34,127,48],'총 플레이 시간',9),([11,58,127,72],'본 엔딩 수',9),([11,82,127,96],'클리어 등급',9)],
0x6499e0:[([42,10,65,25],'등급',7),([90,10,215,25],'게임 오버 이유',9)],
0xaf78f0:[([8,55,58,64],'SF 어드벤처',7)],
0xba9598:[([6,96,44,109],'남은 수',7),([50,139,60,151],'회',7),([87,107,194,120],'숫자 일치',9),([87,139,194,152],'숫자와 자리 일치',9)],
0xbc117c:[([114,5,222,19],'옵션 설정',9),([17,36,87,46],'대사 속도',7),([104,36,127,46],'느림',7),([140,36,164,46],'보통',7),([176,36,199,46],'빠름',7),([210,36,231,46],'일괄',7),
([17,60,87,70],'효과음 표시',7),([131,60,164,70],'안 함',7),([180,60,205,70],'함',7),
([17,84,87,94],'장면 넘기기',7),([131,84,164,94],'안 함',7),([180,84,205,94],'함',7),
([17,108,87,118],'대사 넘기기',7),([17,132,87,142],'저장 보호',7),([131,132,164,142],'안 함',7),([180,132,205,142],'함',7)],
0xbc68e8:[([52,7,88,24],'이름',9),([98,7,137,24],'사진1',9),([146,7,185,24],'사진2',9),([194,7,233,24],'사진3',9)],
0xbc92a0:[([54,22,187,33],'엔딩 목록',9),([54,46,187,57],'사운드 테스트',9),([54,70,187,81],'이미지 목록',9),([54,94,187,105],'미니게임',9)],
0xbca048:[([38,7,204,28],'사운드 테스트',14)]}
for _off in [0xbb7e98,0xbb8e94,0xbb9f68,0xbbb040,0xbbc110]:UI_LABELS[_off]=[([118,6,221,21],'이미지 목록',9)]
for _off in [0xbc6b80,0xbc7f28]:UI_LABELS[_off]=[([130,6,221,21],'미니게임 목록',9)]
UI_LABELS[0x648b88]=[([138,10,199,25],'힌트',14)]
for _off in [0xbb7e98,0xbb8e94,0xbb9f68,0xbbb040,0xbbc110]:UI_LABELS[_off]=[([116,10,218,25],'이미지 목록',14)]
for _off in [0xbc6b80,0xbc7f28]:UI_LABELS[_off]=[([120,10,218,25],'미니게임목록',14)]
UI_LABELS[0xbc117c][0]=([114,3,222,18],'옵션 설정',11)
UI_LABELS[0xbc117c][6]=([17,60,87,70],'문자 흔들림',7)
# The original option text band has twelve rows. Native Galmuri7
# keeps their bevels and horizontal separators clear in every palette state.
for _i in range(1,len(UI_LABELS[0xbc117c])):
    _rect,_text,_size=UI_LABELS[0xbc117c][_i]
    _l,_t,_r,_b=_rect
    UI_LABELS[0xbc117c][_i]=([_l,_t-2,_r,_b],_text,7)
# Four speed cells are centered at x=120,152,184,216. Keep erasure and
# native 16-pixel labels inside their common 20-pixel rectangular interiors.
for _i,_text in enumerate(('느림','보통','빠름','일괄')):
    _left=110+32*_i
    UI_LABELS[0xbc117c][2+_i]=([_left,34,_left+20,46],_text,7)
UI_LABELS[0xbca048]=[([38,2,205,29],'사운드 테스트',14)]
UI_LABELS[0xbc3114]=[([27,73,90,81],'SF 어드벤처',7)]
UI_LABELS[0xbc68e8]=[([24,12,41,28],'번호',11),([52,12,88,28],'이름',11),([98,12,137,28],'사진1',11),([146,12,185,28],'사진2',11),([194,12,233,28],'사진3',11)]


# Credits retain each original line's center and baseline area. Native BDF only.
CREDIT_TEXT={
0x64ffec:['스태프'],0x6502bc:['메인 캐릭터 디자인','이토 타케히코'],
0x658138:['시나리오','오치 이쿠야'],0x696ec0:['프로그램','이와모토 카즈유키'],
0x69cd90:['그래픽','사카노시타 아키코'],0x6cf1ec:['그래픽','시노하라 켄야'],
0x6d9960:['그래픽 지원','고토 킨지','나가오 카즈아키','오카자키 마사루'],
0x6ec3e8:['사운드','니시다 아키히로'],
0x6ef6ec:['목소리','쿠보타 료코','녹음 협력','주식회사 원즈 컴퍼니'],
0x71cf50:['ZERO ONE 스태프','카타세 토시히로','니시타케 히로키'],
0x73ab94:['총괄 프로듀서','타카하시 야스카즈'],
0x765508:['스크립트 지원','카와다 요시오'],
0x78babc:['품질 관리','하타나카 시게오','마츠다이라 히데타카','요시다 다이스케'],
0x7a9b1c:['개발','유한회사 후키 상회'],0x860a30:['제작·저작','주식회사 후키'],
0x8b3d2c:['끝']}
CREDIT_BOXES={
0x64ffec:[[86,72,154,88]],0x6502bc:[[42,55,169,63],[86,72,155,88]],
0x658138:[[50,53,95,63],[85,72,155,87]],0x696ec0:[[49,53,107,63],[85,72,155,88]],
0x69cd90:[[49,53,118,63],[67,72,173,88]],0x6cf1ec:[[49,53,118,63],[85,72,155,88]],
0x6d9960:[[41,28,158,39],[85,55,154,71],[84,80,153,96],[85,104,154,119]],
0x6ec3e8:[[58,53,102,63],[85,73,155,88]],
0x6ef6ec:[[58,35,91,45],[87,55,157,70],[59,91,104,102],[46,114,200,125]],
0x71cf50:[[49,46,155,56],[84,64,154,80],[85,88,154,104]],
0x73ab94:[[41,53,206,64],[85,72,154,88]],0x765508:[[41,53,146,63],[86,72,156,88]],
0x78babc:[[49,29,94,40],[85,56,155,71],[85,80,155,96],[85,104,154,120]],
0x7a9b1c:[[49,54,71,64],[50,72,192,88]],0x860a30:[[48,54,93,64],[59,73,182,88]],
0x8b3d2c:[[97,74,145,88]]}
for _off,_texts in CREDIT_TEXT.items():
    UI_LABELS[_off]=[]
    for _text,(_l,_t,_r,_b) in zip(_texts,CREDIT_BOXES[_off]):
        _size=7 if _b-_t<=11 else 11
        _width=max(_r-_l,len(_text)*8+4)
        _cx=(_l+_r)//2
        UI_LABELS[_off].append(([_cx-_width//2-2,_t-2,_cx+(_width+1)//2+2,_b+2],_text,_size))
UI_LABELS.update({
0xba6580:[([3,31,173,45],'상대보다 빨리 커맨드를 입력해',11),([3,45,173,61],'상대 체력을 0으로 만들어라!',11)],
0xba9064:[([16,18,160,33],'먼저 빛난 순서대로',11),([16,33,160,47],'버튼을 눌러라!',11),([16,61,160,75],'5문제 맞히면 클리어!',11)],
0xba988c:[([8,18,168,33],'네 자리 암호를 추리하라!',11),([8,33,168,47],'10회 안에 맞혀라!',11),([8,47,168,62],'방향키로 이동,',11),([8,62,168,76],'A 버튼으로 결정!',11)],
0x7f41b8:[([77,9,152,25],'시로의 의식',9),([31,81,67,94],'시로',9)],
0x89bac4:[([112,13,142,28],'정보',9),([180,28,201,44],'뇌',11),([108,96,151,106],'개념도',7)],
0x89d654:[([10,52,23,76],'키요타',7),([103,54,132,72],'의식',9),([188,96,231,106],'개념도',7)],
0x89f6b8:[([84,16,159,32],'시로의 의식',9),([7,61,20,85],'키요타',7),([113,41,129,102],'키요타의정보',7)]})
for _off in (0x64ffec,0x8b3d2c):UI_LABELS[_off]=[(rect,text,14) for rect,text,size in UI_LABELS[_off]]
UI_STYLES={
(0x7f41b8,0):{'fg':(0,0,0),'shadow':(31,31,31)},
(0x7f41b8,1):{'fg':(0,0,0),'shadow':(0,0,0)},
(0x89bac4,0):{'fg':(0,0,0),'shadow':(31,31,31),'bg':(30,19,22)},
(0x89bac4,1):{'fg':(0,0,0),'shadow':(31,31,31)},
(0x89bac4,2):{'fg':(0,0,0),'shadow':(31,31,31)},
(0x89d654,0):{'fg':(0,0,0),'shadow':(31,31,31),'vertical':True,'solid_bg':True,'bg':(31,31,31)},
(0x89d654,1):{'fg':(31,31,31),'shadow':(0,0,0),'bg':(0,10,29)},
(0x89d654,2):{'fg':(0,0,0),'shadow':(31,31,31),'column_bg':True},
(0x89f6b8,0):{'fg':(0,0,0),'shadow':(31,31,31)},
(0x89f6b8,1):{'fg':(0,0,0),'shadow':(31,31,31),'vertical':True,'solid_bg':True,'bg':(31,31,31)},
(0x89f6b8,2):{'fg':(0,0,0),'shadow':(31,31,31),'vertical':True,'solid_bg':True,'bg':(20,20,20)}}


# Native-size scenery lettering: retain the plaques, red sign and surroundings.
UI_LABELS[0x7768b8]=[([183,19,207,29],'여자',7),([183,29,207,39],'탈의실',7)]
UI_LABELS[0x7b74d4]=[([113,33,154,46],'도톤보리',7)]
UI_STYLES[(0x7768b8,0)]={'fg':(8,8,8),'shadow':(28,28,28),'solid_bg':True,'bg':(30,30,30)}
UI_STYLES[(0x7768b8,1)]={'fg':(8,8,8),'shadow':(28,28,28),'solid_bg':True,'bg':(30,30,30)}
UI_STYLES[(0x7b74d4,0)]={'fg':(31,31,31),'shadow':(25,0,0),'solid_bg':True,'bg':(31,0,0)}


# The memo is a mirror-reading puzzle: preserve its original ambiguous pen strokes.
UI_LABELS[0x8e97bc]=[([157,54,181,64],'츠무라',7),([157,64,181,74],'001',7)]
UI_STYLES[(0x8e97bc,0)]={'fg':(13,21,24),'shadow':(13,21,24),'preserve_background':True,'no_shadow':True}
UI_STYLES[(0x8e97bc,1)]={'fg':(13,21,24),'shadow':(13,21,24),'preserve_background':True,'no_shadow':True}
# Reconstruct only the prominent prohibition on the left warning board.
UI_LABELS[0x7fe708]=[([97,51,109,87],'출입금지',7)]
UI_LABELS[0x72e4fc]=[([9,18,19,31],'역',9)]
UI_STYLES[(0x72e4fc,0)]={'fg':(29,30,31),'bg':(6,10,28),'solid_bg':True,'no_shadow':True}
UI_STYLES[(0x7fe708,0)]={'fg':(24,3,3),'shadow':(24,3,3),'vertical':True,'solid_bg':True,'bg':(30,30,28),'no_shadow':True}

# 접수 표지는 기존 세로 칸 안에 갈무리7 원본 글리프로 배치한다.
UI_LABELS[0x9212a0]=[([26,79,38,104],'접수',7)]
UI_STYLES[(0x9212a0,0)]={'fg':(8,8,8),'shadow':(8,8,8),'vertical':True,'solid_bg':True,'bg':(29,29,28),'no_shadow':True}
UI_LABELS[0x9485dc]=[([179,10,201,31],'라멘',7)]
UI_STYLES[(0x9485dc,0)]={'fg':(24,5,2),'shadow':(24,5,2),'solid_bg':True,'bg':(30,29,24),'no_shadow':True}


# Native-size vertical labels on the two legible red restaurant signs.
UI_LABELS[0x7bbe38]=[([16,0,28,43],'즈보라야',7),([31,0,40,43],'복어요리',7),([59,13,70,55],'쿠이다오레',7)]
for _i in (0,1,2):
    UI_STYLES[(0x7bbe38,_i)]={'fg':(31,30,26),'shadow':(31,30,26),'vertical':True,'solid_bg':True,'bg':(25,7,5),'no_shadow':True}

def ui_text(original,labels,fonts,resource_offset,reserved_tiles=()):
    import collections
    pix=mapped_pixels(original);newpix=[row[:] for row in pix]
    a,n,po,ps,mo,ms,_,_=struct.unpack_from('<8I',original)
    assert a==32 and po==a+n and mo==po+ps and len(original)==mo+ms
    palette=struct.unpack_from('<'+'H'*(ps//2),original,po)
    tilew,tileh=struct.unpack_from('<HH',original,a)
    bytes_per_tile=64 if n-4==tilew*tileh*64 else 32
    bank_size=ps//2 if bytes_per_tile==64 else 16
    def rgb(c):return tuple(((palette[c]>>s)&31) for s in (0,5,10))
    def nearest(color,bank):return bank*bank_size+min(range(bank_size),key=lambda c:sum((u-v)**2 for u,v in zip(rgb(bank*bank_size+c),color)))
    native=[]
    for label_index,(rect,text,font_size) in enumerate(labels):
        style=dict(UI_STYLES.get((resource_offset,label_index),{}));vertical=style.get('vertical',False)
        if resource_offset==0xbc117c and label_index>0:
            style.update(fg=(31,31,31),no_shadow=True,solid_bg=True)
        if resource_offset in CREDIT_TEXT or resource_offset in (0xba6580,0xba9064,0xba988c,0x7f41b8,0x89bac4,0x89d654,0x89f6b8):style['solid_bg']=True
        l,t,r,bottom=rect;font=fonts[font_size];bgrows={};ink=collections.Counter()
        assert 0<=l<r<=len(pix[0]) and 0<=t<bottom<=len(pix)
        for y in range(t,bottom):
            colors=collections.Counter(rgb(c) for c in pix[y][l:r]);bg=colors.most_common(1)[0][0];bgrows[y]=bg
            if resource_offset==0xbc68e8:bg=(0,0,0);bgrows[y]=bg
            for c in pix[y][l:r]:
                if rgb(c)!=bg:ink[rgb(c)]+=1
        if style.get('solid_bg'):
            solid=collections.Counter(rgb(c) for row in pix[t:bottom] for c in row[l:r]).most_common(1)[0][0]
            if resource_offset in CREDIT_TEXT:solid=rgb(pix[0][0])
            if resource_offset in (0xba6580,0xba9064,0xba988c):solid=rgb(pix[8][8])
            solid=style.get('bg',solid)
            bgrows={y:solid for y in range(t,bottom)}
        if resource_offset==0xbc117c and label_index==0:
            for y in range(t,bottom):
                light=collections.Counter(rgb(c) for c in pix[y][l:r] if rgb(c)[0]>=23 and rgb(c)[2]>=25)
                if light:bgrows[y]=light.most_common(1)[0][0]
        assert ink,('No source text ink',text,rect)
        fg=ink.most_common(1)[0][0]
        shadow=ink.most_common(2)[1][0] if len(ink)>1 else fg
        header=resource_offset in [0x648b88,0xbb7e98,0xbb8e94,0xbb9f68,0xbbb040,0xbbc110,0xbc6b80,0xbc7f28] or text=='옵션 설정'
        if header:fg=(10,9,17);shadow=(20,19,23)
        elif resource_offset in (0xbc117c,0xbc92a0):fg=(13,12,18);shadow=(20,19,23)
        elif resource_offset==0xba9598:fg=(0,31,0);shadow=(0,16,0)
        else:fg=(31,31,31);shadow=(16,15,21)
        if resource_offset in CREDIT_TEXT:shadow=fg
        fg=style.get('fg',fg);shadow=style.get('shadow',shadow)
        for y in range(t,bottom):
            choices=collections.Counter(c for c in pix[y][l:r] if rgb(c)==bgrows[y])
            for x in range(l,r):
                current=pix[y][x];bank=current//bank_size
                if style.get('preserve_background'):continue
                if style.get('column_bg'):
                    newpix[y][x]=nearest(rgb(pix[t-2][x]),bank);continue
                if rgb(current)==bgrows[y]:newpix[y][x]=current;continue
                candidates=[c for c in choices if c//bank_size==bank]
                newpix[y][x]=max(candidates,key=choices.get) if candidates else nearest(bgrows[y],bank)
        def advance(ch):return font[ord(ch)]['advance'] if ch!=' ' else (4 if font_size<14 else 8)
        text_width=max(advance(ch) for ch in text) if vertical else sum(advance(ch) for ch in text)
        assert text_width<=r-l,(text,text_width,rect)
        x0=l+(r-l-text_width)//2;y0=t+(bottom-t-((font_size+1)*len(text)-1 if vertical else font_size))//2
        if 'origin_y' in style:y0=style['origin_y']
        if resource_offset==0xbc68e8:
            # Same 8px origins let the three identical photo labels share tiles.
            x0=24 if text=='번호' else (64 if text=='이름' else l+6)
            y0=16
        assert y0>=t
        points=[];x=x0;char_y=y0
        for ch in text:
            if ch!=' ':
                g=font[ord(ch)];gw,gh,xo,yo=g['bbx'];assert gh<=font_size
                for sy,row in enumerate(g['rows']):
                    for sx in range(gw):
                        if row>>(8*((gw+7)//8)-1-sx)&1:points.append((x+max(xo,0)+sx,char_y+font_size-gh-yo+sy))
            if vertical:char_y+=font_size+1
            else:x+=advance(ch)
        for x,y in points:
            assert l<=x<r and t<=y<bottom,(text,x,y,rect)
            if not style.get('no_shadow') and resource_offset not in CREDIT_TEXT and x+1<r and y+1<bottom:newpix[y+1][x+1]=nearest(shadow,pix[y+1][x+1]//bank_size)
        for x,y in points:newpix[y][x]=nearest(fg,pix[y][x]//bank_size)
        native.append({'text':text,'font_size':font_size,'origin':[x0,y0],'foreground_rgb5':list(fg),'vertical':vertical})
    # Reuse tiles that no unchanged map cell references. Never grow VRAM usage.
    tiles=[original[q:q+bytes_per_tile] for q in range(a+4,a+n,bytes_per_tile)]
    old_count=len(tiles);lookup={}
    for i,tile in enumerate(tiles):lookup.setdefault(tile,i)
    tilemap=bytearray(original[mo:mo+ms]);mw,mh=struct.unpack_from('<HH',tilemap)
    reserved=set(reserved_tiles);cells=[];needed={}
    for ty in range(mh):
        for tx in range(mw):
            entry=struct.unpack_from('<H',tilemap,4+(ty*mw+tx)*2)[0]
            if all(newpix[ty*8+y][tx*8+x]==pix[ty*8+y][tx*8+x] for y in range(8) for x in range(8)):
                reserved.add(entry&1023);continue
            bank=entry&0xf000
            if bytes_per_tile==64:
                tile=bytes(newpix[ty*8+y][tx*8+x] for y in range(8) for x in range(8))
            else:
                assert all(newpix[ty*8+y][tx*8+x]//16==bank>>12 for y in range(8) for x in range(8))
                tile=bytes((newpix[ty*8+y][tx*8+x]&15)|((newpix[ty*8+y][tx*8+x+1]&15)<<4) for y in range(8) for x in range(0,8,2))
            cells.append((tx,ty,bank,tile));needed.setdefault(tile,None)
    for tile in needed:
        if tile in lookup:needed[tile]=lookup[tile];reserved.add(lookup[tile])
    free=[i for i in range(old_count) if i not in reserved]
    missing=[tile for tile,index in needed.items() if index is None]
    assert len(missing)<=len(free),('Fixed VRAM tile capacity',hex(resource_offset),len(missing),len(free))
    for tile,index in zip(missing,free):needed[tile]=index;tiles[index]=tile
    for tx,ty,bank,tile in cells:struct.pack_into('<H',tilemap,4+(ty*mw+tx)*2,bank|needed[tile])
    out=bytearray(original);out[a+4:a+n]=b''.join(tiles);out[mo:mo+ms]=tilemap
    assert len(out)==len(original) and out[:a+4]==original[:a+4] and out[po:po+ps]==original[po:po+ps]
    assert mapped_pixels(out)==newpix
    changed=0
    for y,row in enumerate(pix):
        for x,c in enumerate(row):
            if c!=newpix[y][x]:
                assert any(l<=x<r and t<=y<b for (l,t,r,b),_,_ in labels),(x,y)
                changed+=1
    return bytes(out),changed,native,old_count,len(tiles)

def apply_ui(source,rom,alloc,bdf_reader):
    fonts={s:bdf_reader(ROOT/f'폰트/Galmuri{s}.bdf') for s in (7,9,14)}
    fonts[11]=bdf_reader(ROOT/'폰트/Galmuri11-Condensed.bdf')
    records=[];review=ROOT/'graphics_review'
    for off,labels in UI_LABELS.items():
        old,n=unpack(source,off);new,pixels,native,old_count,new_count=ui_text(old,labels,fonts,off)
        packed=huffman_fixed4(literal_lz(new));assert unpack(packed,0)[0]==new
        needle=struct.pack('<I',off+0x08000000);refs=[];start=0
        while (ref:=source.find(needle,start))>=0:
            start=ref+1
            if ref%4==0:refs.append(ref)
        assert refs,hex(off)
        dest=alloc(packed)
        for ref in refs:
            assert struct.unpack_from('<I',rom,ref)[0]==off+0x08000000
            struct.pack_into('<I',rom,ref,dest+0x08000000)
        render_mapped(old,review/f'screen_{off:08X}.png');render_mapped(new,review/f'korean_{off:08X}.png')
        records.append({'resource':'ui_labels','layout':'mapped_text','original':off,'new':dest,'references':refs,
                        'original_compressed_size':n,'new_compressed_size':len(packed),'original_decoded_size':len(old),'decoded_size':len(new),
                        'text_rectangles':[rect for rect,text,size in labels],'native_labels':native,'scale':[1,1],
                        'unchanged_map_tile_indices_preserved':True,'fixed_vram_tile_count':True,'original_tile_count':old_count,'new_tile_count':new_count,
                        'palette_unchanged':True,'outside_text_rectangles_unchanged':True,'changed_pixels':pixels,'runtime_verified':False})
    return records

RAW_UI={
0x627fa0:{'font':11,'background':1,'foreground':4,'shadow':2,'lines':[(0,1,128,'데이터 불러오기 실패'),(0,17,128,'모든 데이터를 초기화합니다.')]},
0x6287e4:{'font':11,'background':1,'foreground':4,'shadow':2,'lines':[(0,1,128,'데이터 불러오기 실패'),(0,17,128,'A 버튼을 눌러 주세요.')]},
0x629028:{'font':11,'background':0,'foreground':4,'shadow':2,'lines':[(0,1,128,'데이터를 불러오는 중입니다.'),(0,17,128,'잠시 기다려 주세요.')]},
0x62986c:{'font':11,'background':1,'foreground':4,'shadow':2,'lines':[(0,1,144,'이 장면은 아직 볼 수 없습니다.'),(0,17,144,'방향키로 선택, A로 결정'),(0,33,144,'B로 종료'),(0,49,144,'이 게임은 아직 할 수 없습니다.'),(0,65,144,'이 모드는 아직 볼 수 없습니다.')]},
0x62b1b0:{'font':7,'background':0,'foreground':3,'lines':[(16,0,144,'시작하려면 START 버튼을 누르세요')],'dynamic_palette':True},
0x62b494:{'font':11,'background':0,'foreground':4,'lines':[(0,3,128,'다음 이야기로 이어집니다')]},
0x62b8d8:{'font':14,'background':0,'foreground':15,'glow':True,'lines':[(0,9,192,'게임 오버')]},
0x62c51c:{'font':14,'background':0,'foreground':15,'shadow':7,'lines':[(0,9,192,'게임 오버')]},
0x6391f8:{'standalone_palette':0x6391d8,'font':7,'background':'row_mode','foreground':4,'shadow':2,
 'lines':[(82,2,30,'시간'),(80,32,48,'시간 표시'),(80,40,48,'시간 표시'),
          (8,84,48,'인물'),(8,100,48,'사건'),(8,116,48,'기타'),
          (72,84,56,'설정'),(72,100,56,'저장'),(72,116,56,'재시도'),
          (12,140,36,'파일1'),(0,160,128,'START 버튼을 누르세요')],
 'backgrounds':[11,11,11,'row_left','row_left','row_left',0,0,0,'row_left',0],
 'foregrounds':[5,5,5,4,4,4,4,4,4,4,5],
 'font_sizes':[7,7,7,7,7,7,11,11,11,7,7],
 'rectangles':[[82,0,112,12],[80,32,128,40],[80,40,128,48],
               [8,82,56,94],[8,98,56,110],[8,114,56,126],
               [72,80,128,96],[72,96,128,112],[72,112,128,128],
               [12,140,48,148],[0,160,128,168]]}}


NAMEPLATES={
0:('キャスター','앵커'),1:('アシスタント','보조진행자'),2:('ナゴム','나고무'),3:('リツコ','리츠코'),
5:('シロー','시로'),6:('男Ａ','남자 A'),7:('男Ｂ','남자 B'),8:('アキス','아키스'),9:('ゼネコ','제네코'),
10:('刑事？','형사?'),11:('大槻','오츠키'),12:('警官Ａ','경관 A'),13:('ツトム','츠토무'),14:('シン','신'),
15:('アイコ','아이코'),16:('アキラ','아키라'),17:('大本','오모토'),18:('ナナセ','나나세'),19:('ゴート','고트'),
20:('刑事Ａ','형사 A'),21:('ケイト','케이트'),22:('秋山','아키야마'),23:('科学班員','과학반원'),24:('カマキリ','사마귀'),
25:('警官Ｂ','경관 B'),26:('三田','미타'),27:('ノブヒコ','노부히코'),28:('ロバート','로버트'),29:('ジーン','진'),
30:('見張り','보초'),31:('ケネス','케네스'),32:('ＳＷＡＴ','특수기동대'),33:('マサシ','마사시'),34:('自衛官','자위관'),
35:('アスカ','아스카'),36:('アナウンス','안내방송'),37:('清田','키요타'),38:('三田の母','미타 어머니'),39:('裁判長','재판장'),
40:('検事','검사'),41:('弁護士','변호사'),42:('刑事Ｂ','형사 B'),43:('クリエーター','크리에이터'),44:('リポーター','리포터'),
45:('ピリ','피리'),46:('アリス','앨리스'),47:('ゲーマー','게이머'),48:('シロー？？','시로??'),49:('ローズ','로즈'),
50:('エイジ','에이지'),51:('トモ','토모'),52:('犬','개'),53:('警備員','경비원'),54:('タイラ','타이라'),
55:('矢追会長','야오이 회장'),56:('ホテルマン','호텔 직원'),57:('高塚','타카츠카'),58:('マイ','마이')}
RAW_UI[0x63bcbc]={'standalone_palette':0x63bbfc,'font':7,'background':'name_template','foreground':6,'shadow':7,
 'lines':[(8,slot*16+4,48,ko) for slot,(jp,ko) in NAMEPLATES.items()],
 'rectangles':[[8,slot*16+3,56,slot*16+13] for slot in NAMEPLATES]}


def standalone_container(rom,off,palette_off):
    tw,th=struct.unpack_from('<HH',rom,off);n=4+tw*th*32
    return struct.pack('<4I',16,n,16+n,32)+rom[off:off+n]+rom[palette_off:palette_off+32]

def apply_raw_ui(source,rom,alloc,bdf_reader):
    fonts={size:bdf_reader(ROOT/f'폰트/Galmuri{size}.bdf') for size in (7,14)}
    fonts[11]=bdf_reader(ROOT/'폰트/Galmuri11-Condensed.bdf');records=[];review=ROOT/'graphics_review'
    for off,config in RAW_UI.items():
        standalone='standalone_palette' in config
        if standalone:old=standalone_container(source,off,config['standalone_palette'])
        else:
            a,n,po,ps=struct.unpack_from('<4I',source,off);old=source[off:off+po+ps]
        a,n,po,ps=struct.unpack_from('<4I',old);total=po+ps;data=bytearray(old)
        tw,th=struct.unpack_from('<HH',old,a);width=tw*8;height=th*8
        font=fonts[config['font']];rectangles=[];native=[];all_points=[]
        def pixel(x,y,color=None):
            q=a+4+(y//8*tw+x//8)*32+y%8*4+x%8//2;shift=x%2*4
            if color is None:return data[q]>>shift&15
            data[q]=(data[q]&~(15<<shift))|(color<<shift)
        # Whole strips are individual original UI resources, including their shadows.
        for line_index,(left,top,available,text) in enumerate(config['lines']):
            size=config.get('font_sizes',[config['font']]*len(config['lines']))[line_index]
            font=fonts[size]
            foreground=config.get('foregrounds',[config['foreground']]*len(config['lines']))[line_index]
            strip_top=(top//16)*16 if height>=32 else 0
            strip_bottom=min(height,strip_top+(16 if height>=32 else height))
            if len(config['lines'])==1:strip_top=0;strip_bottom=height
            rect=config.get('rectangles',[[x,(y//16)*16,x+w,min(height,(y//16)*16+16)] for x,y,w,_ in config['lines']])[line_index] if standalone else [left,strip_top,left+available,strip_bottom]
            rectangles.append(rect)
            for y in range(rect[1],rect[3]):
                background=config.get('backgrounds',[config['background']]*len(config['lines']))[line_index]
                if background=='name_template':
                    # The unused sixtieth plate is the exact unlettered frame.
                    for x in range(rect[0],rect[2]):pixel(x,y,pixel(x,59*16+y%16))
                    continue
                if background=='row_left':background=pixel(rect[0],y)
                if background=='row_mode':
                    import collections
                    background=collections.Counter(pixel(x,y) for x in range(rect[0],rect[2])).most_common(1)[0][0]
                for x in range(rect[0],rect[2]):pixel(x,y,background)
            def advance(ch):return (4 if size<14 else 8) if ch==' ' else font[ord(ch)]['advance']
            text_width=sum(advance(ch) for ch in text);assert text_width<=available,(hex(off),text,text_width,available)
            x0=left+(available-text_width)//2;cursor=x0;points=[]
            for ch in text:
                if ch!=' ':
                    g=font[ord(ch)];gw,gh,xo,yo=g['bbx']
                    for sy,row in enumerate(g['rows']):
                        for sx in range(gw):
                            if row>>(8*((gw+7)//8)-1-sx)&1:points.append((cursor+max(0,xo)+sx,top+size-gh-yo+sy))
                cursor+=advance(ch)
            for x,y in points:assert 0<=x<width and 0<=y<height,(text,x,y)
            all_points.extend(points)
            if config.get('shadow') is not None:
                for x,y in points:
                    if x+1<width and y+1<height:pixel(x+1,y+1,config['shadow'])
            for x,y in points:pixel(x,y,foreground)
            native.append({'text':text,'font_size':size,'origin':[x0,top],'foreground_index':foreground,'foreground_rgb5':[31,31,31]})
        if config.get('glow'):
            # Keep the original blue ramp and canvas; add a halo around native glyph pixels.
            distances={}
            for x,y in all_points:
                for dy in range(-7,8):
                    for dx in range(-7,8):
                        xx=x+dx;yy=y+dy;distance=max(abs(dx),abs(dy))
                        if 0<=xx<width and 0<=yy<height:distances[(xx,yy)]=min(distance,distances.get((xx,yy),99))
            ramp={1:14,2:12,3:10,4:7,5:5,6:3,7:1}
            for (x,y),distance in distances.items():
                if distance:pixel(x,y,ramp[distance])
            for x,y in all_points:pixel(x,y,15)
        assert data[:a+4]==old[:a+4] and data[po:]==old[po:]
        changed=0
        for y in range(height):
            for x in range(width):
                q=a+4+(y//8*tw+x//8)*32+y%8*4+x%8//2
                if old[q]>>(x%2*4)&15!=pixel(x,y):
                    assert any(l<=x<r and t<=y<b for l,t,r,b in rectangles),(hex(off),x,y)
                    changed+=1
        if standalone:rom[off+4:off+n]=data[a+4:a+n]
        else:rom[off:off+total]=data
        render(old,review/f'raw_original_{off:08X}.png');render(data,review/f'raw_korean_{off:08X}.png')
        if config.get('dynamic_palette'):
            preview=bytearray(data);struct.pack_into('<H',preview,po+config['foreground']*2,0x7fff)
            render(preview,review/f'raw_korean_visible_{off:08X}.png')
        records.append({'resource':'uncompressed_ui','layout':'standalone_bitmap' if standalone else 'uncompressed_bitmap','original':off,'new':off,'references':[],
                        'decoded_size':total,'canvas':[width,height],'text_rectangles':rectangles,'native_labels':native,'scale':[1,1],
                        'palette_unchanged':True,'outside_text_rectangles_unchanged':True,'changed_pixels':changed,
                        'dynamic_palette_preserved':bool(config.get('dynamic_palette')),'runtime_verified':False})
        if standalone:records[-1]['standalone_palette']=config['standalone_palette']
        if off==0x63bcbc:
            assert (width,height)==(64,960)
            records[-1]['nameplate_slots']=[{'slot':slot,'japanese':jp,'korean':ko} for slot,(jp,ko) in NAMEPLATES.items()]
            records[-1]['nameplate_ids_unchanged']=True
    return records
