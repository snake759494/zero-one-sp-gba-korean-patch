import json,struct
from graphics_patch import unpack,mapped_pixels,ui_text,UI_LABELS,ROOT
from build import SOURCE,OUTPUT,bdf
src=SOURCE.read_bytes();fonts={s:bdf(ROOT/('폰트/Galmuri11-Condensed.bdf' if s==11 else f'폰트/Galmuri{s}.bdf')) for s in (7,9,11,14)};old,_=unpack(src,0x8e97bc);new,changed,labels,a,b=ui_text(old,UI_LABELS[0x8e97bc],fonts,0x8e97bc);before=mapped_pixels(old);after=mapped_pixels(new);po,ps=struct.unpack_from('<II',old,8);pal=struct.unpack_from('<'+'H'*(ps//2),old,po);rgb=lambda c:tuple((pal[c]>>s)&31 for s in (0,5,10));points=[]
for y,row in enumerate(before):
 for x,c in enumerate(row):
  if c!=after[y][x]:points.append((x,y,rgb(c)))
minimum=min(color[0] for x,y,color in points);assert minimum>=23,('overlap with original blue pen strokes',minimum)
report=json.loads((ROOT/'build_report.json').read_text(encoding='utf-8'));record=next(i for i in report['image_changes'] if i['original']==0x8e97bc);actual,_=unpack(OUTPUT.read_bytes(),record['new']);assert actual==new
proof={'rom_sha256':report['output_sha256'],'readback_matches':True,'original_resource':'008E97BC','changed_pixels':len(points),'all_added_ink_on_light_paper':True,'minimum_original_red5_at_changed_pixels':minimum,'all_other_pixels_unchanged':True,'original_puzzle_strokes_preserved':True,'native_labels':labels,'script_resource':'00F7205C','script_entry_indices':[1136,1137,1138,1139],'note':'세로 독음 츠무라001과 거울을 통한 가로 독음의 퍼즐을 보존한다. 원래 획을 번역 글자로 덮지 않는다.'};(ROOT/'analysis_evidence/memo_puzzle_preservation.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(proof,ensure_ascii=False))
