# Orchestrator Agent

## Role
Claude Code 프로세스의 생명주기 관리와 작업 실행을 전담하는 에이전트.
시스템의 핵심 엔진으로, 실제 Claude Code CLI를 제어한다.

## Scope
- `src/orchestrator/` 디렉토리 전체
- `src/shared/` 디렉토리 (공유 모듈 관리 책임)
- `tests/test_orchestrator/` 디렉토리

## Responsibilities

### Primary
1. **인스턴스 매니저** - Claude Code 프로세스 풀 관리 (생성, 삭제, 재시작)
2. **프로세스 제어** - asyncio.subprocess로 Claude Code CLI 실행
3. **작업 큐** - 비동기 작업 큐잉, 우선순위 관리, 동시성 제어
4. **상태 관리** - 인스턴스/작업 상태 추적 및 DB 영속화
5. **로그 수집** - 프로세스 stdout/stderr 실시간 캡처
6. **공유 모델 정의** - `src/shared/models.py` 데이터 모델 관리
7. **이벤트 발행** - 상태 변경 시 EventBus로 이벤트 발행 (텔레그램 봇이 수신)

### Secondary
- 리소스 모니터링 (CPU, 메모리 사용량)
- 자동 재시작 정책
- 작업 타임아웃 관리

## Technical Guidelines

### Claude Code CLI Integration
```python
# src/orchestrator/process.py
class ClaudeCodeProcess:
    """단일 Claude Code CLI 프로세스 래퍼"""

    async def execute(self, prompt: str) -> AsyncIterator[str]:
        """Claude Code에 프롬프트를 전달하고 스트리밍 응답 반환"""
        self.process = await asyncio.create_subprocess_exec(
            "claude", "-p", prompt,
            "--output-format", "stream-json",
            cwd=str(self.working_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        async for line in self.process.stdout:
            yield line.decode().strip()

    async def abort(self):
        """실행 중인 프로세스 강제 종료"""
        if self.process and self.process.returncode is None:
            self.process.terminate()
            await self.process.wait()
```

### Instance Manager Pattern
```python
# src/orchestrator/manager.py
class InstanceManager:
    """Claude Code 인스턴스 풀 관리자 - 텔레그램 봇이 직접 호출"""

    def __init__(self, db: Database, event_bus: EventBus):
        self._instances: dict[str, ClaudeCodeProcess] = {}
        self._db = db
        self._event_bus = event_bus

    async def create_instance(self, config: InstanceConfig) -> Instance: ...
    async def execute_task(self, instance_id: str, task: Task) -> TaskResult: ...
    async def get_all_status(self) -> SystemStatus: ...
    async def stop_instance(self, instance_id: str): ...
    async def get_logs(self, instance_id: str, limit: int = 50) -> list[str]: ...
```

### Task Queue Pattern
```python
# src/orchestrator/queue.py
class TaskQueue:
    """우선순위 기반 비동기 작업 큐"""

    def __init__(self, max_concurrent: int = 3):
        self._queue = asyncio.PriorityQueue()
        self._semaphore = asyncio.Semaphore(max_concurrent)
```

### Shared Models (src/shared/models.py)
```python
class InstanceStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Instance(BaseModel):
    id: str
    name: str
    working_dir: str
    status: InstanceStatus
    created_at: datetime
    current_task_id: str | None = None

class Task(BaseModel):
    id: str
    instance_id: str
    prompt: str
    status: TaskStatus
    priority: int = 0
    created_at: datetime
    completed_at: datetime | None = None
    result: str | None = None
    error: str | None = None

class SystemStatus(BaseModel):
    total: int
    running: int
    idle: int
    stopped: int
    error: int
    pending_tasks: int
```

## Dependencies
- aiosqlite
- structlog
- psutil

## Constraints
- Claude Code CLI는 `--output-format stream-json` 또는 `--output-format json` 사용
- 프로세스 생성 시 반드시 working_dir 지정
- 동시 실행 인스턴스 수 제한 (기본 max_concurrent=3)
- 모든 상태 변경은 DB에 즉시 반영 + EventBus로 이벤트 발행
- 프로세스 종료 시 리소스 정리 (좀비 프로세스 방지)
