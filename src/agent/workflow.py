"""자율 개발 에이전트팀 - 워크플로우 엔진"""
from __future__ import annotations

import asyncio
import logging
import uuid
from asyncio import CancelledError
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable

from src.agent.prompts import (
    ANALYSIS_PROMPT,
    DESIGN_PROMPT,
    DEVELOPMENT_PROMPT,
    QA_PROMPT,
    TESTING_PROMPT,
)
from src.shared.ai_session import get_manager

logger = logging.getLogger(__name__)

UpdateCallback = Callable[[str], Awaitable[None]]


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowPhase(str, Enum):
    ANALYSIS = "analysis"
    DESIGN = "design"
    DEVELOPMENT = "development"
    TESTING = "testing"
    QA = "qa"


PHASE_LABELS = {
    WorkflowPhase.ANALYSIS: "🔍 1/5 요구사항 분석",
    WorkflowPhase.DESIGN: "📐 2/5 아키텍처 설계",
    WorkflowPhase.DEVELOPMENT: "💻 3/5 코드 개발",
    WorkflowPhase.TESTING: "🧪 4/5 테스트",
    WorkflowPhase.QA: "✅ 5/5 QA 최종 검증",
}


@dataclass
class Workflow:
    id: str
    requirement: str
    workspace_dir: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_phase: WorkflowPhase | None = None
    phase_results: dict[str, str] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    def elapsed(self) -> str:
        end = self.completed_at or datetime.now()
        secs = int((end - self.created_at).total_seconds())
        if secs < 60:
            return f"{secs}초"
        return f"{secs // 60}분 {secs % 60}초"


