# 계약서 열람 이력 보존 설계 (SHARE-HIST-00)

- 작성: 2026-09-01
- 브랜치/워크트리: `session/sharehist` / `c:\tmp\foms-s-sharehist` (base `origin/deploy`)
- 선행 원장: `docs/plans/2026-08-31-share-contract-drawing-ux-ledger.md` §후속 4(계약서 라이브 반영)
- 상태: **설계 — 사용자 승인 대기** (DB 스키마 추가 = RPI 대상)

## 1. 문제

계약서 공유 링크를 라이브 반영으로 바꾸면서(`_live_estimate_snapshot`), 같은 링크가 늘 최신
주문 값을 렌더한다. 그 대가로 **고객이 특정 시점에 실제로 본 계약서가 어디에도 남지 않는다.**
계약서에는 법적 효력 문구가 들어가므로 분쟁 시 "고객이 그날 본 금액"을 제시할 수단이 필요하다.

## 2. 왜 기존 원장으로는 안 되는가

`order_field_changes`(ORDER-DIFF-01)가 주문 값 변경을 전량 행으로 남긴다(`items.*.price`,
actor, before/after). 그러나 그것은 **주문의 변경 이력**이지 **고객 화면의 재현**이 아니다:

- 계약서 표면에는 회사정보·계좌(`resolve_estimate_company_info` / `resolve_estimate_payment_info`)와
  발주사 판정(factory2)이 함께 들어간다 — 원장에 없는 축이다.
- 스냅샷 화이트리스트(`_SNAPSHOT_ITEM_KEYS`, `snapshot_version`)가 바뀌면 과거 재생 결과가
  당시 화면과 달라진다.
- 계약번호(`contract_no_date`)는 토큰 발급 시점 고정값이다.

→ 재생(replay)은 근거로 쓸 수 없다. **열람 시점에 렌더된 dict 그대로**를 남긴다.

## 3. 사용자 결정 (2026-09-01)

| 항목 | 결정 |
|---|---|
| 방식 | **A — 새 원장 테이블** (security_logs JSONB 적재·동결 회귀 모두 기각) |
| 기록 시점 | **고객이 열람할 때만** (발급·변경 시점 기록 안 함) |
| 열람 권한 | **주문을 볼 수 있는 직원 전부** (`_SHARE_ROLES` = ADMIN/MANAGER/STAFF) |
| 보존 | **영구** (정리 잡 없음) |

## 4. 스키마 — `order_share_snapshots`

마이그레이션 `sharehist_00`, `down_revision = 'naverdisp_00'`(현재 단일 head).
`models.py` 정의와 컬럼 단위로 동일해야 한다(create_all ↔ alembic 지문 게이트).

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | BigInteger (sqlite variant Integer) | 열람 원장이라 32bit 상한 안 남긴다 |
| `share_token_id` | Integer, **FK 없음** | 감사 원장 규약(`OrderFieldChange`·`OrderEvent`와 동일) — 주문 purge 가 증거를 지우면 안 된다 |
| `order_id` | Integer, **FK 없음** | 주문 축 조회용 |
| `kind` | String(20) | `estimate` \| `bundle` |
| `content_hash` | String(64) | canonical JSON 의 sha256 hex — 중복 판정 열쇠 |
| `snapshot` | JSONColumn, NOT NULL | 렌더된 dict 그대로(≤64KB — 빌더 캡이 이미 강제) |
| `source` | String(16) | `live` \| `stored`(라이브 재구성 실패 폴백) |
| `first_viewed_at` | DateTime | `now_utc_naive` |
| `last_viewed_at` | DateTime | 같은 내용 재열람 시 갱신 |
| `view_count` | Integer NOT NULL | 같은 내용 재열람 횟수 |

인덱스: `ix_order_share_snapshots_token_id`(`share_token_id`, `id`),
`ix_order_share_snapshots_order_time`(`order_id`, `first_viewed_at`).

