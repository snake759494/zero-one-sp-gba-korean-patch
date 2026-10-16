"""공개 트리에서 ROM·폰트·실행파일·개인 경로·토큰을 검사한다."""
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]
def main():
    files=[p for p in ROOT.rglob('*') if p.is_file() and not set(p.relative_to(ROOT).parts)&{'work','.git','__pycache__'}]
    denied={'.gba','.nds','.iso','.bin','.sav','.sgm','.exe','.dll','.bdf','.ttf','.otf','.woff','.woff2','.zip','.xdelta','.pyc'}
    issues=[];hashes={}
    for p in files:
        rel=p.relative_to(ROOT).as_posix()
        if p.suffix.lower() in denied:issues.append([rel,'공개 금지 파일 형식'])
        raw=p.read_bytes()
        if p.suffix.lower() not in {'.png'}:
            text=raw.decode('utf-8')
            if re.search(r'(?<![A-Za-z])(?:[A-Za-z]:[\\/]|\\\\[U]sers\\|/[U]sers/)',text):issues.append([rel,'개인 절대 경로'])
            if re.search(r'gh[pousr]_[A-Za-z0-9]{20,}',text):issues.append([rel,'토큰 패턴'])
        if rel!='docs/publication_audit.json':hashes[rel]=hashlib.sha256(raw).hexdigest()
    assert not issues,issues
    report={'public_file_count':len(files),'prohibited_files':[],'personal_paths':[],'secret_patterns':[],'rom_font_executable_save_files_excluded':True,'public_files_sha256':hashes}
    (ROOT/'docs/publication_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8',newline='\n')
    print(json.dumps({k:v for k,v in report.items() if k!='public_files_sha256'},ensure_ascii=False))
if __name__=='__main__':main()
