#!/usr/bin/env bash
# CI 감시·자동 복구 — 크로스플랫폼 정본(tools/harness/ci_watch.py)의 thin wrapper.
#
# 로직 SSOT 는 tools/harness/ci_watch.py 로 이식됐다(Claude Code·Cursor·기타 CLI 공통).
# 이 래퍼는 기존 bash 호출 습관 호환용이다.
#
# 사용: bash scripts/ops/ci_watch_recover.sh [SHA] [BRANCH] [--no-until-final]
#   SHA    기본 = 현재 HEAD
#   BRANCH 기본 = deploy
set -u
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python "${_here}/../../tools/harness/ci_watch.py" "$@"
