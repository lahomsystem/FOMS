# NOTIF-ROLE-01 진행 원장

- 스펙: `docs/specs/2026-08-20-notification-target-role_SPEC.md`
- 작업 트리: `c:/tmp/foms-notifrole` (브랜치 `session/notifrole`, base `origin/deploy` `240c25ae`)
- 총감독: 메인 세션. **모든 task 는 diff 직접 확인 + 테스트 직접 실행 후에만 승인**(에이전트 보고는 주장일 뿐).

| task | 내용 | 담당 | 상태 | 완료 기준 |
|---|---|---|---|---|
| T-A | `models.py`: `Notification.target_role` 컬럼 + `NotificationRecipientSource.TARGET_ROLE` | 총감독 | **DONE** | `APP_OK` — 확인함 |
| T-B | 마이그레이션 `notifrole_00` (+downgrade, 단일 head) | 에이전트 | **DONE(총감독 재검증)** | 단일 head `['notifrole_00']`, 왕복 bootstrap==upgrade |
| T-C | `recipients.py` ROLE 해석 경로 + 계약 테스트 4건 | 에이전트 | **DONE(총감독 재검증)** | 25 passed, 수정 전 3 red 확인 |
| T-D | `account_requests.py` ROLE 1건 전환 + 테스트 | 에이전트 | **DONE(총감독 재검증)** | 159 passed(알림·계정 광역) |
| T-E | `claim_watch.py` ROLE 1건 전환 + 테스트 | 에이전트 | **DONE(총감독 재검증)** | 405 passed(naver·알림·계정 광역) |
| T-F | 통합 검증(에스컬레이션 상호작용 T7) + 문서 등재 | 총감독 | **DONE** | T7 green, `pre_push_smoke` 323 passed exit 0 |
| T-G | deploy push → CI 전 워크플로 green → 운영 승격 | 총감독 | **DONE** | deploy CI 4개 green + 운영 PR #127 머지·운영 DB `notifrole_00` 적용 확인 |

## 검증 로그

- T-A: `python -c "import app; print('APP_OK')"` → `APP_OK` (2026-08-20)
- T-B(총감독 직접 실행): heads=`['notifrole_00']`, down=`naver_relation_00`(에이전트가 지시서의 `assort_00` 오류를 잡아냄 — 로컬 낙후 트리 기준이었음).
  create_all 베이스라인 왕복: `BOOTSTRAP: (('VARCHAR(20)', True), True)` / `AFTER_DOWNGRADE: (None, False)` / `AFTER_UPGRADE: (('VARCHAR(20)', True), True)` / `VERSION: notifrole_00`.
  한계(에이전트 보고 그대로 인정): 실 PostgreSQL 레인 왕복은 미실행 — CI PG Lane 에서 확인한다.
- T-C(총감독 직접 실행): diff 확인 — `_SOURCE_ORDER` 에 ROLE 을 ALL↔TEAM 사이 삽입, ALL 다음에 역할 해석 블록. `pytest test_notification_recipients_role.py test_notification_escalation.py test_notification_user_states.py -q` → `25 passed`.
  에이전트가 수정 전 코드 red(3 failed) 를 확인해 테스트 유효성 입증.

- T-D(총감독 직접 실행): diff 확인 — 루프 제거·ROLE 1건·활성 ADMIN 0명이면 row 미생성. 옛 계약을 박아둔 `test_auth_self_service.py` 2곳도 새 계약으로 갱신(범위 밖이나 필수, 승인).
  `pytest -k "notification or notif or account or self_service"` → `159 passed, 9 skipped`.
  후속 과제(비차단): `foms/api/notifications/__init__.py:67 resolve_notification_recipient_user_ids` 에 ROLE 분기 없음. 현재 호출부(도면·공지 배지 무효화)는 ROLE 알림을 쓰지 않아 회귀 아님. ROLE 알림에 배지 무효화가 필요해지면 그때 분기 추가.

