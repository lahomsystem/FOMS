# 네이버 수집 선행 결함 수정 — 플랜 + 진행 원장

- 등급 `**C` · 브랜치 `session/naver-ingest` · 워크트리 `c:/tmp/foms-s-naver-ingest`
- 스펙: `docs/specs/2026-08-20-naver-ingest-precursor-defects_SPEC.md`
- 설계 정본: `docs/research/2026-08-20-naver-ux/04_설계_결정.md`
- 목표 화면(다음 단계): `docs/design/mockups/naver-ingest-workbench-v2.html`

## 사용자 확정 (2026-08-20)

| 항목 | 결정 |
|---|---|
| 착수 순서 | 6개를 한 플랜으로 (#7 은 UI 개편으로 이관 → 실제 5개) |
| #1 방식 | **묶음키 컬럼 신설** + 마이그레이션 + backfill |
| #7 시점 | UI 개편 때 같이 (v2 목업의 2단 대조표가 그 답) |
| 테스트 | **테스트 먼저 고쳐 red 확인 → 구현 → green** |
| 푸시 | 아직 안 올림(세션 브랜치 유지) |

## Task 순서 (의존 관계 기준)

빠른 것 먼저 → 큰 것 → 큰 것에 의존하는 것.

### T1 — #5 `.alert` 자동닫힘 (DONE)
`templates/admin/naver_ingest.html:20` 에 `data-foms-no-autodismiss` 추가.
**완료 기준**: 계약 테스트가 해당 속성 존재를 확인하고 green · 수집 실행 결과 문구가 5초 뒤에도 남는다.

### T2 — #8 페이지 링크 필터 유실 (DONE)
`templates/admin/naver_ingest.html:246,255` 의 `url_for` 에 `place` 전달.
**완료 기준**: `?place=PENDING&page=2` 링크에 `place=PENDING` 이 실려 있음을 테스트가 확인 · green.

### T3 — #4 취소·반품 큐 이탈 (DONE)
`naver_triage.html` footer 배타 분기를 풀어 `확인 완료`를 공통 영역으로.
**완료 기준**: 주문 없는 취소 건 상세에 `확인 완료` 버튼이 있고 `주문 만들기`는 잠긴 상태 · 테스트 green ·
기존 "주문 있는 건" 경로(담당자 지정 + 확인 완료) 회귀 없음.

### T4 — #1 묶음키 컬럼 (DONE) ← 이 플랜의 본체
1. `mapping.group_key_text()` 신설(기존 `group_key()` 튜플 시그니처 불변)
2. `ExternalOrderLink.group_key` 컬럼 + 마이그레이션 `navergroup_00`(down=`naver_relation_00`)
3. 수집 upsert 에서 기록 · 재수집 시 갱신
4. 이력 표 `_history_group_key` / `_group_key_col()` 이 컬럼 사용(NULL 폴백 유지)
5. `scripts/maintenance/backfill_naver_group_key.py`(멱등·`--dry-run`)
**완료 기준**: 분할배송(같은 주문번호 · 다른 주소) 2건이 **이력에서도 2집**으로 세지는 테스트 green ·
마이그레이션 왕복(upgrade→downgrade→upgrade) PG 레인 통과 · backfill `--dry-run` 출력 확인 ·
컬럼이 NULL 인 행이 섞여도 화면 200.

### T5 — #2 단위 통일 (PENDING, T4 의존)
`compute_triage_pending_count` 를 `count(distinct group_key)` 로 · 화면 헤더 이중 표기.
**완료 기준**: nav 배지와 화면 필터 숫자가 같은 단위(집) · `test_naver_nav_entry.py` 기대값을 집 수로 먼저 고쳐 red 확인 후 green.

### T6 — 통합 검증 (PENDING)
**완료 기준**: `pytest tests/services/integrations/ -q` 전건 통과 · `APP_OK` · `pre_push_smoke.ps1` exit 0 ·
변경 파일 lint · 원장·AI_STATUS 갱신.

## 함정 메모 (착수 전 확인)

- 마이그레이션 안에서 `models`/`mapping` import 금지 — 과거 마이그레이션 소급 오염(상수 동결 원칙).
- 새 감사 행위를 만들면 `audit_message_display` 라벨 등재 필수(pre_push_smoke 사각 → CI red).
- 주문 JSONB 직접 쓰기는 REV-99 게이트 → `execute_order_mutation` 경유. (이번 범위엔 없을 예정)
- `.alert` 자동닫힘은 상시 안내를 지운다 — T1 이 바로 그 건.
- 인벤토리 드리프트: `except` 있는 파일의 줄 수가 바뀌면 failopen 인벤토리 CI red 가능 → 필요 시 원격 tip 클린 worktree 에서 재생성.
- PG 레인은 SQLite 와 달리 FK 강제 — 마이그레이션 검증은 PG 레인에서.

## 진행 기록
- 2026-08-20 스펙·플랜 작성. 코드 사실 확인 완료(두 그룹키 정의·배지 링크 카운트·footer 배타 분기·페이지 링크 누락).
- 2026-08-20 사용자 승인 — T1부터 순차, T마다 끊어 보고.
- 2026-08-20 **T1 완료**. 테스트 `test_run_result_alert_is_not_auto_dismissed` 를 먼저 넣어 red 확인
  (`assert 'data-foms-no-autodismiss' in tag` 실패) → `templates/admin/naver_ingest.html:20` 에 속성 추가 → green.
  `pytest tests/services/integrations/test_naver_admin_surface.py -q` **26 passed**(회귀 없음).
- 2026-08-20 **T2 완료**. 테스트 `test_pagination_links_keep_place_filter` 먼저 red 확인
  (`href="/admin/naver-ingest?page=2"` — place 없음) → 페이지 링크 2곳에 필터 버튼과 **같은 관용구**
  `place='PENDING' if place_pending else None` 적용 → green. 27 passed.
- 2026-08-20 **T3 완료**. 테스트 4건 먼저(취소건 확인완료 존재·정상 수집분도 존재·담당자 select 는 주문쪽만·
  **review 라우트가 주문 없는 링크를 받는가**) → 신규 2건 red 확인 → footer 배타 분기 해제 → green.
  **원인은 템플릿 하나였다**: 서버 review 라우트는 이미 주문 없는 링크를 정상 처리한다(라우트 테스트로 확인).
  부수: 규격 경고를 `selected.order_id and ...` 로 좁히고, 주문 못 만드는 집에는 안내 문구를 따로 뒀다.
  `pytest tests/services/integrations/ -q` **277 passed** · `APP_OK`.
- 2026-08-20 **T4 완료**. 사용자 선택: 마이그레이션은 격리 PG 레인에서만, backfill 은 스크립트만(실행 보류).
  구현 6조각: `mapping.group_key_text()` 신설(기존 튜플 시그니처 불변) · `ExternalOrderLink.group_key`
  + 인덱스 `ix_external_order_link_group` · 마이그레이션 `navergroup_00`(models/mapping import 없음) ·
  수집 2곳(COLLECTED·PENDING_REVIEW) 기록 + `claim_watch` 재수집 시 갱신(빈 값이면 기존 값 보존) ·
  이력 `_history_group_key`/`_group_key_col()` 이 컬럼 사용(폴백 `group_key → external_order_no → link:id`) ·
  `scripts/maintenance/backfill_naver_group_key.py`(멱등·`--dry-run`·배치 커밋).
  검증: SQLite 레인 `tests/services/integrations/` **286 passed** · **PG 레인 전수 737 passed**(PG 17.9, 5440) ·
  `test_migration_chain` 왕복 통과(head=`navergroup_00` 단일, 신규 리비전이 왕복 창에 포함됨) · `APP_OK`.
  **테스트가 무는지 직접 확인**: 기록 라인 2줄을 잠시 빼고 재실행 → 3건 red, 복원 후 green.
  그때 `same_household` 만 양쪽 통과여서(`{None}` 도 원소 1개) `None not in keys` 를 추가로 물렸다.
  **미검증 1건**: backfill `--dry-run` 을 로컬 dev DB 에서 못 돌렸다 — 그 DB 에는 컬럼이 없다
  (마이그레이션 미적용, 사용자 선택). CLI 는 정상 동작하고 backfill 로직은 테스트 2건이 레인에서 검증한다.
