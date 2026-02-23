# Agent Teams 메시지 감시 가이드

> 출처: [Claude Code 공식 문서 — 에이전트 팀](https://code.claude.com/docs/ko/agent-teams)

---

## 메시지 감시가 필요한 이유

에이전트 팀에서 팀원들은 **서로 직접 메시지를 주고받는다.** 리더를 경유하지 않고 팀원 간 직통 통신이 가능하기 때문에, 어떤 팀원이 어떤 메시지를 언제 보냈는지 파악하지 않으면:

- 팀원이 오류에서 멈춰도 인지 못함
- 낭비된 노력이 쌓여도 중간에 재지정 불가
- 리더가 작업 완료 전에 종료해버리는 상황 발생

---

## 메시지 흐름 구조

```
[사용자]
   │  Shift+Up/Down (in-process) 또는 창 클릭 (split)
   ▼
[리더 세션] ──────────────────────────────────────────
   │  message (1:1)   │  broadcast (전체)
   ▼                  ▼
[팀원 A] ◄──────► [팀원 B] ◄──────► [팀원 C]
   │         직접 메시지 (peer-to-peer)
   ▼
[메일박스 (받은편지함)]
   ~/.claude/teams/{team-name}/
```

팀원 메시지는 **자동으로 리더에게 전달**된다. 리더가 폴링할 필요 없음.

---

## 파일 시스템 기반 감시

에이전트 팀의 모든 상태는 로컬 파일에 저장된다. 여기가 가장 직접적인 감시 지점이다.

### 저장 위치

| 경로 | 내용 |
|---|---|
| `~/.claude/teams/{team-name}/config.json` | 팀 구성, 팀원 목록, 에이전트 ID |
| `~/.claude/tasks/{team-name}/` | 작업 목록, 상태, 담당자 |
| `~/.claude/teams/{team-name}/inboxes/` | 팀원별 받은편지함 (메시지 파일) |

### config.json 구조

```json
{
  "team_name": "my-team",
  "leader": { "agent_id": "...", "name": "leader" },
  "members": [
    { "name": "researcher", "agent_id": "...", "agent_type": "general-purpose" },
    { "name": "developer",  "agent_id": "...", "agent_type": "general-purpose" },
    { "name": "reviewer",   "agent_id": "...", "agent_type": "general-purpose" }
  ]
}
```

### 팀원 목록 실시간 확인

```bash
# 현재 팀 구성 확인
cat ~/.claude/teams/*/config.json | jq '.members[].name'

# 특정 팀 팀원 목록
cat ~/.claude/teams/my-team/config.json | jq '.members'
```

---

## 메시지(받은편지함) 감시

각 팀원은 독립적인 받은편지함 파일을 가진다.

### 받은편지함 구조

```
~/.claude/teams/{team-name}/inboxes/
├── leader.json
├── researcher.json
├── developer.json
└── reviewer.json
```

### 메시지 파일 형식

```json
[
  {
    "from": "researcher",
    "to": "developer",
    "type": "message",
    "content": "인증 모듈 분석 완료. JWT 토큰 검증 로직에 취약점 발견.",
    "timestamp": "2026-02-23T08:30:00Z"
  },
  {
    "from": "leader",
    "to": "developer",
    "type": "task_assignment",
    "content": "researcher의 발견사항 기반으로 src/auth/jwt.ts 수정 시작해줘.",
    "timestamp": "2026-02-23T08:31:00Z"
  }
]
```

### 메시지 타입 종류

| type | 설명 |
|---|---|
| `message` | 일반 텍스트 메시지 |
| `task_assignment` | 작업 할당 |
| `shutdown` | 종료 요청 |
| `plan_approval_request` | 계획 승인 요청 (plan approval 모드) |
| `plan_approved` / `plan_rejected` | 계획 승인/거부 응답 |
| `idle_notification` | 팀원 완료 후 자동 유휴 알림 |

### 실시간 메시지 모니터링 명령

```bash
# 특정 팀원의 받은편지함 실시간 감시
watch -n 1 'cat ~/.claude/teams/my-team/inboxes/developer.json | jq .'

# 전체 팀 메시지 스트림 감시 (모든 받은편지함)
watch -n 2 'for f in ~/.claude/teams/my-team/inboxes/*.json; do
  echo "=== $(basename $f) ==="; cat $f | jq ".[-1]"; done'

# 새 메시지 도착 시 알림 (fswatch — macOS)
fswatch -o ~/.claude/teams/my-team/inboxes/ | xargs -I{} \
  osascript -e 'display notification "새 메시지 도착" with title "Agent Team"'

# Linux: inotifywait
inotifywait -m ~/.claude/teams/my-team/inboxes/ -e modify |
  while read path action file; do
    echo "[$(date)] $file 메시지 수신: $(cat $path$file | jq '.[-1].content')"
  done
```

---

## 작업 상태 감시

메시지와 함께 작업 상태를 감시하면 전체 흐름이 보인다.

### 작업 파일 구조

```
~/.claude/tasks/my-team/
├── 1.json   # 작업 #1
├── 2.json   # 작업 #2
└── 3.json   # 작업 #3
```

### 작업 파일 내용

```json
{
  "id": 1,
  "title": "인증 모듈 보안 검토",
  "status": "in_progress",
  "owner": "researcher",
  "dependencies": [],
  "created_at": "2026-02-23T08:00:00Z",
  "updated_at": "2026-02-23T08:30:00Z"
}
```

### 작업 상태 실시간 확인

```bash
# 전체 작업 상태 요약
watch -n 3 'for f in ~/.claude/tasks/my-team/*.json; do
  jq -r "[.status] \(.title) → \(.owner // "미할당")" $f; done'

# 진행 중인 작업만
for f in ~/.claude/tasks/my-team/*.json; do
  jq 'select(.status == "in_progress") | "\(.owner): \(.title)"' $f
done

# 블록된 작업 (종속성 미완료) 확인
for f in ~/.claude/tasks/my-team/*.json; do
  jq 'select(.status == "pending" and (.dependencies | length > 0)) |
    "BLOCKED: \(.title) (depends on: \(.dependencies))"' $f
done
```

---

## 인터랙티브 감시 (터미널 UI)

### In-process 모드 — 키보드 단축키

| 단축키 | 동작 |
|---|---|
| `Shift+Down` | 다음 팀원으로 포커스 이동 |
| `Shift+Up` | 이전 팀원으로 포커스 이동 |
| `Enter` | 선택한 팀원의 세션 전체 보기 |
| `Escape` | 현재 턴 중단 |
| `Ctrl+T` | 작업 목록 토글 |

포커스된 팀원에게 직접 타이핑하면 메시지가 전송된다.

### Split 모드 (tmux / iTerm2)

각 팀원이 독립 창을 가지므로 **모든 팀원의 출력을 동시에 볼 수 있다.**

```bash
# tmux 세션 목록 확인 (팀원별 세션 확인)
tmux ls

# 특정 팀원 세션 직접 접속
tmux attach -t researcher

# 모든 팀원 창 동시 모니터링 (tmux synchronize-panes 해제 상태)
# 각 pane이 독립적으로 팀원 출력을 보여줌
```

---

## 이상 상황 감지 패턴

### 팀원이 멈춘 경우

```bash
# 마지막 메시지 타임스탬프 확인
for f in ~/.claude/teams/my-team/inboxes/*.json; do
  name=$(basename $f .json)
  last_time=$(cat $f | jq -r '.[-1].timestamp // "없음"')
  echo "$name 마지막 메시지: $last_time"
done

# 5분 이상 메시지 없는 팀원 탐지
python3 -c "
import json, os, datetime
inbox_dir = os.path.expanduser('~/.claude/teams/my-team/inboxes/')
now = datetime.datetime.utcnow()
for fname in os.listdir(inbox_dir):
    data = json.load(open(inbox_dir + fname))
    if data:
        last = datetime.datetime.fromisoformat(data[-1]['timestamp'].replace('Z',''))
        delta = (now - last).seconds // 60
        if delta > 5:
            print(f'⚠️  {fname}: {delta}분 동안 메시지 없음')
"
```

### 작업이 장시간 진행 중인 경우

```bash
# 30분 이상 in_progress인 작업 탐지
python3 -c "
import json, os, datetime, glob
now = datetime.datetime.utcnow()
for f in glob.glob(os.path.expanduser('~/.claude/tasks/my-team/*.json')):
    task = json.load(open(f))
    if task.get('status') == 'in_progress':
        updated = datetime.datetime.fromisoformat(task['updated_at'].replace('Z',''))
        delta = (now - updated).seconds // 60
        if delta > 30:
            print(f'⚠️  \"{task[\"title\"]}\" ({task[\"owner\"]}): {delta}분째 진행 중')
"
```

---

## 대시보드 스크립트 (종합)

팀 전체 상태를 한눈에 보는 셸 스크립트:

```bash
#!/usr/bin/env bash
# ~/.local/bin/team-monitor
# 사용법: team-monitor my-team

TEAM_NAME="${1:-$(ls ~/.claude/teams/ | head -1)}"
TEAM_DIR="$HOME/.claude/teams/$TEAM_NAME"
TASK_DIR="$HOME/.claude/tasks/$TEAM_NAME"

clear
echo "═══════════════════════════════════════"
echo "  Agent Team Monitor: $TEAM_NAME"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "═══════════════════════════════════════"

echo ""
echo "[ 팀원 ]"
cat "$TEAM_DIR/config.json" | jq -r '.members[] | "  • \(.name) (\(.agent_type))"' 2>/dev/null

echo ""
echo "[ 작업 현황 ]"
for f in "$TASK_DIR"/*.json 2>/dev/null; do
  [ -f "$f" ] || continue
  jq -r '"  [\(.status)] \(.title) → \(.owner // "미할당")"' "$f"
done

echo ""
echo "[ 최근 메시지 ]"
for f in "$TEAM_DIR/inboxes"/*.json 2>/dev/null; do
  [ -f "$f" ] || continue
  name=$(basename "$f" .json)
  last=$(cat "$f" | jq -r '.[-1] | "\(.from) → \(.to): \(.content[:60])..."' 2>/dev/null)
  [ -n "$last" ] && echo "  $last"
done

echo ""
echo "[ 고아 tmux 세션 ]"
tmux ls 2>/dev/null | grep "$TEAM_NAME" || echo "  없음"
```

```bash
# 설치 및 실행
chmod +x ~/.local/bin/team-monitor
watch -n 5 team-monitor my-team
```

---

## 정리 후 잔여 파일 확인

```bash
# 팀 정리 후 고아 파일 확인
ls ~/.claude/teams/
ls ~/.claude/tasks/

# 완전 삭제 (정리 명령으로 안 지워진 경우)
rm -rf ~/.claude/teams/my-team
rm -rf ~/.claude/tasks/my-team

# 고아 tmux 세션 정리
tmux ls
tmux kill-session -t <session-name>
```

---

## 참고: 공식 문서 핵심 인용

> *"팀원 메시지는 자동으로 리더에게 도착합니다. 리더가 업데이트를 폴링할 필요가 없습니다."*

> *"팀과 작업은 로컬에 저장됩니다: 팀 구성은 `~/.claude/teams/{team-name}/config.json`, 작업 목록은 `~/.claude/tasks/{team-name}/`"*

> *"팀원들을 모니터링하고, 작동하지 않는 접근 방식을 재지정하며, 발견 사항이 들어올 때 종합하십시오. 팀을 무인으로 너무 오래 실행하면 낭비된 노력의 위험이 증가합니다."*
