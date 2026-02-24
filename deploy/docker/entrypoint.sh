#!/bin/bash
# Claude 인증 파일을 볼륨에서 홈 디렉토리로 복사
# ~/.claude/ 볼륨 안에 .claude.json이 있으면 ~/.claude.json 으로 복사
if [ -f "/home/appuser/.claude/.claude.json" ]; then
    cp "/home/appuser/.claude/.claude.json" "/home/appuser/.claude.json"
fi

# Notion MCP 설정은 main.py에서 자동 주입됨 (NOTION_TOKEN 환경변수 기반)

exec "$@"