**UNIQUE 제약을 두지 않는다.** `(share_token_id, content_hash)` 를 UNIQUE 로 묶으면
금액이 A→B→A 로 되돌아간 경우 세 번째 상태가 첫 행에 흡수돼 시간축이 무너진다.
중복 판정은 **그 토큰의 최신 행과만** 비교한다(진짜 시간축 보존). 동시 열람 경합으로
같은 내용 행이 인접 2개 생길 수 있으나 내용이 같으므로 증거 가치는 훼손되지 않는다.

`downgrade()` 는 테이블 drop — 파생 증거이며 주문 원본은 무손실.

## 5. 쓰기 경로

신규 `foms/services/order_share_history.py`:

- `canonical_json(snap) -> str` — `sort_keys=True, ensure_ascii=False, separators=(',',':')`
- `content_hash(snap) -> str` — sha256 hex
- `record_snapshot_view(session, row, snap, *, source) -> None`
  — 그 토큰의 최신 행을 1건 조회 → `content_hash` 가 같으면 `last_viewed_at`/`view_count` 갱신,
  다르거나 없으면 새 행 add. **commit 은 호출자 소관**(기존 `record_view` 규약과 같다).

`foms/api/share.py` 열람 경로 2곳(estimate `:365` 부근, bundle `:385` 부근):

```
try:
    share_history.record_snapshot_view(db_session, row, snap, source=src)
except Exception:                      # noqa: BLE001 — 증거 적재 실패가 고객 화면을 죽이면 안 된다
    db_session.rollback()
    logger.error('공유 계약서 열람 이력 적재 실패: share_id=%s', row.id, exc_info=True)
share_service.record_view(row)
db_session.commit()
```

순서가 중요하다: 이력 적재를 **먼저** 시도하고 실패 시 rollback 해야 `record_view` 증가분이
같이 날아가지 않는다. 조용한 무시가 아니라 `logger.error(exc_info=True)` 로 남긴다.

`source` 는 `_live_estimate_snapshot` 이 라이브 재구성에 성공했는지로 정한다 —
그 함수가 `(snap, source)` 를 돌려주도록 반환형을 넓힌다(호출자 2곳뿐).

**drawing kind 는 기록하지 않는다**(계약 내용이 없다 — 음성 대조군 테스트로 고정).

### 게이트 영향 (T3 조사 결과 재사용: `docs/harness/evidence/2026-08-31-share-route-contracts.md`)

- write_guard / order_mutation_policy / audit_coverage 매니페스트: **GET 라우트는 모집단 밖** → 등재 불필요
- `order_mutation_writer` / `state_writer` 스캐너: 시그널은 `flag_modified(structured_data)`·`.status` 등 → **비저촉**
- `foms_failopen_inventory.json`: 새 `except Exception` 이 생기므로 **`python tools/harness/failopen_scan.py` 재생성 필수**
  (로거 배선 있으므로 `SWALLOW_BY_CONTROL_FLOW` 기준선 180 은 안 늘어난다)
- 네임스페이스 닫힌집합: flat 모듈 `foms/api/share.py` 에 함수 추가는 비저촉(디렉토리 단위 검사)

## 6. 읽기 경로 (직원)

`share_api_bp`(`/api/share`, `@login_required` + `@role_required(_SHARE_ROLES)`) 에 GET 2개:

1. `GET /api/share/history/<int:share_id>`
   → `{items: [{snapshot_id, content_hash, source, first_viewed_at, last_viewed_at,
   view_count, summary: {items_count, items_subtotal, shipping_price, deposit_amount,
   balance_amount, issued_date}}]}`, 최신순 50건. **스냅샷 원문은 목록에 싣지 않는다**(응답 비대).

