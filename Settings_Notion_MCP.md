# Notion MCP 설정 가이드

## 바로가기

- [Notion Integration 생성](https://www.notion.so/profile/integrations)
- [Notion API 공식 문서](https://developers.notion.com/)
- [Notion MCP Server (GitHub)](https://github.com/makenotion/notion-mcp-server)

---

## 개요

telegram_claude_bot은 `.env`의 `NOTION_TOKEN`이 설정되면 봇 시작 시 자동으로 Claude CLI에 Notion MCP를 연결합니다. 별도의 MCP 수동 설정은 필요 없습니다.

**필요한 것:**
- Notion 계정
- Internal Integration 토큰 (`ntn_` 또는 `secret_`으로 시작)
- 대상 페이지에 Integration 연결 (1회)

---

## 설정 순서

### 1단계: Internal Integration 생성

1. [Notion Integrations 페이지](https://www.notion.so/profile/integrations)에 접속
2. 좌측 하단 **"Internal integrations"** 클릭
3. **"새 API 통합 만들기"** (또는 **"New integration"**) 클릭
4. 설정:
   - **이름**: 자유 (예: `telegram_bot`)
   - **관련 워크스페이스**: 사용할 워크스페이스 선택
   - **유형**: Internal
5. **저장** 클릭

### 2단계: 토큰 복사

1. 생성된 Integration 페이지에서 **"내부 통합 시크릿"** (Internal Integration Secret) 확인
2. **"표시"** 클릭 후 토큰 복사 (`ntn_xxxxx...` 형식)

### 3단계: .env에 토큰 설정

```env
NOTION_TOKEN=ntn_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 4단계: 페이지 권한 부여

Integration을 만들었더라도, **접근할 페이지에 직접 연결해야** API로 접근이 가능합니다.

**방법 A: Integration 설정 페이지에서 (권장)**

1. [Notion Integrations 페이지](https://www.notion.so/profile/integrations)에서 만든 Integration 클릭
2. **"콘텐츠 사용 권한"** 탭 클릭
3. **"편집 권한"** → 접근할 최상위 페이지 체크 → **"저장하기"**
4. 최상위 페이지를 선택하면 **하위 페이지 전체에 자동 적용**됩니다

**방법 B: 노션 페이지에서 직접**

1. 접근할 노션 페이지 열기
2. 우측 상단 `···` 클릭
3. **"연결"** (Connections) 선택
4. 만든 Integration 이름 검색 후 선택
5. **"확인"** 클릭

### 5단계: 봇 재시작

```bash
# 개발 모드
python -m src.main

# 또는 EXE
telegram_claude_bot.exe
```

시작 로그에 아래 메시지가 나타나면 정상입니다:
```
Notion MCP 설정 주입 완료: C:\Users\{user}\.claude.json
```

---

## 작동 원리

```
.env (NOTION_TOKEN)
    ↓ 봇 시작 시
~/.claude.json (mcpServers.notion 자동 주입)
    ↓ Claude CLI 실행 시
@notionhq/notion-mcp-server (npx로 자동 실행)
    ↓ API 호출
Notion API
```

1. 봇이 시작되면 `NOTION_TOKEN`을 읽어 `~/.claude.json`에 MCP 서버 설정을 자동 주입
2. Claude CLI가 실행될 때 해당 MCP 설정을 읽어 Notion 서버에 연결
3. Claude가 Notion API를 통해 페이지 생성/수정/검색 등을 수행

---

## 사용 예시

텔레그램에서 Claude에게 직접 요청하면 됩니다:

- `"노션에 오늘 회의록 페이지를 만들어줘"`
- `"노션에서 '프로젝트 계획' 페이지 내용을 요약해줘"`
- `"노션 데이터베이스에 새 항목을 추가해줘"`

---

## 제한사항

| 항목 | 내용 |
|------|------|
| **페이지 접근** | Integration이 연결된 페이지만 접근 가능 (Notion 보안 정책) |
| **새 최상위 페이지** | 새로 만든 최상위 페이지는 별도로 Integration 연결 필요 |
| **워크스페이스 전체 권한** | 불가 — 최상위 페이지 단위로만 권한 부여 |
| **블록 크기** | API 응답 최대 100개 블록 (페이지네이션 필요) |
| **요청 제한** | 초당 3회 요청 제한 (Rate Limit) |
| **파일 업로드** | API로 직접 파일 업로드 불가 (External URL만 지원) |

---

## 문제 해결

### "Notion MCP 설정 주입 완료" 로그가 안 나옴
- `.env`에 `NOTION_TOKEN`이 설정되어 있는지 확인

### Claude가 "Notion에 접근할 수 없습니다" 라고 응답
- 대상 페이지에 Integration이 연결되어 있는지 확인 (4단계)
- 토큰이 올바른지 확인 (`ntn_` 또는 `secret_`으로 시작)

### npm 모듈 관련 오류
- `@notionhq/notion-mcp-server`가 설치되어 있는지 확인:
  ```bash
  npm list -g @notionhq/notion-mcp-server
  ```
- 미설치 시:
  ```bash
  npm install -g @notionhq/notion-mcp-server
  ```

### Docker 환경
- Docker 이미지에는 MCP 모듈이 사전 설치되어 있음
- `docker-compose.yml`에서 `NOTION_TOKEN` 환경변수만 설정하면 됨
