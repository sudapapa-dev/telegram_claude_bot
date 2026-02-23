from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from src.orchestrator.process import ClaudeCodeProcess
from src.orchestrator.queue import TaskQueue
from src.shared.database import Database
from src.shared.events import EventBus
from src.shared.models import (
    Instance, InstanceConfig, InstanceStatus,
    SystemStatus, Task, TaskStatus,
)

logger = logging.getLogger(__name__)


class InstanceManager:
    """Claude Code 인스턴스 풀 관리자"""

    def __init__(
        self,
        db: Database,
        event_bus: EventBus,
        claude_path: str = "claude",
        max_concurrent: int = 3,
        task_timeout: int = 300,
    ) -> None:
        self._db = db
        self._event_bus = event_bus
        self._claude_path = claude_path
        self._task_timeout = task_timeout
        self._processes: dict[str, ClaudeCodeProcess] = {}
        self._queue = TaskQueue(max_concurrent=max_concurrent)
        self._queue.set_handler(self._handle_task)

    async def start(self) -> None:
        await self._queue.start()
        await self._restore_processes()
        logger.info("InstanceManager 시작")

    async def stop(self) -> None:
        await self._queue.stop()
        try:
            for proc in self._processes.values():
                await proc.abort()
        finally:
            self._processes.clear()
        logger.info("InstanceManager 중지")

    # ── Instance CRUD ──

    async def create_instance(self, config: InstanceConfig) -> Instance:
        instance = Instance(
            name=config.name, working_dir=config.working_dir,
            api_key=config.api_key, model=config.model,
            status=InstanceStatus.IDLE,
        )
        wd = Path(config.working_dir)
        if not wd.exists():
            wd.mkdir(parents=True, exist_ok=True)

        self._processes[instance.id] = ClaudeCodeProcess(
            instance_id=instance.id, working_dir=wd,
            api_key=config.api_key, model=config.model,
            claude_path=self._claude_path,
        )
        await self._db.save_instance(instance)
        await self._event_bus.emit("instance:created", instance)
        logger.info("인스턴스 생성: id=%s, name=%s", instance.id, instance.name)
        return instance

    async def delete_instance(self, instance_id: str) -> bool:
        proc = self._processes.get(instance_id)
        if proc and proc.is_running:
            await proc.abort()
        self._processes.pop(instance_id, None)
        await self._db.delete_instance(instance_id)
        await self._event_bus.emit("instance:deleted", instance_id)
        return True

    async def get_instance(self, instance_id: str) -> Instance | None:
        return await self._db.get_instance(instance_id)

    async def get_all_instances(self) -> list[Instance]:
        return await self._db.get_all_instances()

    async def update_model(self, instance_id: str, model: str) -> bool:
        """인스턴스 모델 변경"""
        instance = await self._db.get_instance(instance_id)
        if not instance:
            return False
        instance.model = model
        await self._db.save_instance(instance)
        proc = self._processes.get(instance_id)
        if proc:
            proc.model = model
        logger.info("모델 변경: id=%s, model=%s", instance_id, model)
        return True

    # ── Task ──

    async def submit_task(self, instance_id: str, prompt: str, priority: int = 0) -> Task:
        instance = await self._db.get_instance(instance_id)
        if not instance:
            raise ValueError(f"인스턴스를 찾을 수 없음: {instance_id}")

        task = Task(instance_id=instance_id, prompt=prompt, priority=priority)
        await self._db.save_task(task)
        await self._queue.enqueue(task)
        await self._event_bus.emit("task:queued", task)
        return task

    async def cancel_task(self, task_id: str) -> bool:
        task = await self._db.get_task(task_id)
        if not task:
            return False
        if task.status == TaskStatus.RUNNING:
            proc = self._processes.get(task.instance_id)
            if proc:
                await proc.abort()
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now(timezone.utc)
        await self._db.save_task(task)
        await self._event_bus.emit("task:cancelled", task)
        return True

    async def get_task(self, task_id: str) -> Task | None:
        return await self._db.get_task(task_id)

    async def get_task_history(self, instance_id: str, limit: int = 20) -> list[Task]:
        return await self._db.get_tasks_by_instance(instance_id, limit)

    # ── Monitoring ──

    async def get_status(self) -> SystemStatus:
        instances = await self._db.get_all_instances()
        pending = await self._db.get_pending_task_count()
        status = SystemStatus(total=len(instances), pending_tasks=pending + self._queue.pending_count)
        for inst in instances:
            match inst.status:
                case InstanceStatus.RUNNING: status.running += 1
                case InstanceStatus.IDLE: status.idle += 1
                case InstanceStatus.STOPPED: status.stopped += 1
                case InstanceStatus.ERROR: status.error += 1
        return status

    async def get_logs(self, instance_id: str, limit: int = 50) -> list[str]:
        proc = self._processes.get(instance_id)
        return proc.get_recent_logs(limit) if proc else []

    async def stop_instance(self, instance_id: str) -> bool:
        proc = self._processes.get(instance_id)
        if proc and proc.is_running:
            await proc.abort()
        instance = await self._db.get_instance(instance_id)
        if instance:
            instance.status = InstanceStatus.STOPPED
            instance.current_task_id = None
            await self._db.save_instance(instance)
            await self._event_bus.emit("instance:stopped", instance)
        return True

    async def stop_all(self) -> int:
        count = 0
        for iid in list(self._processes.keys()):
            await self.stop_instance(iid)
            count += 1
        return count

    # ── Internal ──

    async def _restore_processes(self) -> None:
        """재시작 후 DB 인스턴스를 _processes 딕셔너리에 복원"""
        instances = await self._db.get_all_instances()
        for inst in instances:
            if inst.id not in self._processes:
                wd = Path(inst.working_dir)
                self._processes[inst.id] = ClaudeCodeProcess(
                    instance_id=inst.id, working_dir=wd,
                    api_key=inst.api_key, model=inst.model,
                    claude_path=self._claude_path,
                )
            # 재시작 시 RUNNING 상태는 실제로 실행 중이지 않으므로 IDLE로 정리
            if inst.status == InstanceStatus.RUNNING:
                inst.status = InstanceStatus.IDLE
                inst.current_task_id = None
                await self._db.save_instance(inst)
        if instances:
            logger.info("프로세스 복원: %d개 인스턴스", len(instances))

    async def _handle_task(self, task: Task) -> None:
        proc = self._processes.get(task.instance_id)
        if not proc:
            task.status = TaskStatus.FAILED
            task.error = f"프로세스 없음: {task.instance_id}"
            await self._db.save_task(task)
            await self._event_bus.emit("task:failed", task)
            return

        instance = await self._db.get_instance(task.instance_id)
        if instance:
            instance.status = InstanceStatus.RUNNING
            instance.current_task_id = task.id
            await self._db.save_instance(instance)

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc)
        await self._db.save_task(task)
        await self._event_bus.emit("task:started", task)

        try:
            result = await proc.execute(task.prompt, timeout=self._task_timeout)
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = datetime.now(timezone.utc)
            await self._db.save_task(task)
            await self._event_bus.emit("task:completed", task)
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            task.completed_at = datetime.now(timezone.utc)
            await self._db.save_task(task)
            await self._event_bus.emit("task:failed", task)
        finally:
            if instance:
                instance.status = InstanceStatus.IDLE
                instance.current_task_id = None
                await self._db.save_instance(instance)
