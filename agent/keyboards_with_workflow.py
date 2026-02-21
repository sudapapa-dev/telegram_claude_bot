from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.shared.models import Instance, InstanceStatus, Task, TaskStatus
from src.shared.ai_session import AIProvider

_STATUS_EMOJI = {
    InstanceStatus.IDLE: "\u2b55",
    InstanceStatus.RUNNING: "\U0001f7e2",
    InstanceStatus.ERROR: "\u26a0\ufe0f",
    InstanceStatus.STOPPED: "\U0001f534",
}


def instance_list_keyboard(instances: list[Instance]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=f"{_STATUS_EMOJI.get(i.status, '?')} {i.name} ({i.status.value})",
            callback_data=f"inst:{i.id}",
        )]
        for i in instances
    ]
    buttons.append([InlineKeyboardButton("\U0001f504 새로고침", callback_data="refresh:instances")])
    return InlineKeyboardMarkup(buttons)


def instance_detail_keyboard(instance: Instance) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("\u25b6\ufe0f 작업 실행", callback_data=f"action:run:{instance.id}"),
            InlineKeyboardButton("\U0001f4cb 로그", callback_data=f"action:logs:{instance.id}"),
        ],
        [
            InlineKeyboardButton("\u23f9 중지", callback_data=f"action:stop:{instance.id}"),
            InlineKeyboardButton("\U0001f5d1 삭제", callback_data=f"action:delete:{instance.id}"),
        ],
        [
            InlineKeyboardButton("\U0001f4dc 히스토리", callback_data=f"action:history:{instance.id}"),
        ],
        [InlineKeyboardButton("\u00ab 목록으로", callback_data="back:instances")],
    ]
    return InlineKeyboardMarkup(buttons)


def confirm_keyboard(action: str, target_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\u2705 확인", callback_data=f"confirm:{action}:{target_id}"),
            InlineKeyboardButton("\u274c 취소", callback_data="cancel"),
        ]
    ])


def ai_select_keyboard(current: AIProvider) -> InlineKeyboardMarkup:
    """AI provider 선택 인라인 키보드"""
    def _btn(provider: AIProvider) -> InlineKeyboardButton:
        label = provider.display_name()
        if provider == current:
            label = "✅ " + label  # 현재 선택 표시
        return InlineKeyboardButton(label, callback_data=f"ai_select:{provider.value}")

    return InlineKeyboardMarkup([
        [_btn(AIProvider.CLAUDE)],
        [_btn(AIProvider.GEMINI)],
        [InlineKeyboardButton("❌ 취소", callback_data="cancel")],
    ])


def workflow_control_keyboard(workflow_id: str) -> InlineKeyboardMarkup:
    """워크플로우 제어 키보드 (취소 버튼)"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 취소", callback_data=f"workflow:cancel:{workflow_id}")],
    ])


def workflow_status_keyboard(workflow_id: str) -> InlineKeyboardMarkup:
    """워크플로우 상태 조회 키보드"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 상태 새로고침", callback_data=f"workflow:status:{workflow_id}")],
        [InlineKeyboardButton("🚫 취소", callback_data=f"workflow:cancel:{workflow_id}")],
    ])


def task_list_keyboard(tasks: list[Task]) -> InlineKeyboardMarkup:
    emoji = {
        TaskStatus.COMPLETED: "\u2705", TaskStatus.FAILED: "\u274c",
        TaskStatus.RUNNING: "\u23f3", TaskStatus.PENDING: "\u23f8",
        TaskStatus.CANCELLED: "\U0001f6ab",
    }
    buttons = [
        [InlineKeyboardButton(
            text=f"{emoji.get(t.status, '?')} {t.prompt[:30]}...",
            callback_data=f"task:{t.id}",
        )]
        for t in tasks[:10]
    ]
    return InlineKeyboardMarkup(buttons)
