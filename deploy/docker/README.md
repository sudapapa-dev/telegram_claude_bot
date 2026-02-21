# Docker / NAS 배포

NAS(Synology) 또는 Linux 서버에서 Docker로 실행하는 설정 파일입니다.

## 파일 구성
- `Dockerfile` - Docker 이미지 빌드 설정
- `docker-compose.yml` - 컨테이너 실행 설정

## 실행 방법

```bash
# 이미지 빌드 (프로젝트 루트에서 실행)
docker build -f deploy/docker/Dockerfile -t claude-controltower:latest .

# 컨테이너 실행
docker-compose -f deploy/docker/docker-compose.yml up -d

# 로그 확인
docker logs -f claude_controltower
```

## 환경변수
프로젝트 루트의 `.env` 파일을 참고하세요.
