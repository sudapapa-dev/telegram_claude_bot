"""stream-json 프로토콜 버퍼 테스트.

Claude CLI를 stream-json 모드로 실행하고:
1. 오래 걸리는 작업 요청
2. 첫 result 수신 후 즉시 두 번째 메시지 전송
3. 두 번째 응답이 이전 작업 맥락인지 확인

사용법:
    python tests/test_stream_json_buffer.py
"""
import asyncio
import json
import sys
import time
from pathlib import Path

# Claude CLI 경로 (환경에 맞게 수정)
CLAUDE_PATH = "claude"


async def main():
    env = dict(__import__("os").environ)
    env.pop("CLAUDECODE", None)

    cwd = str(Path("data/test_buffer").resolve())
    Path(cwd).mkdir(parents=True, exist_ok=True)

    cmd = [
        CLAUDE_PATH,
        "--dangerously-skip-permissions",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--verbose",
    ]

    print(f"[TEST] 프로세스 시작: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        limit=16 * 1024 * 1024,
    )
    print(f"[TEST] PID: {proc.pid}")

    # ── 메시지 1: 오래 걸리는 작업 ──
    msg1 = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "1부터 10까지 각 숫자마다 3초씩 sleep하면서 하나씩 출력하는 bash 스크립트를 실행해줘. 각 숫자 출력 후 '출력 완료: N' 이라고 말해줘."}],
        },
        "parent_tool_use_id": None,
    }
    line1 = json.dumps(msg1, ensure_ascii=False) + "\n"
    print(f"\n[TEST] === 메시지 1 전송 (오래 걸리는 작업) ===")
    print(f"[TEST] 시각: {time.strftime('%H:%M:%S')}")
    proc.stdin.write(line1.encode())
    await proc.stdin.drain()

    # ── stdout 읽기: 모든 이벤트를 로깅 ──
    result_count = 0
    event_count = 0
    msg2_sent = False

    while True:
        raw = await proc.stdout.readline()
        if not raw:
            print("[TEST] === stdout EOF (프로세스 종료) ===")
            break

        text = raw.decode(errors="replace").strip()
        if not text:
            continue

        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            print(f"[TEST] (파싱 실패) {text[:200]}")
            continue

        event_count += 1
        etype = event.get("type", "?")
        subtype = event.get("subtype", "")

        # 이벤트 요약 출력
        if etype == "system":
            sid = event.get("session_id", "")[:12]
            print(f"[EVENT #{event_count}] {time.strftime('%H:%M:%S')} type=system subtype={subtype} session_id={sid}...")

        elif etype == "assistant":
            msg = event.get("message", {})
            content = msg.get("content", [])
            for block in content:
                if isinstance(block, dict):
                    btype = block.get("type", "?")
                    if btype == "text":
                        preview = block.get("text", "")[:120]
                        print(f"[EVENT #{event_count}] {time.strftime('%H:%M:%S')} type=assistant/text: {preview}")
                    elif btype == "tool_use":
                        name = block.get("name", "?")
                        inp = str(block.get("input", {}))[:100]
                        print(f"[EVENT #{event_count}] {time.strftime('%H:%M:%S')} type=assistant/tool_use: {name} → {inp}")
                    else:
                        print(f"[EVENT #{event_count}] {time.strftime('%H:%M:%S')} type=assistant/{btype}")

        elif etype == "user":
            msg = event.get("message", {})
            content = msg.get("content", [])
            for block in content:
                if isinstance(block, dict):
                    btype = block.get("type", "?")
                    if btype == "tool_result":
                        tr_content = str(block.get("content", ""))[:150]
                        print(f"[EVENT #{event_count}] {time.strftime('%H:%M:%S')} type=user/tool_result: {tr_content}")

        elif etype == "result":
            result_count += 1
            result_text = str(event.get("result", ""))[:200]
            num_turns = event.get("num_turns", "?")
            is_error = event.get("is_error", False)
            print(f"\n[RESULT #{result_count}] {time.strftime('%H:%M:%S')} num_turns={num_turns} is_error={is_error}")
            print(f"[RESULT #{result_count}] text: {result_text}")
            print()

            # ── 첫 번째 result 수신 후 즉시 메시지 2 전송 ──
            if result_count == 1 and not msg2_sent:
                msg2 = {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": "중단해. 지금 몇 시야?"}],
                    },
                    "parent_tool_use_id": None,
                }
                line2 = json.dumps(msg2, ensure_ascii=False) + "\n"
                print(f"[TEST] === 메시지 2 전송 ('중단해. 지금 몇 시야?') ===")
                print(f"[TEST] 시각: {time.strftime('%H:%M:%S')}")
                proc.stdin.write(line2.encode())
                await proc.stdin.drain()
                msg2_sent = True

        else:
            print(f"[EVENT #{event_count}] {time.strftime('%H:%M:%S')} type={etype} {str(event)[:150]}")

        # 두 번째 result까지 받으면 종료
        if result_count >= 2:
            print(f"\n[TEST] === 테스트 완료: result {result_count}개 수신 ===")
            break

    # 정리
    if proc.returncode is None:
        proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except TimeoutError:
            proc.kill()

    print(f"\n[SUMMARY] 총 이벤트: {event_count}개, result: {result_count}개")


if __name__ == "__main__":
    asyncio.run(main())
