# Claude Control Tower - Docker Image (Linux/NAS 호환)
FROM python:3.11-slim

# 시스템 패키지 설치 (Claude CLI 의존성)
RUN apt-get update && apt-get install -y \
    curl \
    nodejs \
    npm \
    git \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI 설치
RUN npm install -g @anthropic-ai/claude-code

# Gemini CLI 설치
RUN npm install -g @google/gemini-cli || true

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 파일 복사 및 설치
COPY pyproject.toml ./
COPY src/ ./src/

# scripts 폴더는 선택적 복사 (없어도 동작)
RUN mkdir -p /app/scripts

RUN pip install --no-cache-dir -e .

# root 대신 일반 유저로 실행 (Claude CLI 보안 정책 대응)
RUN useradd -m -s /bin/bash appuser && \
    mkdir -p /app/data /app/workspace && \
    chown -R appuser:appuser /app && \
    mkdir -p /home/appuser/.claude && \
    chown -R appuser:appuser /home/appuser/.claude

USER appuser

# 환경변수 기본값
ENV DATABASE_PATH=/app/data/controltower.db
ENV CLAUDE_WORKSPACE=/app/workspace
ENV CLAUDE_CODE_PATH=claude
ENV HOME=/home/appuser

# 실행
CMD ["python", "-m", "src.main"]
