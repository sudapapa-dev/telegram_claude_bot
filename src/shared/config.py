from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


def _find_env_file() -> str:
    """프로젝트 루트의 .env 파일을 절대 경로로 찾아 반환.

    탐색 순서:
      1. EXE 실행 시: EXE가 위치한 폴더
      2. 소스 실행 시: src/shared/config.py 기준 2단계 상위 (프로젝트 루트)
      3. 현재 작업 디렉토리 (fallback)
    """
    candidates: list[Path] = []

    # 1) PyInstaller EXE: sys._MEIPASS 또는 sys.executable 기준
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / ".env")
    else:
        # 2) 소스 실행: config.py → shared/ → src/ → 프로젝트 루트
        candidates.append(Path(__file__).resolve().parent.parent.parent / ".env")

    # 3) cwd fallback
    candidates.append(Path.cwd() / ".env")

    for p in candidates:
        if p.is_file():
            logger.info(".env 파일 발견: %s", p)
            return str(p)

    # 못 찾으면 기본값 (pydantic이 환경변수만으로 동작하도록)
    return ".env"


class Settings(BaseSettings):
    """전체 시스템 설정 - .env 파일에서 로드"""
    telegram_bot_token: SecretStr          # SecretStr로 로그 노출 방지
    telegram_chat_id: list[int] = []       # 허용된 사용자 ID 목록 (텔레그램 user ID)

    # Claude
    claude_code_path: str = "claude"
    default_model: str = ""                 # 비어있으면 Claude Code CLI 기본 모델 사용
    default_session_name: str = "suho"     # 기본 세션 표시 이름 (.env에서만 변경 가능)

    @field_validator("claude_code_path", mode="after")
    @classmethod
    def _resolve_claude_path(cls, v: str) -> str:
        """claude 실행 파일 절대 경로 자동 탐지.

        .env에 절대 경로가 설정되어 있으면 그대로 사용.
        상대 이름(예: 'claude')이면 shutil.which → 공통 설치 경로 순으로 탐색.
        """
        # 이미 절대 경로이고 존재하면 그대로
        if os.path.isabs(v) and os.path.isfile(v):
            return v

        # 1) shutil.which (현재 PATH에서 탐색)
        found = shutil.which(v)
        if found:
            logger.info("claude CLI 발견 (PATH): %s", found)
            return found

        # 2) Windows 공통 설치 경로 탐색
        if sys.platform == "win32":
            home = Path.home()
            logger.info("claude CLI 탐색 시작: home=%s", home)
            # 현재 사용자 홈 기준 후보
            candidates = [
                home / ".local" / "bin" / "claude.exe",
                home / "AppData" / "Local" / "Programs" / "claude" / "claude.exe",
                home / "AppData" / "Roaming" / "npm" / "claude.cmd",
                Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Claude" / "claude.exe",
            ]
            # 서비스(SYSTEM) 환경 대비: C:\Users\*에서도 탐색
            users_dir = Path(os.environ.get("SYSTEMDRIVE", "C:") + "\\") / "Users"
            if users_dir.is_dir():
                try:
                    for user_dir in users_dir.iterdir():
                        if not user_dir.is_dir():
                            continue
                        if user_dir.name in ("Public", "Default", "Default User", "All Users"):
                            continue
                        candidates.append(user_dir / ".local" / "bin" / "claude.exe")
                        candidates.append(user_dir / "AppData" / "Roaming" / "npm" / "claude.cmd")
                except PermissionError:
                    logger.warning("C:\\Users 디렉토리 열거 실패 (권한 부족)")
            for p in candidates:
                try:
                    if p.is_file():
                        logger.info("claude CLI 발견 (fallback): %s", p)
                        return str(p)
                except (PermissionError, OSError) as e:
                    logger.debug("경로 접근 실패: %s (%s)", p, e)

        # 3) Linux/Mac 공통 경로
        else:
            candidates = [
                Path.home() / ".local" / "bin" / "claude",
                Path("/usr/local/bin/claude"),
                Path("/usr/bin/claude"),
            ]
            for p in candidates:
                if p.is_file():
                    logger.info("claude CLI 발견 (fallback): %s", p)
                    return str(p)

        logger.warning("claude CLI를 찾지 못했습니다. 기본값 '%s' 사용", v)
        return v

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

    model_config = {"env_file": _find_env_file(), "env_file_encoding": "utf-8", "extra": "ignore"}

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
