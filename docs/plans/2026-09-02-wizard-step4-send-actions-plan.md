# 모바일 마법사 4단계(확인) — 실측 PUSH · 알림톡 예약안내 버튼 (WIZ-SEND-01)

> 세션: session/wizard-push-alimtalk (worktree `c:\tmp\foms-s-wizard-push-alimtalk`)
> 작성: 2026-09-02 / 등급: **B(하루)** — CEO 총괄 + 5 task 병렬

## 1. 요구사항 (사용자)

1. 모바일 주문등록 마법사 4단계(`data-wizard-step="4"`, 확인 화면)에 버튼 2개 추가
   - **실측 PUSH** — PC `#erp-channeltalk-push-measure-btn` 과 같은 동작(변환 텍스트 + 실측 첨부를 채널톡 실측방으로)
   - **알림톡 · 예약 내역** — PC `#erp-alimtalk-send-btn` 과 같은 동작(실측 예약 안내 템플릿 발송)
2. UI 는 미니멀. 인라인 스타일 금지, `foms-wizard__*` BEM 체계 준수.
3. **주문 등록 전에도** 입력 데이터가 실시간 반영되어 정상 발송되어야 한다.

## 2. 조사 결론 (근거)

- 마법사는 최종 제출 전까지 **`Order` 행이 존재하지 않는다**. 있는 것은 `OrderDraft(draft_key, payload JSON)` 뿐.
  `Order` 는 `POST /api/erp/order-draft/submit` 의 `create_order(...)` 에서 처음 생긴다
  ([foms/api/erp_order_draft.py:503-628](../../foms/api/erp_order_draft.py)).
- 서버에 초안 payload → 정식 structured_data 변환기가 **이미 있다**:
  `_draft_payload_to_structured(data)` ([foms/api/erp_order_draft.py:127-240](../../foms/api/erp_order_draft.py)).
- 알림톡 계층의 핵심 함수는 전부 **sd 만 받는 순수 함수**다 — order 불필요:
  `build_variables(sd)` / `render_preview(sd)` / `_dispatch(sd)` / `extract_valid_phone(sd)` /
  `resolve_brand(sd)` / `brand_config()` ([foms/services/kakao_alimtalk.py](../../foms/services/kakao_alimtalk.py)).
  order 의존은 `_ineligible_reason(order, sd)`·`build_dedupe_key(order_id, sd)`·`_record_history(session, order, ...)`·감사 3곳뿐.
- 채널톡 push 본문(변환 텍스트)은 **클라이언트 DOM 리더**(`erpGenerateConversionText`,
  [static/js/orders/erp-order-shared.js:4852](../../static/js/orders/erp-order-shared.js))라 마법사 DOM(`#wiz-*`)에서는 재사용 불가.
  → **서버 SSOT 조립기**를 만든다. 선례 = [foms/services/channel_as_message.py](../../foms/services/channel_as_message.py)
  ("AS 대시보드에는 주문 폼 DOM 이 없으므로 본문을 서버가 단독 조립한다"). JS 3벌째 사본 금지 원칙과 충돌하지 않는다.
- 마법사 첨부는 `payload.items[].attachments[].tmp_key` 로 스토리지에 이미 올라가 있고, 제출 시
  `promote_draft_attachments` 가 `OrderAttachment(category='measurement')` 로 승격한다
  ([foms/services/order_draft_attachments.py:43-90](../../foms/services/order_draft_attachments.py)).
  → 초안 단계에서도 `tmp_key` 로 `storage.get_download_url(...)` 서명 URL 발급이 가능하다(= "실측 첨부만"과 동일 집합).
- CSRF 는 `csrf_bootstrap.html` 전역 fetch 패치로 자동 부착(마법사도 `orders/layout.html` → `layout_head.html` 경유로 포함).

## 3. 확정 설계 (CEO 결정)

**결정 D1 — 주문 행을 만들지 않는다.** 버튼은 초안(`draft_key`) 기준으로 동작한다.
PC 의 "미저장이면 먼저 저장(승격) 후 발송" 패턴은 마법사에 쓰지 않는다 — 사용자 요구가
"주문 등록 전 발송"이고, 버튼이 몰래 주문을 등록하면 '주문 등록' 버튼의 의미가 깨진다.

**결정 D2 — 실시간성은 "초안 flush 후 서버 렌더"로 얻는다.** 클라이언트는 본문 텍스트를 만들지 않는다
(알림톡 스펙 §6.4 F2 "클라 텍스트 불신" 유지). 버튼 클릭 → `draft.js` 강제 flush(PUT) → 서버가
저장된 최신 payload 를 sd 로 변환해 본문을 조립·발송.

**결정 D3 — 발송 이력은 초안에 남기고, 등록 시 주문으로 승계한다.**
`OrderDraft.payload` 는 매 autosave 마다 클라가 통째로 덮으므로 거기 쓰면 안 된다.
→ `OrderDraft.send_history`(JSON, nullable) 컬럼을 Alembic 으로 추가하고 서버만 쓴다.
제출 시 이 이력을 새 주문 `structured_data` 의 정본 키(`alimtalk_measurement`,
`channeltalk_push_measure_room`)로 승계한다.

