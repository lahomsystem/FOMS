# Mobile v2 Railway staging + Cron ops (P0-01 / P0-00C)

> Web 서비스 env 설정 + Cron 서비스 1회 등록. 코드: `MIGRATION_ROADMAP.md` Flag matrix.

## 1. DB 마이그레이션 (deploy 배포 후)

```powershell
cd "C:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"
# Railway Web 서비스 one-off 또는 release command
alembic upgrade head
```

확인: `add_erp_phone_digits` revision 적용, `ix_orders_erp_phone_digits` 존재.

## 2. Web 서비스 env — cohort Day 1

Railway **staging (deploy 브랜치)** Web 서비스 Variables:

| Variable | Day 1 값 | 비고 |
|---|---|---|
| `ERP_MOBILE_V2_ENABLED` | `true` | 전역 ON |
| `FOMS_V3_SHELL_COHORT` | `<user_id>` | 단일 id (예: 안중훈) |
| `FOMS_V3_DRAWING_THUMB_ENABLED` | *(미설정)* | cohort mobile v2 시 auto ON (`feature_flags.py:31-47`) |
| `FOMS_V3_AS_THUMB_ENABLED` | *(미설정)* | 동일 |
| `FOMS_V3_CONSTRUCTION_THUMB_ENABLED` | *(미설정)* | 동일 |
| `FOMS_OFFLINE_SW_ENABLED` | `false` | Day 4+ 실기기 QA 후 |
| `FOMS_BOTTOM_NAV_HTMX_ENABLED` | `false` | Day 5+ 실기기 QA 후 |

**안전 검증** (`MIGRATION_ROADMAP.md:60`):

- `ERP_MOBILE_V2_ENABLED=true` + `FOMS_V3_SHELL_COHORT=` (빈) → **아무도** 새 셸 진입 불가
- cohort id만 포함 user → mobile shell (`context_processors.py` + `is_enabled_for_user`)

## 3. Cohort Day 1~7 확장

| Day | `FOMS_V3_SHELL_COHORT` | 추가 flag |
|---|---|---|
| 1 | 1 user id | — |
| 2~3 | +1~2 id | — |
| 4 | 기존 유지 | `FOMS_OFFLINE_SW_ENABLED=true` (실기기 OK 후) |
| 5 | 기존 유지 | `FOMS_BOTTOM_NAV_HTMX_ENABLED=true` (실기기 OK 후) |
| 7 | 전체 rollout 검토 | KPI/RUM baseline 비교 |

## 4. Railway Cron Service (P0-00C)

1. Railway 프로젝트 → **New Service** → 같은 repo, **deploy** 브랜치
2. Settings → **Config Path**: `railway-cron.toml`
3. Variables: Web과 동일 `DATABASE_URL`, `SECRET_KEY` 등
4. `railway-cron.toml:7-8` — UTC 17:00 = KST 02:00, `cleanup_order_drafts.py --execute`

로컬 dry-run:

```powershell
python tools/cron/cleanup_order_drafts.py
# mode=dry-run scanned=N deleted=0
```

첫 실행 로그: `mode=execute scanned=N deleted=M`

## 5. 실기기 QA (Day 4~5)

- [ ] cohort user 로그인 → bottom nav 5탭 + 검색 overlay (`010-xxxx` digit search)
- [ ] `FOMS_OFFLINE_SW_ENABLED=1` → offline badge / draft queue
- [ ] `FOMS_BOTTOM_NAV_HTMX_ENABLED=1` → 탭 전환 partial swap (회귀 없음)
- [ ] 7일 일지: `docs/design/REVIEW_ENTRY.md` cohort 항목

## 6. 롤백

- 즉시: `FOMS_V3_SHELL_COHORT=` 비우기 또는 `ERP_MOBILE_V2_ENABLED=false`
- Cron 실패: Cron 서비스 일시 중지 (Web 영향 없음)
