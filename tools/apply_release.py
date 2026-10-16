"""원본·패치·적용 결과 해시를 모두 확인하는 xdelta 적용 도구."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--patch',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--xdelta',default='xdelta3');a=p.parse_args()
    m=json.loads((ROOT/'release_manifest.json').read_text('utf-8'))
    assert sha(a.source)==m['files']['source']['sha256'],'원본 해시 불일치'
    assert sha(a.patch)==m['files']['patch']['sha256'],'패치 해시 불일치'
    assert not a.output.exists(),'기존 출력 파일이 있습니다. 새 파일 이름을 사용하세요.'
    assert a.output.resolve()!=a.source.resolve()
    subprocess.run([a.xdelta,'-D','-d','-s',str(a.source),str(a.patch),str(a.output)],check=True)
    assert sha(a.output)==m['files']['output']['sha256'],'결과 ROM 해시 불일치'
    print('패치 적용 및 결과 SHA-256 확인 완료: '+sha(a.output))
if __name__=='__main__':main()
