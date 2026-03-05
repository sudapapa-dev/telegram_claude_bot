"""Multi-AI engine session routing unit tests.

Test targets:
  - src/shared/models.py          -- AIEngine enum
  - src/shared/named_sessions.py  -- NamedSessionManager multi-engine features
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from src.shared.models import AIEngine, NamedSession, NamedSessionStatus
from src.shared.named_sessions import (
    AmbiguousSessionError,
    NamedSessionManager,
    NamedSessionNotFoundError,
)


# ============================================================================
# AIEngine enum
# ============================================================================


class TestAIEngine:
    """AIEngine enum basic behaviour."""

    def test_values(self):
        assert AIEngine.CLAUDE.value == "claude"
        assert AIEngine.GEMINI.value == "gemini"
        assert AIEngine.CODEX.value == "codex"

    def test_is_str_subclass(self):
        """AIEngine inherits str, so comparisons with plain strings work."""
        assert AIEngine.CLAUDE == "claude"
        assert AIEngine.GEMINI == "gemini"
        assert AIEngine.CODEX == "codex"

    def test_member_count(self):
        assert len(AIEngine) == 3

    def test_from_value(self):
        assert AIEngine("claude") is AIEngine.CLAUDE
        assert AIEngine("gemini") is AIEngine.GEMINI
        assert AIEngine("codex") is AIEngine.CODEX

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            AIEngine("gpt4")


# ============================================================================
# NamedSessionManager._make_key
# ============================================================================


class TestMakeKey:
    """_make_key: engine + name => unique key."""

    def test_basic(self):
        assert NamedSessionManager._make_key(AIEngine.CLAUDE, "David") == "claude:david"

    def test_different_engines_different_keys(self):
        k1 = NamedSessionManager._make_key(AIEngine.CLAUDE, "suho")
        k2 = NamedSessionManager._make_key(AIEngine.GEMINI, "suho")
        k3 = NamedSessionManager._make_key(AIEngine.CODEX, "suho")
        assert k1 != k2 != k3

    def test_case_insensitive(self):
        assert NamedSessionManager._make_key(AIEngine.CLAUDE, "Hello") == "claude:hello"
        assert NamedSessionManager._make_key(AIEngine.CLAUDE, "HELLO") == "claude:hello"

    def test_strips_whitespace(self):
        assert NamedSessionManager._make_key(AIEngine.GEMINI, "  suho  ") == "gemini:suho"

    def test_korean_name(self):
        assert NamedSessionManager._make_key(AIEngine.CLAUDE, "suho") == "claude:suho"


# ============================================================================
# NamedSessionManager.create
# ============================================================================


class TestCreate:
    """create: session creation with engine parameter."""

    async def test_create_default_engine_is_claude(self, manager: NamedSessionManager):
        with patch("src.shared.named_sessions.uuid") as mock_uuid, \
             patch("src.shared.ai_session._make_working_dir", return_value="/tmp/work"):
            mock_uuid.uuid4.return_value.hex = "aabbccdd1122"
            session = await manager.create("David")
        assert session.engine == AIEngine.CLAUDE
        assert session.display_name == "David"
        assert session.name == "claude:david"

    async def test_create_gemini_session(self, manager: NamedSessionManager):
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/work"):
            session = await manager.create("Suho", engine=AIEngine.GEMINI)
        assert session.engine == AIEngine.GEMINI
        assert session.name == "gemini:suho"

    async def test_create_codex_session(self, manager: NamedSessionManager):
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/work"):
            session = await manager.create("Bot", engine=AIEngine.CODEX)
        assert session.engine == AIEngine.CODEX
        assert session.name == "codex:bot"

    async def test_same_name_different_engines_creates_separate_sessions(
        self, manager: NamedSessionManager
    ):
        """Same display name with different engines should be two separate sessions."""
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/work"):
            s1 = await manager.create("helper", engine=AIEngine.CLAUDE)
            s2 = await manager.create("helper", engine=AIEngine.GEMINI)
        assert s1.name != s2.name
        assert len(manager.list_all()) == 2

    async def test_same_engine_same_name_raises_valueerror(
        self, manager: NamedSessionManager
    ):
        """Duplicate engine+name must raise ValueError."""
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/work"):
            await manager.create("dup", engine=AIEngine.CLAUDE)
            with pytest.raises(ValueError, match="dup"):
                await manager.create("dup", engine=AIEngine.CLAUDE)

    async def test_same_name_different_engine_no_error(
        self, manager: NamedSessionManager
    ):
        """Same name with different engine should NOT raise."""
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/work"):
            await manager.create("shared", engine=AIEngine.CLAUDE)
            await manager.create("shared", engine=AIEngine.GEMINI)
            await manager.create("shared", engine=AIEngine.CODEX)
        assert len(manager.list_all()) == 3

    async def test_create_with_explicit_working_dir(
        self, manager: NamedSessionManager
    ):
        session = await manager.create("proj", working_dir="/my/project", engine=AIEngine.GEMINI)
        assert session.working_dir == "/my/project"

    async def test_create_rejects_spaces_in_name(self, manager: NamedSessionManager):
        with pytest.raises(ValueError, match="공백"):
            await manager.create("my session", engine=AIEngine.CLAUDE)

    async def test_create_saves_to_db(self, manager: NamedSessionManager, mock_db: AsyncMock):
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/work"):
            session = await manager.create("dbtest", engine=AIEngine.CLAUDE)
        mock_db.save_named_session.assert_awaited_once()
        saved_session = mock_db.save_named_session.call_args[0][0]
        assert saved_session.name == session.name


# ============================================================================
# NamedSessionManager._find_key
# ============================================================================


class TestFindKey:
    """_find_key: lookup by name with optional engine filter."""

    async def _populate(self, manager: NamedSessionManager):
        """Create sessions for search tests."""
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/w"):
            await manager.create("alpha", engine=AIEngine.CLAUDE)
            await manager.create("alpha", engine=AIEngine.GEMINI)
            await manager.create("beta", engine=AIEngine.CODEX)

    async def test_find_with_engine_exact_match(self, manager: NamedSessionManager):
        await self._populate(manager)
        key = manager._find_key("alpha", engine=AIEngine.GEMINI)
        assert key == "gemini:alpha"

    async def test_find_with_engine_not_found(self, manager: NamedSessionManager):
        await self._populate(manager)
        key = manager._find_key("alpha", engine=AIEngine.CODEX)
        assert key is None

    async def test_find_without_engine_ambiguous_raises(
        self, manager: NamedSessionManager
    ):
        await self._populate(manager)
        with pytest.raises(AmbiguousSessionError):
            manager._find_key("alpha")

    async def test_find_without_engine_single_match(
        self, manager: NamedSessionManager
    ):
        """When only one engine has the name, _find_key returns it."""
        await self._populate(manager)
        key = manager._find_key("beta")  # only codex:beta exists
        assert key == "codex:beta"

    async def test_find_without_engine_case_insensitive(
        self, manager: NamedSessionManager
    ):
        await self._populate(manager)
        key = manager._find_key("BETA")
        assert key == "codex:beta"

    async def test_find_nonexistent_returns_none(self, manager: NamedSessionManager):
        await self._populate(manager)
        assert manager._find_key("gamma") is None
        assert manager._find_key("gamma", engine=AIEngine.CLAUDE) is None


# ============================================================================
# NamedSessionManager.get
# ============================================================================


class TestGet:
    """get: public lookup by name with optional engine."""

    async def _populate(self, manager: NamedSessionManager):
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/w"):
            await manager.create("X", engine=AIEngine.CLAUDE)
            await manager.create("X", engine=AIEngine.GEMINI)

    async def test_get_with_engine(self, manager: NamedSessionManager):
        await self._populate(manager)
        session = manager.get("X", engine=AIEngine.GEMINI)
        assert session is not None
        assert session.engine == AIEngine.GEMINI

    async def test_get_without_engine_ambiguous_raises(self, manager: NamedSessionManager):
        await self._populate(manager)
        with pytest.raises(AmbiguousSessionError):
            manager.get("X")

    async def test_get_nonexistent_returns_none(self, manager: NamedSessionManager):
        await self._populate(manager)
        assert manager.get("Z") is None
        assert manager.get("X", engine=AIEngine.CODEX) is None


# ============================================================================
# NamedSessionManager.parse_address
# ============================================================================


class TestParseAddress:
    """parse_address: @=Claude, #=Gemini, $=Codex routing."""

    async def _populate(self, manager: NamedSessionManager):
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/w"):
            await manager.create("jiho", engine=AIEngine.CLAUDE)
            await manager.create("suho", engine=AIEngine.GEMINI)
            await manager.create("david", engine=AIEngine.CODEX)

    async def test_at_routes_to_claude(self, manager: NamedSessionManager):
        await self._populate(manager)
        result = manager.parse_address("@jiho hello world")
        assert result is not None
        name, content = result
        assert name == "jiho"
        assert content == "hello world"

    async def test_double_at_routes_to_gemini(self, manager: NamedSessionManager):
        await self._populate(manager)
        result = manager.parse_address("@@suho report please")
        assert result is not None
        name, content = result
        assert name == "suho"
        assert content == "report please"

    async def test_triple_at_routes_to_codex(self, manager: NamedSessionManager):
        await self._populate(manager)
        result = manager.parse_address("@@@david write code")
        assert result is not None
        name, content = result
        assert name == "david"
        assert content == "write code"

    async def test_unregistered_session_returns_none(self, manager: NamedSessionManager):
        await self._populate(manager)
        assert manager.parse_address("@unknown hello") is None

    async def test_wrong_prefix_for_engine_returns_none(self, manager: NamedSessionManager):
        """@suho should not match because suho is Gemini (needs @@)."""
        await self._populate(manager)
        assert manager.parse_address("@suho hello") is None

    async def test_no_content_returns_none(self, manager: NamedSessionManager):
        await self._populate(manager)
        # No space after name => regex does not match
        assert manager.parse_address("@jiho") is None

    async def test_empty_string_returns_none(self, manager: NamedSessionManager):
        assert manager.parse_address("") is None

    async def test_plain_text_returns_none(self, manager: NamedSessionManager):
        await self._populate(manager)
        assert manager.parse_address("just normal text") is None

    async def test_multiline_content(self, manager: NamedSessionManager):
        await self._populate(manager)
        result = manager.parse_address("@jiho line1\nline2\nline3")
        assert result is not None
        name, content = result
        assert name == "jiho"
        assert "line1" in content
        assert "line3" in content

    async def test_at_does_not_route_to_gemini(self, manager: NamedSessionManager):
        """@suho should not match suho (Gemini) — wrong prefix."""
        await self._populate(manager)
        assert manager.parse_address("@suho hello") is None


