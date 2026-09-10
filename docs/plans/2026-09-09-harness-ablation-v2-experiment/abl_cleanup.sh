#!/bin/sh
# ablation v2 실험 부산물 정리 — 사용자 승인 뒤 C:/DEV/FOMS 에서 실행한다.
# 다른 세션의 워크트리(foms-s-*, promote/own-*)는 건드리지 않는다.
# 기준선 태그 harness-v2-baseline 과 백업 C:/tmp/claude-home-baseline-20260909 는 남긴다.
set -e
cd /c/DEV/FOMS
for t in T1 T2 T3 T4; do
  for a in A B C; do git worktree remove --force "C:/tmp/abl-$t-$a" 2>/dev/null || true; done
done
for a in a b c; do git worktree remove --force "C:/tmp/foms-prod-abl-t4$a" 2>/dev/null || true; done
git worktree prune
for a in a b c; do
  git branch -D "session/abl-t4-$a" 2>/dev/null || true
  git branch -D "promote/abl-t4$a-20260909" 2>/dev/null || true
done
# 설정 사본·훅 디렉토리·메모리 사본 (전부 C:/tmp 또는 ~/.claude/projects 아래의 실험 전용 경로)
python - <<'PY'
import shutil, pathlib
for p in ["C:/tmp/abl-cfg-B", "C:/tmp/abl-cfg-C", "C:/tmp/abl-cfg-smoke", "C:/tmp/abl-hooks"]:
    shutil.rmtree(p, ignore_errors=True)
home = pathlib.Path.home() / ".claude" / "projects"
for t in ("T1", "T2", "T3", "T4"):
    shutil.rmtree(home / f"C--tmp-abl-{t}-A", ignore_errors=True)
print("사본 정리 완료")
PY
git config --unset extensions.worktreeConfig || true
echo "정리 완료."
