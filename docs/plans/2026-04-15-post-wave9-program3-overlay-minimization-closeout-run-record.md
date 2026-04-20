# Post-Wave9 Program 3 — Overlay minimization closeout

> **program:** Program 3  
> **실행일:** 2026-04-15  
> **입력:** Program 1 closeout (`W5-B9`), Program 2 row records (`WR-P1`, `WR-O1`, `WR-J1`, `WR-S2`, `WR-H1`)

## 1. Goal

- `apps/` / root `services/`에 남은 thin overlay를 다시 분류한다.
- 제거 가능한 축만 제거하고, high-risk/runtime-string/packaging 축은 reopen하지 않는다.

## 2. Outcome summary

### 2.1 Removed in the endgame sequence

- `apps/api/personal_board.py` removed (`WR-P1`)
- `services/storage.py` removed (`WR-S2`)

### 2.2 Minimized but intentionally retained

- `apps/api/orders/__init__.py`
  - route shell removed
  - compatibility re-export wrapper retained (`WR-O1`)

### 2.3 Explicitly retained by separate risk axis

- `services/jobs/tasks.py` legacy shim + queue string contract (`WR-J1`)
- `apps.api.notifications`, `apps.api.attachments`, `apps.api.chat/*`, root `services/channel_*` shims (`WR-H1`)
- broad root `services/*` re-export shims not covered by the post-Wave9 endgame order

## 3. Reclassification

| Surface | Current class after Program 3 | Why |
|---------|-------------------------------|-----|
| `apps.api.personal_board` | removed | dead adapter shell retired |
| `apps.api.orders` | re-export-only compatibility wrapper | canonical route owner moved, package path still public |
| `services.storage` | removed | live runtime callers already drained |
| `services.jobs.tasks` | runtime-string retained shim | queued job payload compatibility + worker runtime coupling |
| `services/channel_*` | high-risk compatibility shims | broad multi-module owner/runtime cluster |
| other root `services/*` re-export shims | out of scope for this master order | no dedicated row in Program 2; not reopened here |

## 4. Decision lock

- Program 3 does **not** open a new removal campaign for the remaining root `services/*` shims.
- additional overlay removal now requires either:
  - a dedicated owner/runtime row, or
  - a new approved plan outside the post-Wave9 endgame order

## 5. Closeout verdict

- overlay minimization for the post-Wave9 endgame order is **complete**
- all removable low-risk overlays encountered in Program 2 were either removed or reduced to compatibility-only shape

## 6. Next step

- Program 4 — controlling spec Step 1~7 final checklist re-verification
