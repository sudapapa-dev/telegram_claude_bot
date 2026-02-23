from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import deque
from collections.abc import AsyncIterator
from pathlib import Path

logger = logging.getLogger(__name__)


class ClaudeCodeProcess:
    """단일 Claude Code CLI 프로세스 래퍼"""

    def __init__(
        self,
        instance_id: str,
        working_dir: Path,
        api_key: str,
        model: str,
        claude_path: str = "claude",
    ) -> None:
        self.instance_id = instance_id
        self.working_dir = working_dir
        self.api_key = api_key
        self.model = model
        self.claude_path = claude_path
        self.process: asyncio.subprocess.Process | None = None
        self._log_buffer: deque[str] = deque(maxlen=500)

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.returncode is None

    def get_recent_logs(self, limit: int = 50) -> list[str]:
        """최근 로그 라인 반환"""
        buf = list(self._log_buffer)
        return buf[-limit:]

    async def execute(self, prompt: str, timeout: int = 300) -> str:
        """Claude Code에 프롬프트를 전달하고 결과 반환"""
        env = os.environ.copy()
        env["ANTHROPIC_API_KEY"] = self.api_key

        cmd = [
            self.claude_path, "-p", prompt,
            "--model", self.model,
            "--output-format", "json",
        ]

        logger.info("Claude Code 실행: instance=%s, model=%s", self.instance_id, self.model)

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self.working_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                self.process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
            raise TimeoutError(f"작업 타임아웃 ({timeout}초 초과)")

        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")

        for line in stdout.splitlines():
            self._append_log(line)
        for line in stderr.splitlines():
            self._append_log(f"[stderr] {line}")

        if self.process.returncode != 0:
            err_msg = stderr.strip()[:500] if stderr.strip() else f"종료 코드: {self.process.returncode}"
            raise RuntimeError(err_msg)

        return self._parse_output(stdout)

    async def execute_stream(self, prompt: str) -> AsyncIterator[str]:
        """스트리밍 응답 반환"""
        env = os.environ.copy()
        env["ANTHROPIC_API_KEY"] = self.api_key

        cmd = [
            self.claude_path, "-p", prompt,
            "--model", self.model,
            "--output-format", "stream-json",
        ]

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self.working_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        assert self.process.stdout
        async for raw_line in self.process.stdout:
            line = raw_line.decode(errors="replace").strip()
            if not line:
                continue
            self._append_log(line)
            try:
                data = json.loads(line)
                if data.get("type") == "assistant" and "content" in data:
                    for block in data["content"]:
                        if block.get("type") == "text":
                            yield block["text"]
                elif data.get("type") == "result" and "result" in data:
                    yield data["result"]
            except json.JSONDecodeError:
                yield line

        await self.process.wait()

    async def abort(self) -> None:
        """프로세스 강제 종료"""
        if self.process and self.process.returncode is None:
            logger.info("프로세스 종료: instance=%s", self.instance_id)
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()

    def _append_log(self, line: str) -> None:
        self._log_buffer.append(line)

    @staticmethod
    def _parse_output(raw: str) -> str:
        """Claude Code JSON 출력에서 결과 텍스트 추출"""
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                if "result" in data:
                    return data["result"]
                if "content" in data:
                    texts = [
                        b["text"] for b in data["content"]
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    if texts:
                        return "\n".join(texts)
            return raw
        except json.JSONDecodeError:
            return raw
