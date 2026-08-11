# 카카오 알림톡 v1 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 로 task 단위 실행. 체크박스로 추적. Progress ledger: `docs/plans/2026-07-29-kakao-alimtalk-v1-ledger.md`.
> 정본 스펙: `docs/specs/2026-07-29-kakao-alimtalk-v1-design.md` (v2, 3-agent 교차검수 반영). 본 플랜과 스펙 충돌 시 스펙 우선.

**Goal:** 실측 예약 확정 시 고객에게 알림톡 자동 발송 + 주문 상세 수동 발송 (템플릿 1종, 3표면).

**Architecture:** 전송 계층만 신규(`foms/services/kakao_alimtalk.py` + Solapi SDK). 멱등=`domain_side_effect_outbox` partial UNIQUE, 이력=`structured_data['alimtalk_measurement']`+`OrderEvent`, 발송 실행=T0 확인 결과에 따라 sidefx worker 또는 커밋 후 동기 폴백. 신규 테이블·마이그레이션·RQ task 없음.

**Tech Stack:** Flask 2.3, SQLAlchemy 2.0, solapi SDK(신규 pin), 기존 outbox/OrderEvent 인프라.

## Global Constraints (전 task 공통)

- 함수 50줄 이하, docstring·타입힌트 필수, bare except 금지 (실패는 로그+이력).
- structured_data 수정 = `copy.deepcopy` + `flag_modified`. 타임스탬프 = `now_utc_naive` (`datetime.now` 금지).
- API 응답 = `{'success': bool, 'data': ..., 'error': ...}`.
- 신규 POST/PUT 라우트 = `docs/harness/foms_write_guard_manifest.json` + `docs/harness/foms_order_mutation_policy_manifest.json` 동시 등재 (미등재 = CI red).
- 주문 저장 트랜잭션 절대 비차단 — 알림톡 로직 예외가 저장 500 유발 금지.
- 고객 전화·주소 로그에 원문 출력 금지 (마스킹: `010****6730`).
- 기존 JS 파일 수정 시 `?v=` 범프 + 핀 리터럴 전수 grep + 치환 파일 전부 커밋.
- 커밋 메시지 한글, UTF-8 파일로 `git commit -F`. task당 1커밋.
- 검증 공통: `python -c "import app; print('APP_OK')"` 성공 후 커밋.

---

### Task 0: 선결 확인 (오케스트레이터 직접 — 위임 금지)

**목적:** 발송 실행 경로 분기 결정 + 의존 준비.

- [ ] **0-1** Railway에 sidefx DELIVERY worker 서비스 가동 여부 확인 (`railway status`/대시보드 — CLI 링크는 프로젝트명+`REDIS_PUBLIC_DOMAIN`으로 prod/dev 재확인, 메모리 함정). 결과를 ledger `T0.decision`에 기록: `WORKER_ON`(handler 등록 경로) 또는 `WORKER_OFF`(동기 폴백 경로 — 스펙 §6.3).
- [ ] **0-2** `pip install solapi` 로컬 설치 + `requirements.txt`에 `solapi==5.0.3` 추가. 검증: `python -c "from solapi import SolapiMessageService; print('SOLAPI_OK')"`.
- [ ] **0-3** 커밋: `chore: solapi SDK 의존 추가 (알림톡 v1 T0)`

---

### Task 1: 변수 빌더·자격 판정 (순수 로직, 외부 호출 없음)

**Files:**
- Create: `foms/services/kakao_alimtalk.py`
- Test: `tests/domains/test_kakao_alimtalk_service.py`

