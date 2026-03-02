"""pytest fixtures for telegram_claude_bot tests."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.shared.models import AIEngine, NamedSession
from src.shared.named_sessions import NamedSessionManager


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock Database -- all DB methods are AsyncMock."""
    db = AsyncMock()
    db.save_named_session = AsyncMock()
    db.delete_named_session = AsyncMock()
    db.get_all_named_sessions = AsyncMock(return_value=[])
    db.update_named_session_default = AsyncMock()
    db.clear_named_sessions_default = AsyncMock()
    return db


@pytest.fixture
def manager(mock_db: AsyncMock) -> NamedSessionManager:
    """NamedSessionManager with mocked DB."""
    return NamedSessionManager(db=mock_db)


@pytest.fixture
def manager_no_db() -> NamedSessionManager:
    """NamedSessionManager without DB (db=None)."""
    return NamedSessionManager(db=None)
