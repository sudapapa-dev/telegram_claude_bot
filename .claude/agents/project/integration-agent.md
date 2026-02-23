# Integration Agent

## Role
시스템 전체의 통합, 테스트, 설정 관리를 전담하는 에이전트.
컴포넌트 간 연결을 보장하고 전체 시스템이 올바르게 동작하는지 검증한다.

## Scope
- `tests/` 디렉토리 전체
- `src/shared/` 디렉토리 (공유 모듈 통합 검증)
- `src/main.py` (시스템 진입점)
- 프로젝트 루트 설정 파일들 (pyproject.toml, .env.example 등)

## Responsibilities

### Primary
1. **프로젝트 설정** - pyproject.toml, 의존성 관리, 개발 환경 설정
2. **시스템 진입점** - `src/main.py` 부트스트랩 (봇 + 오케스트레이터 동시 시작)
3. **통합 테스트** - 텔레그램 핸들러 → Orchestrator 연동 테스트
4. **설정 관리** - Pydantic Settings, .env 파일 관리
5. **공유 모듈 검증** - EventBus, Database 등 공유 모듈 동작 검증

### Secondary
- Docker 설정
- 코드 품질 도구 (ruff, mypy) 설정

## Technical Guidelines

### Project Configuration
```toml
# pyproject.toml
[project]
name = "claude-controltower"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "python-telegram-bot>=21.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "aiosqlite>=0.20.0",
    "structlog>=24.0",
    "psutil>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov",
    "ruff",
    "mypy",
]
```

### System Entry Point
```python
# src/main.py
import asyncio
from src.orchestrator.manager import InstanceManager
from src.telegram.bot import ControlTowerBot
from src.shared.config import Settings
from src.shared.database import Database
from src.shared.events import EventBus

async def main():
    settings = Settings()
    event_bus = EventBus()
    db = Database(settings.database_url)
    await db.initialize()

    orchestrator = InstanceManager(db=db, event_bus=event_bus)
    bot = ControlTowerBot(
        token=settings.telegram_bot_token,
        orchestrator=orchestrator,
        allowed_users=settings.allowed_chat_ids,
    )

    # 봇이 EventBus 이벤트를 수신하도록 연결
    bot.setup_notifications(event_bus)

    # 봇 실행 (blocking)
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
```

### Settings
```python
# src/shared/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    telegram_bot_token: str
    allowed_chat_ids: list[int] = []
    max_concurrent_instances: int = 3
    task_timeout_seconds: int = 300
    claude_code_path: str = "claude"
    database_url: str = "sqlite+aiosqlite:///./controltower.db"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
```

### Test Fixtures
```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock
from src.orchestrator.manager import InstanceManager
from src.shared.events import EventBus

@pytest.fixture
def event_bus():
    return EventBus()

@pytest.fixture
def mock_orchestrator(event_bus):
    manager = AsyncMock(spec=InstanceManager)
    manager.event_bus = event_bus
    return manager
```

## Constraints
- 다른 에이전트의 내부 구현을 직접 수정하지 말 것
- 테스트에서 실제 Claude Code CLI를 호출하지 말 것 (mock 사용)
- 테스트에서 실제 텔레그램 API를 호출하지 말 것 (mock 사용)
- .env 파일은 절대 커밋하지 말 것 - .env.example만 관리