**Interfaces (Produces — 이후 task가 이 시그니처에 의존):**
```python
ALIMTALK_TEMPLATE_MEASURE: str  # 스펙 §5 본문, #{변수} 자리 포함 모듈 상수

def normalize_measure_schedule(sd: dict) -> tuple[str, str] | None:
    """실측 일정 canonical화. (dates, time) — dates='2026-08-14|2026-08-15'(정렬·중복제거),
    time=strip. 유효 YYYY-MM-DD 0건이면 None(발송 미자격)."""

def build_dedupe_key(order_id: int, sd: dict) -> str | None:
    """자동 발송 멱등키 'alimtalk:measure:{order_id}:{dates}:{time}'. 미자격 None."""

def extract_valid_phone(sd: dict) -> str | None:
    """parties.customer.phone → 숫자만, '/' 등 다중이면 첫 토큰. 10~11자리·'01' 시작 아니면 None."""

def build_variables(sd: dict) -> dict[str, str]:
    """알림톡 변수 dict. 키는 '#{고객명}' 형식(중괄호 포함). 치환 후 1,000자 하드 가드 내장."""

def render_preview(sd: dict) -> str:
    """ALIMTALK_TEMPLATE_MEASURE에 build_variables를 로컬 치환한 미리보기 텍스트."""
```

**구현 규칙 (스펙 §6.2):**
- 날짜: `foms/services/order_date_sync.py`의 `_normalize_date_str` 재사용. 한글화 `2026-08-14`→`8월 14일`, 다중 `', '` 병기. 정규화 실패 원문은 표기에서 제외.
- 시간: 빈값 `'미정'`. 시공일: `schedule.construction.date` 비면 `'상담'`. 발주사 비면 `'라홈'`. 품목 필드 빈값 `'상담'`.
- 예약금: `from foms.services.erp_display import erp_deposit_amount_from_structured` → `f"{v:,}원"`, None이면 `'상담'`.
- `#{품목내역}`: 품목별 6줄 블록(`제품명 :`/`내 부 :`/`색 상 :`/`옵 션 :`/`손잡이 :`/`기 타 :`) `\n\n` 연결. 치환 후 총 길이 1,000자 초과 시 첫 품목 블록 + `\n외 {N}건`으로 축약.

- [ ] **1-1** 실패 테스트 작성 — 최소 케이스:
```python
def test_normalize_multi_date_order_insensitive():
    sd = {'schedule': {'measurement': {'date': '2026-08-15, 2026-08-14', 'time': ' 3시 30분 '}}}
    sd2 = {'schedule': {'measurement': {'date': '2026-08-14,2026-08-15', 'time': '3시 30분'}}}
    assert normalize_measure_schedule(sd) == normalize_measure_schedule(sd2)

def test_dedupe_key_none_without_valid_date():
    assert build_dedupe_key(1, {'schedule': {'measurement': {'date': '상담'}}}) is None

def test_phone_multi_takes_first_valid():
    sd = {'parties': {'customer': {'phone': '010-2473-6730 / 010-1111-2222'}}}
    assert extract_valid_phone(sd) == '01024736730'

def test_phone_invalid_returns_none():
    assert extract_valid_phone({'parties': {'customer': {'phone': '1234'}}}) is None

def test_variables_deposit_and_fallbacks():
    sd = {'parties': {'customer': {'name': '임다슬', 'phone': '010-2473-6730'}},
          'payment': {'deposit': 100000}, 'schedule': {'measurement': {'date': '2026-08-14', 'time': '3시 30분'}},
          'items': [{'product_name': '무몰딩 여닫이'}]}
    v = build_variables(sd)
    assert v['#{예약금}'] == '100,000원' and v['#{실측일}'] == '8월 14일'
    assert v['#{시공일}'] == '상담' and '무몰딩 여닫이' in v['#{품목내역}']

def test_render_preview_under_1000_with_many_items():
    items = [{'product_name': f'제품{i}', 'internal': 'x'*30, 'color': 'y'*30} for i in range(30)]
    sd = {'parties': {'customer': {'name': 'a', 'phone': '010-2473-6730'}}, 'items': items,
          'schedule': {'measurement': {'date': '2026-08-14', 'time': '3시'}}}
    text = render_preview(sd)
    assert len(text) <= 1000 and '외 29건' in text
```
- [ ] **1-2** `pytest tests/domains/test_kakao_alimtalk_service.py -q` → 전부 FAIL(모듈 없음) 확인
- [ ] **1-3** `kakao_alimtalk.py` 구현 (위 시그니처·규칙 전부, Solapi 호출은 이 task 범위 밖)
- [ ] **1-4** 같은 명령 → 전부 PASS + `APP_OK`
- [ ] **1-5** 커밋: `feat: 알림톡 변수 빌더·자격 판정 서비스 (v1 T1)`

