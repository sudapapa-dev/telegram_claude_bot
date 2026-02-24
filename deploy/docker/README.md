# Docker 배포 가이드

## 배포 방식 선택

| 방식 | 대상 | 특징 |
|------|------|------|
| [일반 Docker](#일반-docker-배포) | Linux 서버, WSL2 | 소스코드에서 직접 빌드 |
| [Synology NAS](#synology-nas-배포) | Synology NAS (Container Manager) | tar 이미지 기반 배포 |

---

## 일반 Docker 배포

### 사전 요구사항
- Docker Engine 또는 Docker Desktop
- Claude CLI 인증 완료 (로컬에서 `claude` 명령 실행 가능한 상태)

### 1. 설정 파일 준비

```
deploy/docker/
├── .env          ← 여기에 생성
├── data/         ← 자동 생성됨
├── workspace/    ← 자동 생성됨
├── sessions/     ← 세션별 작업 디렉토리 (자동 생성됨)
└── claude_auth/  ← Claude 인증 파일 복사 필요
```

프로젝트 루트의 `.env.example`을 `deploy/docker/.env`로 복사하여 수정합니다.

```bash
cp .env.example deploy/docker/.env
```

수정이 필요한 항목:

| 항목 | 설명 | 예시 |
|------|------|------|
| `TELEGRAM_BOT_TOKEN` | BotFather에서 발급받은 토큰 | `1234567890:ABC...` |
| `TELEGRAM_CHAT_ID` | 허용할 텔레그램 사용자 ID 목록 | `[123456789]` |
| `DEFAULT_MODEL` | 사용할 Claude 모델 | `claude-sonnet-4-6` |
| `DEFAULT_SESSION_NAME` | 기본 세션 표시 이름 | `suho` |
| `MAX_CONCURRENT` | 동시 처리 수 | `3` |
| `SYSTEM_PROMPT_1` | 사전 프롬프트 (여러 개 설정 가능) | 비워두면 미사용 |
| `NOTION_TOKEN` | Notion MCP 연동 토큰 (선택) | 비워두면 미사용 |

### 2. Claude 인증 파일 복사

```bash
mkdir -p deploy/docker/claude_auth

# Linux / Mac
cp -r ~/.claude/* deploy/docker/claude_auth/

# Windows (PowerShell)
xcopy "$env:USERPROFILE\.claude" "deploy\docker\claude_auth\" /E /I
```

### 3. 빌드 및 실행

```bash
cd deploy/docker
docker-compose up -d --build
```

### 4. 로그 확인

```bash
docker-compose logs -f
```

### 재시작 / 중지

```bash
docker-compose restart
docker-compose down
docker-compose down --rmi local   # 이미지까지 제거
```

---

## Synology NAS 배포

Synology NAS의 **Container Manager** (= Docker)를 사용한 배포 방식입니다.
소스코드 없이 **tar 이미지 파일**만으로 운영합니다.

### NAS 디렉토리 구조

```
~/                              ← /volume1/homes/{user}/
└── .docker/
    ├── images/
    │   └── telegram_claude_bot.tar     ← 이미지 백업
    └── data/
        └── telegram_claude_bot/        ← 컨테이너 데이터
            ├── .env                    ← 봇 설정
            ├── docker-compose.yml      ← 실행 설정
            ├── data/                   ← DB 저장
            │   └── .db/
            │       └── telegram_claude_bot.db
            ├── workspace/              ← Claude 작업 디렉토리
            ├── sessions/               ← 세션별 작업 디렉토리
            └── claude_auth/            ← Claude 인증 정보
```

### 사전 요구사항
- Synology DSM에 **Container Manager** 패키지 설치
- SSH 접속 가능 (제어판 → 터미널 및 SNMP → SSH 활성화)
- 관리자(administrators 그룹) 계정

### 1. 빌드 환경 준비 (최초 1회)

NAS에 SSH 접속 후 소스코드 전송 및 빌드합니다.

```bash
# 로컬(Windows)에서 소스코드를 NAS로 전송하는 Python 스크립트
# (scp/sftp 대신 paramiko + base64 방식 사용 — Synology SFTP 서브시스템 비활성 대응)
```

> **참고:** Synology NAS는 기본적으로 SFTP 서브시스템이 비활성화되어 있어
> 일반 `scp` 명령이 작동하지 않을 수 있습니다.
> paramiko를 이용한 Python 스크립트로 전송합니다.

### 2. 이미지 빌드 (최초 1회)

NAS에서 SSH로 접속하여 빌드합니다.

```bash
# sudo 필요 (administrators 그룹 계정)
echo 'PASSWORD' | sudo -S /usr/local/bin/docker-compose \
  -f ~/.docker/data/telegram_claude_bot/deploy/docker/docker-compose.yml \
  build --no-cache
```

### 3. 이미지를 tar로 저장

빌드 완료 후 이미지를 tar 파일로 저장합니다. (소스코드 없이 재배포 가능)

```bash
mkdir -p ~/.docker/images

echo 'PASSWORD' | sudo -S /usr/local/bin/docker save \
  telegram_claude_bot:latest \
  -o ~/.docker/images/telegram_claude_bot.tar
```

### 4. .env 파일 설정

```bash
mkdir -p ~/.docker/data/telegram_claude_bot

cat > ~/.docker/data/telegram_claude_bot/.env << 'EOF'
TELEGRAM_BOT_TOKEN=your-token
TELEGRAM_CHAT_ID=[123456789]
CLAUDE_CODE_PATH=claude
DEFAULT_MODEL=claude-sonnet-4-6
DEFAULT_SESSION_NAME=suho
CLAUDE_WORKSPACE=/app/workspace
MAX_CONCURRENT=3
SYSTEM_PROMPT_1=You are a helpful assistant.
SYSTEM_PROMPT_2=Always respond in the same language as the user.
NOTION_TOKEN=
EOF
```

### 5. docker-compose.yml 설정

```yaml
# ~/.docker/data/telegram_claude_bot/docker-compose.yml
version: '3.8'

services:
  telegram_claude_bot:
    image: telegram_claude_bot:latest
    container_name: telegram_claude_bot
    restart: unless-stopped

    env_file:
      - /volume1/homes/{USER}/.docker/data/telegram_claude_bot/.env

    environment:
      - CLAUDE_CODE_PATH=claude
      - CLAUDE_WORKSPACE=/app/workspace
      - DATABASE_PATH=/app/data/.db/telegram_claude_bot.db

    volumes:
      - /volume1/homes/{USER}/.docker/data/telegram_claude_bot/data:/app/data
      - /volume1/homes/{USER}/.docker/data/telegram_claude_bot/workspace:/app/workspace
      - /volume1/homes/{USER}/.docker/data/telegram_claude_bot/sessions:/app/sessions
      - /volume1/homes/{USER}/.docker/data/telegram_claude_bot/claude_auth:/home/appuser/.claude

    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

`{USER}`를 실제 NAS 사용자명으로 교체하세요.

### 6. Claude 인증 파일 복사

컨테이너 내 Claude CLI가 인증을 사용하려면 로컬의 `~/.claude/` 내용을 복사해야 합니다.

```powershell
# Windows PowerShell에서 실행 (NAS 파일 공유 경로 사용)
xcopy "$env:USERPROFILE\.claude" "\\NAS_IP\homes\{USER}\.docker\data\telegram_claude_bot\claude_auth\" /E /I
```

```bash
# Linux / Mac
scp -r ~/.claude/* user@NAS_IP:/volume1/homes/{USER}/.docker/data/telegram_claude_bot/claude_auth/
```

#### entrypoint 동작 방식

컨테이너는 시작 시 `entrypoint.sh`를 실행하여 볼륨에서 인증 파일을 홈 디렉토리로 자동 복사합니다.

```
claude_auth/.claude.json  →  (시작 시 자동 복사)  →  /home/appuser/.claude.json
```

따라서 `claude_auth/` 폴더에 `.claude.json`이 있으면 컨테이너 재시작 후에도 인증이 유지됩니다.

#### 인증 계정 변경 방법

Claude 인증은 브라우저 OAuth 방식으로, **텔레그램으로는 변경 불가**합니다.
인증 계정을 바꾸려면:

1. 로컬에서 `claude` 명령으로 새 계정으로 재인증
2. 생성된 `~/.claude.json` 을 `claude_auth/` 폴더에 복사
3. 컨테이너 재시작

```bash
# 재인증 후 복사 (Linux/Mac)
cp ~/.claude.json /path/to/claude_auth/.claude.json

# Windows
copy %USERPROFILE%\.claude.json \\NAS_IP\homes\{USER}\.docker\data\telegram_claude_bot\claude_auth\.claude.json
```

### 7. 컨테이너 실행

tar 이미지를 로드하고 컨테이너를 시작합니다.

```bash
# 이미지 로드 (최초 또는 이미지 교체 시)
echo 'PASSWORD' | sudo -S /usr/local/bin/docker load \
  -i ~/.docker/images/telegram_claude_bot.tar

# 데이터 폴더 권한 설정
chmod -R 777 ~/.docker/data/telegram_claude_bot/data \
             ~/.docker/data/telegram_claude_bot/workspace \
             ~/.docker/data/telegram_claude_bot/sessions \
             ~/.docker/data/telegram_claude_bot/claude_auth

# 컨테이너 시작
echo 'PASSWORD' | sudo -S /usr/local/bin/docker-compose \
  -f ~/.docker/data/telegram_claude_bot/docker-compose.yml up -d
```

### 운영 명령어

```bash
COMPOSE="sudo /usr/local/bin/docker-compose -f ~/.docker/data/telegram_claude_bot/docker-compose.yml"
DOCKER="sudo /usr/local/bin/docker"

# 로그 확인
echo 'PASSWORD' | $DOCKER logs telegram_claude_bot --tail 50 -f

# 재시작
echo 'PASSWORD' | $DOCKER restart telegram_claude_bot

# 중지
echo 'PASSWORD' | $COMPOSE down

# 상태 확인
echo 'PASSWORD' | $DOCKER ps
```

### 업데이트 절차

코드 변경 시 새 이미지를 빌드하고 tar를 교체합니다.

```bash
# 1. 소스코드 재전송 (로컬 → NAS)
# 2. NAS에서 재빌드
echo 'PASSWORD' | sudo -S /usr/local/bin/docker-compose \
  -f ~/.docker/data/telegram_claude_bot/deploy/docker/docker-compose.yml build

# 3. 새 tar 저장 (기존 덮어쓰기)
echo 'PASSWORD' | sudo -S /usr/local/bin/docker save \
  telegram_claude_bot:latest \
  -o ~/.docker/images/telegram_claude_bot.tar

# 4. 소스코드 삭제
rm -rf ~/.docker/data/telegram_claude_bot/src \
       ~/.docker/data/telegram_claude_bot/deploy \
       ~/.docker/data/telegram_claude_bot/pyproject.toml

# 5. 컨테이너 재시작
echo 'PASSWORD' | sudo -S /usr/local/bin/docker restart telegram_claude_bot
```

---

## 트러블슈팅

### Claude 인증 오류

```
Claude configuration file not found at: /home/appuser/.claude.json
```

위 오류가 발생하면 `claude_auth/` 볼륨에 `.claude.json`이 없는 것입니다.

1. 로컬에서 `claude` 명령 실행 후 `~/.claude.json` 생성 확인
2. `claude_auth/` 폴더에 복사:
   ```bash
   cp ~/.claude.json claude_auth/.claude.json
   ```
3. 컨테이너 재시작:
   ```bash
   docker restart telegram_claude_bot
   ```

백업 파일로 복원하는 방법 (긴급 시):
```bash
# 컨테이너 내부에서 백업 복원
docker exec telegram_claude_bot \
  cp /home/appuser/.claude/backups/.claude.json.backup.* /home/appuser/.claude/.claude.json
docker restart telegram_claude_bot
```

### DB 파일 생성 오류 (unable to open database file)

볼륨 마운트 시 `.db` 하위 폴더가 없어서 발생합니다.

```bash
mkdir -p ~/.docker/data/telegram_claude_bot/data/.db
chmod 777 ~/.docker/data/telegram_claude_bot/data/.db
```

### Synology에서 docker 명령을 찾을 수 없음

Container Manager의 docker는 `/usr/local/bin/docker`에 있습니다.
PATH에 없으므로 전체 경로를 사용하거나 sudo를 통해 실행합니다.

```bash
/usr/local/bin/docker --version
```

### 포트 충돌

이 서비스는 외부 포트를 노출하지 않습니다.
텔레그램 봇은 polling 방식으로 동작하므로 인바운드 포트 개방이 불필요합니다.
