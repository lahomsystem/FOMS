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

### T1 — #5 `.alert` 자동닫힘 (PENDING)
`templates/admin/naver_ingest.html:20` 에 `data-foms-no-autodismiss` 추가.
**완료 기준**: 계약 테스트가 해당 속성 존재를 확인하고 green · 수집 실행 결과 문구가 5초 뒤에도 남는다.

### T2 — #8 페이지 링크 필터 유실 (PENDING)
`templates/admin/naver_ingest.html:246,255` 의 `url_for` 에 `place` 전달.
**완료 기준**: `?place=PENDING&page=2` 링크에 `place=PENDING` 이 실려 있음을 테스트가 확인 · green.

### T3 — #4 취소·반품 큐 이탈 (PENDING)
`naver_triage.html` footer 배타 분기를 풀어 `확인 완료`를 공통 영역으로.
**완료 기준**: 주문 없는 취소 건 상세에 `확인 완료` 버튼이 있고 `주문 만들기`는 잠긴 상태 · 테스트 green ·
기존 "주문 있는 건" 경로(담당자 지정 + 확인 완료) 회귀 없음.

### T4 — #1 묶음키 컬럼 (PENDING) ← 이 플랜의 본체
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
- 2026-08-20 스펙·플랜 작성. 코드 사실 확인 완료(두 그룹키 정의·배지 링크 카운트·footer 배타 분기·페이지 링크 누락). 승인 대기.
