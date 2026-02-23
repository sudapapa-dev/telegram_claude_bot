# telegram_claude_bot - Docker Image (Linux/NAS 호환)
FROM python:3.11-slim

# 시스템 패키지 설치 + NodeSource에서 Node.js 20 LTS 설치
# apt 기본 저장소의 nodejs는 구버전이므로 NodeSource 스크립트 사용
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI 설치 (필수)
RUN npm install -g @anthropic-ai/claude-code

# Gemini CLI 설치 (선택적 - 실패해도 빌드 계속)
RUN npm install -g @google/gemini-cli 2>/dev/null || echo "[INFO] Gemini CLI 설치 건너뜀"

# 작업 디렉토리 설정
WORKDIR /app

# 1단계: 의존성 파일만 먼저 복사 → pip install
# pyproject.toml이 변경되지 않으면 이 레이어는 캐시 재사용됨
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# 2단계: 소스 코드 복사 (소스 변경 시에만 이 레이어부터 재빌드)
COPY src/ ./src/

# src/assets 폴더가 있으면 복사 (없으면 빈 폴더만 생성)
# Docker COPY는 소스가 비어있으면 대상 폴더를 생성하지 않으므로 mkdir로 보장
RUN mkdir -p /app/src/assets

# scripts 폴더 (선택적)
RUN mkdir -p /app/scripts

# 보안: root 대신 일반 유저로 실행 (Claude CLI 보안 정책 대응)
RUN useradd -m -s /bin/bash appuser && \
    mkdir -p /app/data /app/workspace && \
    chown -R appuser:appuser /app && \
    mkdir -p /home/appuser/.claude && \
    chown -R appuser:appuser /home/appuser/.claude

USER appuser

# 환경변수 기본값 (docker-compose.yml 또는 .env에서 덮어씀)
ENV DATABASE_PATH=/app/data/.db/telegram_claude_bot.db
ENV CLAUDE_WORKSPACE=/app/workspace
ENV CLAUDE_CODE_PATH=claude
ENV HOME=/home/appuser

CMD ["python", "-m", "src.main"]
