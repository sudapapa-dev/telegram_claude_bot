# telegram_claude_bot - Docker Image (Linux/NAS 호환)
FROM python:3.11-slim

# 시스템 패키지 설치 + NodeSource에서 Node.js 20 LTS 설치
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI 설치 (필수)
RUN npm install -g @anthropic-ai/claude-code

# Notion MCP 설치
RUN npm install -g @notionhq/notion-mcp-server

# 보안: root 대신 일반 유저로 실행 (COPY --chown 전에 먼저 생성)
RUN useradd -m -s /bin/bash appuser

# 작업 디렉토리 설정
WORKDIR /app

# 1단계: 의존성 파일만 먼저 복사 → pip install
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# 2단계: 소스 코드 복사 후 권한 명시적 설정
# find로 디렉토리와 파일을 분리하여 chmod 적용
COPY src/ ./src/
RUN find /app/src -type d -exec chmod 755 {} \; && \
    find /app/src -type f -exec chmod 644 {} \; && \
    chown -R appuser:appuser /app/src

# 필요 디렉토리 생성 및 권한 설정
RUN mkdir -p /app/scripts /app/data/.db /app/workspace /app/sessions && \
    mkdir -p /home/appuser/.claude && \
    chown -R appuser:appuser /app /home/appuser/.claude

# entrypoint 복사 (USER 변경 전 root로)
COPY deploy/docker/entrypoint.sh /app/entrypoint.sh
RUN chmod 755 /app/entrypoint.sh && chown appuser:appuser /app/entrypoint.sh

USER appuser

# 환경변수 기본값
ENV DATABASE_PATH=/app/data/.db/telegram_claude_bot.db
ENV CLAUDE_CODE_PATH=claude
ENV HOME=/home/appuser

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "src.main"]
