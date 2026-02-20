from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """전체 시스템 설정 - .env 파일에서 로드"""
    telegram_bot_token: str
    telegram_chat_id: list[int] = []      # 허용된 사용자 ID 목록 (텔레그램 user ID)
    allowed_users: int = 3                 # 최대 동시 인스턴스 수
    claude_code_path: str = "claude"
    database_path: str = "./controltower.db"
    default_model: str = "claude-sonnet-4-6"
    claude_workspace: str = ""             # Claude Code 작업 디렉토리

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