**결정 D4 — 알림톡 중복 발송 차단(사용자 미요청, 필수 안전).**
승계 시 `alimtalk_measurement.dedupe_key` 를 `build_dedupe_key(new_order.id, sd)` 로 재작성한다.
그러지 않으면 등록 후 첫 저장에서 자동 발송이 같은 안내를 고객에게 한 번 더 보낸다
(`_already_sent` 는 dedupe_key 동일성으로만 판정).

**결정 D5 — 채널톡 본문의 "주문 상세 보기" 링크는 초안 발송에서 생략**한다(가리킬 주문이 없다).
대신 머리말 한 줄 `※ 등록 전 초안 실측 공유` 를 붙여 수신자가 상태를 오해하지 않게 한다.

## 4. API 계약 (task 간 인터페이스 — 이 시그니처로 고정)

### 4.1 서비스

```python
# foms/services/kakao_alimtalk.py (추가)
def draft_ineligible_reason(sd: dict) -> str | None:
    """order 축(존재·삭제·draft)을 뺀 sd 전용 자격 판정.
    순서: not_configured → 일정없음(not_eligible) → no_valid_phone → brand_profile_missing."""

def send_alimtalk_for_sd(sd: dict, *, sent_by: int | None, dedupe_key: str) -> dict:
    """order 행 없이 sd 로 발송한다. 이력·OrderEvent 를 쓰지 않는다(호출자 몫).
    Returns: {'sent': bool, 'error': str | None, 'message_id': str | None}"""
```

```python
# foms/services/channel_measure_message.py (신규)
def build_measure_push_text(sd: dict, *, draft_notice: bool = False) -> str:
    """실측방 PUSH 본문을 sd 로 조립한다(PC erpGenerateConversionText 서버 미러)."""
```

```python
# foms/services/channel_draft_push.py (신규)
def push_measure_room_for_draft(*, sd: dict, files: list[dict], user_id: int) -> dict:
    """실측방 그룹으로 초안 본문+첨부를 전송한다.
    files: [{'filename': str, 'url': str, 'type': 'image'|'video'}]
    Returns: {'sent': bool, 'error': str | None, 'files_count': int}"""

def collect_draft_measure_files(payload: dict) -> list[dict]:
    """payload.items[].attachments[].tmp_key → 서명 URL 목록(최대 20)."""
```

### 4.2 라우트 (신규 모듈 `foms/api/erp_order_draft_send.py`, prefix `/api/erp/order-draft`)

모두 `@login_required` + `@role_required(['ADMIN','MANAGER','STAFF'])` + `_require_wizard()` 동등 게이트.
응답 규약 `{'success': bool, 'data': ..., 'error': ...}`.

| method | path | 용도 |
|---|---|---|
| GET | `/alimtalk/preview` | `?draft_key=` → `{text, eligible, ineligible_reason, last, configured}` |
| POST | `/alimtalk/send` | body `{draft_key}` → 발송 + 초안 이력 기록 |
| GET | `/channel-push/preview` | `?draft_key=` → `{text, files_count, configured}` |
| POST | `/channel-push/send` | body `{draft_key, change_note?}` → 실측방 전송 + 초안 이력 기록 |

- POST 2종은 **mutation route** → `docs/harness/foms_write_guard_manifest.json` +
  `docs/harness/foms_order_mutation_policy_manifest.json` 등재 필수(미등재 = CI red).
- 감사 action: `ALIMTALK_DRAFT_SENT`, `CHANNEL_PUSH_DRAFT_SENT` — `foms/services/audit_message_display.py` 라벨 등재 필수.
  `target_type='order_draft'`, `target_id=OrderDraft.id`.

## 5. Task 분할 (병렬)

| task | 범위 | 파일 | 완료 기준 |
|---|---|---|---|
| T1 | 알림톡 sd 발송 계층 | `foms/services/kakao_alimtalk.py` | 신규 pytest 통과 + 기존 `tests/domains/test_kakao_alimtalk_*.py` 전부 green |
| T2 | 실측방 본문 서버 조립기 | `foms/services/channel_measure_message.py`(신규) | 골든 텍스트 계약 테스트 통과 |
| T3 | 초안 발송 서비스 + 라우트 + manifest/감사라벨 | `foms/services/channel_draft_push.py`, `foms/api/erp_order_draft_send.py`, manifest 2종, `audit_message_display.py`, `foms/platform/blueprints.py` | `test_write_guard.py`·`test_audit_coverage_inventory.py` green + 라우트 단위테스트 |
| T4 | 마법사 UI(버튼·시트·JS) | `templates/orders/wizard/step4_confirm.html`, `static/css/components/foms-wizard.css`, `static/js/foms/wizard-send.js`(신규), `wizard_shell.html` | 소스 계약 테스트 + 실제 화면 동작 |
| T5 | 이력 컬럼·승계 | `models.py`, Alembic 마이그레이션, `foms/services/order_draft_service.py`, `foms/api/erp_order_draft.py`(submit 승계) | 단일 head 유지 + 승계 pytest |