# ============================================================================
# NamedSessionManager.parse_address_full
# ============================================================================


class TestParseAddressFull:
    """parse_address_full: returns (display_name, content, engine)."""

    async def _populate(self, manager: NamedSessionManager):
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/w"):
            await manager.create("jiho", engine=AIEngine.CLAUDE)
            await manager.create("suho", engine=AIEngine.GEMINI)
            await manager.create("david", engine=AIEngine.CODEX)

    async def test_returns_engine_claude(self, manager: NamedSessionManager):
        await self._populate(manager)
        result = manager.parse_address_full("@jiho hello")
        assert result is not None
        name, content, engine = result
        assert name == "jiho"
        assert content == "hello"
        assert engine == AIEngine.CLAUDE

    async def test_returns_engine_gemini(self, manager: NamedSessionManager):
        await self._populate(manager)
        result = manager.parse_address_full("@@suho report")
        assert result is not None
        _, _, engine = result
        assert engine == AIEngine.GEMINI

    async def test_returns_engine_codex(self, manager: NamedSessionManager):
        await self._populate(manager)
        result = manager.parse_address_full("@@@david code")
        assert result is not None
        _, _, engine = result
        assert engine == AIEngine.CODEX

    async def test_unregistered_returns_none(self, manager: NamedSessionManager):
        await self._populate(manager)
        assert manager.parse_address_full("@ghost hello") is None

    async def test_no_content_returns_none(self, manager: NamedSessionManager):
        await self._populate(manager)
        assert manager.parse_address_full("@@suho") is None


