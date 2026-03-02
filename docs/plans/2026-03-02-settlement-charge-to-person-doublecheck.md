# 비용 청구 귀속 인원(개인) 선택 — 1:1 소스코드 더블체크

**기준 문서**: `docs/plans/2026-03-02-settlement-charge-to-person-plan.md`  
**검토일**: 2026-03-02

---

## 1. 계획 §2 데이터 구조 vs 구현

| 계획 | 구현 위치 | 결과 |
|------|-----------|------|
| deduction에 optional `charge_to_user_id`, `charge_to_name` | `erp_orders_completion.py` L199–210: `ded_item`에 `if charge_to_user_id is not None` / `if charge_to_name` 시에만 추가 | ✅ 일치 |
| 기존 deduction 필드 유지 (id, department, amount, reason, created_at, created_by) | 동일 `ded_item`에 기존 5개 필드 + 조건부 2개 | ✅ 하위 호환 |

---

## 2. 계획 §3.1 API 요청·검증·저장 vs 구현

| 계획 항목 | 구현 (소스 위치) | 결과 |
|-----------|------------------|------|
| **body에 `charge_to_user_id` (optional)** | L156: `charge_to_user_id = data.get('charge_to_user_id')` | ✅ |
| **CUSTOMER일 때 무시** | L171–173: `if department == 'CUSTOMER': charge_to_user_id = None` | ✅ |
| **User 존재·is_active** | L179: `db.query(User).filter(User.id == uid, User.is_active == True).first()` | ✅ |
| **User.team == department (대소문자 통일)** | L182: `(charge_user.team or '').strip().upper() != department` | ✅ |
| **잘못된 인원 시 400** | L176–183: int 변환 실패 / user 없음 / team 불일치 시 각각 400 + 메시지 | ✅ |
| **deduction에 charge_to_user_id, charge_to_name 저장** | L207–210 | ✅ |
| **OrderEvent.payload에 포함** | L224–229: `event_payload`에 동일 조건으로 추가 | ✅ |
| **SecurityLog 메시지에 귀속 인원** | L237–239: `log_msg += f" {charge_to_name}({charge_to_user_id})"` (charge_to_name 있을 때만) | ✅ |

**함수·흐름**  
- `api_settlement_issue(order_id)`: 단일 함수 내에서 수신 → 검증 → settlement 갱신 → OrderEvent/SecurityLog → commit. 계획한 순서와 동일.  
- `_ensure_dict`, `copy.deepcopy(sd)`, `flag_modified(order, 'structured_data')`: 기존 settlement 처리와 동일 방식 유지.

---

## 3. 계획 §3.2 구성원 API 활용 vs 구현

| 계획 | 구현 | 결과 |
|------|------|------|
| `GET /erp/api/users?team=<TEAM>` 사용, 변경 없음 | `erp_map.py` L215: `@erp_map_bp.route('/erp/api/users')`, team 파라미터로 필터 | ✅ |
| 프론트에서 부서 선택 시 해당 경로로 fetch | `erp_completion_scripts.html` L78: `fetch('/erp/api/users?team=' + encodeURIComponent(team), ...)` | ✅ |

---

## 4. 계획 §4.1 모달 HTML vs 구현

| 계획 | 구현 (erp_completion_dashboard.html) | 결과 |
|------|--------------------------------------|------|
| 귀속 대상 select **바로 아래**에 “귀속 인원” 영역 | L64–70: 부서 select 다음에 `#erp-settlement-charge-to-wrapper` 블록 | ✅ |
| 라벨 “귀속 인원 (선택)” | L66 | ✅ |
| `<select id="erp-settlement-charge-to-user">` | L67–69 | ✅ |
| 기본 옵션 value="" “부서만” | L68: `<option value="">부서만</option>` | ✅ |
| SALES/DRAWING/PRODUCTION/CONSTRUCTION일 때만 표시, CUSTOMER 시 숨김 | wrapper에 `d-none` 기본, JS에서 부서 change 시 표시/숨김 (scripts L99–108) | ✅ |

---

## 5. 계획 §4.2 스크립트 vs 구현