- T-E(총감독 직접 실행): diff 확인 — `_notify_targets` 가 `(user_ids, is_admin_fallback)` 반환, ADMIN 폴백만 ROLE 1건. 반환값을 state 수가 아니라 **수신자 수**로 둔 판단 승인 — `refresh_claims` 의 `if sent:` 가 `notified_status` 기록 게이트라 0이면 5분마다 재알림(폭주 재발). `pytest -k "naver or claim or notification or notif or account"` → `405 passed, 24 skipped`.
- T-F(총감독 작성·실행): T7 통합 테스트 추가 — ROLE 원본 1건+state 3 → 에스컬레이션 총 3건(관리자 1인당 1건). 대조 실험(전환 전 형태: 관리자마다 원본 3건)은 같은 조건에서 **9건** — N²→N 실측. 대조 파일은 실행 후 삭제.
  `pre_push_smoke` → `323 passed` / `=== PRE-PUSH SMOKE PASSED ===`.

## 선행 배포 상태 (같은 주제, 이미 반영)

- `67ecaff3` (production): 에스컬레이션 본문 + 원본당 1건 중복 억제
- `240c25ae` (deploy): 브로드캐스트 유형 에스컬레이션 제외
- 스테이징 알림함 정리: 옛 형식 888건 + 네이버 클레임 백로그 111건 보관 완료

## 운영 승격 (2026-08-21, PR #127 → production `1d35ed06`)

**막힘과 해소**: `notifrole_00` 의 deploy 부모 `naver_relation_00` 이 운영 계보에 없었다(운영 실측 `alembic_version=assort_00`,
`external_order_links` 부재, 네이버 수집 전체가 운영 미반영 — 마이그레이션 5개 + 코드 59파일 16.9k줄). 그대로 올리면
운영 `alembic upgrade head` 가 `KeyError` 로 죽는다. `target_role` 컬럼은 네이버와 무관하므로 **운영 브랜치에서만 부모를
`assort_00` 으로** 두고 승격했다 — 이 저장소가 승격 때 실행 순서 기준으로 체인을 재배열해 온 방식과 같다
(`assort_00` 자신도 deploy=`asaxis_00` / 운영=`asfresh_00`). 마이그레이션 docstring 에 브랜치별 부모를 명시.

**부채**: 네이버 체인이 운영으로 오면 `notifrole_00` 과 `naver_relation_00` 이 둘 다 `assort_00` 자식이 되므로
merge revision 1건이 필요하다.

**승격 범위**: `models.py`(`target_role` + `TARGET_ROLE`), `notifrole_00`, `recipients.py`, `account_requests.py`,
`foms/api/notifications/__init__.py`(배지 resolver ROLE 분기). **제외**: 네이버 `claim_watch.py` ROLE 전환과 네이버
테스트 3파일 — 네이버 수집 자체가 운영에 없다. 네이버 승격 때 함께 간다.

**검증**: 승격 트리 `APP_OK` · 알림/계정 46 passed · 게이트 계약 111 passed(write_guard·audit coverage·failopen·
api error containment·rev_99·release gate) · 단일 head `['notifrole_00']` · `pre_push_smoke` exit 0(323) ·
`tests/domains`+`tests/harness` 4847 passed(유일 red `test_claude_stop_gate.py::test_pending_import_success_clears`
는 **깨끗한 production 베이스에서도 동일 red** — 로컬 cp949 환경 문제) · PR CI pg-lane pass·perf-gate pass ·
머지 후 운영 DB `alembic_version=notifrole_00`·`target_role` 컬럼 존재 확인 · `/login` 200.

**구조적 사각(기록)**: FOMS CI·Harness CI 는 트리거가 `main`/`deploy` 한정이라 **production 대상 PR 에서 안 돈다**.
운영 승격 PR 을 덮는 워크플로는 pg-lane·perf-gate 둘뿐이므로, 승격 전 로컬 전수 실행이 사실상의 대체 게이트다.