# ============================================================================
# NamedSessionManager.list_by_engine
# ============================================================================


class TestListByEngine:
    """list_by_engine: filtered and full listing."""

    async def _populate(self, manager: NamedSessionManager):
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/w"):
            await manager.create("a", engine=AIEngine.CLAUDE)
            await manager.create("b", engine=AIEngine.CLAUDE)
            await manager.create("c", engine=AIEngine.GEMINI)
            await manager.create("d", engine=AIEngine.CODEX)

    async def test_filter_claude(self, manager: NamedSessionManager):
        await self._populate(manager)
        result = manager.list_by_engine(AIEngine.CLAUDE)
        assert len(result) == 2
        assert all(s.engine == AIEngine.CLAUDE for s in result)

    async def test_filter_gemini(self, manager: NamedSessionManager):
        await self._populate(manager)
        result = manager.list_by_engine(AIEngine.GEMINI)
        assert len(result) == 1
        assert result[0].display_name == "c"

    async def test_filter_codex(self, manager: NamedSessionManager):
        await self._populate(manager)
        result = manager.list_by_engine(AIEngine.CODEX)
        assert len(result) == 1
        assert result[0].display_name == "d"

    async def test_filter_none_returns_all(self, manager: NamedSessionManager):
        await self._populate(manager)
        result = manager.list_by_engine(None)
        assert len(result) == 4

    async def test_empty_engine_returns_empty(self, manager: NamedSessionManager):
        """No Gemini sessions created => empty list."""
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/w"):
            await manager.create("only_claude", engine=AIEngine.CLAUDE)
        result = manager.list_by_engine(AIEngine.GEMINI)
        assert result == []


