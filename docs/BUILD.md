# 재현 빌드

Python 3.11 이상과 `requirements.txt`의 라이브러리를 준비합니다. 작성·검증 환경은 Python 3.13입니다. ROM·글꼴·VBA·xdelta 실행파일은 저장소와 릴리즈에 포함하지 않습니다.

```powershell
python -m pip install -r requirements.txt
python -X utf8 tools/rebuild.py --source 'Zero One SP (Japan).gba'
```

`--source`에는 직접 준비한 원본의 경로를 넣습니다. SHA-256 불일치 시 중단합니다. 공식 갈무리 v2.40.4 ZIP을 메모리로 내려받아 BDF 네 개의 해시를 검증하고 `work/fonts/`에 준비합니다. 자동 다운로드 대신 `data/font_manifest.json`과 일치하는 파일을 같은 경로에 준비해도 됩니다.

도구는 `work/한글패치작업/`에 엔진·번역·글꼴을 구성하고, 원본에서 비공개 추출 목록을 다시 생성합니다. `translation/`의 ROM 위치 참조를 원문으로 복원한 뒤 빌드하고 릴리즈 해시와 대조합니다. 글리프·제어 코드·이미지·사전 상대 포인터의 정적 검사도 실행합니다.

결과는 `work/Zero One SP (Korean).gba`입니다. `docs/reproduction.json`에 재현 결과를 남깁니다. `work/`의 ROM·폰트·추출 자료·캐시를 Git에 추가하지 마세요.

## xdelta 적용 및 재생성

```powershell
python tools/apply_release.py --source 'Zero One SP (Japan).gba' --patch 'Zero_One_SP_GBA_KR.xdelta' --output 'Zero One SP (Korean).gba' --xdelta '.\xdelta.exe'
.\xdelta.exe -f -0 -S none -D -e -s 'Zero One SP (Japan).gba' 'work/Zero One SP (Korean).gba' 'Zero_One_SP_GBA_KR.xdelta'
```

재생성 패치는 xdelta 구현의 애플리케이션 헤더 등에 따라 파일 해시가 달라질 수 있습니다. 적용 결과 ROM은 반드시 manifest의 결과 해시와 같아야 합니다. 공식 릴리즈 파일 자체의 해시는 별도로 고정합니다.

## 추가 VBA 검증

Windows용 `tools/engine/qa_current_build.py`와 `vba_memory.py`는 특정 작업용 VBA 실행파일을 검사한 뒤 숨김 실행합니다. 해당 실행파일의 SHA-256은 도구에 명시되어 있습니다. 사용자의 키보드·마우스·포커스를 쓰지 않고 해당 프로세스의 입력 콜백만 제어하며, 종료 시 에뮬레이터를 닫고 설정·기존 배터리 저장을 복원합니다. 공개 재빌드는 VBA를 요구하지 않으며 자동으로 실행하지 않습니다.
