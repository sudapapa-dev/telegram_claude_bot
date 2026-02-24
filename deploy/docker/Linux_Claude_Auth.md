# Linux/Docker 환경 Claude CLI 인증 가이드

Claude Code CLI는 OAuth 브라우저 인증을 사용합니다.
GUI 브라우저가 없는 Linux/Docker/NAS 환경에서는 아래 방법으로 인증합니다.

---

## 방법 1: 헤드리스 인증 (터미널에서 직접)

브라우저 없이 터미널에서 URL을 복사하여 인증하는 방식입니다.

### 1-1. 컨테이너 내부에서 실행

```bash
# 컨테이너에 접속
sudo docker exec -it telegram_claude_bot bash

# Claude CLI 로그인 실행
claude login
```

### 1-2. NAS SSH에서 직접 실행

```bash
DOCKER=/volume1/@appstore/ContainerManager/usr/bin/docker

echo 'PASSWORD' | sudo -S $DOCKER exec -it telegram_claude_bot claude login
```

### 인증 절차

1. `claude login` 실행 시 아래와 같은 메시지가 출력됩니다:

```
To sign in, open this URL in your browser:
https://console.anthropic.com/oauth/authorize?client_id=...&code_challenge=...

Waiting for authentication...
```

2. 출력된 URL을 복사하여 **PC 또는 스마트폰 브라우저**에서 엽니다.
3. Anthropic 계정으로 로그인하고 권한을 승인합니다.
4. 승인 완료 시 터미널에 자동으로 인증 성공 메시지가 표시됩니다:

```
Successfully authenticated!
```

5. 인증 파일이 컨테이너 내부 `/home/appuser/.claude/.credentials.json`에 저장됩니다.
6. 볼륨 마운트(`claude_auth/`)를 통해 컨테이너 재시작 후에도 유지됩니다.

### 인증 후 컨테이너 재시작

```bash
DOCKER=/volume1/@appstore/ContainerManager/usr/bin/docker
COMPOSE_FILE=~/.docker/data/telegram_claude_bot/docker-compose.yml

echo 'PASSWORD' | sudo -S $DOCKER compose -f $COMPOSE_FILE down
echo 'PASSWORD' | sudo -S $DOCKER compose -f $COMPOSE_FILE up -d
```

---

## 방법 2: 로컬 PC에서 인증 후 파일 복사

GUI 브라우저가 있는 PC에서 인증하고, 인증 파일을 서버로 복사하는 방식입니다.

### 순서

```
로컬 PC (브라우저 인증)  →  인증 파일 복사  →  서버/NAS
```

### 2-1. 로컬에서 인증

```bash
# 로컬 PC에서 실행
claude login
# 브라우저가 자동으로 열리고 인증 진행
```

### 2-2. 인증 파일 확인

인증 완료 후 아래 두 파일이 생성됩니다:

| 파일 | 경로 | 내용 |
|------|------|------|
| `.credentials.json` | `~/.claude/.credentials.json` | OAuth 토큰 (핵심) |
| `.claude.json` | `~/.claude.json` | 계정 정보, 설정 |

### 2-3. NAS로 복사

```powershell
# Windows PowerShell (SMB 네트워크 공유)
copy "$env:USERPROFILE\.claude\.credentials.json" "\\NAS_IP\homes\{USER}\.docker\data\telegram_claude_bot\claude_auth\"
copy "$env:USERPROFILE\.claude.json" "\\NAS_IP\homes\{USER}\.docker\data\telegram_claude_bot\claude_auth\"
```

```bash
# Linux / Mac (SSH)
scp ~/.claude/.credentials.json user@NAS_IP:/volume1/homes/{USER}/.docker/data/telegram_claude_bot/claude_auth/
scp ~/.claude.json user@NAS_IP:/volume1/homes/{USER}/.docker/data/telegram_claude_bot/claude_auth/.claude.json
```

### 2-4. 컨테이너 재시작

```bash
DOCKER=/volume1/@appstore/ContainerManager/usr/bin/docker
COMPOSE_FILE=~/.docker/data/telegram_claude_bot/docker-compose.yml

echo 'PASSWORD' | sudo -S $DOCKER compose -f $COMPOSE_FILE down
echo 'PASSWORD' | sudo -S $DOCKER compose -f $COMPOSE_FILE up -d
```

---

## 토큰 만료 시 재인증

OAuth 토큰은 일정 기간 후 만료됩니다. 만료 시 봇에서 아래와 같은 오류가 발생합니다:

```
Failed to authenticate. API Error: 401
{"type":"error","error":{"type":"authentication_error",
"message":"OAuth token has expired. Please obtain a new token or refresh your existing token."}}
```

이 경우 위 방법 1 또는 방법 2를 다시 수행하면 됩니다.

### 빠른 재인증 (방법 1 - 권장)

```bash
DOCKER=/volume1/@appstore/ContainerManager/usr/bin/docker

# 컨테이너 내부에서 재인증
echo 'PASSWORD' | sudo -S $DOCKER exec -it telegram_claude_bot claude login

# 재인증 후 컨테이너 재시작
echo 'PASSWORD' | sudo -S $DOCKER restart telegram_claude_bot
```

---

## 인증 파일 구조

```
claude_auth/                          ← docker-compose 볼륨 마운트
├── .credentials.json                 ← OAuth 토큰 (accessToken, refreshToken)
├── .claude.json                      ← 계정 정보, MCP 설정 등
├── settings.json                     ← CLI 설정
└── ...                               ← 기타 캐시/이력 파일
```

컨테이너의 `docker-compose.yml`에서 이 폴더가 마운트됩니다:

```yaml
volumes:
  - ./claude_auth:/home/appuser/.claude
```

`entrypoint.sh`가 컨테이너 시작 시 `.claude.json`을 홈 디렉토리로 복사합니다:

```
claude_auth/.claude.json  →  /home/appuser/.claude.json
```
