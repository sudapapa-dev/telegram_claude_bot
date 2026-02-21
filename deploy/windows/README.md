# Windows 실행 / EXE 빌드

Windows PC에서 직접 실행하거나 EXE로 빌드하는 설정 파일입니다.

## 파일 구성
- `controltower.spec` - PyInstaller EXE 빌드 설정
- `.env.example` - 환경변수 예시

## 실행 방법

```bash
# 개발 실행
python -m src.main

# EXE 빌드
pyinstaller deploy/windows/controltower.spec --clean --noconfirm
# dist/controltower.exe 생성됨
```

## 윈도우 전용 기능
`scripts/` 폴더의 유틸리티 스크립트가 자동으로 로드됩니다:
- `screenshot.py` - 스크린샷 캡처
- `launch_program.py` - 프로그램 실행
- `find_process.py` - 프로세스 검색
