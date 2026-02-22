"""AI 세션 추상화 레이어 - Claude / Gemini CLI 통합 관리"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class AIProvider(str, Enum):
    CLAUDE = "claude"
    GEMINI = "gemini"

    @classmethod
    def from_str(cls, s: str) -> "AIProvider":
        s = s.strip().lower()
        if s in ("claude", "c"):
            return cls.CLAUDE
        if s in ("gemini", "g"):
            return cls.GEMINI
        raise ValueError(f"알 수 없는 AI 제공자: {s}")

    def display_name(self) -> str:
        return {
            AIProvider.CLAUDE: "🟣 Claude Code",
            AIProvider.GEMINI: "🔵 Gemini CLI",
        }[self]

    def emoji(self) -> str:
        return {
            AIProvider.CLAUDE: "🟣",
            AIProvider.GEMINI: "🔵",
        }[self]


# ─────────────────────────────────────────────
# 기본 프로세스 세션 (추상)
# ─────────────────────────────────────────────

class BaseAISession(ABC):
    """AI CLI 프로세스를 유지하는 기본 클래스"""

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._ready = False

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def ask(self, prompt: str, timeout: int = 300) -> str: ...

    async def stop(self) -> None:
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.stdin.close()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except (asyncio.TimeoutError, Exception):
                self._proc.kill()
                await self._proc.wait()
        self._ready = False
        logger.info("%s 프로세스 종료", self.__class__.__name__)


# ─────────────────────────────────────────────
# Claude Code CLI 세션
# ─────────────────────────────────────────────

class ClaudeSession(BaseAISession):
    """Claude Code CLI (stream-json 프로토콜)"""

    def __init__(
        self,
        claude_path: str = "claude",
        model: str | None = None,
        working_dir: str | None = None,
        scripts_dir: str | None = None,
    ) -> None:
        super().__init__()
        self.claude_path = claude_path
        self.model = model
        self.working_dir = (working_dir.strip() if working_dir else None) or str(Path.home())
        self.scripts_dir = scripts_dir

    async def start(self) -> None:
        scripts_info = ""
        if self.scripts_dir:
            scripts_info = (
                f"\n\nYou have pre-built utility scripts in: {self.scripts_dir}\n"
                "Available scripts (use with `python <script>`):\n"
                "- screenshot.py [monitor] [output]  : Take a screenshot.\n"
                "- launch_program.py <name> [args]   : Find and launch a program by name or path.\n"
                "- find_process.py [keyword]         : List running processes.\n"
                "When a user asks to take a screenshot, launch a program, or find processes, "
                "use these scripts via the Bash tool. "
                "You can also CREATE new scripts in this folder when asked by the user."
            )

        cmd = [
            self.claude_path, "-p",
            "--dangerously-skip-permissions",
            "--verbose",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--strict-mcp-config", "[]",
        ]
        if self.model:
            cmd += ["--model", self.model]
        cmd += [
            "--system-prompt",
            (
                "You are an autonomous agent controlling a Windows PC via Telegram. "
                "Always use tools (Bash, Read, Write, Edit, etc.) to execute tasks directly. "
                "Never just describe how to do something — actually do it."
                + scripts_info
            ),
        ]

        env = os.environ.copy()
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.working_dir,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._ready = True
        logger.info("Claude CLI 시작: pid=%s", self._proc.pid)

    async def ask(self, prompt: str, timeout: int = 300) -> str:
        async with self._lock:
            if not self._ready or not self._proc or self._proc.returncode is not None:
                await self.start()

            msg = json.dumps({
                "type": "user",
                "message": {"role": "user", "content": prompt},
            })
            self._proc.stdin.write((msg + "\n").encode())
            await self._proc.stdin.drain()
            return await asyncio.wait_for(self._collect_response(), timeout=timeout)

    async def _collect_response(self) -> str:
        result_parts: list[str] = []
        assert self._proc and self._proc.stdout
        async for raw in self._proc.stdout:
            line = raw.decode(errors="replace").strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                t = data.get("type", "")
                if t == "assistant":
                    for block in data.get("message", {}).get("content", []):
                        if isinstance(block, dict) and block.get("type") == "text":
                            result_parts.append(block["text"])
                elif t == "result":
                    if data.get("subtype") == "error":
                        raise RuntimeError(data.get("error", {}).get("message", "오류 발생"))
                    final = data.get("result", "")
                    return final if final else "".join(result_parts) or "(응답 없음)"
                elif t == "error":
                    raise RuntimeError(data.get("message", "알 수 없는 오류"))
            except json.JSONDecodeError:
                pass
        return "".join(result_parts) or "(응답 없음)"


# ─────────────────────────────────────────────
# Gemini CLI 세션 (Google OAuth 로그인 방식)
# ─────────────────────────────────────────────

class GeminiSession(BaseAISession):
    """Google Gemini CLI - OAuth 로그인 방식 (API Key 불필요)

    gemini CLI는 대화형 TUI로 동작하므로 요청별 subprocess 실행 방식 사용.
    ~/.gemini/oauth_creds.json 이 있으면 자동 로그인됨.
    """

    def __init__(
        self,
        gemini_path: str = "gemini",
        model: str | None = None,
        working_dir: str | None = None,
    ) -> None:
        super().__init__()
        self.gemini_path = gemini_path
        self.model = model or "gemini-2.0-flash"
        self.working_dir = (working_dir.strip() if working_dir else None) or str(Path.home())

    async def start(self) -> None:
        # Gemini CLI는 요청별 실행 방식 - start는 준비만 확인
        self._ready = True
        logger.info("Gemini CLI 세션 준비 완료 (요청별 실행 모드)")

    async def ask(self, prompt: str, timeout: int = 300) -> str:
        async with self._lock:
            if not self._ready:
                await self.start()

            # gemini -p "<prompt>" 방식으로 비대화형 실행
            # --model 옵션으로 모델 지정
            cmd = [
                self.gemini_path,
                "-p", prompt,
            ]

            env = os.environ.copy()
            # HOME 환경변수로 OAuth credentials 경로 지정
            # ~/.gemini/oauth_creds.json 을 자동으로 사용
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=self.working_dir,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                output = stdout.decode(errors="replace").strip()
                err = stderr.decode(errors="replace").strip()

                if proc.returncode != 0 and not output:
                    # 인증 오류 감지
                    if "auth" in err.lower() or "login" in err.lower() or "credential" in err.lower():
                        raise RuntimeError(
                            "🔵 Gemini 인증이 필요합니다.\n"
                            "PC에서 `gemini auth login` 을 실행해주세요."
                        )
                    raise RuntimeError(f"Gemini CLI 오류: {err[:300]}")

                return output or "(응답 없음)"

            except FileNotFoundError:
                raise RuntimeError(
                    f"Gemini CLI({self.gemini_path})를 찾을 수 없습니다.\n"
                    "설치: npm install -g @google/gemini-cli"
                )

    async def stop(self) -> None:
        self._ready = False
        logger.info("Gemini CLI 세션 종료")


# ─────────────────────────────────────────────
# 독립 작업 세션 (매번 새 프로세스, 백그라운드)
# ─────────────────────────────────────────────

class TaskSession:
    """독립 작업 세션 - 매번 새 Claude 프로세스로 실행, 완료 후 종료.

    대화 세션(ClaudeSession)과 완전히 분리되어 메인 대화를 블로킹하지 않음.
    """

    def __init__(
        self,
        task_id: str,
        prompt: str,
        claude_path: str = "claude",
        model: str | None = None,
        working_dir: str | None = None,
        on_done: "Callable[[str, str, str | None], None] | None" = None,
    ) -> None:
        from typing import Callable
        self.task_id = task_id
        self.prompt = prompt
        self.claude_path = claude_path
        self.model = model
        self.working_dir = (working_dir.strip() if working_dir else None) or str(Path.home())
        self.on_done = on_done  # (task_id, result, error) 콜백
        self._task: asyncio.Task | None = None

    def start(self) -> asyncio.Task:
        """백그라운드 asyncio Task로 실행 시작"""
        self._task = asyncio.create_task(self._run(), name=f"task-{self.task_id}")
        return self._task

    async def cancel(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    async def _run(self) -> None:
        session = ClaudeSession(
            claude_path=self.claude_path,
            model=self.model,
            working_dir=self.working_dir,
        )
        result: str | None = None
        error: str | None = None
        try:
            await session.start()
            result = await session.ask(self.prompt, timeout=1800)
        except asyncio.CancelledError:
            error = "취소됨"
        except Exception as e:
            error = str(e)
            logger.exception("TaskSession 실패: id=%s", self.task_id)
        finally:
            await session.stop()
            if self.on_done:
                try:
                    await self.on_done(self.task_id, result or "", error)
                except Exception:
                    logger.exception("TaskSession 콜백 오류: id=%s", self.task_id)
            logger.info("TaskSession 완료: id=%s, error=%s", self.task_id, error)


class TaskSessionManager:
    """실행 중인 TaskSession 목록 관리"""

    def __init__(self, claude_path: str = "claude", model: str | None = None, working_dir: str | None = None) -> None:
        self.claude_path = claude_path
        self.model = model
        self.working_dir = working_dir
        self._sessions: dict[str, TaskSession] = {}

    def run(
        self,
        task_id: str,
        prompt: str,
        on_done: "Callable | None" = None,
    ) -> TaskSession:
        """새 독립 작업 세션 시작"""
        from typing import Callable
        session = TaskSession(
            task_id=task_id,
            prompt=prompt,
            claude_path=self.claude_path,
            model=self.model,
            working_dir=self.working_dir,
            on_done=on_done,
        )
        self._sessions[task_id] = session
        session.start()
        logger.info("TaskSession 시작: id=%s, prompt=%s...", task_id, prompt[:50])
        return session

    async def cancel(self, task_id: str) -> bool:
        session = self._sessions.get(task_id)
        if session:
            await session.cancel()
            return True
        return False

    def list_active(self) -> list[str]:
        return [tid for tid, s in self._sessions.items() if s._task and not s._task.done()]

    async def cancel_all(self) -> None:
        for session in self._sessions.values():
            await session.cancel()
        self._sessions.clear()


# ─────────────────────────────────────────────
# 전역 세션 관리자
# ─────────────────────────────────────────────

class AISessionManager:
    """현재 활성 AI 세션을 관리 (provider 전환 지원)"""

    def __init__(self) -> None:
        self._session: BaseAISession | None = None
        self._provider: AIProvider = AIProvider.CLAUDE
        self._history_store = None
        self._configs: dict[str, dict] = {}
        self.task_sessions: TaskSessionManager = TaskSessionManager()

    def configure(
        self,
        *,
        claude_path: str = "claude",
        claude_model: str | None = None,
        claude_working_dir: str | None = None,
        claude_scripts_dir: str | None = None,
        gemini_path: str = "gemini",
        gemini_model: str | None = None,
        working_dir: str | None = None,
    ) -> None:
        self._configs = {
            "claude": {
                "path": claude_path,
                "model": claude_model,
                "working_dir": claude_working_dir or working_dir,
                "scripts_dir": claude_scripts_dir,
            },
            "gemini": {
                "path": gemini_path,
                "model": gemini_model,
                "working_dir": working_dir,
            },
        }
        # 작업 세션 매니저도 같은 Claude 설정으로 초기화
        self.task_sessions = TaskSessionManager(
            claude_path=claude_path,
            model=claude_model,
            working_dir=claude_working_dir or working_dir,
        )

    def set_history_store(self, store) -> None:
        self._history_store = store

    @property
    def provider(self) -> AIProvider:
        return self._provider

    def _build_session(self, provider: AIProvider) -> BaseAISession:
        cfg = self._configs
        if provider == AIProvider.CLAUDE:
            c = cfg.get("claude", {})
            return ClaudeSession(
                claude_path=c.get("path", "claude"),
                model=c.get("model"),
                working_dir=c.get("working_dir"),
                scripts_dir=c.get("scripts_dir"),
            )
        elif provider == AIProvider.GEMINI:
            c = cfg.get("gemini", {})
            return GeminiSession(
                gemini_path=c.get("path", "gemini"),
                model=c.get("model"),
                working_dir=c.get("working_dir"),
            )
        raise ValueError(f"지원하지 않는 provider: {provider}")

    async def switch_provider(self, provider: AIProvider) -> None:
        if self._session:
            await self._session.stop()
            self._session = None
        self._provider = provider
        logger.info("AI Provider 전환: %s", provider.value)

    async def ask(self, prompt: str, timeout: int = 300) -> str:
        if self._history_store:
            await self._history_store.add("user", prompt)

        if self._session is None:
            self._session = self._build_session(self._provider)

        reply = await self._session.ask(prompt, timeout=timeout)

        if self._history_store:
            await self._history_store.add("assistant", reply)
        return reply

    async def new_session(self, provider: AIProvider | None = None) -> None:
        if provider and provider != self._provider:
            await self.switch_provider(provider)
        elif self._session:
            await self._session.stop()
            self._session = None
        logger.info("새 세션 시작: provider=%s", self._provider.value)

    async def stop(self) -> None:
        if self._session:
            await self._session.stop()
            self._session = None


# ─────────────────────────────────────────────
# 전역 인스턴스 (모듈 레벨 래퍼)
# ─────────────────────────────────────────────

_manager: AISessionManager = AISessionManager()


def get_manager() -> AISessionManager:
    return _manager


def init_default(
    claude_path: str = "claude",
    model: str | None = None,
    working_dir: str | None = None,
    scripts_dir: str | None = None,
    gemini_path: str = "gemini",
    gemini_model: str | None = None,
) -> AISessionManager:
    _manager.configure(
        claude_path=claude_path,
        claude_model=model,
        claude_working_dir=working_dir,
        claude_scripts_dir=scripts_dir,
        gemini_path=gemini_path,
        gemini_model=gemini_model,
        working_dir=working_dir,
    )
    return _manager


def set_history_store(store) -> None:
    _manager.set_history_store(store)


async def ask(prompt: str, timeout: int = 300) -> str:
    return await _manager.ask(prompt, timeout=timeout)


async def new_session(provider: AIProvider | None = None) -> None:
    await _manager.new_session(provider)


async def stop() -> None:
    await _manager.stop()
