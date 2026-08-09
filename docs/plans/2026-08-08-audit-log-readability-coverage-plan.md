# 감사 로그 가독성·커버리지 실행 플랜 (AUDIT-LOG P4)

- 스펙: `docs/specs/2026-08-08-audit-log-readability-coverage-design.md`
- 원장: `docs/plans/2026-08-08-audit-log-readability-coverage-ledger.md`
- 상태: **승인 대기**
- 등급: `**C` (릴레이 — 단계별 승인·검증·커밋)

## 진행 규약

- task 단위로 **위임 → diff 직접 확인 → 테스트 직접 실행 → 커밋 → 원장 갱신**.
- 각 task 는 **완료 기준(통과할 명령)** 없이 착수하지 않는다.
- push 는 `deploy` 만. production 승격은 사용자 명시 요청 시에만.

---

## Phase A — 표시 SSOT (승격 없이 즉시 효과)

### A1. 표시 SSOT 모듈 신설
- 산출: `foms/services/audit_message_display.py`
  - `field_label()` / `format_value()` / `render_audit_line()` / `parse_legacy_message()`
  - 라벨 맵은 `foms/web/orders/edit.py:274-278` 에서 **이관**(복제 금지).
- 완료 기준:
  - `pytest tests/domains/test_audit_message_display.py -q` (신규, 값 포맷 6종·라벨 이관·역파싱 성공/실패 경로)
  - `pytest tests/domains/test_order_edit*.py -q` 회귀 green (edit.py 이관 후 동작 동일)
  - 계약 테스트 1건: **라벨 사전이 저장소에 두 벌 존재하지 않음**(grep 기반)

### A2. 보안 로그 화면에 표시 SSOT 적용
- 산출: `foms/web/admin/audit.py` + `templates/admin/security_logs.html`
  - 구조화 행(`action`/`detail` 있음) → 구조화 기반 문장
  - 구 형식 행(운영 24,605행) → `parse_legacy_message()` 역파싱 문장, 실패 시 원문
  - 주문번호 옆 고객명: 페이지 단위 배치 조회 1회
- 완료 기준:
  - 신규 계약 테스트: 구조화/구형식/파싱실패 3경로 + **쿼리 수 고정(페이지당 주문 조회 1회)**
  - 운영 실데이터 표본 20건을 역파싱에 넣어 **문장 생성 실패 0건** (실측 스크립트, 커밋 제외)
  - `APP_OK` + smoke exit 0

### A3. 거부 로그 분리
- 산출: 기본 목록에서 `ACCESS_DENIED`(및 구형식 `권한 없는 접근 시도`) 제외 + 스위치로 열람
- 완료 기준: 계약 테스트(기본 숨김·스위치 노출·페이지 링크 유지) + 화면 실측
- 부산물 보고: `/trash` 거부 282건 1인 집중 → 권한/메뉴 정리 필요 여부 사용자 확인

---

## Phase B — 기록 보강 (before→after·대상 스냅샷)

### B1. 주문 필드 수정 3경로 구조화
- 대상: `foms/api/orders/field_update.py`, `foms/api/orders/regional.py`, `foms/api/orders/status.py`
- 산출: `action`·`target_type/target_id`·`detail{field, before, after, order_type, customer_name}`
- 완료 기준:
  - 신규 계약 테스트: 3경로 각각 before/after 기록·PII 최소성(연락처·주소 미포함)
  - `pytest tests/domains -q` 전수 green
  - 스테이징 실검증: 실제로 값 바꾼 뒤 화면 문장 확인

### B2. 레거시 writer 문장 생성기 통일
- 대상: 남은 `log_access` 호출부 중 자유 텍스트 조립부
- 산출: 문장은 표시 SSOT 로 생성(문자열 조립 금지)
- 완료 기준: grep 계약 테스트(라우트에서 `f"주문 #{...}의 '{field}'"` 형태 직접 조립 0건)

---

## Phase C — 커버리지 배선

### C1. 우선순위 배선 (결제·시공·AS·도면·생산·파일)
- 스펙 3-3 표의 묶음별로 task 분할(묶음 1개 = 1 task).
- 각 묶음 완료 기준: 신규 계약 테스트(행위 1건당 원장 1행·행위자·대상 주문) + domains 전수 green.

### C2. 커버리지 게이트
- 산출: 쓰기 라우트 대비 감사 기록 커버리지를 **인벤토리 파일로 고정**하고 CI 에서 감소를
  차단(기존 `foms_failopen_inventory.json` 방식과 동일 패턴).
- 완료 기준: 인벤토리 생성 + 인위적 라우트 추가로 red 실증 + `pre_push_smoke` 편입.

---

## Phase D — 열람 기록 (사용자 결정 대기)

### D1. 규모 계측 (행 미기록)
- 산출: 주문 상세 조회 카운터(집계 1일 1행) 1주일 수집.
- 완료 기준: 1주 후 실측 수치 보고 → **사용자 결정**(전체 기록 / 민감 화면만 / 미도입).

### D2. (결정 시) 열람 기록 배선
- 결정 전에는 착수하지 않는다.

---

## 순서·의존

```
A1 → A2 → A3        (승격 무관, 즉시 효과)
        ↘ B1 → B2   (구조화 detail — 운영 반영은 승격 후)
                ↘ C1 → C2
D1 은 A 와 병행 가능(독립)
```

## 승격 전제

Phase B·C 의 구조화 컬럼은 **운영 DB에 아직 없다**(T4~T11 미승격). 운영에서 효과를 보려면
승격이 선행되어야 하며, 승격 전 확인 사항 3건은 `docs/harness/runtime/HANDOFF_AUDIT_LOGGING.md`
의 "운영 주의" 절에 있다.
