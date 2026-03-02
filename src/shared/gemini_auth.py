"""Gemini CLI 인증 관리.

Gemini CLI는 두 가지 인증 방식을 지원한다:

1. API Key 방식 (USE_GEMINI)
   - GEMINI_API_KEY 환경변수 설정
   - 무료 티어: 60 req/min, 1000 req/day
   - 가장 단순하고 즉시 사용 가능

2. Google OAuth 방식 (LOGIN_WITH_GOOGLE)
   - `gemini auth login` + NO_BROWSER=true 로 URL 추출
   - 헤드리스 환경에서는 URL을 텔레그램으로 전달
   - 로컬 콜백 서버가 필요하므로 서버 환경에서 제약 있음

텔레그램 봇에서는 API Key 방식을 기본으로 사용하고,
Google OAuth는 보조 수단으로 제공한다.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

# ANSI 코드 제거
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
# URL 패턴
_URL_PATTERN = re.compile(r"https?://\S+")

OnUrlCallback = Callable[[str], Awaitable[None]]
OnDoneCallback = Callable[[], Awaitable[None]]
OnErrorCallback = Callable[[str], Awaitable[None]]

# .env / 설정에서 읽는 키 이름
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"


def find_gemini_path() -> str | None:
    """gemini CLI 실행 파일 경로 탐색."""
    found = shutil.which("gemini")
    if found:
        return found

    if sys.platform == "win32":
        home = Path.home()
        candidates = [
            home / "AppData" / "Roaming" / "npm" / "gemini.cmd",
            home / "AppData" / "Local" / "Programs" / "gemini" / "gemini.exe",
            home / ".local" / "bin" / "gemini.exe",
        ]
    else:
        candidates = [
            Path.home() / ".local" / "bin" / "gemini",
            Path("/usr/local/bin/gemini"),
        ]

    for p in candidates:
        if p.is_file():
            return str(p)

    return None


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text).strip()


def get_api_key() -> str | None:
    """현재 설정된 GEMINI_API_KEY 반환."""
    return os.environ.get(GEMINI_API_KEY_ENV)


def set_api_key_env(api_key: str) -> None:
    """현재 프로세스 환경변수에 API 키 설정 (런타임 한정)."""
    os.environ[GEMINI_API_KEY_ENV] = api_key


def save_api_key_to_env_file(api_key: str) -> bool:
    """EXE/소스 위치의 .env 파일에 GEMINI_API_KEY 저장.

    Returns True if saved successfully.
    """
    # .env 파일 위치 탐색 (config.py와 동일 로직)
    if getattr(sys, "frozen", False):
        env_path = Path(sys.executable).parent / ".env"
    else:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"

    if not env_path.is_file():
        env_path = Path.cwd() / ".env"

    try:
        if env_path.is_file():
            content = env_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            updated = False
            new_lines = []
            for line in lines:
                if line.startswith(f"{GEMINI_API_KEY_ENV}="):
                    new_lines.append(f"{GEMINI_API_KEY_ENV}={api_key}")
                    updated = True
                else:
                    new_lines.append(line)
            if not updated:
                new_lines.append(f"{GEMINI_API_KEY_ENV}={api_key}")
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        else:
            env_path.write_text(f"{GEMINI_API_KEY_ENV}={api_key}\n", encoding="utf-8")

        set_api_key_env(api_key)
        logger.info("GEMINI_API_KEY .env 저장 완료: %s", env_path)
        return True

    except Exception as e:
        logger.exception("GEMINI_API_KEY .env 저장 실패")
        return False


def remove_api_key() -> bool:
    """환경변수 및 .env 파일에서 GEMINI_API_KEY 제거."""
    os.environ.pop(GEMINI_API_KEY_ENV, None)

    if getattr(sys, "frozen", False):
        env_path = Path(sys.executable).parent / ".env"
    else:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"

    if not env_path.is_file():
        env_path = Path.cwd() / ".env"

    try:
        if env_path.is_file():
            content = env_path.read_text(encoding="utf-8")
            lines = [
                l for l in content.splitlines()
                if not l.startswith(f"{GEMINI_API_KEY_ENV}=")
            ]
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    except Exception:
        logger.exception("GEMINI_API_KEY 제거 실패")
        return False


# ── Google OAuth (LOGIN_WITH_GOOGLE) ──────────────────────────────────────────

class GeminiOAuthSession:
    """gemini auth login 프로세스 관리 (Google OAuth 방식).

    NO_BROWSER=true 환경변수로 브라우저 자동 실행을 막고
    stdout에서 인증 URL을 파싱하여 텔레그램으로 전달한다.
    """

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(
        self,
        gemini_path: str,
        on_url: OnUrlCallback,
        on_done: OnDoneCallback,
        on_error: OnErrorCallback,
    ) -> None:
        """Google OAuth 인증 프로세스 시작."""
        env = {**os.environ, "NO_BROWSER": "true"}
        self._proc = await asyncio.create_subprocess_exec(
            gemini_path, "auth", "login",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            stdin=asyncio.subprocess.PIPE,
        )
        # stdin에 'y' 입력 (consent 프롬프트 자동 승인)
        if self._proc.stdin:
            self._proc.stdin.write(b"y\n")
            await self._proc.stdin.drain()

        self._task = asyncio.create_task(
            self._run(on_url, on_done, on_error),
            name="gemini_oauth",
        )

    async def _run(
        self,
        on_url: OnUrlCallback,
        on_done: OnDoneCallback,
        on_error: OnErrorCallback,
    ) -> None:
        url_sent = False
        try:
            assert self._proc and self._proc.stdout
            async for raw in self._proc.stdout:
                line = _strip_ansi(raw.decode("utf-8", errors="replace"))
                if not line:
                    continue
                logger.debug("gemini auth stdout: %s", line)

                if not url_sent:
                    m = _URL_PATTERN.search(line)
                    if m:
                        url = m.group(0).rstrip(".,)")
                        # Google OAuth URL만 추출 (accounts.google.com 등)
                        if "google" in url or "oauth" in url or "auth" in url:
                            url_sent = True
                            try:
                                await on_url(url)
                            except Exception:
                                logger.exception("on_url 콜백 오류")

            await self._proc.wait()

            if self._proc.returncode == 0:
                await on_done()
            else:
                await on_error(
                    f"인증 프로세스가 종료 코드 {self._proc.returncode}으로 종료됐습니다.\n"
                    "서버 환경에서는 GEMINI_API_KEY 방식을 권장합니다."
                )

        except asyncio.CancelledError:
            await self.cancel()
            raise
        except Exception as e:
            logger.exception("gemini OAuth 인증 오류")
            await on_error(str(e))

    async def cancel(self) -> None:
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except Exception:
                self._proc.kill()
        if self._task and not self._task.done():
            self._task.cancel()


# ── 전역 OAuth 세션 ────────────────────────────────────────────────────────────
_active_oauth: GeminiOAuthSession | None = None


async def start_google_auth(
    on_url: OnUrlCallback,
    on_done: OnDoneCallback,
    on_error: OnErrorCallback,
) -> None:
    """Google OAuth 인증 시작. gemini CLI 필요."""
    global _active_oauth

    if _active_oauth and _active_oauth.is_running:
        raise RuntimeError("이미 Gemini Google 인증이 진행 중입니다.")

    gemini_path = find_gemini_path()
    if not gemini_path:
        raise RuntimeError(
            "gemini CLI를 찾을 수 없습니다.\n"
            "`npm install -g @google/gemini-cli` 로 설치 후 다시 시도하세요."
        )

    _active_oauth = GeminiOAuthSession()
    await _active_oauth.start(gemini_path, on_url, on_done, on_error)
    logger.info("Gemini Google OAuth 인증 시작: path=%s", gemini_path)


async def cancel_google_auth() -> bool:
    """진행 중인 OAuth 인증 취소. 취소됐으면 True."""
    global _active_oauth
    if _active_oauth and _active_oauth.is_running:
        await _active_oauth.cancel()
        _active_oauth = None
        return True
    return False


def is_oauth_running() -> bool:
    return _active_oauth is not None and _active_oauth.is_running


def get_auth_status() -> dict:
    """현재 인증 상태 요약."""
    api_key = get_api_key()
    return {
        "api_key_set": bool(api_key),
        "api_key_preview": f"{api_key[:8]}..." if api_key else None,
        "oauth_running": is_oauth_running(),
        "gemini_path": find_gemini_path(),
    }
