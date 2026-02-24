#!/bin/bash
# claude_auth/ 볼륨이 ~/.claude 로 직접 마운트됨
# .credentials.json 만 있으면 인증 완료

exec "$@"