| 계획 항목 | 구현 (erp_completion_scripts.html) | 결과 |
|-----------|-------------------------------------|------|
| **부서 변경 시** 값이 SALES/DRAWING/PRODUCTION/CONSTRUCTION이면 `/erp/api/users?team=<값>` fetch 후 옵션 채우기·영역 표시 | L99–108: `depSelect.addEventListener('change', ...)`, `DEPTS_WITH_MEMBERS.indexOf(dep) !== -1` 시 `loadTeamMembers(dep)` 호출, wrapper `d-none` 제거 | ✅ |
| CUSTOMER 선택 시 옵션 비우고 영역 숨김 | L106–107: `else { resetChargeToUser(); }` → 옵션 “부서만”만 남기고 wrapper에 `d-none` | ✅ |
| “부서만” 옵션 유지 | `loadTeamMembers` 내부 L82, `resetChargeToUser` L71: 항상 첫 옵션 `부서만` | ✅ |
| **모달 오픈 시** 부서/귀속 인원 초기화 | L118–122: `depSelect.value = ''`, `resetChargeToUser()` 호출 | ✅ |
| **제출 시** charge_to_user_id가 숫자일 때만 body에 포함 | L139–141: `chargeVal = chargeToSelect.value`, `if (chargeVal && /^\d+$/.test(chargeVal)) payload.charge_to_user_id = parseInt(chargeVal, 10)` | ✅ |
| 부서·금액·사유만 필수, 귀속 인원 선택 사항 | L134–137: oid, dep, amount, reason만 검사; payload에는 조건부로 charge_to_user_id 추가 | ✅ |

**함수·변수**  
- `resetChargeToUser()`: 옵션 초기화 + wrapper 숨김. 모달 오픈·CUSTOMER 선택 시 사용.  
- `loadTeamMembers(team, callback)`: `/erp/api/users?team=...` 호출 후 `data.users`로 option 채움, 실패 시 “부서만”만 유지.  
- `DEPTS_WITH_MEMBERS`: `['SALES','DRAWING','PRODUCTION','CONSTRUCTION']` — 계획의 “부서별 표시” 대상과 일치.

---

## 6. 논리·엣지 케이스 점검

| 케이스 | 기대 동작 | 구현 확인 |
|--------|-----------|-----------|
| 부서만 선택(귀속 인원 빈값) | deduction에 charge_to_user_id/charge_to_name 없음 | API: L170 조건으로 검증 블록 미진입 → L207–210 미추가 ✅ |
| CUSTOMER + body에 charge_to_user_id 있음 | API에서 무시, 부서만 저장 | L172–173에서 `charge_to_user_id = None` ✅ |
| 다른 부서 user_id를 넣은 경우 | 400 “선택한 인원이 해당 부서 소속이 아닙니다.” | L182–183 ✅ |
| 비활성 User id | 400 “해당 귀속 인원을 찾을 수 없거나 비활성입니다.” | L179–181 ✅ |
| charge_to_user_id 문자열/잘못된 형식 | 400 “귀속 인원이 올바르지 않습니다.” | L174–177 (int 변환 실패) ✅ |
| 모달에서 부서 변경: 영업 → 고객 → 도면 | 영업 시 wrapper 표시·옵션 로드, 고객 시 숨김·초기화, 도면 시 다시 표시·도면팀 옵션 로드 | change 이벤트마다 분기 처리됨 ✅ |

---

## 7. 결론

- **데이터 구조**: 계획 §2 확장 규격과 구현이 1:1 일치하며, 기존 deduction 형식과 하위 호환됨.  
- **API**: 요청 수신·검증(CUSTOMER 무시, User 존재·is_active·team 일치)·저장·OrderEvent·SecurityLog가 계획대로 구현됨.  
- **HTML**: 귀속 인원 블록 위치·id·라벨·기본 옵션·표시 조건이 계획과 일치.  
- **JS**: 부서 변경 시 API 호출·옵션 채우기·표시/숨김, 모달 오픈 시 초기화, 제출 시 `charge_to_user_id` 조건부 포함이 계획과 일치.  
- **엣지 케이스**: “부서만”, CUSTOMER, 타부서/비활성/잘못된 형식, 부서 전환 시 동작이 계획 및 검증 규칙과 맞음.

**종합: 계획 대비 구현 1:1 일치, 논리·함수·엣지 케이스 점검 이상 없음.**
