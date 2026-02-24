from __future__ import annotations

import logging
import os

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """전체 시스템 설정 - .env 파일에서 로드"""
    telegram_bot_token: SecretStr          # SecretStr로 로그 노출 방지
    telegram_chat_id: list[int] = []       # 허용된 사용자 ID 목록 (텔레그램 user ID)

    # Claude
    claude_code_path: str = "claude"
    default_model: str = "claude-sonnet-4-6"
    default_session_name: str = "suho"     # 기본 세션 표시 이름 (.env에서만 변경 가능)

    @field_validator("default_session_name", mode="before")
    @classmethod
    def _default_session_name_fallback(cls, v: str) -> str:
        """공백만 있거나 빈 문자열이면 'suho'로 대체"""
        if not v or not v.strip():
            return "suho"
        return v.strip()

    # 사전 프롬프트 — SYSTEM_PROMPT 단일 또는 SYSTEM_PROMPT_1~N 다중 설정 지원
    # 다중 설정 시 번호 순서대로 줄바꿈으로 합쳐서 사용
    system_prompts: list[str] = []

    database_path: str = "./telegram_claude_bot.db"

    notion_token: str = ""                 # Notion MCP 토큰 (선택적)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @model_validator(mode="before")
    @classmethod
    def _load_system_prompts(cls, values: dict) -> dict:
        """SYSTEM_PROMPT / SYSTEM_PROMPT_1~N 환경변수를 읽어 system_prompts 구성"""
        prompts: list[str] = []

        # 단일: SYSTEM_PROMPT
        single = values.get("system_prompt") or os.environ.get("SYSTEM_PROMPT", "")
        if single:
            prompts.append(single.strip())

        # 다중: SYSTEM_PROMPT_1, SYSTEM_PROMPT_2, ...
        i = 1
        while True:
            key = f"SYSTEM_PROMPT_{i}"
            val = values.get(key.lower()) or os.environ.get(key, "")
            if not val:
                break
            prompts.append(val.strip())
            i += 1

        if prompts:
            values["system_prompts"] = prompts
        return values

    @property
    def system_prompt(self) -> str:
        """모든 사전 프롬프트를 줄바꿈으로 합친 최종 프롬프트"""
        return "\n\n".join(p for p in self.system_prompts if p)

    def warn_if_open_access(self) -> None:
        """TELEGRAM_CHAT_ID 미설정 시 경고 출력"""
        if not self.telegram_chat_id:
            logger.warning(
                "TELEGRAM_CHAT_ID가 설정되지 않았습니다. "
                "현재 모든 텔레그램 사용자가 봇에 접근할 수 있습니다. "
                ".env에 TELEGRAM_CHAT_ID를 설정하여 접근을 제한하세요."
            )