# ============================================================================
# NamedSessionManager.delete
# ============================================================================


class TestDelete:
    """delete: with and without engine specification."""

    async def _populate(self, manager: NamedSessionManager):
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/w"):
            await manager.create("target", engine=AIEngine.CLAUDE)
            await manager.create("target", engine=AIEngine.GEMINI)

    async def test_delete_with_engine(self, manager: NamedSessionManager):
        await self._populate(manager)
        result = await manager.delete("target", engine=AIEngine.GEMINI)
        assert result is True
        # Claude session should still exist
        assert manager.get("target", engine=AIEngine.CLAUDE) is not None
        # Gemini session should be gone
        assert manager.get("target", engine=AIEngine.GEMINI) is None

    async def test_delete_without_engine_ambiguous_raises(self, manager: NamedSessionManager):
        await self._populate(manager)
        with pytest.raises(AmbiguousSessionError):
            await manager.delete("target")

    async def test_delete_nonexistent_returns_false(self, manager: NamedSessionManager):
        result = await manager.delete("nonexistent")
        assert result is False

    async def test_delete_clears_default_session(self, manager: NamedSessionManager):
        """Deleting the default session should clear _default_session."""
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/w"):
            await manager.create("def_test", engine=AIEngine.CLAUDE)
        await manager.set_default("def_test", engine=AIEngine.CLAUDE)
        assert manager.default_session is not None

        await manager.delete("def_test", engine=AIEngine.CLAUDE)
        assert manager.default_session is None

    async def test_delete_calls_db(self, manager: NamedSessionManager, mock_db: AsyncMock):
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/w"):
            await manager.create("delme", engine=AIEngine.CODEX)
        mock_db.reset_mock()
        await manager.delete("delme", engine=AIEngine.CODEX)
        mock_db.delete_named_session.assert_awaited_once()


