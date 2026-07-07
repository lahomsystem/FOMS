#!/usr/bin/env bash
# CI 감시·자동 복구 — deploy push 후 1회 실행.
#
# 하는 일:
#   1) 대상 커밋 SHA 의 모든 워크플로 완료를 폴링 대기
#   2) 실패 워크플로를 분류:
#      - perf-gate "wait_staging_deploy 타임아웃": Railway 배포가 CI 대기(600s)보다
#        느렸던 것 → healthz commit==SHA 확인되면 자동 재실행(배포 완료 후 통과)
#      - perf-gate TTFB/render tail flaky(dTTFB/render 근소 초과): 네트워크 tail
#        → 자동 재실행 1회
#      - perf-gate bytes 초과: 데이터 가변 탭(measurement/shipment 등 목록)이면
#        코드 회귀 아님 → perf_budgets.json 관측×1.3 보정값을 "제안"(적용은 사람 확인,
#        무한 자동 상향은 회귀 은폐라 금지)
#      - Harness/FOMS CI 실패: 코드 문제 → 실패 로그 tail 출력(사람 수정)
#   3) 요약 출력
#
# 사용: bash scripts/ops/ci_watch_recover.sh [SHA] [BRANCH]
#   SHA    기본 = 현재 HEAD
#   BRANCH 기본 = deploy
set -u

SHA="${1:-$(git rev-parse HEAD)}"
SHORT="${SHA:0:8}"
BRANCH="${2:-deploy}"
HEALTHZ="https://lahom-dev.up.railway.app/healthz"

echo "[ci-watch] target=$SHORT branch=$BRANCH"

# 1) 워크플로가 등록될 때까지 잠깐 대기 후 완료 폴링
sleep 30
for _ in $(seq 1 120); do
  pending=$(gh run list --branch="$BRANCH" --limit=8 \
    --json headSha,status --jq \
    "[.[]|select(.headSha|startswith(\"$SHORT\"))|select(.status!=\"completed\")]|length" 2>/dev/null)
  total=$(gh run list --branch="$BRANCH" --limit=8 \
    --json headSha --jq "[.[]|select(.headSha|startswith(\"$SHORT\"))]|length" 2>/dev/null)
  [ "${total:-0}" -ge 1 ] && [ "${pending:-1}" = "0" ] && break
  sleep 20
done

fails=$(gh run list --branch="$BRANCH" --limit=8 \
  --json headSha,workflowName,conclusion,databaseId --jq \
  "[.[]|select(.headSha|startswith(\"$SHORT\") and .conclusion==\"failure\")]" 2>/dev/null)
nfail=$(echo "$fails" | python -c "import sys,json;print(len(json.load(sys.stdin)))" 2>/dev/null)

if [ "${nfail:-0}" = "0" ]; then
  echo "[ci-watch] ALL GREEN ✓"
  exit 0
fi

echo "[ci-watch] $nfail failed workflow(s):"
echo "$fails" | python -c "import sys,json;[print(' -',w['workflowName']) for w in json.load(sys.stdin)]" 2>/dev/null

# 2) 실패 분류·대응
echo "$fails" | python -c "import sys,json;[print(w['databaseId'],w['workflowName']) for w in json.load(sys.stdin)]" 2>/dev/null | \
while read -r RID WF; do
  echo "----- $WF ($RID) -----"
  if echo "$WF" | grep -qi "perf-gate"; then
    log=$(gh run view "$RID" --log 2>/dev/null)
    if echo "$log" | grep -q "wait-deploy.*타임아웃\|Wait for staging deploy"; then
      hz=$(curl -s "$HEALTHZ" 2>/dev/null | python -c "import sys,json;print(json.load(sys.stdin).get('commit','')[:8])" 2>/dev/null)
      if [ "$hz" = "$SHORT" ]; then
        echo "  원인=배포 대기 타임아웃, 지금 healthz=$SHORT 배포 완료 → 재실행"
        gh run rerun "$RID" >/dev/null 2>&1 && echo "  rerun 요청됨"
      else
        echo "  배포 미완(healthz=$hz != $SHORT) — 몇 분 후 재실행 필요"
      fi
    elif echo "$log" | grep -qE "> budget.*ms|render [0-9]+ms > budget"; then
      echo "  원인=TTFB/render tail flaky(근소 초과) → 재실행"
      gh run rerun "$RID" >/dev/null 2>&1 && echo "  rerun 요청됨"
    elif echo "$log" | grep -q "bytes [0-9]* > budget"; then
      line=$(echo "$log" | grep -oE "bytes [0-9]+ > budget [0-9]+" | head -1)
      obs=$(echo "$line" | grep -oE "bytes [0-9]+" | grep -oE "[0-9]+")
      sugg=$(python -c "print(int($obs*1.3))" 2>/dev/null)
      path=$(echo "$log" | grep -B1 "bytes $obs > budget" | grep -oE "/erp/[a-z/]+\?view=fragment" | head -1)
      echo "  원인=bytes 초과($line). 데이터 가변 탭이면 코드 회귀 아님."
      echo "  ▶ 수정 제안: perf_budgets.json '$path' body_bytes_max → $sugg (관측 $obs ×1.3)"
      echo "    (데이터 가변 확인 후 적용. 코드성 비만이면 dTTFB/쿼리 계약이 별도로 잡음)"
    else
      echo "  원인 미분류 — 로그 확인 필요: gh run view $RID --log"
    fi
  else
    echo "  코드 CI 실패 → 실패 스텝/로그(수정 필요):"
    gh run view "$RID" --json jobs --jq '.jobs[].steps[]|select(.conclusion=="failure")|"    step: "+.name' 2>/dev/null | head
    gh run view "$RID" --log-failed 2>/dev/null | grep -iE "error|assert|failed|fail" | head -8 | sed 's/^/    /'
  fi
done

echo "[ci-watch] 대응 완료. 재실행한 워크플로는 이 스크립트를 다시 돌려 결과 확인."