---

### Task 2: Solapi 클라이언트 + 발송·이력 기록

**Files:**
- Modify: `foms/services/kakao_alimtalk.py` (발송 계층 추가)
- Modify: `foms/services/order_event_display.py` (라벨 맵 2줄)
- Modify: `tools/ops/run_domain_side_effect_outbox.py` (T0=WORKER_ON일 때만 handler 등록)
- Test: `tests/domains/test_kakao_alimtalk_send.py`

**Interfaces (Produces):**
```python
def is_configured() -> bool:
    """SOLAPI_API_KEY/SECRET/PF_ID/TEMPLATE_MEASURE_ID/SENDER_PHONE 전부 존재 여부."""

def send_alimtalk(order_id: int, *, manual_by: int | None = None) -> dict:
    """주문 재조회→자격판정→발송→이력 기록. 반환 {'sent': bool, 'error': str|None}.
    이력: sd['alimtalk_measurement']={'sent_at','message_id','dedupe_key','error','sent_by'}
    (deepcopy+flag_modified) + OrderEvent('ALIMTALK_SENT'|'ALIMTALK_FAILED')."""

def maybe_send_measure_alimtalk(order_id: int) -> None:
    """자동 트리거 진입점(커밋 후 호출 전용). 게이트: FOMS_ALIMTALK_AUTO_ENABLED →
    자격판정 → outbox insert(effect_type='ALIMTALK_SEND', dedupe_key, 별도 tx,
    IntegrityError=중복 정상 흡수) → T0 분기(WORKER_OFF: 즉시 send_alimtalk 후 DONE 마킹).
    모든 예외 내부 처리(로그) — 호출부로 전파 금지."""
```

**구현 규칙:** Solapi 오류 분류 `auth/balance/template_mismatch/invalid_phone/length_exceeded/network`(스펙 §6.7). `from_`=`SOLAPI_SENDER_PHONE` 필수(failover 전제). `text` 파라미터 미사용. outbox insert는 `foms/services/sidefx_outbox.py`의 `enqueue_side_effect` 사용하되 **주문 저장 tx 밖 별도 세션**. 로그에 전화번호 마스킹. OrderEvent 라벨: `ALIMTALK_SENT`='알림톡 발송', `ALIMTALK_FAILED`='알림톡 실패'.

- [ ] **2-1** 실패 테스트: SDK를 `monkeypatch`로 스텁 —
```python
def test_send_records_history_and_event(pg_session, stub_solapi_ok): ...
    # sd['alimtalk_measurement']['message_id'] 기록 + OrderEvent ALIMTALK_SENT 1건
def test_send_no_phone_records_failed(pg_session): ...
    # error='no_valid_phone', OrderEvent ALIMTALK_FAILED, Solapi 미호출
def test_maybe_send_dedupe_second_call_noop(pg_session, stub_solapi_ok): ...
    # 같은 일정 2회 호출 → 발송 1회 (IntegrityError 흡수)
def test_maybe_send_flag_off_noop(pg_session, monkeypatch): ...
def test_maybe_send_never_raises(pg_session, monkeypatch): ...
    # enqueue_side_effect가 RuntimeError 던져도 예외 전파 없음
```
- [ ] **2-2** FAIL 확인 → 구현 → `pytest tests/domains/test_kakao_alimtalk_send.py -q` PASS + `APP_OK`
- [ ] **2-3** (WORKER_ON일 때만) `register_handler("ALIMTALK_SEND", handle_alimtalk_send, replace=True)` 등록 + 소비 테스트 1건
- [ ] **2-4** 커밋: `feat: 알림톡 발송 계층·이력 기록 (v1 T2)`

---

### Task 3: 자동 트리거 배선 (쓰기 경로 3개)

