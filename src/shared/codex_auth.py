"""Codex CLI OAuth Device Code Flow 인증 관리.

codex login --device-auth 프로세스를 subprocess로 실행하여
stdout에서 인증 URL과 코드를 파싱, 텔레그램으로 전달한다.
인증 완료/실패/취소는 콜백으로 상위에 통보한다.
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import sys
from pathlib import Path
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

# ANSI 색상 코드 제거용 정규식
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
# 인증 코드 패턴 (예: ABCD-1234, AB12-CD34)
_CODE_PATTERN = re.compile(r"\b([A-Z0-9]{4,8}-[A-Z0-9]{4,8})\b")
# URL 패턴
_URL_PATTERN = re.compile(r"https?://\S+")

OnCodeCallback = Callable[[str, str], Awaitable[None]]
OnDoneCallback = Callable[[], Awaitable[None]]
OnErrorCallback = Callable[[str], Awaitable[None]]


def find_codex_path() -> str | None:
    """codex CLI 실행 파일 경로 탐색."""
    found = shutil.which("codex")
    if found:
        return found

    if sys.platform == "win32":
        home = Path.home()
        candidates = [
            home / "AppData" / "Roaming" / "npm" / "codex.cmd",
            home / "AppData" / "Local" / "Programs" / "codex" / "codex.exe",
            home / ".local" / "bin" / "codex.exe",
        ]
        for p in candidates:
            if p.is_file():
                return str(p)
    else:
        for p in [
            Path.home() / ".local" / "bin" / "codex",
            Path("/usr/local/bin/codex"),
        ]:
            if p.is_file():
                return str(p)

    return None


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text).strip()


class CodexDeviceAuthSession:
    """단일 Device Code 인증 세션."""

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(
        self,
        codex_path: str,
        on_code: OnCodeCallback,
        on_done: OnDoneCallback,
        on_error: OnErrorCallback,
    ) -> None:
        """인증 프로세스 시작. 논블로킹 — 완료는 콜백으로 통보."""
        self._proc = await asyncio.create_subprocess_exec(
            codex_path, "login", "--device-auth",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self._task = asyncio.create_task(
            self._run(on_code, on_done, on_error),
            name="codex_device_auth",
        )

    async def _run(
        self,
        on_code: OnCodeCallback,
        on_done: OnDoneCallback,
        on_error: OnErrorCallback,
    ) -> None:
        url: str | None = None
        code: str | None = None
        code_sent = False

        try:
            assert self._proc and self._proc.stdout
            async for raw in self._proc.stdout:
                line = _strip_ansi(raw.decode("utf-8", errors="replace"))
                if not line:
                    continue
                logger.debug("codex login stdout: %s", line)

                # URL 파싱
                if not url:
                    m = _URL_PATTERN.search(line)
                    if m:
                        url = m.group(0).rstrip(".,)")

                # 인증 코드 파싱
                if not code:
                    m = _CODE_PATTERN.search(line)
                    if m:
                        code = m.group(1)

                # URL + 코드 모두 확보되면 텔레그램으로 전송
                if url and code and not code_sent:
                    code_sent = True
                    try:
                        await on_code(url, code)
                    except Exception:
                        logger.exception("on_code 콜백 오류")

            await self._proc.wait()

            if self._proc.returncode == 0:
                await on_done()
            else:
                await on_error(f"인증 프로세스가 종료 코드 {self._proc.returncode}으로 종료됐습니다.")

        except asyncio.CancelledError:
            await self.cancel()
            raise
        except Exception as e:
            logger.exception("codex 인증 오류")
            await on_error(str(e))

    async def cancel(self) -> None:
        """진행 중인 인증 취소."""
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except Exception:
                self._proc.kill()
        if self._task and not self._task.done():
            self._task.cancel()


# ── 전역 인증 세션 (동시에 1개만) ──────────────────────────
_active_session: CodexDeviceAuthSession | None = None


async def start_device_auth(
    on_code: OnCodeCallback,
    on_done: OnDoneCallback,
    on_error: OnErrorCallback,
) -> None:
    """Codex Device Code 인증 시작.

    이미 진행 중이면 RuntimeError. codex CLI 미설치 시 RuntimeError.
    """
    global _active_session

    if _active_session and _active_session.is_running:
        raise RuntimeError("이미 Codex 인증이 진행 중입니다.")

    codex_path = find_codex_path()
    if not codex_path:
        raise RuntimeError(
            "codex CLI를 찾을 수 없습니다.\n"
            "`npm install -g @openai/codex` 로 설치 후 다시 시도하세요."
        )

    _active_session = CodexDeviceAuthSession()
    await _active_session.start(codex_path, on_code, on_done, on_error)
    logger.info("Codex Device Code 인증 시작: path=%s", codex_path)


async def cancel_device_auth() -> bool:
    """진행 중인 인증 취소. 취소됐으면 True."""
    global _active_session
    if _active_session and _active_session.is_running:
        await _active_session.cancel()
        _active_session = None
        return True
    return False


def is_auth_running() -> bool:
    """현재 인증이 진행 중인지 여부."""
    return _active_session is not None and _active_session.is_running
