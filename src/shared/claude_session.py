from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class ClaudeProcess:
    """단일 Claude Code CLI 프로세스를 유지하며 대화를 처리."""

    def __init__(
        self,
        claude_path: str = "claude",
        model: str | None = None,
        working_dir: str | None = None,
        scripts_dir: str | None = None,
    ) -> None:
        self.claude_path = claude_path
        self.model = model
        self.working_dir = (working_dir.strip() if working_dir else None) or str(Path.home())
        self.scripts_dir = scripts_dir
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._ready = False

    async def start(self) -> None:
        """프로세스 시작"""
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
        scripts_info = ""
        if self.scripts_dir:
            scripts_info = (
                f"\n\nYou have pre-built utility scripts in: {self.scripts_dir}\n"
                "Available scripts (use with `python <script>`):\n"
                "- screenshot.py [monitor] [output]  : Take a screenshot. monitor=0 for all, 1/2/... for specific monitor.\n"
                "- launch_program.py <name> [args]   : Find and launch a program by name or path.\n"
                "- find_process.py [keyword]         : List running processes, optionally filtered by keyword.\n"
                "When a user asks to take a screenshot, launch a program, or find processes, "
                "use these scripts via the Bash tool. "
                "You can also CREATE new scripts in this folder when asked by the user."
            )
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
        logger.info("Claude CLI 프로세스 시작: pid=%s, cwd=%s", self._proc.pid, self.working_dir)

    async def ask(self, prompt: str, timeout: int = 300) -> str:
        """프롬프트 전송 후 응답 수집"""
        async with self._lock:
            if not self._ready or not self._proc or self._proc.returncode is not None:
                await self.start()

            # stream-json 입력 형식: {"type": "user", "message": {"role": "user", "content": "..."}}
            msg = json.dumps({
                "type": "user",
                "message": {"role": "user", "content": prompt},
            })
            self._proc.stdin.write((msg + "\n").encode())
            await self._proc.stdin.drain()

            return await asyncio.wait_for(self._collect_response(), timeout=timeout)

    async def _collect_response(self) -> str:
        """stdout에서 응답 완료까지 읽기"""
        result_parts: list[str] = []

        assert self._proc and self._proc.stdout
        async for raw in self._proc.stdout:
            line = raw.decode(errors="replace").strip()
            if not line:
                continue
            logger.debug("Claude stdout: %s", line)
            try:
                data = json.loads(line)
                t = data.get("type", "")

                # 텍스트 스트리밍 청크
                if t == "assistant":
                    for block in data.get("message", {}).get("content", []):
                        if isinstance(block, dict) and block.get("type") == "text":
                            result_parts.append(block["text"])

                # 최종 결과 (subtype: success/error)
                elif t == "result":
                    subtype = data.get("subtype", "")
                    if subtype == "error":
                        raise RuntimeError(data.get("error", {}).get("message", "오류 발생"))
                    # result 필드가 있으면 우선 사용, 없으면 누적된 assistant 텍스트 사용
                    final = data.get("result", "")
                    return final if final else "".join(result_parts) or "(응답 없음)"

                # 에러
                elif t == "error":
                    raise RuntimeError(data.get("message", "알 수 없는 오류"))

            except json.JSONDecodeError:
                logger.debug("JSON 파싱 실패 (무시): %s", line[:200])

        return "".join(result_parts) or "(응답 없음)"

    async def stop(self) -> None:
        """프로세스 종료"""
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.stdin.close()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except (asyncio.TimeoutError, Exception):
                self._proc.kill()
                await self._proc.wait()
        self._ready = False
        logger.info("Claude CLI 프로세스 종료")


# 전역 단일 프로세스 인스턴스
_default_process: ClaudeProcess | None = None
_history_store: "ChatHistoryStore | None" = None  # type: ignore[name-defined]


def init_default(
    claude_path: str = "claude",
    model: str | None = None,
    working_dir: str | None = None,
    scripts_dir: str | None = None,
) -> ClaudeProcess:
    """앱 시작 시 호출. 전역 프로세스 초기화."""
    global _default_process
    _default_process = ClaudeProcess(
        claude_path=claude_path,
        model=model,
        working_dir=working_dir,
        scripts_dir=scripts_dir,
    )
    return _default_process


def get_default() -> ClaudeProcess:
    if _default_process is None:
        raise RuntimeError("Claude 프로세스가 초기화되지 않았습니다.")
    return _default_process


def set_history_store(store: "ChatHistoryStore") -> None:  # type: ignore[name-defined]
    """ChatHistoryStore 연결 (main.py에서 초기화 후 호출)"""
    global _history_store
    _history_store = store


async def ask(prompt: str, timeout: int = 300) -> str:
    if _history_store:
        await _history_store.add("user", prompt)
    reply = await get_default().ask(prompt, timeout=timeout)
    if _history_store:
        await _history_store.add("assistant", reply)
    return reply


async def new_session() -> None:
    """새 대화 시작 - 기존 프로세스 종료 후 재시작 준비"""
    if _default_process:
        await _default_process.stop()


async def stop() -> None:
    if _default_process:
        await _default_process.stop()