# ============================================================================
# NamedSessionManager.load_from_db -- legacy key migration
# ============================================================================


class TestLoadFromDbMigration:
    """load_from_db: legacy keys (no ':') should be migrated to engine:name."""

    async def test_legacy_key_migration(self, manager: NamedSessionManager, mock_db: AsyncMock):
        """A session stored with name='david' (no colon) should be migrated to 'claude:david'."""
        legacy_session = NamedSession(
            name="david",  # legacy: no engine prefix
            display_name="david",
            engine=AIEngine.CLAUDE,
            working_dir="/tmp/legacy",
        )
        mock_db.get_all_named_sessions.return_value = [(legacy_session, False)]

        count = await manager.load_from_db()
        assert count == 1
        # After migration, the key should be engine:name
        assert "claude:david" in manager._sessions
        migrated = manager._sessions["claude:david"]
        assert migrated.name == "claude:david"
        assert migrated.display_name == "david"
        assert migrated.engine == AIEngine.CLAUDE

    async def test_modern_key_no_migration(self, manager: NamedSessionManager, mock_db: AsyncMock):
        """A session stored with name='gemini:suho' should be used as-is."""
        modern_session = NamedSession(
            name="gemini:suho",
            display_name="suho",
            engine=AIEngine.GEMINI,
            working_dir="/tmp/modern",
        )
        mock_db.get_all_named_sessions.return_value = [(modern_session, False)]

        count = await manager.load_from_db()
        assert count == 1
        assert "gemini:suho" in manager._sessions
        session = manager._sessions["gemini:suho"]
        assert session.name == "gemini:suho"

    async def test_legacy_default_session_restored(
        self, manager: NamedSessionManager, mock_db: AsyncMock
    ):
        """A legacy session marked as default should set _default_session correctly."""
        legacy_session = NamedSession(
            name="main",
            display_name="main",
            engine=AIEngine.CLAUDE,
            working_dir="/tmp/main",
        )
        mock_db.get_all_named_sessions.return_value = [(legacy_session, True)]

        count = await manager.load_from_db()
        assert count == 1
        assert manager._default_session == "claude:main"

    async def test_duplicate_key_skipped(self, manager: NamedSessionManager, mock_db: AsyncMock):
        """If a session with the same key already exists in memory, skip it."""
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/w"):
            await manager.create("existing", engine=AIEngine.CLAUDE)

        db_session = NamedSession(
            name="claude:existing",
            display_name="existing",
            engine=AIEngine.CLAUDE,
            working_dir="/tmp/db",
        )
        mock_db.get_all_named_sessions.return_value = [(db_session, False)]

        count = await manager.load_from_db()
        assert count == 0  # skipped because already exists

    async def test_load_from_db_no_db(self, manager_no_db: NamedSessionManager):
        """When db is None, load_from_db returns 0."""
        count = await manager_no_db.load_from_db()
        assert count == 0

    async def test_load_from_db_exception_returns_zero(
        self, manager: NamedSessionManager, mock_db: AsyncMock
    ):
        """DB exception during load should be caught, returning 0."""
        mock_db.get_all_named_sessions.side_effect = Exception("DB error")
        count = await manager.load_from_db()
        assert count == 0

    async def test_multiple_sessions_mixed_legacy_modern(
        self, manager: NamedSessionManager, mock_db: AsyncMock
    ):
        """Mix of legacy and modern sessions should all load correctly."""
        legacy = NamedSession(
            name="old",
            display_name="old",
            engine=AIEngine.CLAUDE,
            working_dir="/tmp/old",
        )
        modern = NamedSession(
            name="gemini:new",
            display_name="new",
            engine=AIEngine.GEMINI,
            working_dir="/tmp/new",
        )
        mock_db.get_all_named_sessions.return_value = [
            (legacy, False),
            (modern, True),
        ]

        count = await manager.load_from_db()
        assert count == 2
        assert "claude:old" in manager._sessions
        assert "gemini:new" in manager._sessions
        assert manager._default_session == "gemini:new"


