# Docker 배포 가이드

## 사전 요구사항
- Docker Desktop 또는 Docker Engine
- Claude CLI 인증 완료 (로컬에서 `claude` 명령 실행 가능한 상태)

## 빠른 시작

### 1. 설정 파일 준비

```
deploy/docker/
├── .env          <- 여기에 생성
├── data/         <- 자동 생성됨
├── workspace/    <- 자동 생성됨
└── claude_auth/  <- Claude 인증 파일 복사 필요
```

### 2. .env 파일 작성

프로젝트 루트의 `.env.example`을 `deploy/docker/.env`로 복사하여 수정합니다.

```bash
# 프로젝트 루트에서 실행
cp .env.example deploy/docker/.env
```

수정이 필요한 항목:

| 항목 | 설명 | 예시 |
|------|------|------|
| `TELEGRAM_BOT_TOKEN` | BotFather에서 발급받은 토큰 | `1234567890:ABC...` |
| `TELEGRAM_CHAT_ID` | 허용할 텔레그램 사용자 ID 목록 | `[123456789]` |
| `DEFAULT_MODEL` | 사용할 Claude 모델 | `claude-sonnet-4-6` |
| `SESSION_POOL_SIZE` | 동시 처리 메시지 수 | `3` |
| `SYSTEM_PROMPT` | 모든 메시지 앞에 삽입할 사전 프롬프트 | 비워두면 미사용 |

### 3. Claude 인증 파일 복사

`claude_auth/` 폴더를 생성하고 로컬 Claude CLI 인증 파일을 복사합니다.

```bash
mkdir -p deploy/docker/claude_auth
```

운영체제별 복사 명령:

```bash
# Linux / Mac
cp -r ~/.claude/* deploy/docker/claude_auth/

# Windows (PowerShell)
xcopy "$env:USERPROFILE\.claude" "deploy\docker\claude_auth\" /E /I
```

Windows에서 인증 파일 위치가 다를 경우 `%APPDATA%\claude` 폴더도 확인하세요.

### 4. 빌드 및 실행

`deploy/docker/` 폴더에서 실행합니다.

```bash
cd deploy/docker
docker-compose up -d --build
```

### 5. 로그 확인

```bash
docker-compose logs -f
```

## 재시작 / 중지

```bash
# 재시작
docker-compose restart

# 중지 (컨테이너 제거, 데이터 보존)
docker-compose down

# 중지 + 이미지까지 제거
docker-compose down --rmi local
```

## 데이터 위치

| 경로 | 설명 |
|------|------|
| `./data/telegram_claude_bot.db` | SQLite DB (인스턴스, 작업 이력) |
| `./data/chat_history.json` | 대화 이력 |
| `./workspace/` | Claude Code 작업 디렉토리 |
| `./claude_auth/` | Claude CLI 인증 파일 (영속화) |

## .dockerignore 권장 설정

프로젝트 루트에 `.dockerignore` 파일을 만들어 불필요한 파일이 빌드 컨텍스트에 포함되지 않도록 합니다.

```
.git
.env
__pycache__
*.pyc
*.pyo
.pytest_cache
.mypy_cache
.ruff_cache
dist/
build/
*.egg-info/
deploy/docker/data/
deploy/docker/workspace/
deploy/docker/claude_auth/
tests/
```

## 트러블슈팅

### Claude 인증 오류

컨테이너 로그에 인증 관련 오류가 표시될 경우:

1. 로컬에서 `claude` 명령이 정상 동작하는지 확인
2. `./claude_auth/` 폴더에 `.credentials.json` 등의 파일이 있는지 확인
3. 파일 권한 확인: `ls -la deploy/docker/claude_auth/`

### 포트 충돌

이 서비스는 외부 포트를 노출하지 않습니다. 텔레그램 봇은 polling 방식으로 동작하므로 인바운드 포트 개방이 불필요합니다.

### 이미지 재빌드

소스 코드 변경 후 재빌드:

```bash
docker-compose up -d --build
```

`pyproject.toml`이 변경되지 않으면 pip install 레이어는 캐시에서 재사용됩니다.
