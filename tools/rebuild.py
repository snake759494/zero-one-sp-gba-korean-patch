"""공개 자료와 사용자가 준비한 원본으로 릴리즈 ROM을 재현한다."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys
from fetch_fonts import fetch
ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);args=ap.parse_args()
    manifest=json.loads((ROOT/'release_manifest.json').read_text('utf-8'))
    assert digest(args.source)==manifest['files']['source']['sha256'],'원본 ROM SHA-256 불일치'
    fonts=fetch();work=ROOT/'work';engine=work/'한글패치작업';engine.mkdir(parents=True,exist_ok=True)
    for directory in ['폰트','graphics_review','재점검/이미지검토']:(engine/directory).mkdir(parents=True,exist_ok=True)
    shutil.copyfile(args.source,work/manifest['files']['source']['file'])
    for p in (ROOT/'tools/engine').glob('*.py'):shutil.copyfile(p,engine/p.name)
    for p in fonts.glob('*.bdf'):shutil.copyfile(p,engine/'폰트'/p.name)
    def run(name):
        result=subprocess.run([sys.executable,'-X','utf8',str(engine/name)],cwd=work,text=True,encoding='utf-8',stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (work/(name+'.log')).write_text(result.stdout,'utf-8')
        if result.returncode:print(result.stdout);raise SystemExit(result.returncode)
        print(name+': 통과',flush=True)
    run('analyze.py');sys.path.insert(0,str(engine));from analyze import lz10
    rom=args.source.read_bytes();cache={}
    def source(ref):
        resource=ref['resource']
        if resource is None:data=rom
        else:
            if resource not in cache:cache[resource]=lz10(rom,resource)[0]
            data=cache[resource]
        p,n=ref['offset'],ref['size'];raw=data[p:p+n]
        if ref['endian']=='little':raw=b''.join(raw[i:i+2][::-1] for i in range(0,len(raw),2))
        return raw.decode('cp932')
    def write(name,obj):(engine/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n','utf-8')
    for name in ['translations','name_translations','additional_text_translations']:
        rows=json.loads((ROOT/f'translation/{name}.json').read_text('utf-8'));write(name+'.json',{source(row['source']):row['korean'] for row in rows})
    rows=json.loads((ROOT/'translation/context_translations.json').read_text('utf-8'));write('context_translations.json',{key:{'japanese':source(row['source']),'korean':row['korean']} for key,row in rows.items()})
    for name in ['preserved_resources.json','split_ui_translations.json','extra8_ui_translations.json']:shutil.copyfile(ROOT/'data'/name,engine/name)
    shutil.copyfile(ROOT/'data/split_tile_maps.json',engine/'재점검/이미지검토/분리타일맵_전체목록.json')
    run('build.py');output=work/manifest['files']['output']['file'];actual=digest(output);assert actual==manifest['files']['output']['sha256'],actual
    for name in ['validate.py','audit_translations.py','audit_additional_readback.py']:run(name)
    report={'source_sha256':digest(args.source),'output_sha256':actual,'expected_output_sha256':manifest['files']['output']['sha256'],'matches':True,'public_source_rebuild_verified':True,'font_bdf_hashes_verified':True,'original_rom_distributed':False}
    (ROOT/'docs/reproduction.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print('정식 릴리즈 ROM 재현 완료: '+actual)
if __name__=='__main__':main()