**Files:**
- Modify: `foms/api/erp_orders_structured.py` — PUT `/structured` 커밋 후(geocode enqueue :953-954 인접) + PATCH `/structured/fields` 커밋 후 + `_record_structured_events`에 measurement `.time` 비교 추가(:359-370 블록 인접, date와 동일 패턴)
- Modify: `foms/api/orders/field_update.py` — `measurement_date` 분기(:443-447) 커밋 후
- Test: `tests/domains/test_kakao_alimtalk_trigger.py`

**Consumes:** `maybe_send_measure_alimtalk(order_id)` (T2).

**배선 형태 (3곳 동일):**
```python
from foms.services.kakao_alimtalk import maybe_send_measure_alimtalk
# ... db.commit() 성공 직후:
maybe_send_measure_alimtalk(order.id)  # 내부 완전 비차단(T2 계약)
```
draft autosave 경로(`erp_orders_structured.py:1392-1403`)에는 **배선 금지** (스펙 H1 — draft 미자격이 이중 방어지만 호출 자체를 안 함).

- [ ] **3-1** 실패 테스트:
```python
def test_put_structured_with_measure_date_triggers_send(client, stub_maybe_send): ...
    # 신규 실측일 저장 → maybe_send 1회 호출 (draft 선저장돼 있어도 — diff 무관 검증)
def test_patch_fields_triggers(client, stub_maybe_send): ...
def test_field_update_quickedit_triggers(client, stub_maybe_send): ...
def test_draft_autosave_does_not_trigger(client, stub_maybe_send): ...
def test_measurement_time_change_records_event(client): ...  # 신설 time 비교
```
- [ ] **3-2** FAIL → 배선 구현 → PASS + `APP_OK`
- [ ] **3-3** 회귀: `pytest tests/domains/test_erp_orders_structured*.py -q` (기존 저장 경로 무파괴)
- [ ] **3-4** 커밋: `feat: 실측 예약 알림톡 자동 트리거 3경로 배선 (v1 T3)`

---

### Task 4: 수동 발송 API (preview + send-manual)

**Files:**
- Create: `foms/api/kakao/__init__.py` (Blueprint `kakao_bp`, url_prefix `/api/kakao`)
- Modify: `app.py` 블루프린트 등록부가 아닌 기존 blueprint 등록 모듈(현행 패턴 확인 후 동일 위치 — app.py 직접 추가 금지 규칙)
- Modify: `docs/harness/foms_write_guard_manifest.json`, `docs/harness/foms_order_mutation_policy_manifest.json`
- Test: `tests/domains/test_kakao_alimtalk_api.py`

**Routes:**
```python
GET  /api/kakao/alimtalk/preview/<int:order_id>
  # role_required(['ADMIN','MANAGER','STAFF']) — 응답 data: {'text': render_preview(sd),
  # 'eligible': bool, 'last': sd.get('alimtalk_measurement')}
POST /api/kakao/alimtalk/send-manual/<int:order_id>
  # 같은 권한 + CSRF. 서버 저장본 sd로 재렌더·발송(클라 text 파라미터 없음 — 받지도 않음).
  # dedupe_key='alimtalk:measure:{id}:manual:{uuid4}', sent_by=session user_id.
  # is_configured() False → 503 {'success': False, 'error': 'not_configured'}
```

- [ ] **4-1** 실패 테스트: 권한 401/403, 미설정 503, preview 렌더 일치, send-manual 이력 `sent_by` 기록, 요청 body의 `text` 무시 검증
- [ ] **4-2** FAIL → 구현 + **manifest 2종 등재**(send-manual: write_guard `mode: guard` + mutation policy `STAFF_MUTATION`) → PASS
- [ ] **4-3** `pytest tests/domains/test_write_guard.py -q` PASS (등재 검증) + `APP_OK`
- [ ] **4-4** 커밋: `feat: 알림톡 수동 발송 API + manifest 등재 (v1 T4)`

---### Task 5: UI 3표면 (PC·모바일·태블릿)

