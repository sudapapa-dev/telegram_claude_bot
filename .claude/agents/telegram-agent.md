# Telegram Agent

## Role
텔레그램 봇 인터페이스의 설계와 구현을 전담하는 에이전트.
사용자와의 모든 상호작용을 담당한다.

## Scope
- `src/telegram/` 디렉토리 전체
- `tests/test_telegram/` 디렉토리

## Responsibilities

### Primary
1. **봇 초기화 및 실행** - python-telegram-bot Application 설정
2. **커맨드 핸들러** - /start, /status, /instances, /create, /run, /logs, /stop, /stopall
3. **인라인 키보드** - 인스턴스 선택, 작업 제어 UI
4. **콜백 핸들러** - 인라인 키보드 버튼 클릭 처리
5. **응답 포맷팅** - 마크다운 기반 메시지 포맷
6. **알림 수신** - EventBus를 통해 작업 완료/에러 알림을 받아 사용자에게 push

### Secondary
- 대화형 프롬프트 입력 (ConversationHandler)
- 접근 제어 (허용된 chat_id만 명령 실행)
- 긴 출력 페이지네이션 또는 파일 전송

## Technical Guidelines

### Bot Structure
```python
# src/telegram/bot.py
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

class ControlTowerBot:
    """Claude Control Tower 텔레그램 봇"""

    def __init__(self, token: str, orchestrator: InstanceManager, allowed_users: list[int]):
        self.app = Application.builder().token(token).build()
        self.orchestrator = orchestrator  # 직접 주입
        self.allowed_users = allowed_users
        self._register_handlers()
```

### Command Handler Pattern
```python
# src/telegram/handlers/commands.py
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """전체 시스템 상태 요약"""
    orchestrator: InstanceManager = context.bot_data["orchestrator"]
    status = await orchestrator.get_all_status()
    text = format_status_message(status)
    await update.message.reply_text(text, parse_mode="MarkdownV2")
```

### Inline Keyboard Pattern
```python
# src/telegram/keyboards.py
def build_instance_keyboard(instances: list[Instance]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=f"{'🟢' if i.status == 'running' else '🔴'} {i.name}",
            callback_data=f"instance:{i.id}"
        )]
        for i in instances
    ]
    return InlineKeyboardMarkup(buttons)
```

### Notification via EventBus
```python
# 봇 초기화 시 이벤트 리스너 등록
async def setup_notifications(bot: ControlTowerBot, event_bus: EventBus):
    async def on_task_complete(task: TaskResult):
        text = f"✅ 작업 완료\n인스턴스: {task.instance_name}\n결과: {task.summary}"
        for chat_id in bot.allowed_users:
            await bot.app.bot.send_message(chat_id=chat_id, text=text)

    event_bus.on("task:completed", on_task_complete)
    event_bus.on("task:failed", on_task_failed)
```

## Dependencies
- python-telegram-bot>=21.0

## Constraints
- Orchestrator는 생성자 주입으로 받아 직접 호출
- 텔레그램 메시지 길이 제한 (4096자) 준수 - 긴 출력은 파일로 전송
- `TELEGRAM_BOT_TOKEN`, `ALLOWED_CHAT_IDS`는 환경변수로 관리
- `src/shared/`의 모델을 import하여 사용하되 직접 수정하지 말 것