## 6. 검증 (완료 기준 — 전부 통과해야 완료)

- `python -c "import app; print('APP_OK')"`
- `python -m pytest tests/domains/test_kakao_alimtalk_send.py tests/domains/test_kakao_alimtalk_api.py tests/domains/test_channel_integration_smoke.py tests/domains/test_write_guard.py tests/domains/test_audit_coverage_inventory.py tests/domains/test_alembic_single_head.py -q`
- 신규 테스트 `tests/domains/test_wizard_draft_send.py` green
- `scripts/ops/pre_push_smoke.ps1` exit 0
- 스테이징 실기기/실브라우저 QA (채널톡 키가 로컬 `.env` 에 없어 실측 PUSH E2E 는 스테이징 전용)

## 7. 계약 부록 (T5 ↔ T3 인터페이스)

```python
# foms/services/order_draft_service.py (T5 추가)
SEND_KIND_ALIMTALK = "alimtalk_measurement"
SEND_KIND_CHANNEL_MEASURE = "channeltalk_push_measure_room"

def record_draft_send(db, *, draft_key: str, user_id: int, kind: str, entry: dict) -> None:
    """초안 발송 이력 1건을 OrderDraft.send_history[kind] 에 굳힌다(서버 전용 쓰기).
    entry 는 주문 sd 의 정본 이력 모양 그대로 넣는다(승계 시 무변환 복사)."""

def get_draft_send_history(db, *, draft_key: str, user_id: int) -> dict:
    """{kind: entry} 반환. 없으면 {}."""
```

- `alimtalk_measurement` entry 모양(주문 정본과 동일):
  `{sent_at, message_id, dedupe_key, error, sent_by, sent_by_name, channel: None, channel_checked_at: None}`
- `channeltalk_push_measure_room` entry 모양: 기존 `_record_push_metadata` 가 쓰는 모양을 따른다
  (`foms/api/channel/channel_integration.py:207-330` 확인 후 동일 키 사용).

## 8. 공통 규율 (전 task)

- 근본 원인 수정만. `try/except: pass`·하드코딩 우회·TODO 미봉책 금지, bare except 금지.
- 신규 함수 **docstring + 타입 힌트 필수**, 함수 50줄 이하.
- structured_data 수정은 `copy.deepcopy` + `flag_modified` 패턴.
- 인라인 스타일 금지, jQuery 금지, `JSON.parse('{{ x|tojson }}')` 금지(`data-*` + `safeJsonParse`).
- 기존 JS/CSS 를 고치면 `?v=` 핀 범프 + 핀 전수 grep(SW staticCacheFirst 규약).
- 타임스탬프는 `now_utc_naive`.
- 커밋하지 말 것 — 통합·검증·커밋은 CEO 가 한다.

## 9. D4 개정 (2026-09-02, CEO — rev_99 게이트 충돌 해소)

T5 가 보고한 문제: 승계를 `create_order` **뒤에** 하면 `flag_modified(order,'structured_data')` 가
새 EXTERNAL order-mutation writer 로 잡혀 REV-99 릴리스 게이트(EXTERNAL 증가 금지)가 red 가 된다.
게이트 메시지의 지시는 "REV-00 `execute_order_mutation` 경유"지만, 그러자고 새 policy id 를
만드는 것은 이 작은 승계 한 건에 과한 비용이다.

**개정 D4' — 주문 id 기반 dedupe 재작성을 폐기하고, 일정 서명(schedule signature)으로 중복을 막는다.**

1. 초안 발송 이력 entry 에 `draft_schedule` 키를 추가한다
   = `normalize_measure_schedule(sd)` 의 `f"{dates}:{time}"` (없으면 `None`).
2. 승계는 `create_order(...)` **호출 전에** `structured_data` dict 에 키를 넣는 **순수 dict 병합**으로 한다.
   `_prepare_structured` 는 sd 를 deepcopy 후 가산만 하므로 미지의 최상위 키가 보존된다
   ([foms/services/orders/order_create.py:100-126](../../foms/services/orders/order_create.py)).
   → ORM 쓰기 0건, `flag_modified` 0건, REV-99 인벤토리 무변화.
3. 자동 발송 중복 차단은 `_already_sent` 를 확장해 처리한다:
   기존 키 동일 판정에 더해, **성공 이력의 `draft_schedule` 이 현재 sd 의 일정 서명과 같으면 이미 보낸 것**으로 본다.
   일정이 바뀌면 서명이 달라져 자동 재발송이 정상 동작한다(원래 요구된 거동).

이 개정은 dedupe 문자열 일치보다 의미가 정확하다 — 막으려는 것은 "같은 키 재사용"이 아니라
"같은 실측 일정 안내의 중복 도달"이다.
