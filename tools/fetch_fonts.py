"""공식 갈무리 배포본에서 해시가 일치하는 BDF만 로컬 work에 준비한다."""
from pathlib import Path
import hashlib,io,json,urllib.request,zipfile
ROOT=Path(__file__).resolve().parents[1]
def fetch():
    m=json.loads((ROOT/'data/font_manifest.json').read_text('utf-8'));out=ROOT/'work/fonts';out.mkdir(parents=True,exist_ok=True)
    if all((out/n).exists() and hashlib.sha256((out/n).read_bytes()).hexdigest()==h for n,h in m['files'].items()):return out
    request=urllib.request.Request(m['url'],headers={'User-Agent':'Zero-One-SP-Korean-Patch/1.0.0'})
    with urllib.request.urlopen(request,timeout=120) as response:payload=response.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        for name,expected in m['files'].items():
            candidates=[p for p in z.namelist() if p.rsplit('/',1)[-1]==name];assert len(candidates)==1,(name,candidates)
            data=z.read(candidates[0]);assert hashlib.sha256(data).hexdigest()==expected,name
            (out/name).write_bytes(data)
    print('공식 갈무리 BDF 4개 해시 확인 완료. 폰트는 공개 저장소에 포함하지 않습니다.')
    return out
if __name__=='__main__':fetch()
