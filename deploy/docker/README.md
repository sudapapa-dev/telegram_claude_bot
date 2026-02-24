# Docker 배포 가이드

## 배포 방식 선택

| 방식 | 대상 | 특징 |
|------|------|------|
| [일반 Docker](#일반-docker-배포) | Linux 서버, WSL2 | 소스코드에서 직접 빌드 |
| [Synology NAS](#synology-nas-배포) | Synology NAS (Container Manager) | 로컬에서 빌드한 tar 이미지 배포 |

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
└── claude_auth/  ← .credentials.json 복사 필요
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
| `SYSTEM_PROMPT_1` | 사전 프롬프트 (여러 개 설정 가능) | 비워두면 미사용 |
| `NOTION_TOKEN` | Notion MCP 연동 토큰 (선택) | 비워두면 미사용 |

### 2. Claude 인증 파일 복사

인증에 필요한 파일은 `.credentials.json` 하나뿐입니다.

```bash
mkdir -p deploy/docker/claude_auth

# Linux / Mac
cp ~/.claude/.credentials.json deploy/docker/claude_auth/

# Windows (PowerShell)
copy "$env:USERPROFILE\.claude\.credentials.json" "deploy\docker\claude_auth\"
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
**로컬(Windows)에서 이미지를 빌드**하고, tar 파일로 NAS에 전송하여 운영합니다.

### NAS 디렉토리 구조

```
~/                              ← /volume1/homes/{user}/
└── .docker/
    ├── images/
    │   └── telegram_claude_bot.tar     ← Docker 이미지 파일
    └── data/
        └── telegram_claude_bot/        ← 컨테이너 데이터
            ├── .env                    ← 봇 설정
            ├── docker-compose.yml      ← 실행 설정
            ├── data/                   ← DB 저장
            │   └── .db/
            │       └── telegram_claude_bot.db
            ├── workspace/              ← Claude 작업 디렉토리
            └── claude_auth/            ← .credentials.json
```

### 사전 요구사항
- Synology DSM에 **Container Manager** 패키지 설치
- SSH 접속 가능 (제어판 → 터미널 및 SNMP → SSH 활성화)
- 관리자(administrators 그룹) 계정
- 로컬에 Docker Desktop 설치 (이미지 빌드용)

### 1. 로컬에서 이미지 빌드 및 tar 생성

로컬(Windows/Mac/Linux)에서 Docker 이미지를 빌드하고 tar로 저장합니다.

```bash
# 프로젝트 루트에서 실행
docker build -t telegram_claude_bot:latest -f deploy/docker/Dockerfile .

# tar 파일로 저장
docker save telegram_claude_bot:latest -o build/telegram_claude_bot.tar
```

### 2. tar 파일을 NAS로 전송

Windows 파일 탐색기 또는 네트워크 공유를 사용하여 전송합니다.

```
build/telegram_claude_bot.tar
  → \\NAS_IP\homes\{USER}\.docker\images\telegram_claude_bot.tar
```

> **참고:** Synology NAS는 기본적으로 SFTP 서브시스템이 비활성화되어 있어
> 일반 `scp` 명령이 작동하지 않을 수 있습니다. SMB 공유 폴더를 사용하세요.

### 3. .env 파일 설정

```bash
mkdir -p ~/.docker/data/telegram_claude_bot

cat > ~/.docker/data/telegram_claude_bot/.env << 'EOF'
TELEGRAM_BOT_TOKEN=your-token
TELEGRAM_CHAT_ID=[123456789]
DEFAULT_MODEL=claude-sonnet-4-6
DEFAULT_SESSION_NAME=suho
SYSTEM_PROMPT_1=You are a helpful assistant.
NOTION_TOKEN=
EOF
```

### 4. docker-compose.yml 설정

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
      - DATABASE_PATH=/app/data/.db/telegram_claude_bot.db

    volumes:
      - /volume1/homes/{USER}/.docker/data/telegram_claude_bot/data:/app/data
      - /volume1/homes/{USER}/.docker/data/telegram_claude_bot/workspace:/app/workspace
      - /volume1/homes/{USER}/.docker/data/telegram_claude_bot/claude_auth:/home/appuser/.claude

    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

`{USER}`를 실제 NAS 사용자명으로 교체하세요.

### 5. Claude 인증 파일 복사

인증에 필요한 파일은 `.credentials.json` 하나뿐입니다.

```powershell
# Windows PowerShell에서 실행 (NAS 파일 공유 경로 사용)
copy "$env:USERPROFILE\.claude\.credentials.json" "\\NAS_IP\homes\{USER}\.docker\data\telegram_claude_bot\claude_auth\"
```

```bash
# Linux / Mac
scp ~/.claude/.credentials.json user@NAS_IP:/volume1/homes/{USER}/.docker/data/telegram_claude_bot/claude_auth/
```

#### 인증 계정 변경 방법

Claude 인증은 브라우저 OAuth 방식입니다.
인증 계정을 바꾸려면:

1. 로컬에서 `claude login` 으로 새 계정으로 재인증
2. 생성된 `~/.claude/.credentials.json` 을 `claude_auth/` 폴더에 복사
3. 컨테이너 재시작: `docker restart telegram_claude_bot`

자세한 내용은 [Linux_Claude_Auth.md](Linux_Claude_Auth.md)를 참조하세요.

### 6. 이미지 로드 및 컨테이너 실행

NAS에 SSH 접속 후 실행합니다.

```bash
DOCKER=/volume1/@appstore/ContainerManager/usr/bin/docker

# 이미지 로드 (최초 또는 이미지 교체 시)
echo 'PASSWORD' | sudo -S $DOCKER load \
  -i ~/.docker/images/telegram_claude_bot.tar

# 데이터 폴더 권한 설정
chmod -R 777 ~/.docker/data/telegram_claude_bot/data \
             ~/.docker/data/telegram_claude_bot/workspace \
             ~/.docker/data/telegram_claude_bot/claude_auth

# 컨테이너 시작
echo 'PASSWORD' | sudo -S $DOCKER compose \
  -f ~/.docker/data/telegram_claude_bot/docker-compose.yml up -d
```

### 운영 명령어

```bash
DOCKER=/volume1/@appstore/ContainerManager/usr/bin/docker
COMPOSE_FILE=~/.docker/data/telegram_claude_bot/docker-compose.yml

# 로그 확인
echo 'PASSWORD' | sudo -S $DOCKER logs telegram_claude_bot --tail 50 -f

# 재시작 (.env 변경, 인증 파일 교체 시)
echo 'PASSWORD' | sudo -S $DOCKER restart telegram_claude_bot

# 중지
echo 'PASSWORD' | sudo -S $DOCKER compose -f $COMPOSE_FILE down

# 상태 확인
echo 'PASSWORD' | sudo -S $DOCKER ps
```

### 업데이트 절차

코드 변경 시 로컬에서 새 이미지를 빌드하여 NAS에 배포합니다.

```bash
# === 로컬(Windows)에서 ===

# 1. 이미지 빌드
docker build -t telegram_claude_bot:latest -f deploy/docker/Dockerfile .

# 2. tar 저장
docker save telegram_claude_bot:latest -o build/telegram_claude_bot.tar

# 3. NAS로 전송 (SMB 공유 또는 파일 탐색기)
#    build/telegram_claude_bot.tar → \\NAS_IP\homes\{USER}\.docker\images\

# === NAS (SSH)에서 ===
DOCKER=/volume1/@appstore/ContainerManager/usr/bin/docker
COMPOSE_FILE=~/.docker/data/telegram_claude_bot/docker-compose.yml

# 4. 이미지 로드
echo 'PASSWORD' | sudo -S $DOCKER load \
  -i ~/.docker/images/telegram_claude_bot.tar

# 5. 컨테이너 재생성 (새 이미지 적용)
echo 'PASSWORD' | sudo -S $DOCKER compose -f $COMPOSE_FILE down
echo 'PASSWORD' | sudo -S $DOCKER compose -f $COMPOSE_FILE up -d

# 6. 로그 확인
echo 'PASSWORD' | sudo -S $DOCKER logs telegram_claude_bot --tail 20
```

> **주의:** `docker restart`는 기존 컨테이너를 그대로 재시작하므로 새 이미지가 적용되지 않습니다.
> 반드시 `docker compose down` + `up -d`로 컨테이너를 재생성해야 합니다.

---

## 트러블슈팅

### Claude 인증 오류

```
Failed to authenticate. API Error: 401
```

위 오류가 발생하면 `claude_auth/` 볼륨에 `.credentials.json`이 없거나 만료된 것입니다.

1. 로컬에서 `claude login` 실행
2. `claude_auth/` 폴더에 복사:
   ```bash
   cp ~/.claude/.credentials.json claude_auth/
   ```
3. 컨테이너 재시작:
   ```bash
   docker restart telegram_claude_bot
   ```

### DB 파일 생성 오류 (unable to open database file)

볼륨 마운트 시 `.db` 하위 폴더가 없어서 발생합니다.

```bash
mkdir -p ~/.docker/data/telegram_claude_bot/data/.db
chmod 777 ~/.docker/data/telegram_claude_bot/data/.db
```

### Synology에서 docker 명령을 찾을 수 없음

Container Manager의 docker 경로는 DSM 버전에 따라 다릅니다.

```bash
# 경로 확인
which docker || find / -name docker -type f 2>/dev/null | head -5

# 일반적인 경로
/volume1/@appstore/ContainerManager/usr/bin/docker
```

### 이미지 교체 후 컨테이너에 반영되지 않음

`docker load`로 새 이미지를 로드한 후 반드시 컨테이너를 **재생성**해야 합니다.

```bash
# (X) restart는 기존 이미지의 컨테이너를 재시작할 뿐
docker restart telegram_claude_bot

# (O) down + up으로 새 이미지로 컨테이너 재생성
docker compose -f $COMPOSE_FILE down
docker compose -f $COMPOSE_FILE up -d
```

### 포트 충돌

이 서비스는 외부 포트를 노출하지 않습니다.
텔레그램 봇은 polling 방식으로 동작하므로 인바운드 포트 개방이 불필요합니다.