# ============================================================================
# PREFIX_ENGINE_MAP and ENGINE_ICONS constants
# ============================================================================


class TestConstants:
    """Verify the prefix-to-engine and engine-to-icon mappings."""

    def test_prefix_engine_map(self):
        assert NamedSessionManager.PREFIX_ENGINE_MAP["@"] == AIEngine.CLAUDE
        assert NamedSessionManager.PREFIX_ENGINE_MAP["@@"] == AIEngine.GEMINI
        assert NamedSessionManager.PREFIX_ENGINE_MAP["@@@"] == AIEngine.CODEX

    def test_engine_icons_has_all_engines(self):
        for engine in AIEngine:
            assert engine in NamedSessionManager.ENGINE_ICONS


# ============================================================================
# Integration-style: create + get + delete + list_by_engine
# ============================================================================


class TestMultiEngineIntegration:
    """End-to-end scenarios combining multiple operations."""

    async def test_full_lifecycle(self, manager: NamedSessionManager):
        """Create sessions across engines, query, list, delete."""
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/w"):
            await manager.create("worker", engine=AIEngine.CLAUDE)
            await manager.create("worker", engine=AIEngine.GEMINI)
            await manager.create("worker", engine=AIEngine.CODEX)

        # All 3 should exist
        assert len(manager.list_all()) == 3
        assert len(manager.list_by_engine(AIEngine.CLAUDE)) == 1
        assert len(manager.list_by_engine(AIEngine.GEMINI)) == 1
        assert len(manager.list_by_engine(AIEngine.CODEX)) == 1

        # get with engine
        claude_s = manager.get("worker", engine=AIEngine.CLAUDE)
        gemini_s = manager.get("worker", engine=AIEngine.GEMINI)
        codex_s = manager.get("worker", engine=AIEngine.CODEX)
        assert claude_s is not None and claude_s.engine == AIEngine.CLAUDE
        assert gemini_s is not None and gemini_s.engine == AIEngine.GEMINI
        assert codex_s is not None and codex_s.engine == AIEngine.CODEX

        # Delete Gemini only
        await manager.delete("worker", engine=AIEngine.GEMINI)
        assert manager.get("worker", engine=AIEngine.GEMINI) is None
        assert len(manager.list_all()) == 2

        # parse_address should work for remaining
        result = manager.parse_address("@worker hello")
        assert result is not None
        assert result[0] == "worker"

        # @@worker should fail (deleted)
        assert manager.parse_address("@@worker hello") is None

        # @@@worker should work
        result = manager.parse_address("@@@worker code it")
        assert result is not None
        assert result[0] == "worker"

    async def test_set_default_with_engine(self, manager: NamedSessionManager):
        """Setting default session with engine parameter."""
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/w"):
            await manager.create("main", engine=AIEngine.CLAUDE)
            await manager.create("main", engine=AIEngine.GEMINI)

        await manager.set_default("main", engine=AIEngine.GEMINI)
        default = manager.default_session
        assert default is not None
        assert default.engine == AIEngine.GEMINI
        assert default.display_name == "main"

    async def test_reset_session_with_engine(self, manager: NamedSessionManager):
        """reset should find correct session when engine is specified."""
        with patch("src.shared.ai_session._make_working_dir", return_value="/tmp/w"):
            await manager.create("resettable", engine=AIEngine.CODEX)

        session = await manager.reset("resettable", engine=AIEngine.CODEX)
        assert session.status == NamedSessionStatus.IDLE
        assert session.message_count == 0

    async def test_reset_nonexistent_raises(self, manager: NamedSessionManager):
        with pytest.raises(NamedSessionNotFoundError):
            await manager.reset("ghost", engine=AIEngine.CLAUDE)