**Files:**
- Create: `templates/orders/partials/erp_alimtalk_modal.html` (erp_channel_push_resend_modal.html 25줄 패턴 복제 — read-only 본문+발송/취소)
- Create: `static/js/orders/erp-alimtalk-send.js` (erp-channel-push-confirm.js 싱글톤·버튼 잠금 패턴)
- Modify: `templates/orders/partials/erp_order_tab.html` (:413-421 채널톡 버튼 옆), `erp_order_tab_mobile.html` (:441-446 sticky footer), `static/js/foms/tablet-measure-form.js` (:1136-1141 섹션)
- Test: `tests/visual/test_p1_mockup_erp_order_tab*.py` 계열 기존 구조 테스트 무파괴 + 신규 계약 테스트(버튼 id 3표면 존재)

**동작:** 버튼 클릭 → `GET preview` → 모달(본문 + last 발송 정보 + 재발송 경고) → 확인 → `POST send-manual` → 버튼 옆 상태 한 줄 갱신. `window.fomsErpAutosave.isDirty()` true면 버튼 disabled + title="저장 후 발송". 전역 리스너는 `window.__FOMS_ALIMTALK_BOUND` 싱글톤 가드(G4).

- [ ] **5-1** 계약 테스트 작성(3표면 버튼·모달 partial include·JS 체인 `?v=` 핀) → FAIL
- [ ] **5-2** 구현 (기존 수정 JS `?v=` 범프 → 핀 리터럴 grep 전수 치환 → **치환 파일 전부 스테이징 확인**)
- [ ] **5-3** PASS + `APP_OK` + `pytest tests/domains/test_erp_order_shared_form_scripts.py -q` 회귀
- [ ] **5-4** gstack browse 스모크: PC 1440·모바일 390·태블릿 1180 각 1회 — 버튼 노출·모달 열림·미설정 503 토스트(로컬은 키 없음) 확인
- [ ] **5-5** 커밋: `feat: 알림톡 수동 발송 UI 3표면 (v1 T5)`

---

### Task 6: 통합 검증 + 스테이징 (오케스트레이터 직접)

- [ ] **6-1** 전체: `pytest tests/domains/test_kakao_alimtalk*.py tests/domains/test_write_guard.py -q` + `APP_OK` + `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` exit 0
- [ ] **6-2** deploy push → `python tools/harness/ci_watch.py <SHA> deploy` (run_in_background) green + perf-gate 확인(`gh run list`)
- [ ] **6-3** Railway FOMS-DEV env 6종 등록(§6.6) — Solapi 키 발급 완료 후
- [ ] **6-4** 스테이징 E2E (직원 본인 번호): 자동 최초 발송 / 일정 변경 재발송 / 같은 일정 중복 차단 / 수동 재발송 / SMS failover(채널 차단 상태 재현) / `text` 파라미터 거동 확인(스펙 §8-3) — 결과 ledger 기록
- [ ] **6-5** `docs/AI_STATUS.md` 갱신

**운영 승격(별도 게이트):** 템플릿 심사 승인 + 스테이징 E2E green + **사용자 명시 승인** 후 세션 커밋 cherry-pick → `gh pr create --base production`. perf-gate blocking 유의.

---

## Self-Review 기록
- 스펙 §5(템플릿 동결)→T1 상수, §6.1(멱등)→T2, §6.2(빌더·오류분류)→T1/T2, §6.3(트리거 3경로+time 비교+worker 분기)→T0/T2/T3, §6.4(수동 API·manifest·dirty)→T4/T5, §6.5(UI 3벌)→T5, §6.6(env)→T6, §6.7(오류지도)→T2 테스트, §6.8(검증)→각 task+T6. 잔여 없음.
- placeholder 스캔: 코드 블록 전 task 실재. "적절히" 류 문구 없음.
- 시그니처 일관성: T2가 T1의 `build_dedupe_key`/`render_preview` 소비, T3/T4가 T2의 `maybe_send_measure_alimtalk`/`send_alimtalk` 소비 — 명칭 일치 확인.