class WorkflowManager:
    """자율 개발 파이프라인 관리자"""

    def __init__(self, base_workspace: str = "D:/workspace") -> None:
        self._workflows: dict[str, Workflow] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self.base_workspace = Path(base_workspace)

    # ─────────────────────────────────────────────
    # 공개 API
    # ─────────────────────────────────────────────

    async def start(
        self,
        requirement: str,
        update_callback: UpdateCallback,
    ) -> Workflow:
        """새 워크플로우 시작. 즉시 반환하고 백그라운드에서 실행."""
        wf_id = uuid.uuid4().hex[:8]
        workspace = self.base_workspace / wf_id
        workspace.mkdir(parents=True, exist_ok=True)

        wf = Workflow(
            id=wf_id,
            requirement=requirement,
            workspace_dir=str(workspace),
        )
        self._workflows[wf_id] = wf
        self._cancel_events[wf_id] = asyncio.Event()

        task = asyncio.create_task(
            self._run_pipeline(wf, update_callback),
            name=f"workflow-{wf_id}",
        )
        self._tasks[wf_id] = task
        logger.info("워크플로우 시작: id=%s, req=%s...", wf_id, requirement[:50])
        return wf

    async def cancel(self, wf_id: str) -> bool:
        """워크플로우 취소 요청"""
        ev = self._cancel_events.get(wf_id)
        if ev:
            ev.set()
        task = self._tasks.get(wf_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    def get(self, wf_id: str) -> Workflow | None:
        return self._workflows.get(wf_id)

    def list_all(self) -> list[Workflow]:
        return sorted(self._workflows.values(), key=lambda w: w.created_at, reverse=True)

    def active(self) -> list[Workflow]:
        return [w for w in self._workflows.values() if w.status == WorkflowStatus.RUNNING]

    # ─────────────────────────────────────────────
    # 파이프라인 실행
    # ─────────────────────────────────────────────

    async def _run_pipeline(self, wf: Workflow, update_cb: UpdateCallback) -> None:
        wf.status = WorkflowStatus.RUNNING
        workspace = Path(wf.workspace_dir)
        mgr = get_manager()

        try:
            # ── 단계 1: PM 분석 ──
            await self._check_cancel(wf)
            wf.current_phase = WorkflowPhase.ANALYSIS
            await update_cb(f"🔍 **[1/5] 요구사항 분석 중...**\n`{wf.id}`")

            analysis = await mgr.ask(
                ANALYSIS_PROMPT.format(req=wf.requirement),
                timeout=300,
            )
            (workspace / "analysis.md").write_text(analysis, encoding="utf-8")
            wf.phase_results["analysis"] = analysis

            preview = analysis[:600] + ("..." if len(analysis) > 600 else "")
            await update_cb(f"✅ **분석 완료**\n\n{preview}")

            # ── 단계 2: 설계 ──
            await self._check_cancel(wf)
            wf.current_phase = WorkflowPhase.DESIGN
            await update_cb(f"📐 **[2/5] 아키텍처 설계 중...**")

            design = await mgr.ask(
                DESIGN_PROMPT.format(req=wf.requirement, analysis=analysis),
                timeout=300,
            )
            (workspace / "design.md").write_text(design, encoding="utf-8")
            wf.phase_results["design"] = design

            preview = design[:600] + ("..." if len(design) > 600 else "")
            await update_cb(f"✅ **설계 완료**\n\n{preview}")

            # ── 단계 3: 개발 ──
            await self._check_cancel(wf)
            wf.current_phase = WorkflowPhase.DEVELOPMENT
            src_dir = workspace / "src"
            await update_cb(f"💻 **[3/5] 코드 개발 중...**\n⏳ 이 단계는 시간이 걸릴 수 있습니다.")

            dev_result = await mgr.ask(
                DEVELOPMENT_PROMPT.format(
                    req=wf.requirement,
                    design=design,
                    workspace=str(src_dir),
                ),
                timeout=1800,
            )
            (workspace / "dev_log.md").write_text(dev_result, encoding="utf-8")
            wf.phase_results["development"] = dev_result

            # 생성된 파일 목록 수집
            if src_dir.exists():
                for f in src_dir.rglob("*"):
                    if f.is_file():
                        wf.artifacts.append(str(f.relative_to(workspace)))

            await update_cb(f"✅ **개발 완료**\n생성된 파일: {len(wf.artifacts)}개")

            # ── 단계 4: 테스트 ──
            await self._check_cancel(wf)
            wf.current_phase = WorkflowPhase.TESTING
            await update_cb(f"🧪 **[4/5] 테스트 작성 및 실행 중...**")

            test_result = await mgr.ask(
                TESTING_PROMPT.format(workspace=str(workspace)),
                timeout=900,
            )
            (workspace / "test_report.md").write_text(test_result, encoding="utf-8")
            wf.phase_results["testing"] = test_result

            preview = test_result[:400] + ("..." if len(test_result) > 400 else "")
            await update_cb(f"✅ **테스트 완료**\n\n{preview}")

            # ── 단계 5: QA ──
            await self._check_cancel(wf)
            wf.current_phase = WorkflowPhase.QA
            await update_cb(f"✅ **[5/5] QA 최종 검증 중...**")

            qa_result = await mgr.ask(
                QA_PROMPT.format(
                    req=wf.requirement,
                    analysis=analysis,
                    design=design,
                    test_result=test_result,
                    workspace=str(workspace),
                ),
                timeout=600,
            )
            (workspace / "qa_report.md").write_text(qa_result, encoding="utf-8")
            wf.phase_results["qa"] = qa_result

            # ── 완료 보고 ──
            wf.status = WorkflowStatus.COMPLETED
            wf.completed_at = datetime.now()

            artifact_list = "\n".join(f"  ├── {a}" for a in wf.artifacts) or "  (파일 없음)"
            summary = (
                f"🎉 **개발 완료!** (소요시간: {wf.elapsed()})\n\n"
                f"📁 결과물: `{wf.workspace_dir}`\n"
                f"{artifact_list}\n"
                f"  ├── analysis.md\n"
                f"  ├── design.md\n"
                f"  ├── dev_log.md\n"
                f"  ├── test_report.md\n"
                f"  └── qa_report.md\n\n"
                f"**QA 요약:**\n{qa_result[:800]}"
            )
            await update_cb(summary)
            logger.info("워크플로우 완료: id=%s, 소요=%s", wf.id, wf.elapsed())

        except (CancelledError, asyncio.CancelledError):
            wf.status = WorkflowStatus.CANCELLED
            wf.completed_at = datetime.now()
            await update_cb(f"🚫 **워크플로우 취소됨** (`{wf.id}`)")
            logger.info("워크플로우 취소: id=%s", wf.id)

        except Exception as e:
            wf.status = WorkflowStatus.FAILED
            wf.error = str(e)
            wf.completed_at = datetime.now()
            phase = wf.current_phase.value if wf.current_phase else "unknown"
            await update_cb(
                f"❌ **워크플로우 실패** (`{wf.id}`)\n"
                f"단계: {phase}\n오류: {e}"
            )
            logger.exception("워크플로우 실패: id=%s, phase=%s", wf.id, phase)

        finally:
            self._cancel_events.pop(wf.id, None)
            self._tasks.pop(wf.id, None)

    async def _check_cancel(self, wf: Workflow) -> None:
        """취소 여부 확인 - 취소 신호가 있으면 CancelledError 발생"""
        ev = self._cancel_events.get(wf.id)
        if ev and ev.is_set():
            raise CancelledError(f"사용자 취소: {wf.id}")
        # 이벤트 루프에 제어권 반환 (취소 기회 제공)
        await asyncio.sleep(0)


# ─────────────────────────────────────────────
# 전역 인스턴스
# ─────────────────────────────────────────────

_workflow_manager: WorkflowManager | None = None


def get_workflow_manager() -> WorkflowManager:
    global _workflow_manager
    if _workflow_manager is None:
        _workflow_manager = WorkflowManager()
    return _workflow_manager


def init_workflow_manager(base_workspace: str) -> WorkflowManager:
    global _workflow_manager
    _workflow_manager = WorkflowManager(base_workspace=base_workspace)
    return _workflow_manager