2. `GET /api/share/history/<int:snapshot_id>/page`
   → 저장된 스냅샷을 **`share_estimate_view.html` 그대로** 렌더한 전체 페이지.
   고객이 본 것과 같은 CSS·같은 파셜이어야 증거로 의미가 있으므로 사본을 만들지 않는다.
   ERP 는 이걸 **새 탭**으로 연다 — ERP 셸에 공유 전용 CSS 를 끌어들이지 않는다(스타일 오염 0).
   템플릿에 `history_meta`(열람 시각·직원 열람 표시) 배너를 옵션으로 추가하며,
   **고객 경로는 무변경**(`{% if history_meta is defined and history_meta %}`).

`/api` 접두어 아래 HTML 페이지가 하나 생기는 어색함은 감수한다 — 새 블루프린트·새 디렉토리는
닫힌집합 게이트를 건드리고, 이 페이지는 공유 열람 기능의 부속이다(근거를 코드 주석에 남긴다).

감사: 2번 라우트에서 `log_access(..., action='SHARE_HISTORY_VIEWED', ...)` 1건.
`action=` 키워드 형태이므로 **`foms/services/audit_message_display.py` 라벨 등재 필수**
(미등재 시 `tests/domains/test_admin_audit_screen_readability_3.py` red).

## 7. ERP UI

`static/js/orders/erp-share.js` `_itemHtml` — kind 가 `estimate`/`bundle` 인 항목에
"고객이 본 내용" 버튼 추가 → 목록 API 호출 → 시각·금액 요약 리스트 → 행 클릭 시 `/page` 새 탭.
자산 `?v=` 핀 범프(erp-share.js 를 싣는 템플릿 전수 grep 후 동시 범프).

**고객 페이지 자산(`foms-share-view.css`·`foms-share-contract.css`·`share-*.js`)은 무변경** →
share_view / share_estimate_view / share_bundle_view 3핀 범프 불필요.
단 `share_estimate_view.html` 마크업에 배너 조건이 들어가므로 드리프트 테스트 재확인.

## 8. 완료 기준 (검증 명령)

- [ ] `python -c "import app; print('APP_OK')"` → `APP_OK`
- [ ] `python -m alembic heads` → 단일 head
- [ ] 신규 `tests/domains/test_order_share_history.py` 전부 통과:
  - 같은 내용 재열람 → 행 증가 0, `view_count` 2, `last_viewed_at` 갱신
  - 금액 변경 후 열람 → 새 행 1개(총 2행), 각 행이 각자 금액 보존
  - A→B→A 되돌림 → **3행**(시간축 보존)
  - 라이브 재구성 실패 폴백 → `source='stored'`
  - 원장 쓰기 예외 → 계약서 여전히 200, `record_view` 는 증가
  - bundle 경로도 기록 / **drawing 은 0행(음성 대조군)**
  - 목록 API: 비로그인 리다이렉트·VIEWER 403·응답에 `snapshot` 원문 부재
  - `/page`: 저장 금액이 현재 주문 금액과 다르게 렌더된다(라이브 오염 0)
  - `SHARE_HISTORY_VIEWED` 라벨 등재
- [ ] `pytest tests/domains/test_order_share_view.py tests/domains/test_order_share_api.py tests/domains/test_order_share_estimate.py tests/domains/test_order_share_history.py tests/contracts tests/domains/test_failopen_inventory.py tests/domains/test_write_guard.py tests/domains/test_audit_coverage_inventory.py tests/domains/test_admin_audit_screen_readability_3.py tests/visual/test_share_ui_contract.py`
- [ ] `python tools/harness/failopen_scan.py` 재생성 후 인벤토리 드리프트 0
- [ ] PG 레인: `tests/postgres` 해당분 + create_all↔alembic 왕복 지문 일치
- [ ] `scripts/ops/pre_push_smoke.ps1` exit 0

## 9. 범위 밖 (명시)

- 발급·변경 시점 캡처(고객 미열람 건) — 사용자가 열람 시점만으로 결정
- 보존 기간 정리 잡 — 영구 보존 결정
- 도면 이미지 이력 — 계약 내용이 아니다
- 스냅샷 원문의 서명·타임스탬프 인증(TSA) — 별도 주제
