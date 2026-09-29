# 도면 결함 2차 묶음 — SPEC (v2 · 리뷰 반영 · 2026-09-29 사용자 승인)

> 2026-09-29 · 상태: **v2(리뷰 2건 반영) · 사용자 승인(2026-09-29, "병렬로 빨리 끝내") · 구현 중** · 근거: 원장 `docs/plans/2026-09-29-drawing-defects-verification-ledger.md`(판정표·운영 규모·순서 의존·1차 리뷰 R1~R13), 검증 원자료(진단·반박·누락 점검), 1차 묶음 = deploy `756582cee` = **production `4bc407c49`(PR #451, 병합 `287782ce3`, 2026-09-29 15:42 KST)**
> 등급: 코어 변경(API 입력 계약 · 상태 전이 게이트 · 파일 삭제 규칙 · 운영 데이터 판단) → Spec → 승인 → 구현.
> 이미 확정된 사용자 결정(이 문서는 바꾸지 않는다): ① 확정 때 파일 삭제 안 함(1차 반영) ② 1차 알림톡 문구 그대로 ③ 고객이 링크에서 직접 승인하는 버튼은 나중 ④ 관리자는 도면팀이 아니어도 주문 변경 확인 가능(그대로).
> 표기: "코드 확인" = 이 문서를 쓰며 파일:행을 다시 읽어 확인함. "확인 필요" = 코드·실행으로 확인하지 못함. 리뷰 반영 내역은 끝의 §11.

---

## 0. 한눈에

**지금 가장 급한 것**: 1차가 이미 운영에 있으므로 원장 순서 의존 7(M1 × 확정 재계산 제거)이 **운영에서 열려 있다**. 오래된 주문 폼을 한 번 저장하면 되돌려진 `drawing_current_files` 가 그대로 확정본·고객 링크·생산 탭이 된다. → **2a-1①(서버 소유 키 잠금)을 긴급 묶음으로 따로 먼저 운영에 올리고**, 운영 측정 ①(C1·C2·C3)을 지금 한다(둘 다 사용자 명시 요청 필요).

| ID | 한 줄 | 뿌리 | 묶음 | 새 엔드포인트 |
|---|---|---|---|---|
| M1 | 오래된 주문 폼 저장이 도면 상태·현재 도면·도면 배정(+고객확인·퀘스트)을 되돌린다 | A | **2a-1①(긴급)** · 2a-1② | 없음 |
| C21 (+M3·M16) | 수정 중·미확정 도면인데 고객컨펌 완료·제작 시작·일반 상태 쓰기가 생산으로 넘긴다 | A | **2a-2** | 없음 |
| M5 | 수정요청 files 를 검증 없이 저장 → 남의 도면 삭제·링크 주입 | B | 2b | 없음 |
| M2 (+R2 동기 삭제) | 수정요청 취소가 기록을 지우고, 참고사진을 커밋 전에 지운다 | A·B | 2b | 없음(본문에 선택 필드 `reason`) |
| M7 | 전달 취소가 아직 쓰는 파일을 삭제 예약한다 | B | 2b | 없음 |
| M9 | 수령 확정·전달 취소·창구 업로드 완료 마지막 catch 에 로거가 없다 | B | 2b | 없음 |
| (복구 보강) | 삭제 예약 없는 휴지통 행을 복구 API 가 거짓 문구로 거절한다 | 리뷰 | 2b | 없음 |
| M10 | 작업실·ERP 전달 창에서 직접 올린 도면이 전달에서 빠진다 | C | **2c-1(2a-2 보다 먼저)** | 없음 |
| M14-a | 담당 아닌 도면팀에게 전달 버튼이 켜진다(서버 403) | 화면 | 2c-1 | 없음 |
| R1 | 전달 못 된 고아 업로드 53행 | C | 2c-2(운영 쓰기 별도 승인) | 없음 |
| R3 | 첨부 개수 4곳이 교체된 옛 도면까지 센다 | 1차 뒤처리 | 2c-2 | 없음 |
| R4 | ERP 내부 첨부 탭에서도 옛 도면이 확정 전부터 숨는다 | 1차 뒤처리 | 2c-2 | 없음(목록 API 선택 인자) |
| M14-b~e | 막힌 상태 색·딥링크 tab·태블릿 시트 전달·죽은 코드 | 화면 | 2d | 없음 |
| M13 | v2 모바일에 도면방 PUSH 가 없다 | 화면 | 2d | 없음 |
| R12 (+94px 가림) | 반영 체크 접근성 3건 + 관리자 하단 바가 본문을 가림 | 화면 | 2d | 없음 |
| R11 | 1차 테스트 약점 3곳 | 테스트 | 2d | 없음 |

### 0.1 원장 대조표 (원장 22개 · 1차 리뷰 R1~R13 · 1차 W2 열린 질문 전수)

| ID | 상태 |
|---|---|
| C8 | 1차 반영(운영 `4bc407c49`) — 확정이 파일을 지우지 않는다. 이미 지워진 참고사진 2장(#4080·#5177) 복구 가능성 = R2 버전 관리 확인(측정 ②, 읽기 전용) → 결과 보고 |
| C8-X | 1차 반영(운영) — 확정 때 이력 재계산 제거 |
| C8(a) · M15 | 1차 사용자 결정으로 닫힘(확정 때 삭제 안 함) |
| C8(b) | 확정 경로는 1차로 사라짐. 남은 수정요청 취소 경로 → **2b**(M2, 파일 안 지움) |
| C9 | 1차 반영(운영) — 폰 반영 체크. 실제 업로드 끝-끝(1차 리뷰 R2) → **2c-1** |
| C21 · M3 · M16 | **2a-2** |
| M1 | **2a-1①(긴급)** · 2a-1② |
| M2 · M5 · M7 · M9 | **2b** |
| M4 | 1차(C8-X)로 해소. 결합 회귀 테스트는 2a-2 |
| M6 · M8 | 1차로 삭제 경로가 사라져 닫힘(`foms/services/drawing_confirm_cleanup.py:225-244`, 코드 확인) |
| M10 · M14-a | **2c-1** |
| M11 · M12 | 1차 반영(운영) |
| M13 · M14-b~e | **2d** |
| R1 | **2c-2**(운영 쓰기 별도 승인, Q4). 복구 보강은 2b |
| R2 | **2c-1**(M10 과 함께 C9 끝-끝 실제 업로드) |
| R3 · R4 | **2c-2**(R4 는 §8 기본안) |
| R5 · R6 | 측정 완료 — 1차 승격 직전 H1·H2 = 0(`docs/AI_CHANGELOG.md` 2026-09-29) |
| R7 · R8 | 1차에서 고침 |
| R9 | 의도로 받아들임(닫힘) |
| R10 | 승격 직전 C2 = 0. 1차가 운영이라 **측정 ①(C1·C2·C3) 지금 재측정** + 2a-1① 긴급 |
| R11 · R12 | **2d** |
| R13 | 보고만(`construction_dashboard_display.py` 499/500). 2b 의 4.3.4 가 이 파일의 저장 URL 우선을 지워 줄 수가 준다(늘리지 않음) |
| W2 열린 질문 ① 관리자 하단 바 94px > 본문 여백 84px(가림) | **2d**(R12 와 같은 CSS 파일) |
| W2 열린 질문 ② 옛 한글 파일명 참고사진 key 는 개수만 보임 | **2b** 4.3.4 표시 규칙 한 줄(측정 E1 결과로 정함) |
| W2 열린 질문 ③ 상세가 중첩 `drawing.status` 를 먼저 읽음 | **2a-2** 판정 함수 하나로 통일 + 측정 I1 |

---

## 1. 목표 / 비목표

### 목표
1. 도면이 "영업이 수령 확정한 최신본"이 아니면 **정식 경로(고객컨펌 승인·제작 시작·일반 상태 쓰기)로는** 고객컨펌 → 생산으로 넘어가지 않는다. 예외는 둘뿐이고 둘 다 도면 상태를 기록으로 남긴다: (가) 관리자(ADMIN)의 사유 있는 뚫기 (나) ADMIN·MANAGER 의 단계 강제 변경(Q5 — 추천: 허용하되 경고·기록).
2. 전용 도면 API 가 쓴 값(도면 상태·현재 도면·이력·도면 배정)과 퀘스트·고객확인을 **주문 폼 전체 저장이 되돌리지 못한다**.
3. 클라이언트가 보낸 파일 key 로 서버가 남의 파일을 지우거나, 저장된 URL 로 스크립트가 도는 길을 없앤다.
4. 파일을 지우는 남은 길(전달 취소 회수 · 첨부 삭제 · 삭제 outbox)은 **하나의 "지워도 되는 키" 판정**을 거친다. 휴지통으로 보낸 행은 되살릴 수 있다고 말한 대로 되살아난다.
5. 작업실·ERP 대시보드 전달 창에서 직접 올린 도면이 전달된다.
6. 1차 리뷰 뒤처리(R3·R4·R11·R12)와 화면·서버 불일치(M13·M14)를 정리한다.
7. 각 묶음은 따로 운영에 올릴 수 있다. 단 §3 의 "운영 반영 전제"(순서)는 지킨다.

### 비목표
- 도면 revision ID 체계(v9 마스터 `docs/plans/2026-07-22-foms-full-system-bug-audit-report.md:322-344`) 도입 — 이번에는 `drawing_status` 축 게이트로 막는다.
- 도면 쓰기 전체를 전이 엔진 command 로 옮기기(STATE-DRAWING-01) — 이번에는 행 잠금·버전 올림까지(§4.1 ②).
- 생산 보드에 "도면 수정 중" 배지, 생산 변경 배지 창 시작점이 승인 시각으로 잘리는 문제(반박-C21 정정 1, `production_change_alerts.py:98-139`) — 기록만. 2a-2 게이트가 이 경로(수정요청 뒤 승인)를 닫으므로 운영 영향은 줄어든다.
- 제작 시작이 풀렸을 때 생산팀에 알리는 "풀림 알림" — 이번에는 두지 않는다(생산 보드 새로고침으로 확인).
- 반영 체크 게이트 범위 좁히기(C9 C안, 옛 회차 미체크가 막는 V7), '완료 해제'를 옛 요청에도 보일지.
- 같은 뿌리의 다른 폼 되돌림 중 `estimate_preview`·`channeltalk_push*`, 영업 담당(`assignments.sales_assignee_user_ids` — 배정 원장 `foms/services/orders/assignment.py:245 set_sales_assignee` 가 따로 있고 도면 게이트와 무관) — 별건 기록. **도면 배정(`assignments.drawing_assignee_user_ids`)은 도면 전달 권한의 기준값이라 이번 잠금에 넣는다**(§4.1).
- 전달 API 의 중복 key append 막기(`erp_orders_drawing.py:182`) — 삭제 판정이 막아 주므로 이번에는 두지 않음.
- 견적 자동 저장이 409 를 받았을 때 확인창 대신 상태 줄로 알리기 — 견적 화면 별건(§4.1 부작용).
- `quest.py` 의 `datetime.datetime.now()`(서버 현지 시각)와 도면 이력 UTC 가 섞이는 문제 — §10 확인 필요 목록에만.
- 고객 링크 직접 승인 버튼(사용자 결정: 나중).

---

## 2. 지금 기준선 (2026-09-29, 워크트리 HEAD `da99a9916` = origin/deploy)

| 확인 | 결과 |
|---|---|
| 1차 묶음 위치 | deploy `756582cee` · **production `4bc407c49`(PR #451, 병합 `287782ce3`, 2026-09-29 15:42 KST)**. 승격이 cherry-pick 이라 커밋 번호가 다르다 — `git patch-id --stable` 두 커밋 모두 `a08c5c6fd71f…` 로 같다. (초안 v1 은 조상 관계만 보고 "운영에 없음"으로 잘못 적었다.) |
| 1차 승격 직전 운영 측정 | R5·R6·R10 모두 0(H1·H2·C2, `docs/AI_CHANGELOG.md` 2026-09-29 행). **C1 은 재지 않았다.** |
| 누락 점검 프로브(저장소 밖) — 1차가 지운 `drawing_confirm_cleanup.get_storage` 패치만 `raising=False` 로 바꾼 사본 | **5 failed, 3 passed**(`ac3c9c2a3` 에서 실행. 이후 커밋은 문서·검색뿐이라 도면 코드는 같다) |
| └ 빨강 | P1 M1(:119) · P2 M5 남의 주문 key 삭제(:137) · P2b M5 현재 도면 삭제(:154) · P3 M10(:173) · P6 M7(:269) |
| └ 초록(1차가 고침) | P4 M4(C8-X 결합) · P5 M11 · P5b M12 |
| `tests/domains/test_bugrepro_c21_confirm_quest_while_returned.py` | 1 passed(음성 대조군) · **7 xfailed**(strict) |
| 1차 회귀 `test_drawing_mobile_revision_check.py` · `test_drawing_mobile_revision_refs_and_cancel.py` | 위 파일과 함께 `12 passed, 7 xfailed`, EXIT=0 |
| 리뷰 프로브(`scratchpad/revprobe/test_rev_probe.py`) | 한글 단계값 '고객컨펌' + RETURNED 주문에 영업 승인 → 200·PRODUCTION(§4.2.2) · 도면 담당 [d1]→[d2] 뒤 오래된 폼 PUT → [d1] 로 되돌아감(§4.1) |

---

## 3. 묶음과 배포 순서

```
지금 ─► 측정 ①(C1·C2·C3) ─► 2a-1① 서버 소유 키 잠금(긴급, 단독 운영 반영)
                                   │
                                   ▼
        2a-1② 도면 라우트 행 잠금·버전 올림 ─► 2b M5·M2·M7·M9·복구 보강
                                                   │
                     측정 ②(A1·A2·B1·C 재측정·D1·E1·F1·G1·I1·J1·K1·R2 버전 관리)
                                                   │
                                   2c-1 M10·M14-a ─┤
                                                   ▼
                        2a-2 C21 게이트(+M3·M16·일반 쓰기·제작 시작·화면·캐시·강제 변경 기록)
                                                   │
                                   2c-2 R1·R3·R4 ──┤
                                                   ▼
                                   2d M13·M14 나머지·R12·94px·R11
```

**권장 순서: 2a-1① → 2a-1② → 2b → 2c-1 → 2a-2 → 2c-2 → 2d.**
- 2a-1① 은 사용자 답이 필요 없고 결함(운영에서 열린 순서 의존 7)을 혼자 닫는다 → 가장 먼저, 다른 것과 섞지 않고 운영에 올린다.
- 2c-1(M10)은 2a-2 **보다 먼저 또는 같은 배포**여야 한다. 2a-2 게이트가 들어가면 CONFIRM+RETURNED/TRANSFERRED 주문의 출구는 "재전달 → 수령 확정"(또는 관리자)뿐인데, 전달 창 직접 업로드는 M10 때문에 400 이다(`erp_orders_drawing.py:140-141`, 원장 순서 의존 6). 지금까지는 C21 구멍 덕에 드러나지 않았다.
- 2b 는 2a-2 보다 먼저: 같은 `erp_orders_revision.py` 를 고치므로 **구현도 승격도 2a-1② → 2b → 2a-2 순서**(cherry-pick 순서가 뒤바뀌면 충돌한다. 충돌 = 다른 세션 의존 신호, 임의 해결 금지).

| 묶음 | 운영 반영 전제 | 같이 가야 하는 것 | 되돌리기 |
|---|---|---|---|
| **2a-1①(긴급)** | 없음. 측정 ① 과 병행 가능 | 서버 잠금 + 폼 JS 보존 목록 정리 + 계약 테스트 뒤집기(JS 는 같은 배포가 아니어도 된다) | 커밋 revert. 데이터 변화 없음 |
| 2a-1② | 2a-1① 운영 | 도면 라우트 5곳 행 잠금·버전 올림 + REV-99 allowlist·인벤토리 | revert. 데이터 변화 없음 |
| 2b | 2a-1② · **Q3 답(없으면 추천안)** | M5 공통 판정과 M7 은 같은 커밋 묶음. 첨부 삭제(4.3.6)와 복구 보강은 같은 커밋 | revert. M2 가 붙인 `REVISION_CANCELLED` 는 남지만 옛 코드는 모르는 action 을 건너뛴다(§4.4) |
| 2c-1 | 2a-1①(M14-a 가 쓰는 도면 배정 값이 잠겨 있어야 함) | M10 서버·JS 는 같은 배포 권장(서버만으로도 결함은 닫힘) | revert. 이미 `drawing/` 에 올라간 파일은 옛 코드에서도 전달 가능 |
| 2a-2 | 2a-1①② · 2b · **2c-1(M10) 운영** · 1차(C8-X Fx1 · C9 A안 — 이미 운영) · 측정 ②(A1·A2·B1·I1·K1) · 사용자 답 Q1·Q2·Q5 · I1 이 0 이 아니면 중첩 상태 보정(별도 승인) | 게이트·화면·캐시 무효화를 한 묶음 안에서 같이 | revert. 게이트·화면만이라 데이터 쓰기 없음. M16 이 False 로 바꾼 `blueprint.customer_confirmed` 는 읽는 게이트가 없어 남아도 무해 |
| 2c-2 | 2b(복구 보강) · 2a-2(캐시 무효화) · R1 은 Q4 답 + 목록 확인 + 별도 승인 | R3·R4 는 코드, R1 은 `tools/ops/` 스크립트 | revert. R1 적용분은 휴지통 복구로 되돌림 |
| 2d | 2c-1 뒤 권장 | CSS·JS 핀 | revert + 핀 되돌림 |

**승격 절차(묶음마다)**: 워크트리에서 구현 → `scripts/ops/pre_push_smoke.ps1` exit 0 → deploy push → CI green(런 생성 뒤 `ci_watch`) → 스테이징 확인 → **사용자 명시 요청** → `python tools/harness/promote_own_to_production.py --session-id <id>`(이 세션 커밋만 cherry-pick + PR) → PR CI green → 병합 → 운영 배포 확인. "deploy 푸쉬"는 production 을 포함하지 않는다.

**운영 측정도 묶음 단위로 요청**: production 측정은 사용자 명시 요청 1건당 1회라, §5 의 측정을 4묶음으로 나눈다(측정 ①~④). 묶음마다 요청 1건.

파일 겹침: 2a-1②·2b·2a-2 가 모두 `foms/api/drawing/erp_orders_revision.py` 를 고친다. 같은 날 두 창이 동시에 하면 워크트리를 나눈다(AGENTS.md).

---

## 4. 항목별 설계

### 4.1 M1 — 주문 폼 저장이 도면 축을 되돌린다 (2a-1① 긴급 · 2a-1②)

**문제** (코드 확인)
- 폼 JS 는 폼을 연 순간의 스냅샷에서 도면 키를 그대로 실어 보낸다: 보존 목록 `static/js/orders/erp-order-shared.js:2207-2228`(`assignments`·`quests`·`drawing`·`blueprint`·`drawing_status`·`drawing_current_files`·`drawing_transfer_history`·`last_drawing_transfer` 등), 복사 `:2345-2354`. 태블릿 실측 폼도 같은 PUT 을 **If-Match 없이** 통째로 보낸다(`static/js/foms/tablet-measure-form.js:1529-1538`).
- 서버는 키가 **요청에 없을 때만** 서버값으로 되돌린다: `foms/api/erp_orders_structured.py:541-543`. 이력만 `_force_preserve_drawing_transfer_history`(:466-479)가 지킨다. allowlist(`foms/services/orders/structured_form_projection.py:115-141`)는 이미 있는 키라 통과시킨다. `quests` 도 없을 때만 복원(:565-566). `assignments` 는 deep-merge 라 **들어온 값이 이긴다**(:555-561).
- 도면 배정 `assignments.drawing_assignee_user_ids` 는 도면 전달 권한의 기준값이다(`foms/services/orders/erp_policy_permissions.py:28-31` DRAWING_DOMAIN 우선). 리뷰 프로브: 담당 [d1]→[d2] 뒤 오래된 스냅샷 PUT → 200, [d1] 로 되돌아감 → 옛 담당자가 전달 권한을 되찾고 새 담당자는 403.
- 도면 API 는 `mutation_version` 을 올리지 않는다. 올리는 곳은 전달 취소 outbox 경로 한 곳(`foms/api/drawing/erp_orders_drawing.py:594`). 단계 유지 수령 확정(`foms/services/orders/drawing_receipt_command.py:64-66`)도 안 올린다. 그래서 If-Match 도 오래된 폼을 못 거른다. 태블릿 경로는 If-Match 자체가 없다.
- 재현(프로브 P1, 지금 빨강): 전달 → 수령 확정 → 폼 GET(버전 2) → 수정요청(RETURNED, 버전 2 그대로) → 스냅샷 PUT `If-Match: 2` → 200, `drawing_status` 가 CONFIRMED 로 되돌아감 → 승인 200·PRODUCTION.
- **1차가 운영에 있어 지금 살아 있는 위험이다**(원장 순서 의존 7 · 리뷰 R10): 확정이 이력 재계산을 안 하므로 폼이 되돌린 `drawing_current_files` 가 그대로 확정본·고객 링크·생산 탭이 되고, 방금 전달한 도면은 교체된 옛 도면으로 숨는다.
- 같은 뿌리(코드만 확인, 실행 안 함): 같은 보존 목록 때문에 오래된 폼이 퀘스트 승인 상태, `blueprint.customer_confirmed`, `blueprint.current`(`foms/services/orders/blueprint_projection.py`)도 되돌릴 수 있다.
- 게이트가 못 본 이유: REV-99 스캐너는 쓰기 자리를 **파일 단위**로 분류한다(`tools/harness/order_mutation_writer_scan.py:39-43`, :158-169). `erp_orders_drawing.py` 는 전달 취소 bump 때문에 파일 전체가 VERSIONED_DIRECT 로 등재돼, 버전을 안 올리는 전달 쓰기(:258)도 VERSIONED_DIRECT 로 잘못 표시돼 있다.

**목표 동작**
- 주문 폼 전체 저장(`PUT /api/orders/<id>/structured`)은 도면 축·도면 배정·고객확인·퀘스트를 **절대 바꾸지 않는다**. 클라이언트가 무엇을 보내든(If-Match 가 있든 없든, 최신 버전이든 아니든) 저장 순간의 DB 값(행 잠금 아래 `old_sd`)이 이긴다.
- 도면 API 가 주문을 바꾸면 행 잠금 아래에서 쓰고 `mutation_version` 이 오른다 → 그 전에 연 폼(If-Match 를 보내는 PC 폼)은 다음 저장에서 기존 409 `VERSION_CONFLICT` 를 받는다.

**설계 ① 서버 소유 키 잠금 (2a-1① 긴급 — 이것만으로 결함이 닫힌다)**
- `structured_form_projection.py` 에 `SERVER_LOCKED_KEYS`(frozenset), `SERVER_LOCKED_SUBKEYS`(dict: 부모 키 → 하위 키 튜플), `lock_server_owned_keys(old_sd, structured_data) -> list[str]` 를 둔다. 규칙: `old_sd` 에 있으면 그 값 deepcopy 로 덮고, 없으면 pop(하위 키도 같은 규칙). 클라이언트 값이 달랐던 키 경로를 돌려주고 `logger.warning("[DATA-01] ignored client values for server-locked keys: %s", ...)`.
- 최상위 대상: `drawing`, `drawing_status`, `drawing_transferred`, `drawing_confirmed_at`, `drawing_confirmed_by`, `drawing_current_files`, `drawing_transfer_history`, `last_drawing_transfer`, `drawing_assignees`, `drawing_wizard`, `blueprint`, `quests`.
- 하위 대상: `assignments.drawing_assignee_user_ids`, `assignments.drawing_assignees`(옛 모양). 쓰는 곳은 도면 담당 지정 API(`foms/api/drawing/erp_orders_draftsman.py:124`·:260)뿐이다(검색 확인).
- 호출 위치: `project_structured_form`(:221-243) 안, `lock_provenance` 옆. `assignments` deep-merge(`erp_orders_structured.py:555-561`) **뒤**에 돈다(projection 은 병합을 마친 dict 를 받는다 — 함수 docstring 전제). **순서 확인함**: 같은 PUT 안에서 서버가 붙이는 ERP_ORDER_CHANGED 이력(`_emit_drawing_order_change_if_needed`, `erp_orders_structured.py:1602`)은 projection(:1586) **뒤**라 잠금이 지우지 않는다. `old_sd` 는 `execute_order_mutation` 콜백 안에서 FOR UPDATE 로 읽은 값이다.
- `_force_preserve_drawing_transfer_history`(:466-479)는 잠금이 대신하므로 호출과 함수를 지운다.
- `_OPERATIONAL_TOP_LEVEL_KEYS`(:231-)는 "왜 서버 소유인가"의 문서이고 계약 테스트(`tests/domains/test_erp_order_shared_form_scripts.py:603`)가 문자열로 읽으므로 그대로 둔다.
- 폼 JS 보존 목록(`preservedTopLevelKeys`)에서 잠금 대상 최상위 키(`quests`·`drawing`·`blueprint`·`drawing_status`·`drawing_transferred`·`drawing_confirmed_at`·`drawing_confirmed_by`·`drawing_current_files`·`drawing_transfer_history`·`last_drawing_transfer`·`drawing_assignees`)를 뺀다. `assignments` 는 다른 하위 키가 있어 남긴다(서버가 도면 하위 키만 잠근다). 핀 `templates/orders/partials/erp_order_js.html:30` `?v=20260929a` → 구현일 핀.
- **계약 테스트 뒤집기(필수)**: `tests/domains/test_erp_order_shared_form_scripts.py:562-588 test_shared_erp_order_js_preserves_drawing_operational_state` 는 위 도면 키가 `erpCollectStructured` 블록에 **있다**고 단언한다 → 이름을 `test_shared_erp_order_js_does_not_resend_server_locked_keys` 로 바꾸고, `test_channel_push_trace.py:119` 처럼 `preservedTopLevelKeys` 블록만 잘라 잠금 대상 키가 `not in` 임을 단언한다. `estimate_preview`·`channeltalk_push*` 는 지금처럼 `in`(비목표). 같은 테스트의 workflow 블록 단언은 그대로.
- 응답 모양·권한 변화 없음. 관리자 예외 없음(도면 축은 전용 API·단계 강제 변경으로만 바꾼다).

**설계 ② 도면 쓰기를 행 잠금 아래에서 하고 버전을 올린다 (2a-1②, 별도 커밋)**
- 대상 라우트: 전달(`perform_drawing_transfer`, `erp_orders_drawing.py:50` — transfer-drawing·마법사 transfer-pending 공용), 전달 취소(:460 부근 — 이미 bump), 수정요청(`erp_orders_revision.py:38`), 반영 체크(:414), 수정요청 취소(:281), 수령 확정 중 **단계 유지** 확정(`erp_orders_draftsman.py` `stage_moved False` 경로).
- **잠금 먼저(lost update 차단)**: 지금 라우트들은 잠금 전에 `structured_data` 를 deepcopy 하고 상태 검사까지 끝낸다(`erp_orders_revision.py:64`, `erp_orders_drawing.py:82-89`). `execute_order_mutation` 은 clean 객체만 expire 하므로(`foms/services/orders/revision.py:224-236`) 콜백 전에 객체를 dirty 로 만들면 FOR UPDATE 대기 뒤에도 옛 값을 되쓴다. 그래서:
  - `revision.py` 에 공용 도우미 `lock_order_row(session, order_id) -> Order | None` 를 둔다 = `query(Order).filter(id).populate_existing().with_for_update().first()`(선례 `erp_orders_structured.py:2016-2037 _lock_draft_row`). 415줄 → 약 428줄.
  - 각 라우트는 **첫 주문 조회를 이 도우미로 바꾼다** — 읽기·권한 검사·상태 검사·deepcopy 는 모두 그 뒤. SQLite 레인에서는 FOR UPDATE 가 무시된다(단일 writer).
  - 실제 `order.structured_data = …; flag_modified` 는 `execute_order_mutation` 콜백 **안에서** 한다(콜백 전에 order 를 dirty 로 만들지 않는다). 같은 tx 가 이미 잠금을 쥐고 있으므로 엔진의 두 번째 FOR UPDATE 는 기다리지 않는다. 알림 행 추가와 커밋은 지금처럼 라우트가 한다.
- 수령 확정: draftsman 은 494줄(래칫 500, 목록 밖)이라 :437 의 구조화 쓰기를 `drawing_receipt_command.py`(95줄)의 새 도우미 `write_receipt_structured(db, order, s_data, *, actor_user_id, stage_moving)` 로 옮긴다. 단계 유지면 `execute_order_mutation` 콜백 안에서 쓰고, 단계가 옮겨지면 지금처럼 전이 직전 같은 tx 에서 order 에 반영한다(전이 엔진이 버전을 올린다 — 한 번 더 올리지 않는다).
- **REV-99(쓰기 자리 게이트) — 정확한 영향**:
  - EXTERNAL 은 allowlist(`docs/harness/foms_order_mutation_writer_allowlist.json`)를 고치지 않는 한 줄지 않는다(분류가 파일 단위).
  - `erp_orders_revision.py`: 쓰기 자리 3곳(:120 수정요청 · :339 취소 · :488 반영 체크, 모두 지금 EXTERNAL)을 **모두** 콜백 안으로 옮기므로 파일을 CANONICAL 로 등재한다(사유: "수정요청·취소·반영 체크를 REV-00 execute_order_mutation 경유로 수행"). EXTERNAL −3.
  - `erp_orders_draftsman.py`: 배정 쓰기 :144·:283 이 남아 **등재할 수 없다**. 확정 쓰기 :437 만 빠지므로 EXTERNAL −1.
  - `drawing_receipt_command.py`: 새 쓰기 자리가 생긴다(allowlist 밖이면 새 EXTERNAL → `test_rev_99.py:192 test_no_new_external_writers` 빨강). 이 파일의 쓰기는 모두 엔진 콜백 안이거나 전이 직전 같은 tx(선례: `foms/api/cs/complete.py` CANONICAL "transition_order 반환 직후 같은 트랜잭션에서만 쓴다")이므로 CANONICAL 로 등재한다.
  - `erp_orders_drawing.py`: 지금 VERSIONED_DIRECT(파일 단위). 전달 쓰기가 실제로 엔진 경유가 되므로 분류는 그대로 두고 **사유 문구를 사실대로 고친다**("전달·반영은 execute_order_mutation, 전달 취소는 직접 bump").
  - 예상 baseline `{total: 74, external: 28}` → `{total: 74, external: 24}`(자리 이동이라 total 유지). **구현 뒤 재생성 값이 정본**. 줄번호가 바뀌므로 `python tools/harness/refresh_inventories.py` 필수(`test_no_new_external_writers` 는 (path, lineno, kind) 집합이 정확히 같아야 통과).
- 부작용(409 증가 — 흐름 3곳): ① 저장 버튼(기존 덮어쓸지 묻기 창) ② 견적 미리보기 자동 저장(`static/js/orders/estimate-preview.js:733-741`, 타이머 — 입력 중 확인창이 갑자기 뜰 수 있다) ③ 알림톡 발송 전 저장(`static/js/orders/erp-alimtalk-send.js:82`). 덮어써도 ①이 도면 축을 지키므로 데이터는 안전하다. 409 확인창 문구(`erp-order-shared.js:2870-2881`)에 한 줄을 더한다: "(도면·퀘스트·고객확인 정보는 서버가 지키므로 덮어써도 바뀌지 않습니다)". 견적 자동 저장의 확인창 방식 자체는 비목표.
- ②를 되돌려도 ①만으로 결함은 닫힌다.

**옛 데이터·운영**: 측정 ①(C1·C2·C3, §5) — **지금 즉시**. 1차 배포(`287782ce3`) 뒤 폼 저장이 도면 축을 바꾼 흔적이 있으면 주문별로 이력의 마지막 도면 동작에서 도면 상태·현재본을 다시 세우는 일회성 보정(운영 쓰기 — 별도 승인). 2a-1① 이 운영에 오른 뒤 측정 ② 에서 다시 잰다. 런타임 재계산은 되살리지 않는다(1차 결정).

**테스트**
- 새 `tests/domains/test_structured_put_server_locked_keys.py`(2a-1①)
  - (a) 태블릿 경로: 전달 → 확정 → 스냅샷 GET → 수정요청 → 스냅샷 본문으로 **If-Match 없이** PUT → 200 이지만 `drawing_status == 'RETURNED'`, 현재본 불변.
  - (a') 최신 버전 경로: 같은 흐름에서 수정요청 **뒤** 버전을 다시 받아 **최신 If-Match + 옛 스냅샷 본문**으로 PUT → 200 이지만 도면 축 불변. (a)(a')는 ②가 있든 없든 ①만이 막는다.
  - (b) 반대 방향: 재전달(TRANSFERRED·[v2]) 뒤 오래된 폼 저장(If-Match 없이)이 RETURNED·[v1] 로 못 되돌림.
  - (c) `blueprint.customer_confirmed`·`blueprint.current`·`quests[].status` 되돌림 없음.
  - (f) 도면 담당 [d1]→[d2](담당 지정 API) 뒤 오래된 폼 PUT → [d2] 유지(리뷰 프로브를 옮김). `assignments` 의 다른 하위 키는 폼 값이 그대로 들어간다.
  - (e) 같은 PUT 이 붙이는 ERP_ORDER_CHANGED 는 남는다(`test_erp_orders_structured_put.py:940-980` 계열 유지).
  - (d) DB 에 없던 `drawing_status` 를 클라이언트가 새로 못 만든다 — **기존 동작 유지 확인**(지금도 `enforce_form_allowlist` 가 막는다. 결함 재현 테스트가 아니다).
  - 음성 대조: `lock_server_owned_keys` 호출을 빼면 (a)(a')(b)(c)(f) 빨강 — ② 커밋이 있든 없든 성립.
- 폼 JS 계약 테스트 뒤집기(위).
- ②(2a-1②): 도면 라우트 5곳 각각 뒤 `mutation_version` +1, 그 전 버전으로 PUT `If-Match` → 409.
- ② PG 레인 두 세션 동시성(`tests/postgres/test_drawing_route_row_lock_pg.py` 새 파일 — `tests/postgres/test_data_structured_pg.py` 방식): 연결 B 가 행을 FOR UPDATE 로 쥐고 도면 쓰기를 한 뒤 커밋 전 대기 → 스레드 A 의 도면 라우트 요청이 잠금에서 기다림 → B 커밋 → A 는 B 의 결과 위에서 판정·쓰기. 경우: 수정요청 대 반영 체크, 수정요청 대 수령 확정(최종 이력에 두 동작이 모두 있고 상태는 마지막 동작과 일치). 음성 대조: 첫 조회를 잠금 도우미 대신 일반 조회로 바꾸면 lost update 로 빨강.
- 기존 `test_erp_orders_structured_put.py:455-466`(키를 안 보낸 경우 보존)은 계속 초록.

**위험·되돌리기**: 폼이 정당하게 `quests`·`blueprint`·도면 배정을 새로 쓰는 길이 있으면 막힌다 — 검색상 폼 JS 는 스냅샷 복사만 하고, 주문 생성의 퀘스트(`foms/services/orders/order_create.py:125`)는 PUT 이 아니다. 구현 첫 단계에서 전체 레인으로 확인. 되돌리기는 ①·② 각각 revert.

---

### 4.2 C21 (+M3·M16·일반 상태 쓰기·제작 시작 a/b·화면·강제 변경 기록) (2a-2)

**문제** (코드 확인)
- 수정요청은 TRANSFERRED·CONFIRMED 양쪽에서 받고 단계는 그대로 둔다(`erp_orders_revision.py:98-101`, 2026-07-22 사용자 승인 "컨펌 후 수정요청 진입로"). 그래서 CONFIRM + RETURNED 는 정상 흐름에서 생긴다.
- CONFIRM → PRODUCTION 입구 어디도 도면 축을 안 본다.
  1. 고객컨펌 승인 `foms/api/quest.py:317` → `quest_transition_service.py:201-279`(유일 게이트 :261 퀘스트 완료) → CUSTOMER_CONFIRM(`order_transition_service.py:200-203`).
  2. 재전이(완료 퀘스트 + CONFIRM) `quest.py:416-446`.
  3. 제작 시작 CONFIRM 호환 (b) `production/orders.py:779-790`(보류·퀘스트만) → :838.
  4. 일반 상태 쓰기: 단건 `foms/api/orders/status.py:361`→:399, 일괄 :612→:648, 필드 `foms/api/orders/field_update.py:622`→:643. 막는 것은 `requires_privileged_override`(`foms/services/orders/stage_override.py:179-189` — 역행·건너뛰기)뿐이라 인접 전진은 통과. **도면 게이트뿐 아니라 퀘스트 게이트도 건너뛴다**(반박-C21 정정 3).
  5. 생산 단계에 들어간 뒤 (a) run 시작(`production/orders.py:770-778`)도 도면 축을 안 본다.
  6. 단계 강제 변경: `foms/services/orders/stage_override.py:73 OVERRIDE_ALLOWED_ROLES = {ADMIN, MANAGER}`, `apply_stage_override`(:299-392)는 `order.status`·`workflow.stage` 를 직접 쓰고 STAGE_OVERRIDE 이벤트만 남긴다 — 도면 검사 없음. MANAGER 도 CONFIRM→PRODUCTION 을 넘길 수 있다.
  7. 관리자 뚫기 전이: `PRODUCTION_UNCOMPLETE`(`production/orders.py:1238-1253`, INVALID_STAGE 뚫기 뒤 target PRODUCTION)·`CONSTRUCTION_REWORK` 는 `emergency_override` 면 인접성 검사를 건너뛴다(`order_transition_service.py:338`·:364-367) — ADMIN 이 CONFIRM 주문에 쓰면 도면 게이트 없이 PRODUCTION.
- **한글 단계값**: 라우트의 `current_stage_code` 는 `get_stage` 가 정규화 없이 돌려주는 `workflow.stage` 원문이다(`erp_policy_data_access.py:135-140`). 전이 서비스는 `STAGE_NAME_TO_CODE.get(stage, stage)` 로 정규화한 뒤 전이한다(`quest_transition_service.py:250-253`). 운영에 한글 단계값이 실제로 있다(`foms/services/common/dashboard_cache.py:125-131` 주석·매핑). 리뷰 프로브: `workflow.stage='고객컨펌'`·RETURNED 주문 승인 → 200·PRODUCTION. 제작 시작 (b)는 이미 두 값을 다 본다(`production/orders.py:779`).
- **동시성(TOCTOU)**: 승인 라우트는 잠금 없이 `sd = order.structured_data`(:350)를 읽어 판정하고, 전이 호출 전에 `order.structured_data = sd; flag_modified`(:572-573)로 객체를 dirty 로 만든다 → `execute_order_mutation` 이 expire 하지 않아(:224-236) FOR UPDATE 대기 뒤에도 옛 sd 를 되쓴다. 승인 도중 수정요청이 커밋되면 RETURNED 가 CONFIRMED 로 덮이고 생산으로 넘어간다. 제작 시작도 게이트(보류·퀘스트)를 잠금 전 sd 로 판정한다(`production/orders.py:742`·:760-800, 잠금은 :818).
- 화면 SSOT 도 같은 원인: `foms/services/erp_quest_display.py:321-366 _compute_can_assignee_approve`, `:381-423 build_current_quest_payload`(CTA 는 :402), `foms/services/orders/quest_approve_cta.py:61-120 build_approve_cta`, `quest_approve_authz.py:182-213 display_team_axes(approvable_teams·can_retransition)` 가 도면 축을 안 봐서 RETURNED 에서도 [고객 컨펌 완료]가 나온다. 소비 템플릿: `templates/orders/partials/dashboard_grid.html:110·150·177·201`, `templates/partials/shared/erp_mobile_queue_card_v2.html:248-257·306-329`, `templates/orders/partials/order_detail_mobile_v2.html:124-131·269-282·416-419`, `templates/orders/partials/tablet_dashboard_sheet.html:82·89`.
- 캐시: 수정요청 라우트는 대시보드 캐시를 전혀 무효화하지 않는다(`erp_orders_revision.py:38-194`, 배지만). 전달·수정요청 취소는 DRAWING·ORDERS 만 지운다(`erp_orders_drawing.py:317-323`, `erp_orders_revision.py:376-379`). CONFIRM 단계는 PRODUCTION family 이고(`dashboard_cache.py:117`) 패널 캐시 수명은 300초(:38-40).
- M3: 막는 목록 {RETURNED, TRANSFERRED} 으로 하면 PENDING·키 없는 CONFIRM 주문이 통과한다(로컬 dev DB 에 1건 관찰).
- M16: 고객컨펌 뒤 수정요청이 와도 `blueprint.customer_confirmed` 가 True 로 남는다(쓰는 곳 `quest.py:562-570` 뿐, 지우는 곳 없음). 읽는 곳은 감사·백필 도구(`audit_drawing_revisions.py:234-236`, `backfill_drawing_revisions.py:156-160`)뿐이라 지금 게이트 영향은 없다.
- 반박-C21: 이 경로(수정요청 **뒤** 승인)에서는 생산 보드 변경 배지가 안 뜨고, "[생산] 도면 변경" 벨은 CS·SALES 에게만 간다(`production_change.py:45`). 승인 **뒤** 수정요청이면 배지는 정상으로 뜬다(반박 대조 실험).

**목표 동작**
- CONFIRM → PRODUCTION(정식 경로)은 **도면이 수령 확정(CONFIRMED)일 때만**. RETURNED·TRANSFERRED·PENDING/없음은 409 `DRAWING_STATUS`. 단계값이 영문이든 한글이든 같다.
- 제작 대기(PRODUCTION · 진행 중 run 없음)에서 RETURNED·TRANSFERRED 면 [제작 시작]도 409 `DRAWING_STATUS`(Q2 추천안). 이미 만드는 중이면 막지 않는다.
- 일반 상태 쓰기(단건·일괄·필드)는 ERP 주문의 DRAWING→CONFIRM, CONFIRM→PRODUCTION 인접 전진을 하지 않는다 → 409 `COMMAND_REQUIRED`(일괄은 차단 목록)(Q1 추천안).
- 관리자(ADMIN)는 **화면에서** 사유를 적고 뚫을 수 있다(고객컨펌 승인·제작 시작). 뚫은 기록과 그 순간의 도면 상태가 타임라인에 남는다.
- 단계 강제 변경(ADMIN·MANAGER + 사유 + 확인)은 따로 남는 탈출구. 도면 미확정이면 경고를 보이고 도면 상태를 기록한다(Q5 추천안).
- 판정은 **행 잠금 아래**에서 한다.
- 화면은 서버와 같은 답: 막히면 비관리자에게는 버튼 대신 이유 한 줄, 관리자에게는 이유 + 경고 모양 버튼.
- 수정요청이 오면 고객확인 표시를 무효로 하고, 그 수정요청을 취소하면 되살린다(M16).

**설계**

4.2.1 판정 모듈(새 파일, 순수 함수) `foms/services/orders/confirm_drawing_gate.py` (약 120줄)
- `effective_drawing_status(sd) -> str`: 최상위 `drawing_status`(대문자·빈 문자열은 없음 취급) 우선, 없으면 중첩 `drawing.status`, 둘 다 없으면 `'NONE'`.
  - 최상위 우선인 근거(코드 확인): 지금 도면 상태를 **쓰는** 곳은 모두 최상위만 쓴다(수령 확정 `erp_orders_draftsman.py:397`, 수정요청 `erp_orders_revision.py:98-101`, 전달 `erp_orders_drawing.py:254`). `foms/` 안에 중첩 `drawing.status` 를 쓰는 코드는 없다(검색 확인) — 중첩은 옛 데이터일 뿐이다.
  - 반대로 **읽는** 곳 일부는 중첩을 먼저 본다: 전달 라우트(`erp_orders_drawing.py:116`), 작업실 목록·상세(`foms/web/drawing/workbench.py:608`·:946), 도면팀 알림 게이트(`foms/services/notifications/drawing_order_change.py:105-109`). 중첩이 낡은 옛 주문이면 게이트와 서로 다른 값을 본다.
  - 그래서 2a-2 에서 **전달 라우트(:116)와 작업실(:608·:946)도 이 함수를 부르게 한다**(한 함수가 답한다). 알림 게이트(:105)는 동작 차이가 알림 여부뿐이라 같은 커밋에서 함께 바꾼다. SQL 쪽 `drawing_workbench_read_model._drawing_status_exprs` 는 인덱스 때문에 두 키를 따로 비교하므로 두고, 측정 I1 로 영향 범위를 본다.
  - I1 이 0 이 아니면 2a-2 운영 반영 **전에** 중첩 값을 최상위와 맞추는 일회성 보정(운영 쓰기, 별도 승인)을 한다.
- `confirm_exit_block(sd) -> GateBlock | None` — **허용 목록(M3)**: CONFIRMED 만 None. 영업용 사유 문구:
  - RETURNED: "도면 수정 요청이 진행 중입니다. 수정본을 받아 수령 확정한 뒤 고객 컨펌을 완료하세요."
  - TRANSFERRED: "새로 전달된 도면을 아직 수령 확정하지 않았습니다. 도면을 확인하고 수령 확정부터 해 주세요."
  - 그 밖(PENDING·NONE 등): "도면 수령 확정 기록이 없습니다. 도면 전달과 수령 확정을 먼저 해 주세요."
- `revision_in_flight_block(sd) -> GateBlock | None` — 막는 목록: RETURNED·TRANSFERRED 만 막는다. 생산 단계 run 시작 전용(이미 CONFIRM 을 지난 주문이라 옛 데이터 잠김을 피한다).
- `production_block_reason(block, sales_names) -> str` — **생산팀용 문구**(생산 라우트 (a)(b) 둘 다 이것을 쓴다):
  - RETURNED: "도면을 고치는 중이라 아직 제작을 시작할 수 없어요. 영업 담당({이름})이 새 도면을 수령 확정하면 시작할 수 있어요."
  - TRANSFERRED: "새 도면이 도착했지만 영업 담당({이름})이 아직 수령 확정하지 않았어요. 확정되면 시작할 수 있어요."
  - 그 밖((b) 에서만): "도면 수령 확정 기록이 없어 제작을 시작할 수 없어요. 영업 담당({이름})에게 도면 확정을 요청해 주세요."
  - 이름은 `get_assignee_ids(order, 'SALES_DOMAIN')` → 사용자 이름(막힐 때만 쿼리 1회). 없으면 "영업 담당".
- `GateBlock` = NamedTuple(`code='DRAWING_STATUS'`, `reason`, `drawing_status`).
- `DRAWING_STATUS`·`COMMAND_REQUIRED` 코드는 새로 만들지 않는다: `foms/services/orders/admin_override.py:51 GATE_DRAWING_STATUS`·`GATE_COMMAND_REQUIRED`, 화면 재시도 목록 `static/js/foms/foms-admin-override.js:28-38`, 타임라인 한글 `foms/services/order_event_display.py:47-48`.

4.2.2 고객컨펌 승인(PC·모바일 공용) `quest.py`
- **잠금**: 첫 조회(:321 `db.query(Order).filter(...).first()`)를 `lock_order_row(db, order_id)`(§4.1 ②)로 바꾼다. 이후 판정·승인 기록·전이가 모두 같은 잠금 아래다.
- **정규화**: `current_stage_norm = STAGE_NAME_TO_CODE.get(current_stage_code, current_stage_code)` 를 한 번 구해 새 게이트와 blueprint 기록 조건(:563 `current_stage_code == 'CONFIRM'` — 같은 원문 비교 결함)에 쓴다.
- 위치: 단계·admin_override 판정 뒤, 지금의 COMMAND_REQUIRED 게이트(:356-368) 바로 아래, 퀘스트 조회 전. 그래서 **일반 승인과 재전이를 한 곳에서** 막는다.
- `if current_stage_norm == 'CONFIRM' and (block := confirm_exit_block(sd)):` → admin_override 없으면 409 `{success: false, code: 'DRAWING_STATUS', message: block.reason}`; 있으면 `punched.append('DRAWING_STATUS')`. 뒤쪽 기존 `record_admin_override_event(..., axis='QUEST')`(:439 · :604)가 기록한다.
- 승인 기록·blueprint 기록(:562-570) 전에 막으므로 롤백할 것이 없다.
- **뒤를 받치는 방어선(전이 엔진)**: `order_transition_service.transition_order` 에 키워드 `drawing_gate_waived: bool = False` 를 더하고, `_mutate`(잠금 아래, `actual_from` 재확인 직후)에서 `command_id in {"CUSTOMER_CONFIRM", "PRODUCTION_START"}` 이고 waived 가 아니면 `confirm_exit_block(order.structured_data)` 를 다시 본다. 막히면 새 예외 `DrawingGateBlockedError(TransitionError)`(`error_code='DRAWING_STATUS'`, `status_code=409`, 메시지 = 사유)를 던진다. 두 라우트의 기존 `_transition_error_response`(`quest.py:300-311`, `production/orders.py:434`)가 `error_code`·`status_code` 를 그대로 읽으므로 매핑 추가 없음. `advance_stage_on_quest_completion` 은 같은 키워드를 통과시키기만 한다. 라우트는 관리자가 `DRAWING_STATUS` 를 실제로 뚫었을 때만 True 를 넘긴다(override 객체는 넘기지 않는다 — 지금 설계 "그 계층에는 override 를 넘기지 않는다" 유지). 엔진은 473줄 → 약 488줄(래칫 500, 목록 밖 — 판정 본문은 게이트 모듈에 둔다).

4.2.3 제작 시작 `production/orders.py:721`
- **잠금**: 첫 조회(:742 `db.get`)를 `lock_order_row` 로 바꾼다(보류·퀘스트·도면 게이트가 모두 잠금 아래 sd 로 판정).
- (b) CONFIRM 호환(:779-790): 기존 퀘스트 게이트 줄 뒤에 `_punch_or_return(_drawing_block_response(order, sd, confirm_exit_block), "DRAWING_STATUS", override, punched)`. 관리자가 INVALID_STAGE 를 뚫는 분기(:791-800)에도 같은 줄. 전이 호출(:838)에 `drawing_gate_waived=('DRAWING_STATUS' in punched)`.
- (a) run 시작(:770-778, Q2): 보류 게이트 뒤에 `_punch_or_return(_drawing_block_response(order, sd, revision_in_flight_block), "DRAWING_STATUS", override, punched)`.
- `_drawing_block_response(order, sd, pred)`: 막히면 `(jsonify({success: False, code: 'DRAWING_STATUS', message: production_block_reason(...)}), 409)`, 아니면 None. `_hold_block_response`(:369)와 같은 모양, 같은 파일(known large).
- 제작 완료(:867)는 막지 않는다(이미 만드는 중 — 알림형 설계 유지).

4.2.4 일반 상태 쓰기 3경로 (Q1)
- `stage_override.py` 에 `requires_dedicated_command(from_stage, to_stage) -> bool`: **정규화 후**(한글 단계값 포함) (DRAWING→CONFIRM) 또는 (CONFIRM→PRODUCTION) 이면 True. 문구 상수 `DEDICATED_COMMAND_MESSAGE = "이 단계 이동은 전용 버튼(도면 수령 확정 / 고객 컨펌 완료)으로만 합니다. 관리자는 주문 상세의 그 버튼에서 사유를 적고 진행할 수 있습니다."`. 414줄 → 약 430줄.
- 단건 `status.py:361`: `requires_privileged_override` 검사 뒤 같은 모양으로 — ERP 주문이고 True 면 override 없을 때 409 `{code: 'COMMAND_REQUIRED', message}`, override 면 `punched.append('COMMAND_REQUIRED')`(이 파일은 끝에 `if override is not None and punched: record_admin_override_event(...)` 공통 흐름이 있다 — :412-414).
- 필드 `field_update.py:622`: 이 파일에는 끝의 공통 기록 흐름이 **없다**(기록은 OVERRIDE_BLOCK 분기 안 :622-633 과 :564 두 곳뿐). 그래서 새 분기 안에서 **바로** `record_admin_override_event(db, order, override=override, gates=list(punched), route="orders.update_order_field", axis="MAIN", from_value=..., to_value=value)` 를 부른다(OVERRIDE_BLOCK 분기와 같은 모양). 역행·건너뛰기(OVERRIDE_BLOCK)와 인접 전진(COMMAND_REQUIRED)은 서로 겹치지 않으므로 이중 기록 없음.
- 일괄 `status.py:612`: `blocked_command_required` 목록에 넣고 continue. **성공 판정(:680)과 메시지에 새 목록을 넣는다**: `success = updated > 0 or not (blocked_override_required or blocked_as_orders or blocked_command_required)`, 전부 막히면 `success=False` + 메시지 "{N}건은 전용 버튼으로만 넘길 수 있어 바꾸지 않았습니다." 응답에 `blocked_command_required: [id…]`.
- 화면: 일괄 바 소비자 `static/js/orders/dashboard/erp-dashboard-detail-dom.js:1063-1074` 에 새 목록 알림 한 줄(성공 때만 새로고침하는 지금 흐름 그대로라, 전부 막히면 새로고침하지 않고 메시지를 띄운다). 필드 인라인 편집(:1152-1168)은 실패 메시지를 이미 띄운다. **일괄·인라인에는 관리자 재시도를 붙이지 않는다** — 관리자 출구는 전용 버튼(4.2.5)이다. API 는 다른 게이트와 같게 `admin_override` 를 받는다(API 직접 호출 호환).
- 핀: `static/js/orders/erp-dashboard-entry.js:13` 의 detail-dom `?v=` 와 entry 자체 핀(`templates/partials/shared/layout_scripts.html:1634`).
- 관리자가 일반 쓰기를 뚫으면 도면·퀘스트 게이트를 따로 보지 않는다. 대신 **모든 ADMIN_OVERRIDE 이벤트 payload 에 그 순간의 `drawing_status`(effective) 스냅샷을 남긴다** — `record_admin_override_event`(`admin_override.py:200-240`)의 payload 에 한 줄(326줄 → 약 330줄). 그래서 게이트 코드가 COMMAND_REQUIRED 뿐이어도 "도면이 수정 중이었다"가 기록된다.
- Q1 에서 "막지 말라"면 대안: 같은 자리에 `confirm_exit_block` + CONFIRM 퀘스트 완료 검사를 건다(도면만 덧대는 부분 땜질임을 DECISIONS 에 기록).
- 타임라인 라벨: `order_event_display.py:47` `'COMMAND_REQUIRED': '도면 전용 경로'` → **'전용 버튼 경로'**(고객컨펌 뚫기가 도면 뚫기로 보이지 않게). 이 문자열을 단언하는 테스트는 없다(검색 확인).

4.2.5 화면(PC 그리드 · 모바일 큐 카드 · 모바일 상세 · 태블릿 시트 · PC 생산 보드)
- `build_approve_cta(stage_code, order, *, sd=None)`: stage CONFIRM(정규화)이고 `sd` 가 있고 `confirm_exit_block(sd)` 면 `approve_blocked=True`, `approve_blocked_reason=<사유>` 를 더한다(다른 키 그대로). **`sd=None` 이면 막지 않는다**(`measurement/drawing_transfer_cta.py:141` 은 확인 문구만 쓰려고 sd 없이 부른다). 120줄 파일.
- `build_current_quest_payload`: :402 를 `build_approve_cta(stage_code_key, order, sd=sd)` 로. 막혔을 때 규칙(한 줄 도우미 `_blocked_for(user, cta)` — 비관리자면 True):
  - `can_assignee_approve = can_assignee_approve and not _blocked_for(user, cta)` — **ADMIN 은 버튼을 유지**한다.
  - `display_team_axes`(`quest_approve_authz.py:182-213`)의 `approvable_teams`·`can_retransition` 도 같은 규칙(비관리자면 비움/거짓).
  - `erp_quest_display.py` **494줄 → 약 497줄(래칫 500, 목록 밖)** — 넘치면 규칙을 `quest_approve_cta.py` 로 옮긴다.
- 템플릿 4곳(PC 그리드 :201 팀 버튼 포함 · 큐 카드 :257 · 모바일 상세 :277 · 태블릿 시트 :89): `approve_blocked` 면
  - 비관리자: 버튼 자리에 `approve_blocked_reason` 한 줄(기존 CSS 클래스 — 인라인 스타일 금지, 필요하면 `static/css/foundation/erp-pro.css`).
  - 관리자: 이유 한 줄 + **경고 모양 버튼**(erp-pro.css 의 기존 경고 버튼 클래스). 누르면 보통 요청 → 409 `DRAWING_STATUS` → 이미 연결된 `FomsAdminOverride.retry`(`static/js/foms/erp-quest-approve.js:184`, `erp-order-shared.js:6162`, `static/js/orders/dashboard/erp-dashboard-quest.js:26`)가 사유 시트를 열어 1회 재시도.
  - 각 화면에 `foms-admin-override.js`·사유 시트(`partials/shared/foms_reason_sheet.html`)가 실려 있는지 구현 때 확인(대시보드·주문 폼·모바일 상세는 실려 있다 — `templates/orders/dashboard.html:25`, `erp_order_js.html:39`, `order_detail_mobile_v2.html:439`).
- **PC 생산 보드**: `templates/production/partials/scripts.html:253-266 submitProductionTransition` 은 HOLD_ACTIVE 만 재시도하고 나머지는 `alert('오류: …')` 다. 여기에 `FomsAdminOverride.retry` 를 연결하고(태블릿 칸반 `static/js/foms/tablet-production-kanban.js:116` 과 같은 모양), 이 partial 에 사유 시트 include 와 `foms-admin-override.js`(핀 `20260921a` 그대로)를 싣는다. 비관리자는 생산팀용 문구가 알림으로 보인다.
- quest 패널을 쓰는 나머지 화면(`templates/orders/object.html:304`, `templates/production/partials/scripts.html:346`, `erp-order-shared.js:6150`)은 409 메시지가 그대로 보이는지만 확인한다(구조 변경 없음).
- **캐시 무효화(화면과 서버가 같은 답)** — ②의 cache intent 에 기대지 않고(②는 따로 되돌릴 수 있다) 라우트에서 직접:
  - 수정요청·수정요청 취소·단계 유지 수령 확정: `invalidate_order_dashboard_families(order, extra=(DASHBOARD_FAMILY_PRODUCTION, DASHBOARD_FAMILY_CONSTRUCTION))`.
  - 전달·전달 취소(첨부 행과 개수가 바뀐다): `invalidate_dashboard_families(*ATTACHMENT_DASHBOARD_FAMILIES)`(`dashboard_cache.py:99`). 생산·시공 첨부 개수 캐시는 key 가 주문 id 목록이고 수명 120초라(`foms/web/production/dashboard.py:195-214`, `foms/web/construction/dashboard.py:180-201`) family 무효화가 필요하다(R3 "확인 필요"를 여기서 닫는다).
- 서버와 화면이 **같은 판정 함수 하나**를 부르므로 갈라지지 않는다.

4.2.6 M3 옛 데이터 잠김 대응
- 허용 목록이면 CONFIRM 인데 도면 기록이 없는 주문은 승인이 막힌다. 출구: 도면 전달 → 수령 확정 → 승인, 또는 관리자 뚫기(기록 남음).
- 운영 반영 전에 측정 A1. 0 이 아니면 목록을 사용자에게 보이고 (가) 관리자 뚫기로 하나씩 처리 (나) 일회성 보정 중 고른다. **보정은 이력으로 근거가 있는 경우만**: 중첩 `drawing.status='CONFIRMED'` 이거나 이력에 CONFIRM_RECEIPT 가 있는데 최상위 값만 빠진 주문. 근거가 없는 주문에 CONFIRMED 를 써 넣으면 없던 수령 확정을 만드는 것이라 하지 않는다 — 그런 주문은 관리자 뚫기로만(운영 쓰기, 별도 승인).

4.2.7 M16 고객확인 무효화 `erp_orders_revision.py`
- 수정요청(:101 뒤): `blueprint.customer_confirmed` 가 True 면 False 로 바꾸고 `invalidated_at`(UTC `now_utc_naive` 문자열)·`invalidated_by_request_at`(이번 요청 `at`)을 남긴다. `confirmed_at`·`confirmed_by` 는 이력으로 그대로 둔다. 이번 REQUEST_REVISION 항목에 `customer_confirmation_invalidated: true`.
- 수정요청 취소(§4.4): 취소한 요청에 그 표시가 있고 남은 열린 요청이 없으면 `customer_confirmed=True` 로 되돌리고 `invalidated_*` 를 지운다.
- 단계와 관계없이(생산 단계 수정요청 포함) 같은 규칙. 막는 데 쓰는 곳은 없다(게이트는 `drawing_status`). 감사·백필 도구가 사실대로 읽게 하는 것이 목적.
- 1차 알림톡 문구는 건드리지 않는다.

4.2.8 단계 강제 변경 기록·경고 (Q5)
- `apply_stage_override`(`stage_override.py:299-392`)의 STAGE_OVERRIDE payload 에 `drawing_status`(effective) 스냅샷을 항상 남긴다(한 줄).
- 강제 변경 창(`static/js/orders/erp-stage-override.js`)은 목표가 PRODUCTION 이후이고 도면이 CONFIRMED 가 아니면 확인 문구에 "도면이 아직 확정되지 않았어요(지금 상태: 수정 중/수령 전/기록 없음). 옛 도면으로 생산될 수 있어요." 한 줄을 더한다. 도면 상태는 창을 여는 화면이 이미 가진 주문 값을 `data-drawing-status` 로 넘긴다(창 템플릿 위치는 구현 때 확인).
- Q5 답이 "팀장은 막는다"면: `apply_stage_override` 에서 MANAGER 이고 CONFIRM 이하 → PRODUCTION 이후 이동이며 도면이 CONFIRMED 가 아니면 `ValueError("도면이 확정되지 않은 주문은 관리자만 생산 이후로 강제 변경할 수 있습니다.")`(기존 400 매핑).

**에러 코드·권한 요약**

| 입구 | 막히는 조건 | 응답 | 관리자(ADMIN) 출구 |
|---|---|---|---|
| `POST /api/orders/<id>/quest/approve` (CONFIRM, 영문·한글 단계) | CONFIRMED 아님 | 409 `DRAWING_STATUS`(영업 문구) | 화면: 경고 버튼 → 사유 시트 → 통과, 이벤트 axis=QUEST(+drawing_status 스냅샷) |
| `POST /api/orders/<id>/production/start` (b) | CONFIRMED 아님 | 409 `DRAWING_STATUS`(생산 문구) | 화면: PC 생산 보드·태블릿 칸반 사유 시트 → 통과, axis=MAIN |
| `POST /api/orders/<id>/production/start` (a) | RETURNED·TRANSFERRED | 409 `DRAWING_STATUS`(생산 문구) | 같음 |
| `/api/update_order_status` · `/api/update_order_field`(status) | DRAWING→CONFIRM · CONFIRM→PRODUCTION | 409 `COMMAND_REQUIRED` | 화면 재시도 없음 — 전용 버튼에서 뚫는다(API 는 admin_override 수용·기록) |
| `/api/bulk_update_order_status` | 같음 | `blocked_command_required`, 전부 막히면 `success: false` | 같음 |
| 전이 엔진 CUSTOMER_CONFIRM·PRODUCTION_START | CONFIRMED 아님(잠금 아래 재확인) | `DrawingGateBlockedError` → 409 `DRAWING_STATUS` | 라우트가 뚫었을 때만 waived |
| 관리자 뚫기 전이 PRODUCTION_UNCOMPLETE·CONSTRUCTION_REWORK(CONFIRM 주문) | 게이트 없음(허용 목록) | — | ADMIN_OVERRIDE 이벤트에 drawing_status 스냅샷 자동 기록 |
| 단계 강제 변경 | 그대로(ADMIN·MANAGER + 사유 + 확인) + 경고·스냅샷(Q5) | — | — |
| MANAGER `emergency_override`(권한 축) | 이 게이트들을 풀지 않는다 | — | — |

**옛 데이터·운영**: A1(허용 목록에 걸릴 주문 — 한글 단계 따로), A2(생산 대기 중 수정 중인 주문), B1(최근 90일 이동 경로), D1(남은 고객확인), I1(중첩 상태 불일치), K1(과거 C21 발생) — §5 측정 ②. 이미 잘못 넘어간 주문이 있으면 관리자가 단계 강제 변경 PRODUCTION→CONFIRM(완료 퀘스트 재오픈 `stage_override.py:250-296`) — **단 A2 처럼 진행 중 run 이 없는 주문만** 권한다(진행 중 run 이 있으면 생산팀과 먼저 확인). blueprint 는 M16 규칙으로 보정 가능 — 운영 쓰기 별도 승인. 2a-2 반영 뒤 측정 ④(L1)로 뚫기·강제 변경 빈도를 본다.

**테스트**
- `test_bugrepro_c21_confirm_quest_while_returned.py`: `_C21_PENDING`(:39-42)을 모두 뗀다. 본 주장·재전이·제작 시작(b)·CTA 4건은 게이트로, 일반 쓰기 3건(상태 불변식만 단언, :277-297)은 Q1 막음으로 초록. 대조군(:199-209)은 계속 초록.
- 새 경우(새 파일 `tests/domains/test_confirm_drawing_gate.py`, 500줄 이하 — 넘치면 둘로): TRANSFERRED@CONFIRM 409 · PENDING/키 없음@CONFIRM 409(M3) · **`workflow.stage='고객컨펌'`·RETURNED 승인 409**(리뷰 프로브를 옮김) · 중첩 `drawing.status=CONFIRMED` 만 있는 옛 주문은 통과 · 최상위 CONFIRMED + 중첩 TRANSFERRED 인 주문에서 전달 라우트·작업실·게이트가 같은 값을 본다 · 관리자 뚫기 200 + ADMIN_OVERRIDE 이벤트 gates 에 `DRAWING_STATUS`·payload 에 `drawing_status` · MANAGER `emergency_override` 로는 409 · run(a) RETURNED 409(생산 문구·영업 담당 이름) / CONFIRMED 200 · 제작 완료는 RETURNED 여도 그대로 · 엔진 방어선: 라우트 게이트를 우회해 `advance_stage_on_quest_completion` 을 직접 부르면 `DrawingGateBlockedError` · M1 결합(오래된 폼 PUT 뒤 승인 409) · M4 결합(프로브 P4) · M16 무효화와 취소 복원.
- 일반 쓰기: 단건·필드·일괄 **세 경로 모두** 관리자 뚫기 200 + ADMIN_OVERRIDE 이벤트 gates 에 `COMMAND_REQUIRED` · 일괄에서 전부 막히면 `success: false`·`updated: 0` · 일부만 막히면 `success: true` + `blocked_command_required`.
- **PG 레인 동시성**(`tests/postgres/test_confirm_gate_concurrency_pg.py`): ① 수정요청 대 승인 — 연결 B 가 행을 잠그고 RETURNED + REQUEST_REVISION 을 쓴 뒤 커밋 전 대기 → 스레드 A 승인 요청이 잠금에서 기다림 → B 커밋 → A 는 409 `DRAWING_STATUS`, 최종 CONFIRM·RETURNED. ② 수정요청 대 제작 시작(a) — 같은 방식, A 409. 음성 대조: 라우트 첫 조회를 잠금 없는 조회로 되돌리면 ①이 200·PRODUCTION(RETURNED 덮임)으로 빨강.
- **입구 전수 가드**(`test_confirm_drawing_gate.py`): `order_transition_service.COMMAND_REGISTRY` 에서 **to_values 에 PRODUCTION 이 있는 전 command** 를 모아 고정 표와 같은지 단언 — `{CUSTOMER_CONFIRM: 게이트, PRODUCTION_START: 게이트, SET_MAIN_STAGE: 라우트 COMMAND_REQUIRED(인접)·OVERRIDE_BLOCK(비인접), PRODUCTION_UNCOMPLETE: 관리자 뚫기 허용 목록, CONSTRUCTION_REWORK: 관리자 뚫기 허용 목록}`(지금 등록 목록과 같음 — 실행 확인). 그리고 state_writer 인벤토리(`docs/harness/foms_state_writer_inventory.json`)의 MAIN 축 raw 쓰기 **파일 집합**을 고정한다 — 새 raw 단계 쓰기 파일이 생기면 빨개져 게이트를 달게 한다.
- 화면 계약(실제 렌더): `approve_blocked` 면 비관리자는 `can_assignee_approve`·`can_retransition` 거짓·`approvable_teams` 빈 목록 + 이유 줄 / **관리자는 버튼(경고 클래스) + 이유 줄** · `sd=None` 이면 막지 않음 · 4 템플릿 렌더 · PC 생산 보드 스크립트에 `FomsAdminOverride.retry` 문자열 계약.
- 캐시: 수정요청 직후 PRODUCTION family 캐시 키가 비워진다(무효화 호출 단언).
- **기존 시드 갱신**: 허용 목록과 엔진 방어선 때문에 `drawing_status` 없이 CONFIRM 을 시드해 승인·제작·상태 경로를 부르는 테스트가 깨진다. 공용 주문 시드 헬퍼는 **없다**(파일마다 `_make_order`, 공용은 `tests/support/quest_seed.py` 뿐). → `tests/support/confirm_seed.py` 를 새로 두고(`confirmed_drawing_sd(**overrides)` — `drawing_status='CONFIRMED'`·최소 전달/확정 이력) 아래 파일을 **파일별로** 고친다:
  - 1순위(모두 `drawing_status` 0회): test_auth_quest_approve · test_confirm_to_production_flow · test_production_start_requires_confirm_quest · test_quest_retransition_deadend · test_stage_override_reopens_quest · test_confirm_to_production_board · test_confirm_to_production_display · test_erp_quest_display · test_quest_surfaces_retransition_and_team_buttons · **test_production_transition_guard_api · test_state_prod · test_state_prod_actions · test_state_quest · test_confirm_to_production_predicate · test_auth_enforcement · test_measure_approval_teams**.
  - PG 레인: **`tests/postgres/test_state_prod_pg.py`**, `tests/postgres/test_order_transition_service.py`(엔진 방어선).
  - 일반 쓰기 성공을 단언할 수 있는 test_admin_override_status_routes · test_logistics_dashboard_status · test_state_legacy · test_workflow_stage_override 도 확인.
  - 나머지(`'CONFIRM'` 을 쓰고 `drawing_status` 가 없는 `tests/domains` 파일 약 35개)는 전체 레인 결과로 찾아 같은 헬퍼로 고친다.

**위험·되돌리기**
- 현장에서 경미한 수정이 남은 채 구두 컨펌하던 흐름이 막힌다 → 관리자 뚫기 또는 팀장 강제 변경(Q5)으로 흡수. 업무 관행은 확인 필요.
- 일반 상태 바로 CONFIRM→PRODUCTION 을 하던 사람이 막힌다 → B1 로 규모 확인, 문구로 전용 버튼 안내.
- 되돌리기: 게이트·화면 커밋 revert(데이터 쓰기 없음). 엔진 방어선은 별도 커밋으로 두어 따로 되돌릴 수 있게 한다.

---

### 4.3 M5 — 수정요청 files 무검증 + 공통 "지워도 되는 키" + 첨부 삭제·복구 (2b)

**문제** (코드 확인)
- `request-revision` 이 클라이언트 files 를 그대로 저장한다(`erp_orders_revision.py:51`, :110). key·filename·view_url·download_url 모두 검증 없음. files 키가 없거나 list 가 아니면 지금은 `[]` 로 처리한다(:51).
- 수정요청 취소 `_delete_revision_reference_files`(:214-254)가 그 key 를 경로 검사 없이 **커밋 전에**(:330, 커밋 :370) R2 에서 지운다. 프로브 P2(남의 주문 `orders/2/drawing_wizard/exports/b1.png` 삭제)·P2b(자기 현재 도면 v1 과 첨부 행 삭제) 지금 빨강. 필요한 권한은 `erp_edit` + 그 주문 영업 권한뿐(화면에서는 안 닿고 API 로만).
- 1차 뒤 남은 삭제 길: ① 수정요청 취소(동기, 위) ② 전달 취소 outbox(`erp_orders_drawing.py:493-510`, :595-603) ③ 첨부 삭제 유예 purge(`foms/api/files/order_routes.py:595-` → `_enqueue_attachment_purge` :179-209) ④ 공용 outbox 핸들러(`foms/services/storage_delete_handler.py:60-81`, 참조 확인 없음).
- 링크 주입·저장 URL 신뢰(모든 호출 경로):
  - PC 작업실 타임라인 `img src`·`a href`(`templates/drawing/partials/workbench_detail_body.html:36-37`, :53, :62 — 저장값 우선).
  - ERP 창구 이력 JS 저장값 우선(`static/js/orders/dashboard/erp-dashboard-gateway.js:36-40`).
  - **모바일 도면 방 현재 도면 목록·뷰어·다운로드**: `foms/web/drawing/workbench.py:297-340 _build_handoff_files` 가 `drawing_current_files` 의 저장 `view_url`·`download_url` 을 먼저 쓴다(:322-323) → `templates/drawing/partials/workbench_mobile_handoff.html:124` `href="{{ selected.download_url }}"`, :74·:137 `img src`. (1차 W2 가 key 로 URL 을 다시 만드는 것은 **수정요청 참고사진**뿐이다 — `workbench.py:369-410`.)
  - 시공 카드 썸네일: `foms/services/construction_dashboard_display.py:103-112 _url_from_file_entry` 저장 view_url 우선.
  - `a href="javascript:…"` 는 Jinja 이스케이프로 막히지 않아 클릭하면 스크립트가 돈다(코드 확인, 실행 안 함). 2a-1① 전까지는 폼 PUT 이 `drawing_current_files` 에 임의 URL 을 넣을 수 있었고(M1 과 같은 구멍), 이미 들어간 값은 남는다.
- 창구 업로드 완료 `drawing-gateway/complete` 의 key 검사가 부분 문자열이다(`erp_orders_drawing.py:757-759` `expected not in key`).
- 복구 API 는 삭제 예약 행이 없으면 거절한다: `order_routes.py:681-691` `if not purge_rows or any(row.status != 'PENDING' …)` → 409 "유예 기간이 지나 스토리지 파일이 이미 삭제되었습니다". 예약 조회는 dedupe_key 정확 일치(:212-229). 끝난(DONE) outbox 행은 30일 뒤 지워지므로(`foms/services/sidefx_outbox.py:33 DONE_RETENTION`) "예약 행 없음"만으로는 "파일 보존"과 "이미 삭제 후 정리됨"을 가를 수 없다.

**목표 동작**
- 수정요청 files 에는 **이 주문의 `drawing_gateway/` 정본 경로 key** 만 저장된다. 그 밖은 400. files 가 없거나 null 이면 지금처럼 `[]`.
- 저장되는 URL 은 서버가 key 로 만든 값뿐이고, **화면은 어디서도 저장된 URL 을 믿지 않고 key 로 다시 만든다**.
- 파일을 지우는 모든 길은 공통 판정을 거친다: **자기 주문 폴더이고, 지금 어떤 도면 기록·살아 있는 첨부 행도 쓰지 않는 key 만** 지운다.
- 휴지통으로 보냈지만 파일을 남긴 행은 복구 API 로 되살아난다.

**설계**

4.3.1 참고 파일 검증(새 파일) `foms/services/orders/drawing_revision_files.py` (약 70줄)
- `is_revision_reference_key(order_id, key) -> bool`: `key == key.strip()`, `key.startswith(f"orders/{order_id}/drawing_gateway/")`, `validate_upload_key(key, order_id)[0]`(`foms/services/files/upload_authz.py:127-162` — 정규화·안전 문자·주문 일치·폴더 화이트리스트, `drawing_gateway` 는 목록에 있다). 1차 W2 의 `workbench._revision_reference_files`(:369-410) 판정을 여기로 옮기고 workbench 는 이 함수를 부른다(한 함수가 답한다).
- `normalize_revision_files(order_id, files) -> tuple[list[dict], list[str]]`: 통과 항목을 `{key, filename(앞뒤 공백 제거·255자·없으면 key 끝), file_type(확장자로 서버 판정), view_url: build_file_view_url(key), download_url: build_file_download_url(key)}` 로 만든다. 거절 이유 목록을 돌려준다.
- 서버가 만드는 key 는 `secure_filename` + 시각 + uuid 라 늘 안전 문자다(`foms/services/storage.py:305-310`, :415-419, :458-461) → 정상 화면 업로드는 걸리지 않는다.

4.3.2 `request-revision` 입력 계약(:51)
- 본문은 `request.get_json(silent=True) or {}` 로 읽는다.
- **files 키가 없거나 null 이면 `[]`**(태블릿 도면 검토 화면 `static/js/foms/tablet-drawing-review.js:413-416` 은 `{note, target_drawing_keys}` 만 보낸다 — 지금처럼 200). 키가 **있는데** list 가 아니거나 항목 하나라도 거절되면 400 `{success: false, code: 'INVALID_REVISION_FILE', message: '참고 파일 경로가 올바르지 않습니다. 파일을 다시 올려 주세요.'}`. 조용히 버리지 않는다(보안 입력은 명시 거절).
- 개수 상한 20(같은 코드 400) — 화면 업로드 상한과 맞출 값은 확인 필요.
- 저장은 normalize 결과만(:110), `files_count` 도 그 길이. 권한 변화 없음.

4.3.3 창구 업로드 완료(:748-787): key 검사를 `is_revision_reference_key` 로 바꾼다. 응답 모양 그대로. 이 함수의 마지막 catch(:786)에 로거를 단다(§4.6).

4.3.4 화면이 저장 URL 을 믿지 않기
- PC 매크로 `render_gateway_file_gallery`(workbench_detail_body.html:30-71): key 가 있으면 `/api/files/view/<key>`·`/api/files/download/<key>` 만 쓰고, key 가 없으면 링크를 그리지 않는다(저장 URL 폴백 제거). 수정요청 항목은 `is_revision_reference_key` 를 통과한 것만 링크, 나머지는 개수만(모바일 W2 와 같은 규칙) — 라우트(workbench.py, known large)가 미리 계산해 넘긴다.
- PC 현재 도면 갤러리(:1649, :1739)도 같은 규칙.
- **모바일 `_build_handoff_files`(workbench.py:297-340)**: `view_url`·`download_url` 을 key 로만 조립한다(:322-323 의 `file_map.get(...) or` 제거). key 가 자기 주문 경로가 아니면 URL 을 비운다(템플릿은 이미 빈 값이면 그리지 않는다 — :73·:121·:123).
- **시공 카드 `_url_from_file_entry`(construction_dashboard_display.py:103-112)**: 저장 view_url 우선 3줄을 지우고 `build_file_view_url(key)` 만 쓴다. 499줄 → 약 496줄(R13 — 늘리지 않는다).
- `erp-dashboard-gateway.js:36-40`: `f.key` 로만 조립, key 없으면 링크 없음. 이 파일은 지금 핀이 없다(`erp-dashboard-entry.js:9`) → 핀을 새로 붙인다.
- **옛 한글 파일명 참고사진 key**(1차 W2 열린 질문 ②): 안전 문자 규칙(`upload_authz.py:49 _SAFE_SEGMENT`) 때문에 "이상"으로 판정돼 PC 에서도 링크가 사라지고 개수만 남는다. 측정 E1 의 `non_ascii_key` 가 0 이면 규칙 그대로. 0 이 아니면 "자기 주문 `drawing_gateway/` 이고 한글만 걸린 key" 에 한해 **표시 전용**으로 `build_file_view_url`(인코딩)로 링크를 보인다 — 삭제 판정과는 분리(삭제는 하지 않으므로 영향 없음). 결정은 E1 결과를 보고 한 줄로 DECISIONS 에 적는다.

4.3.5 공통 판정 "지워도 되는 키"(새 파일) `foms/services/orders/drawing_key_safety.py` (약 140줄)
- `drawing_keys_in_use(sd) -> frozenset[str]`: `drawing_current_files`, `last_drawing_transfer.files`, 이력의 TRANSFER `files`·`previous_current_files`, CONFIRM_RECEIPT `files`, REQUEST_REVISION `files`, REVISION_CANCELLED `request.files`(§4.4), `drawing_wizard.pending`(dict 값)의 `key`·`versions` 항목의 `key`(있으면 — 구현 때 모양 확인)의 합집합.
- `history_referenced_keys(sd) -> frozenset[str]`: 위에서 `drawing_wizard` 를 뺀 것(행 보존 판정용, §4.5).
- `is_own_order_key(order_id, key) -> bool`: 정규화(앞뒤 공백·`\`·절대경로·`..` 거부) + `orders/{order_id}/` 로 시작 + 첫 하위 폴더가 **서버가 만드는 폴더 전부**(`upload_authz.ALLOWED_UPLOAD_SUBFOLDERS` ∪ `{"drawing_wizard"}` — `validate_upload_key` 의 목록에는 `drawing_wizard` 가 없어 그대로 쓰면 마법사 산출 파일이 절대 "삭제 가능"이 되지 않는다). 썸네일(`thumb_*`)은 같은 폴더라 함께 통과.
- `split_deletable_keys(db, order_id, sd_after, candidates, *, scope='any', exclude_attachment_ids=()) -> tuple[set[str], set[str]]`: 후보마다 (1) `is_own_order_key` 통과 (1') `scope == 'drawing'` 이면 `drawing_transfer._is_drawing_key`(`drawing_wizard/`·`drawing/`·`drawing_gateway/`, `foms/services/orders/drawing_transfer.py:83-96`)도 통과 (2) `drawing_keys_in_use(sd_after)` 에 없음 (3) 제외 목록 밖의 **살아 있는**(`deleted_at IS NULL`) `OrderAttachment` 행이 storage_key·thumbnail_key 로 쓰지 않음(쿼리 1회) — 모두 맞으면 삭제 가능, 아니면 보존. 보존한 key 는 이유와 함께 `logger.info`. 주문 폴더 밖의 옛 모양 key 는 보존(지우는 쪽보다 남기는 쪽이 안전 — 용량만).
- 쓰는 곳: 전달 취소(§4.5, scope='drawing'), 첨부 삭제 purge(4.3.6, scope='any'), outbox 핸들러 재확인(§4.5, scope='any'). 수정요청 취소는 M2 로 더 이상 지우지 않는다(§4.4).

4.3.6 첨부 삭제·복구(`order_routes.py:595 api_order_attachments_delete`, :646- `api_order_attachments_restore`)
- 지우려는 첨부의 storage_key 가 `drawing_current_files` 에 있으면 409 `{code: 'DRAWING_IN_USE', message: '지금 전달된 도면이라 첨부 탭에서 지울 수 없습니다. 도면 작업실에서 교체하거나 전달을 취소해 주세요.'}`. 관리자도 같은 답(뚫기 게이트가 아니다 — 교체·전달 취소가 올바른 길).
- `split_deletable_keys` 가 보존이라 한 key(이력에만 있는 교체된 옛 도면·참고사진 등)는 행 tombstone 은 하되 purge 예약을 하지 않고, **`ATTACHMENT_DELETED` 이벤트 payload 에 `file_retained: true, retained_reason: 'DRAWING_HISTORY'`** 를 싣는다(`emit_attachment_event(..., extra=...)`, `order_routes.py:81-111` — 이미 extra 를 받는다). 파일 보존은 1차 결정 "확정 뒤에도 파일 남김"과 같은 뜻(타임라인·비교 탭 링크 유지).
- 그 밖은 지금처럼(7일 유예 purge).
- **복구 보강**: 예약 행이 **0개**이면, 이 첨부의 마지막 `ATTACHMENT_DELETED` 이벤트(주문의 해당 이벤트를 id 역순으로 읽어 이 attachment_id 의 첫 것)가 `file_retained: true` 인지 본다. 맞으면 `storage.object_exists(storage_key)`(`foms/services/storage.py:334`, 읽기 1회)로 확인하고 tombstone 을 풀고 `ATTACHMENT_RESTORED` → 200. 파일이 없으면 409 "파일이 저장소에 없어 복구할 수 없습니다."(사실대로). `file_retained` 표시가 없으면 지금 그대로 409(지금 문구가 사실). 예약 행이 있을 때의 흐름은 무변경.
- R1 보정 스크립트(2c-2)도 같은 표시(`retained_reason: 'ORPHAN_UPLOAD'`)로 tombstone 한다 → 같은 복구 API 로 되살아난다.

**옛 데이터·운영**: E1(§5 측정 ②) — **측정만 한다**. 4.3.4 뒤로 화면이 저장 URL 을 쓰지 않으므로 URL 필드를 지우는 보정은 필요 없다(불필요한 운영 쓰기). 결과는 한글 key 표시 결정(4.3.4)에만 쓴다. 원장 기준 사진 달린 수정요청은 역대 3건.

**테스트**
- 프로브 P2·P2b 를 저장소로 옮기며 뜻을 바꾼다: 남의 주문 key 로 수정요청 → 400 `INVALID_REVISION_FILE`, 저장 0 · 자기 현재 도면 key(`drawing_wizard/…`) → 400 · traversal·절대경로·`\`·한글 key → 400 · files 가 문자열 → 400 · 정상 gateway key → 200 이고 저장 view_url == `/api/files/view/<key>`(보낸 `javascript:` 는 무시됨).
- **태블릿 회귀**: files 키 없는 본문(`{note, target_drawing_keys}`) → 200 · `files: null` → 200.
- PC 렌더: 옛 이력에 `download_url: 'javascript:alert(1)'` 을 심어도 HTML 에 `javascript:` 가 없다. **모바일 도면 방**: `drawing_current_files` 에 `download_url: 'javascript:…'` 를 심어도 `workbench_mobile_handoff.html` 렌더에 없고 key 로 만든 URL 만 있다. 시공 카드 썸네일도 같은 단언.
- gateway/complete: `foo/orders/1/drawing_gateway/x.png`·`orders/1/drawing_gateway/../measurement/x` → 400.
- 공통 판정 단위: 남의 주문 key·현재본 key·이력 key·다른 살아 있는 첨부 행 key → 보존 · 아무도 안 쓰는 자기 `drawing/` key → 삭제 · 아무도 안 쓰는 자기 `drawing_wizard/exports/` key → 삭제(폴더 판정이 막지 않음) · scope='drawing' 에서 자기 `measurement/` key → 보존.
- 첨부 삭제: 현재 도면 행 → 409 · 옛 도면 행 → 200 이고 outbox 0 + 이벤트 `file_retained` · 일반 사진 → 200 이고 outbox 2(본체·썸네일).
- **복구**: 예약 없는 `file_retained` 휴지통 행 → 복구 200(파일 있음 대역) · 같은 행에 파일 없음 대역 → 409 사실 문구 · 표시 없는 예약 0 행 → 기존 409.
- 음성 대조: 판정을 끄면 보존 단언 빨강.

**위험·되돌리기**: 옛 클라이언트가 이상한 files 를 보내면 400 — 화면 업로드는 모두 gateway 경로(`workbench_detail_body.html:2518`·:2556, `erp-dashboard-drawing.js:254`·:277)라 영향 없음. revert 가능(데이터 변화 없음 — `file_retained` 이벤트 표시는 옛 코드가 무시).

---

### 4.4 M2 — 수정요청 취소가 기록을 지운다 (+ R2 남은 동기 R2 삭제) (2b, Q3)

**문제** (코드 확인)
- 취소가 REQUEST_REVISION 을 이력에서 pop 하고(`erp_orders_revision.py:333`) 참고사진을 지운다(:330). 남는 것은 SecurityLog 한 줄(:340-346)뿐이라 타임라인·감사에 "이 단계에서 수정요청이 있었다"가 남지 않는다.
- 사진 삭제가 커밋(:370)보다 먼저라 커밋이 실패하면 파일만 사라진다(원장 C8(b) 의 남은 경로).
- 도면팀이 '반영 완료'를 누르고 작업 중이어도 취소된다(정책 — Q3).
- 취소 화면 두 곳은 본문과 Content-Type 없이 POST 한다(`erp-dashboard-drawing.js:210`, `workbench_detail_body.html:2838` `{ method: 'POST' }`).

**목표 동작**
- 취소해도 원래 요청(메모·대상 도면·참고사진·반영 체크)과 취소자·시각·이유가 이력에 남는다.
- 취소는 **파일을 지우지 않는다** → 커밋 전 삭제 문제가 사라진다.
- 취소 뒤 상태 복원 규칙(TRANSFERRED/CONFIRMED)은 그대로.

**설계**
- 이력에서 요청 항목을 빼는 것은 그대로 두고(열린 요청을 세는 소비자들이 바뀌지 않게), 대신 이력 끝에 새 항목을 붙인다:
  `{action: 'REVISION_CANCELLED', at: <UTC 문자열>, by_user_id, by_user_name, reason: <본문 선택 필드, 200자>, request: <뺀 REQUEST_REVISION 항목 전체 복사>}`
- 본문 `{reason?: string}` 선택 — **`request.get_json(silent=True) or {}` 로 읽는다**(본문·Content-Type 없는 지금 화면 두 곳이 415/400 이 나지 않게). 새 엔드포인트 없음.
- `_delete_revision_reference_files`(:214-254)·`_revision_reference_keys`(:197-211)를 지운다. SecurityLog 문구에서 "참고파일 N개 삭제"를 뺀다.
- 모르는 action 을 건너뛰는지 코드로 확인한 소비자: `_resolve_revision_restore_status`(:257-278, TRANSFER·CONFIRM_RECEIPT 만) · 전달 취소 복원(`erp_orders_drawing.py:540-553`) · `has_pending_unchecked_drawing_revision_requests`(`foms/services/orders/erp_policy_permissions.py:109-119`, REQUEST_REVISION 만) · `superseded_drawing_keys`(TRANSFER·CONFIRM_RECEIPT 만) · 감사(`audit_drawing_revisions.py` "알 수 없는 action 은 무시") · 생산 변경 배지(`production_change_alerts.py:193` 이하). 모두 건너뛴다.
- **표시 라벨**: `workbench.py:453`·:711·:962 라벨 표, `erp-dashboard-gateway.js:4`, 작업실 타임라인 배지(workbench_detail_body.html:1328), 대시보드 그리드(dashboard_grid.html:304), 모바일 스레드(`_build_handoff_thread` :482 태그). 라벨 "수정요청 취소", 원래 요청 메모를 흐리게.
- **거짓이 되는 안내 문구 3곳 고치기**: 취소가 파일을 지우지 않으므로
  - `static/js/orders/dashboard/erp-dashboard-detail-dom.js:392` "요청 시 첨부한 참고 파일이 삭제되고…" → "취소해도 요청 기록과 참고 파일은 남고, 도면 전달 상태로 돌아갑니다."
  - `erp-dashboard-drawing.js:207`, `workbench_detail_body.html:2836` 확인창 "참고 파일이 함께 삭제되며" → "요청 기록과 참고 파일은 남고, 도면 전달 상태로 돌아갑니다."
  - 핀: detail-dom(`erp-dashboard-entry.js:13`)·erp-dashboard-drawing.js(`erp-dashboard-entry.js:11` `20260909a`)·entry 자체(`layout_scripts.html:1634`). 템플릿은 핀 없음.
- 알림 딥링크(`foms/api/notifications/__init__.py:200` target_action REQUEST_REVISION)는 바꾸지 않는다.
- M16 복원(§4.2.7)은 이 라우트에서 한다(2a-2 가 2b 위에 얹는다). M1 잠금 뒤로 폼이 이 이력을 되돌리지 못한다.

**옛 데이터**: 이미 pop 된 취소는 되살릴 수 없다. 규모는 J1(§5 측정 ②).

**테스트**
- `tests/domains/test_drawing_revision_cancel.py:135 test_cancel_revision_deletes_reference_files_only` 를 뒤집는다 → "취소는 아무 파일도 지우지 않고, REVISION_CANCELLED 에 원래 요청과 사진 key 가 남는다".
- 본문 없이(Content-Type 없이) POST → 200(지금 화면 두 곳과 같은 요청) · `{reason}` 이 이력에 남는다.
- 복원 규칙 기존 테스트(:81·:99)는 계속 초록.
- 취소된 요청이 미체크여도 전달이 막히지 않는다.
- 취소 → 재수정요청 → 전달 취소 조합에서 상태 복원이 맞다.
- 프로브 P2b(현재 도면 삭제)는 삭제 자체가 없어져 초록.
- 라벨·안내 문구 렌더(PC·모바일·ERP 창구) — "삭제" 문구가 없다.

**위험·되돌리기**: 이력 길이는 늘지 않는다(빼기 1 + 붙이기 1). revert 하면 REVISION_CANCELLED 항목이 남는데 옛 코드는 라벨 없이 원문 action 을 그릴 수 있다(모바일 태그는 `action or '-'`, :482) — 무해.

---

### 4.5 M7 — 전달 취소가 아직 쓰는 파일을 지운다 (2b)

**문제** (코드 확인)
- 같은 key 를 두 번 전달하면 중복 제거 없이 현재본이 [v1, v1] 이 된다(`erp_orders_drawing.py:182`). 취소하면 `newly_uploaded_keys` = 마지막 TRANSFER files 전부(:478-486)를 회수 대상으로 삼아, 복원된 현재본 [v1] 이 가리키는 v1 행을 지우고(:501-507) STORAGE_DELETE 를 예약한다(:595-603). 프로브 P6 빨강.
- 이 outbox 에는 유예가 없고, 핸들러는 참조 확인 없이 지운다(`storage_delete_handler.py:74-81`). 첨부 삭제는 7일 유예다(`order_routes.py:63`, :194).
- 전달은 마법사 산출 key(`drawing_wizard/exports/`)에 category='drawing' 첨부 행을 만든다(:199-215). 지금 취소는 그 행을 지운다. 전달 취소는 TRANSFER 를 이력에서 빼므로 `superseded_drawing_keys` 로도 숨지 않는다(`drawing_confirm_cleanup.py:100-101`) — 행을 남기면 거둬들인 도면이 고객 링크·ZIP·생산/시공 도면 탭·발주 PUSH 에 그대로 보인다.

**목표 동작**: 취소는 "이번 전달이 새로 들여온 key" 의 **행**은 복원된 현재본·남은 이력이 가리키지 않으면 지우고(지금처럼), **파일**은 취소 뒤에도 아무도 안 쓰는 것만 회수한다. 실제 R2 삭제는 7일 뒤이고, 그때 다시 확인한다.

**설계**
- 전달 취소(:493-510): 복원할 `restored_files` 와 줄어든 history 로 `sd_after` 를 먼저 만든다.
- **행과 파일을 따로 판정한다**:
  - 행: `newly_uploaded_keys` 중 `restored_files` 에도 `history_referenced_keys(sd_after)` 에도 없는 key 의 첨부 행을 지운다(지금과 같은 hard delete). 복원 현재본이나 남은 이력이 가리키면 행을 남긴다(남은 이력만 가리키는 행은 superseded 규칙으로 이미 숨는다).
  - 파일: `split_deletable_keys(db, order_id, sd_after, newly_uploaded_keys ∪ 그 행들의 thumbnail_key, scope='drawing', exclude_attachment_ids=<이번에 지울 행>)` 의 삭제 가능 key 만 outbox 예약. 마법사 pending·versions 가 아직 가리키는 key 는 보존(마법사 화면이 쓴다), 아무도 안 쓰면 지금처럼 회수.
- outbox 예약에 `available_at = now + ATTACHMENT_PURGE_GRACE`(`order_routes.py:63` 상수 재사용 — 공용 위치로 옮길 때 import 순환 확인).
- 핸들러 재확인(`handle_storage_delete`): `source_domain == 'ORDER_EVENT'` 이고 payload 에 `order_id` 가 있으면 그 주문의 structured_data 와 살아 있는 첨부 행으로 `split_deletable_keys(scope='any')` 를 다시 보고, 쓰이면 지우지 않고 `_LOGGER.info("[storage-delete] still referenced — skip")` 후 정상 반환(DONE). 주문이 없으면(하드 삭제) 지금처럼 지운다. 다른 도메인(WIZARD_PENDING 등)은 그대로.
- 응답 문구 "신규 업로드 파일 N개 삭제"(:670)는 실제 회수 수로.

**옛 데이터·운영**: F1(§5 측정 ②) — 이미 실행된 전달 취소 삭제 중 지금 현재본이 가리키는 key. 있으면 그 파일은 R2 HEAD 로 확인(읽기 전용) 뒤 사용자 보고.

**테스트**
- 프로브 P6 을 **두 벌**로 옮긴다: `drawing/` key 판(M10 뒤 흔한 경로)과 `drawing_wizard/exports/` key 판. 각각 복원 현재본 key 는 행 유지·outbox 없음.
- 음성 대조: `drawing_keys_in_use` 판정만 끈 경우 두 벌 모두 빨강(폴더 판정 때문에 초록이 되는 일이 없게 — 두 판 모두 폴더 판정은 통과하는 key 다).
- 마법사 key 끝-끝: 마법사 전달 → 취소 → 첨부 목록 API·고객 링크에 안 보임, 그 key 의 첨부 행 0, outbox 예약 여부는 판정대로(pending·versions 가 가리키면 없음, 아니면 7일 뒤 1건).
- `drawing/` key 보통 회수(새 key 1개): 행 0 · 본체+썸네일 예약 · `available_at` ≥ 지금+7일.
- 예약 뒤 같은 key 가 다시 현재본이 되면 핸들러의 R2 삭제 호출 0.

**위험·되돌리기**: 회수 파일이 7일 동안 R2 에 남는다(용량 미미). revert 가능.

---

### 4.6 M9 — 마지막 catch 에 로거가 없다 (2b)

**문제**: 수령 확정 라우트 마지막 catch(`erp_orders_draftsman.py:490-494`, failopen 인벤토리 `lineno 491` SWALLOW_BY_CONTROL_FLOW)에 로거가 없다. 1차로 확정 때 R2 삭제는 없어졌지만 500 의 원인은 여전히 흔적 없이 사라진다. 이 묶음에서 함께 고치는 전달 취소 마지막 catch(`erp_orders_drawing.py:672-675`, `lineno 672`)와 창구 업로드 완료 catch(:786 — 4.3.3 이 이 함수를 고친다)도 같다.

**설계**: 세 catch 에 `log_handled_exception()` 한 줄. draftsman 은 :6 에서 이미 import. **`erp_orders_drawing.py` 에는 import 가 없다** → import 한 줄 추가. draftsman 494 → 495줄. failopen `_SWALLOW_BASELINE` 172 → **169** 로 내려 잠근다(`tests/domains/test_failopen_inventory.py:47`, 주석 한 줄) + `docs/harness/foms_failopen_inventory.json` baselines + `python tools/harness/refresh_inventories.py`. 창구 업로드(multipart) catch(:741)는 이 묶음이 그 함수를 고치지 않으므로 두고, 기준값에 넣지 않는다.

**테스트**: `test_failopen_inventory.py` 전체 초록(정확히 같음 단언 :202-211).

**위험**: 여러 창이 같은 기준값을 동시에 바꾸면 충돌 → 반영 직전 origin 기준으로 다시 센다(169 는 지금 172 기준 계산값).

---

### 4.7 M10 — 직접 올린 도면이 전달에서 빠진다 (2c-1) · R1 고아 53행 (2c-2)

**문제** (코드 확인)
- 작업실 전달 창과 ERP 대시보드 전달 창은 도면을 `POST /api/orders/<id>/attachments`(category=drawing)로 올린다(`workbench_detail_body.html:2414-2443` multipart, :2446-2477 direct `folder = orders/<id>/attachments`; `erp-dashboard-drawing.js:103-131` multipart). 서버 multipart 폴더는 category 와 관계없이 `orders/<id>/attachments`(`order_routes.py:356`). 폰의 '수정본 전달'도 같은 전달 창(#dwTransferModal)을 연다(`templates/drawing/partials/workbench_mobile_handoff.html:264-267`).
- 전달 필터 `materialize_transfer_attachments`(`foms/services/orders/drawing_transfer.py:99-128`)는 `drawing_wizard/`·`drawing/`·`drawing_gateway/` 만 통과(`_is_drawing_key` :83-96) → 첫 전달 400 "전달할 도면이 없습니다"(`erp_orders_drawing.py:146-148`), 재전달 400 "수정본 재전송 시 도면 파일 업로드가 필요합니다"(:140-141), 마법사 대기 도면과 섞으면 직접 올린 것만 소리 없이 빠진다. 프로브 P3 빨강. 운영: 8~9월 53개 모두 미전달(원장). 폰과 PC 모두 파일 업로드 전달이 막히고 마법사 저장본 전달만 된다(1차 판정 deferred R2).
- 참고: ERP 첨부 탭의 direct 업로드는 이미 `orders/<id>/<category>` 폴더를 쓴다(`erp-order-shared.js:4422`) → 첨부 탭 '도면'(direct)은 지금도 `drawing/` 로 간다. 막히는 것은 전달 창 두 곳과 multipart 폴백.
- R1: 전달에 실패한 업로드 행(category=drawing, `attachments/`)은 1차 뒤로 확정 때 지워지지 않아 고객 링크·ZIP·합본·생산/시공 도면 탭·발주 PUSH 에 남는다(`foms/api/share.py:175-222`, 1차 리뷰 R1). 첨부 탭 multipart 업로드와 같은 엔드포인트·경로라 코드로 가를 신호가 없다.

**목표 동작**: category=drawing 업로드는 어느 길이든 `orders/<id>/drawing/` 에 저장된다 → 전달 필터를 그대로 통과한다. 전달 필터·시공 카드 deny-list(`foms/services/construction_dashboard_display.py:120` `/attachments/`)·고객 링크 allow-list 는 **바꾸지 않는다**(원장 누락 점검 — `attachments/` 를 필터에 넣으면 두 규칙과 부딪힌다).

**설계 (2c-1)**
- multipart(`order_routes.py:356`): `folder = f"orders/{order_id}/drawing" if category == "drawing" else f"orders/{order_id}/attachments"`. 썸네일도 같은 folder 변수를 쓴다(:370-379).
- direct 세션(`foms/api/files/direct_upload.py:42` 단건 · :101 일괄): 본문 `category == 'drawing'` 이고 정규화 폴더가 `orders/<id>/attachments` 면 `orders/<id>/drawing` 으로 바꿔 key 를 만든다 → 캐시된 옛 JS 도 고쳐진다. 권한 판정은 바뀐 폴더 기준(`category_upload_allowed('drawing')` = DRAWING_TEAM 또는 ERP_EDIT, `upload_authz.py:57`). direct_upload.py 289줄(래칫 500).
- complete(:164-): key 폴더가 drawing 이면 `key_category='drawing'` — 지금 코드 그대로 맞다.
- JS: 작업실 전달 창 direct 폴더(`workbench_detail_body.html:2447`) → `orders/${orderId}/drawing`. 공용 도우미 `static/js/runtime/upload-progress.js:395` 기본 폴더도 category 가 drawing 이면 drawing(핀 `layout_scripts.html:113` `?v=20260820a`). erp-dashboard-drawing.js 는 multipart 라 서버 변경만으로 된다.
- 권한 변화 없음.
- M14-a(전달 버튼 권한, §4.10)를 같은 묶음에 넣어 "올렸는데 403" 으로 생기는 고아를 줄인다.
- 2c-1 뒤에 새로 생길 고아(전달이 400/403 으로 실패한 뒤 남는 업로드 행)는 드물다(전달 창은 막힘 상태면 열리지 않고 M14-a 로 권한 불일치가 사라진다). 남는 경우는 비목표로 기록.

**R1 기존 53행 (2c-2, Q4)** — 운영 쓰기라 별도 승인. 전제: 2b 의 복구 보강이 운영에 있어야 "되살릴 수 있다"가 사실이 된다. 추천안: 측정 G1 로 **세 무리**로 나눈다.
- (가) 마지막 성공 전달 **이전**에 올렸고 그 주문에 현재 도면이 있는 행 → tombstone(휴지통, purge 예약 없이 + `ATTACHMENT_DELETED` 에 `file_retained: true, retained_reason: 'ORPHAN_UPLOAD'` — 2b 복구 API 로 되살림).
- (나) 마지막 성공 전달 **이후**에 올린 행 → **숨기지 않는다**. M10 때문에 전달에 실패한, 도면팀이 보내려던 최신본일 수 있다. 도면팀 확인 목록으로 넘긴다(숨기면 고객·생산에는 더 오래된 전달본만 남아 옛 도면 생산 위험).
- (다) 현재 도면이 없는 주문 → 목록을 도면팀에 넘겨 다시 올리게(2c-1 뒤로는 `drawing/` 로 가서 전달된다).
- 첨부 탭에서 일부러 올린 '도면'도 섞여 있을 수 있어(같은 경로) 목록을 보고 하나씩 정한다. 스크립트는 `tools/ops/` 에 dry-run 기본, 무리별 목록 출력 → 사용자 확인 → 적용.

**옛 데이터·운영**: G1(측정 ②), G2(측정 ③ — 2c-1 배포 뒤 새 업로드 경로 확인) — §5.

**테스트 (2c-1)**
- 프로브 P3 을 옮김: multipart category=drawing 업로드 key 가 `orders/<id>/drawing/…` 이고 전달 200·현재본 포함.
- direct 세션: folder attachments + category drawing → 발급 key 가 `drawing/` · category measurement 면 `attachments/` 그대로.
- **1차 리뷰 R2**: C9 끝-끝(폰 반영 체크 → 실제 업로드 경로 → 수정본 전달 200)을 실제 업로드로 다시 쓴다(`test_drawing_mobile_revision_check.py:293-296` 의 합성 key 교체). 먼저 M10 strict xfail 로 고정한 뒤 이 묶음에서 뗀다.
- 시공 카드·고객 링크: `drawing/` 업로드를 전달한 뒤 두 곳에 보인다.
- 음성 대조: 폴더 변경을 끄면 P3 빨강.

**테스트 (2c-2 R1 스크립트)**: dry-run 은 쓰기 0 · 세 무리 분류(업로드 시각 대 마지막 TRANSFER 시각) · 적용 뒤 (가) 행은 휴지통 + 이벤트 표시 + outbox 0 · 복구 API 200.

**위험·되돌리기**: 첨부 탭 '도면' multipart 업로드도 `drawing/` 로 간다 — 경로를 특별 취급하는 곳은 `drawing_transfer.py` 뿐(검색 확인)이라 표시·권한 차이 없음. revert 해도 이미 `drawing/` 에 올라간 파일은 옛 코드에서도 전달 가능. R1 은 휴지통 복구로 되돌림.

---

### 4.8 R3 — 개수 4곳이 옛 도면을 센다 (2c-2)

**문제** (코드 확인): 1차 뒤 옛 도면 행이 남는데, 목록·미리보기·배치 개수는 빼지만 개수 쿼리 4곳은 전체 행을 센다 — `foms/services/production_read_model.py:235-253`(raw SQL), `foms/services/orders/dashboard_read_model.py:388-398`(ORM), `foms/services/construction_read_model.py:128-147`(raw SQL), `foms/services/erp_mobile_order_display.py:672-685 _attachment_count`(단건 경로). 그래서 📎N·+N 이 눌러 연 목록보다 크고, 모바일 배치/단건 결과가 달라진다(docstring '100% 동일' 계약 깨짐).

**목표**: 네 곳 모두 목록과 같은 수.

**설계**
- `drawing_confirm_cleanup.py`(244줄)에 `superseded_drawing_row_counts(db, structured_data_by_order) -> dict[int, int]`: 옛 key 가 있는 주문만 모아 `category='drawing' AND storage_key IN (...)` 를 주문별로 세는 쿼리 1회(옛 key 가 없으면 쿼리 0회).
- 네 곳은 기존 카운트 뒤 `counts[oid] -= superseded[oid]` 만 한다(raw SQL 과 그 계약 테스트의 `deleted_at IS NULL` 고정 유지). structured_data 는 호출자가 이미 읽은 Order 에서(`load_structured_data_by_order` 재사용 — identity map).
- `_attachment_count(db, order_id)` 시그니처는 그대로(기존 테스트가 `lambda _db, _oid` 로 바꿔 끼움) — 호출 쪽에서 뺀다.
- dashboard_read_model.py **491줄 → +2~3줄(래칫 500, 목록 밖)**.
- 캐시(확인함): 생산·시공 첨부 개수는 캐시된다(key = 주문 id 목록, 수명 120초 — `foms/web/production/dashboard.py:195-214`, `foms/web/construction/dashboard.py:180-201`). 전달·전달 취소 때의 무효화는 2a-2 가 이미 넣는다(§4.2.5 — `ATTACHMENT_DASHBOARD_FAMILIES`). 2c-2 는 2a-2 뒤라 따로 할 일 없음.

**테스트**: 옛 도면 k개가 있는 주문에서 네 경로 개수 == 목록 API 개수 · 모바일 배치 == 단건 · 옛 key 없는 페이지는 추가 쿼리 0(쿼리 수 단언) · `tests/performance/test_perf_regression_guard.py`·`perf_scan --guard`.

**위험**: 옛 도면 있는 페이지만 쿼리 1회 증가. revert 가능.

---

### 4.9 R4 — 내부 첨부 탭에서도 옛 도면이 숨는다 (2c-2, §8 기본안)

**문제** (코드 확인): 목록 API 가 모든 호출자에게 옛 도면을 뺀다(`order_routes.py:275-281`, 휴지통 조회만 예외). 생산·시공 도면 탭(`templates/production/partials/scripts.html:168·460`, `static/js/construction/dashboard.js:95·306`)과 ERP 내부 첨부 탭(`erp-order-shared.js:4241`, `static/js/orders/dashboard/erp-dashboard-attachments.js:9`, `static/js/orders/order-detail-fragment.js:298`)이 같은 GET 이다. 예전에는 확정 전까지 내부 탭에 보였다.

**목표(기본안)**: 내부 첨부 탭에서만 옛 도면이 '교체됨' 표시와 함께 보인다. 생산·시공·고객은 지금처럼 숨김.

**설계**
- 목록 API 선택 인자 `?include_superseded=1`: 켜면 옛 도면 행도 돌려주고 그 행에 `is_superseded: true`. 권한: 첨부 목록을 볼 수 있는 사람 누구나(삭제가 아니라 교체라서 휴지통 `include_deleted` 같은 관리 권한은 요구하지 않는다). 기본값은 지금 그대로(숨김).
- ERP 첨부 탭 JS 두 곳(erp-order-shared.js:4241, erp-dashboard-attachments.js:9)만 인자를 붙이고 '교체됨' 배지(흐리게, erp-pro.css 클래스). order-detail-fragment.js:298 은 쓰는 화면이 내부용인지 확인 뒤 결정(확인 필요).
- 핀: `erp-dashboard-attachments.js` 는 entry 목록에 핀이 **없다**(`erp-dashboard-entry.js:10`) → 새로 붙인다 + entry 자체 핀. `erp-order-shared.js` 는 2a-1① 에 이어 **다시** 핀을 올린다(같은 날이면 다음 글자).
- 새 엔드포인트 없음.

**테스트**: 인자 없으면 숨김(기존 테스트) · 인자 있으면 k개 늘고 `is_superseded` · 생산·시공 호출 코드에는 인자가 없음(정적 계약).

**위험**: 낮음. revert 가능.

---

### 4.10 M14 — 화면·서버 불일치 모음 (a 는 2c-1, 나머지 2d)

**문제** (코드 확인)
- a. 전달 버튼 권한: 화면 `can_transfer = has_assignee and is_drawing_participant and (ADMIN or 도면팀)`(workbench.py:1022, `foms/web/drawing/tablet_sheet.py:121-131`) — 담당이 아닌 도면팀도 참. 서버는 ADMIN·지정 담당·사유 있는 MANAGER 만(`erp_orders_drawing.py:104-114`) → 403.
- b. 반영 체크로 막힌 상태에도 차례 리본이 mine 색: `_build_drawing_turn`(workbench.py:222-243)이 막힘을 모른다.
- c. 모바일이 딥링크 `tab` 을 무시: `active_tab`(:993)은 숨은 PC 칸에만 쓰이고, 모바일 목록/상세 판정(:1084-1093)은 event_id·target_no 만 본다. 알림 착지(`foms/services/notifications/push_sender.py:176`, `foms/api/notifications/__init__.py:201`, `static/js/foms/foms-drawing-alert.js:73`)가 `?tab=requests` 라 도면이 여러 장이면 목록에 떨어져 스레드가 안 보인다.
- d. 태블릿 시트 '시트 전달'(`templates/drawing/partials/tablet_sheet_body.html:89-97` → 마법사 transfer-pending, `static/js/foms/tablet-drawing-gallery.js:99-124`)이 반영 체크 막힘과 "수정본은 교체 대상 필요"(RETURNED 이고 현재본 2장 이상이면 `erp_orders_drawing.py:176-177` 400)를 모른 채 켜져 있다.
- e. ERP 대시보드 `requestTabHtml`(`erp-dashboard-detail-dom.js:410-436`)은 만들고 안 쓰는 코드.

**설계**
- a: 서비스 술어 `can_transfer_drawing(user, order) -> bool`(ADMIN 또는 `user.id in get_assignee_ids(order, 'DRAWING_DOMAIN')`)을 `foms/services/erp_policy` 쪽에 두고 전달 서버(:104-114 — MANAGER 사유 분기는 서버에만 둔다)·workbench·tablet_sheet 가 함께 쓴다. 담당 아닌 도면팀에게는 버튼 대신 "담당자만 전달할 수 있어요" 한 줄. 기준값 `assignments.drawing_assignee_user_ids` 는 2a-1① 로 폼 되돌림에서 잠겨 있어야 한다(전제).
- b: `_build_drawing_turn(..., gated=transfer_gated_by_revision_checklist)` → 막히면 tone 'other', 라벨 "수정요청 반영 체크 필요".
- c: `active_tab == 'requests'` 도 딥링크로 보고 상세 보기로 착지 + 첫 미체크 수정요청 말풍선 `is_highlight`.
- d: tablet_sheet 가 workbench 와 같은 막힘 판정(`has_pending_unchecked_drawing_revision_requests`, RETURNED 이고 현재본 2장 이상)을 계산해 버튼을 끄고 이유를 보인다("작업실에서 반영 체크/교체할 도면을 고른 뒤 전달").
- e: 죽은 코드 삭제(entry 핀 올림).

**테스트**: a 화면 == 서버(담당 아닌 도면팀: 버튼 없음 + API 403, 담당: 버튼 + 200) · b 리본 · c `?tab=requests` 착지에 스레드와 강조 · d 막힘에서 버튼 disabled · e 문자열 없음.

**위험**: 낮음. revert 가능.

---

### 4.11 M13 — v2 모바일에 도면방 PUSH 가 없다 (2d)

**문제** (코드 확인): 옛 모바일 바에는 `#dw-btn-drawing-room-push-mobile`(workbench_detail_body.html:1579-1585)이 있지만 v2 에서는 그 바가 숨고, 새 모바일 바(`templates/drawing/partials/workbench_mobile_handoff.html:263-306`)에는 없다. PC 버튼 `#dw-btn-drawing-room-push`(:1508-1515)는 숨은 PC 칸에 있다.

**설계**: 하단 바에 버튼을 더하지 않고(관리자 바 높이 94px > 본문 여백 84px — §4.12 에서 가림을 고친다) 현재 도면 칸(기존 블록 — `DETAIL_TOP_BLOCKS=5` 유지, `tests/domains/test_drawing_mobile_back_to_workbench.py:35`)에 작은 "도면방 보내기" 버튼을 둔다. 조건은 PC 와 같다(`can_toggle_revision_check`, 전달 도면 없으면 disabled). 동작은 `static/js/foms/drawing-handoff.js` 대신 누르기 표(:70-75)에 `'drawing-room-push': 'dw-btn-drawing-room-push'` 를 더해 기존 `pushDrawingRoom`(workbench_detail_body.html:2799-2832)을 그대로 쓴다. 새 엔드포인트 없음. 핀: drawing-handoff.js(:3023), 필요하면 CSS.

**테스트**: v2 폰 렌더에 버튼 1개와 조건 · 대신 누르기 표 문자열 계약 · 기존 도면방 PUSH 테스트 초록.

---

### 4.12 R12 — 반영 체크 접근성 + 관리자 하단 바 가림 (2d)

- 토글 버튼(handoff.html:228-236): `aria-label="{{ event.at_text }} 수정요청 {{ '반영 완료 해제' if rc.checked else '반영 완료 표시' }}"`, `aria-pressed="{{ 'true' if rc.checked else 'false' }}"`.
- 막힌 이유(:275 `<small>` — disabled 버튼 안이라 탭 이동으로 못 닿음)를 버튼 밖 `<p id="dw-transfer-gate-reason" class="foms-drawing-action-bar__reason">` 로 빼고 버튼에 `aria-describedby`.
- 글자 0.62rem → 0.72rem(`static/css/components/foms-drawing-mobile.css:776-785`).
- **관리자 하단 바 가림(1차 W2 열린 질문 ①)**: 관리자 바 높이 94px 가 본문 아래 여백 84px 보다 커서 마지막 줄이 가린다. 같은 CSS 파일에서 본문 아래 여백을 바 높이 변수에 맞춘다(관리자 바가 있을 때의 여백 규칙 한 곳). 390px 캡처로 관리자·비관리자 두 경우 바 높이와 마지막 줄을 재확인.
- 핀: foms-drawing-mobile.css 지금 `20260929b` → 구현일 핀. `@import`(foms-mobile-surfaces.css:24), share_view.html:12, share_bundle_view.html:12, 부모 layout_head.html:239, `ASSET_PIN_LOCK`(`tests/domains/test_drawing_mobile_asset_pin_freshness.py:118-121` 해시·핀), 핀 복제 단언 테스트(1차가 고친 5~6개 — grep 으로 찾기).

**테스트**: 렌더 속성 단언 · 핀 테스트 · 390px 실화면 캡처(gstack browse, 관리자·비관리자).

---

### 4.13 R11 — 1차 테스트 약점 (2d)

- `tests/domains/test_drawing_mobile_revision_refs_and_cancel.py:190` `status_code not in (400, 403)` → r2 대역 스토리지(`test_share_hides_superseded_drawings.py` 의 `_ShareStorage` 방식)로 302 를 단언(404·500 도 통과하던 구멍).
- `test_drawing_mobile_revision_check.py:305` 영업 테스트 끝에 같은 본문으로 POST → 403 단언(노출 == 서버 허용을 양쪽으로).
- JS 계약(`:321`)은 문자열 검사뿐 → 스테이징 gstack browse 스모크로 토글을 한 번 눌러 새로고침 뒤 상태 확인(QA 절차, CI 아님).

---

## 5. 운영 읽기 전용 측정

- 모두 `BEGIN TRANSACTION READ ONLY` 안에서. production 은 `claude_master` 규칙(사용자 명시 요청 1건당 1회·측정만·실데이터 불가침). staging·로컬은 자유.
- **측정 묶음 = 사용자 요청 1건씩**:

| 묶음 | 언제 | 포함 |
|---|---|---|
| 측정 ① | **지금 즉시**(1차가 운영에 있음) | C1 · C2 · C3 |
| 측정 ② | 2a-1① 운영 반영 뒤, 2b 전 | C1·C2·C3 재측정(0 확인) · A1 · A2 · B1 · D1 · E1 · F1 · G1 · I1 · J1 · K1 · R2 버킷 버전 관리 확인(읽기 — 지워진 참고사진 2장 복구 가능성) |
| 측정 ③ | 2c-1 운영 배포 뒤 | G2 |
| 측정 ④ | 2a-2 운영 반영 뒤, 사용자가 요청할 때마다 1회(권장 주 1회 · 4주) | L1 |

- 결과가 0 이 아니면 해당 묶음의 운영 반영 전에 사용자에게 보고한다. 보정은 모두 운영 쓰기라 별도 승인.
- H1·H2(R5·R6)와 C2(R10)는 1차 승격 직전 0 으로 **측정 완료**(`docs/AI_CHANGELOG.md` 2026-09-29). H1·H2 는 다시 재지 않는다(SQL 은 참고로 남김).

| ID | 묶음 | 목적 |
|---|---|---|
| A1 | ② | 허용 목록 게이트에 걸릴 CONFIRM 주문(M3) — 영문·한글 단계값 따로 |
| A2 | ② | 생산 대기 중 수정 중인 주문(Q2) |
| B1 | ② | 최근 90일 CONFIRM→PRODUCTION·DRAWING→CONFIRM 이 어느 길로 일어났나(Q1) |
| C1·C2 | ①·② | 폼 저장 되돌림 흔적(M1·R10) |
| C3 | ①·② | 1차 배포(`287782ce3`) 뒤 "도면 동작 → 그 뒤 폼 전체 저장"이 있었던 주문 + 폼 저장이 도면 담당을 바꾼 기록 |
| D1 | ② | 수정 중인데 고객확인이 남은 주문(M16) |
| E1 | ② | 저장된 파일 항목의 key·URL 이상 — 현재본·마지막 전달·이력 TRANSFER/CONFIRM_RECEIPT/REQUEST_REVISION 전부(M5, 측정만) |
| F1 | ② | 이미 실행된 전달 취소 삭제 중 현재본이 가리키는 key(M7) |
| G1 | ② | 고아 도면 업로드 세 무리(R1·Q4) |
| G2 | ③ | 새 도면 업로드가 `drawing/` 로 가는지 |
| I1 | ② | 최상위·중첩 도면 상태 불일치 — 0 이 아니면 2a-2 전 보정 |
| J1 | ② | 지금까지 수정요청 취소 횟수(M2) |
| K1 | ② | 과거 C21 발생(원장 Q12, Q0 시간대 보정 필요) |
| L1 | ④ | 관리자 뚫기(DRAWING_STATUS·COMMAND_REQUIRED)와 도면 미확정 강제 변경 빈도 |

```sql
-- A1: 단계 고객컨펌(영문·한글)인데 도면이 수령 확정이 아닌 주문(허용 목록에 걸림)
SELECT o.erp_stage_code,
       upper(coalesce(nullif(o.structured_data->>'drawing_status', ''),
                      nullif(o.structured_data->'drawing'->>'status', ''), 'NONE')) AS drawing_status,
       count(*) AS orders, (array_agg(o.id ORDER BY o.id))[1:30] AS sample_ids
FROM orders o
WHERE o.deleted_at IS NULL AND o.status <> 'DELETED' AND o.is_erp_order
  AND o.erp_stage_code IN ('CONFIRM', '고객컨펌')
  AND upper(coalesce(nullif(o.structured_data->>'drawing_status', ''),
                     nullif(o.structured_data->'drawing'->>'status', ''), 'NONE')) <> 'CONFIRMED'
GROUP BY 1, 2 ORDER BY 3 DESC;
-- 한글 단계값 주문 수(도면 상태 무관, 게이트 정규화가 필요한 규모)
SELECT o.structured_data->'workflow'->>'stage' AS raw_stage, count(*)
FROM orders o
WHERE o.deleted_at IS NULL AND o.status <> 'DELETED' AND o.is_erp_order
  AND o.structured_data->'workflow'->>'stage' IN ('고객컨펌', '생산', '도면')
GROUP BY 1;

-- A2: 생산 단계(영문·한글) + 수정 중/수령 전, 제작 시작 전·후로 나눔
SELECT upper(o.structured_data->>'drawing_status') AS drawing_status,
       count(*) FILTER (WHERE r.id IS NULL) AS waiting_start,
       count(*) FILTER (WHERE r.id IS NOT NULL) AS in_progress
FROM orders o
LEFT JOIN production_runs r ON r.order_id = o.id AND r.is_current AND r.status = 'IN_PROGRESS'
WHERE o.deleted_at IS NULL AND o.status <> 'DELETED' AND o.is_erp_order
  AND o.erp_stage_code IN ('PRODUCTION', '생산')
  AND upper(coalesce(o.structured_data->>'drawing_status', '')) IN ('RETURNED', 'TRANSFERRED')
GROUP BY 1;

-- B1: 최근 90일 두 이동의 경로(STAGE_CHANGED = 일반 상태 쓰기 SET_MAIN_STAGE)
SELECT e.event_type, e.payload->>'from' AS from_stage, e.payload->>'to' AS to_stage,
       count(*) AS moves, count(DISTINCT e.created_by_user_id) AS actors
FROM order_events e
WHERE e.created_at >= now() - interval '90 days'
  AND ((e.payload->>'from' IN ('CONFIRM', '고객컨펌') AND e.payload->>'to' IN ('PRODUCTION', '생산'))
    OR (e.payload->>'from' IN ('DRAWING', '도면') AND e.payload->>'to' IN ('CONFIRM', '고객컨펌')))
GROUP BY 1, 2, 3 ORDER BY 4 DESC;

-- C1: 도면 상태와 이력 마지막 도면 동작이 어긋난 주문(폼 되돌림 흔적 후보)
WITH o AS (SELECT id, erp_stage_code, structured_data AS sd FROM orders
           WHERE deleted_at IS NULL AND status <> 'DELETED'
             AND jsonb_typeof(structured_data->'drawing_transfer_history') = 'array'),
la AS (SELECT DISTINCT ON (o.id) o.id, o.erp_stage_code, o.sd->>'drawing_status' AS drawing_status,
              x.e->>'action' AS last_action
       FROM o CROSS JOIN LATERAL jsonb_array_elements(o.sd->'drawing_transfer_history') WITH ORDINALITY x(e, i)
       WHERE x.e->>'action' IN ('TRANSFER', 'REQUEST_REVISION', 'CONFIRM_RECEIPT')
       ORDER BY o.id, x.i DESC)
SELECT last_action, drawing_status, erp_stage_code, count(*) AS orders,
       (array_agg(id ORDER BY id))[1:30] AS sample_ids
FROM la
WHERE (last_action = 'TRANSFER' AND drawing_status IS DISTINCT FROM 'TRANSFERRED')
   OR (last_action = 'REQUEST_REVISION' AND drawing_status IS DISTINCT FROM 'RETURNED')
   OR (last_action = 'CONFIRM_RECEIPT' AND drawing_status IS DISTINCT FROM 'CONFIRMED')
GROUP BY 1, 2, 3 ORDER BY 4 DESC;

-- C2: 마지막 전달 파일이 현재본에 하나도 없는 주문(리뷰 R10 ②)
WITH o AS (SELECT id, erp_stage_code, structured_data AS sd FROM orders
           WHERE deleted_at IS NULL AND status <> 'DELETED'
             AND jsonb_typeof(structured_data->'drawing_transfer_history') = 'array'),
lt AS (SELECT DISTINCT ON (o.id) o.id, o.erp_stage_code, o.sd, x.e AS t
       FROM o CROSS JOIN LATERAL jsonb_array_elements(o.sd->'drawing_transfer_history') WITH ORDINALITY x(e, i)
       WHERE x.e->>'action' = 'TRANSFER' ORDER BY o.id, x.i DESC)
SELECT id, erp_stage_code, sd->>'drawing_status' AS drawing_status
FROM lt
WHERE jsonb_typeof(t->'files') = 'array' AND jsonb_array_length(t->'files') > 0
  AND NOT EXISTS (
    SELECT 1 FROM jsonb_array_elements(t->'files') f
    JOIN jsonb_array_elements(CASE WHEN jsonb_typeof(sd->'drawing_current_files') = 'array'
                                   THEN sd->'drawing_current_files' ELSE '[]'::jsonb END) c
      ON c->>'key' = f->>'key')
ORDER BY id;

-- C3: 1차 배포(:deploy_at = 287782ce3 운영 배포 SUCCESS 시각, UTC) 뒤 "도면 동작 → 그 뒤 폼 전체 저장" 주문
--     (도면 이력 시각: TRANSFER 는 transferred_at, 나머지는 at — 모두 UTC 'YYYY-MM-DD HH:MM:SS')
WITH acts AS (
  SELECT o.id AS order_id, x.e->>'action' AS action,
         (coalesce(x.e->>'at', x.e->>'transferred_at'))::timestamp AS acted_at
  FROM orders o
  CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(o.structured_data->'drawing_transfer_history') = 'array'
                                               THEN o.structured_data->'drawing_transfer_history' ELSE '[]'::jsonb END) x(e)
  WHERE x.e->>'action' IN ('TRANSFER', 'REQUEST_REVISION', 'CONFIRM_RECEIPT')
    AND coalesce(x.e->>'at', x.e->>'transferred_at') ~ '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$'),
saves AS (
  SELECT target_id AS order_id, timestamp AS saved_at, user_id
  FROM security_logs
  WHERE action = 'ORDER_STRUCTURED_SAVED' AND target_type = 'order'
    AND detail->>'mode' = 'full' AND timestamp >= :deploy_at)
SELECT s.order_id, count(DISTINCT s.saved_at) AS saves_after_action,
       min(a.acted_at) AS first_action_after_deploy, max(s.saved_at) AS last_save,
       o.erp_stage_code, o.structured_data->>'drawing_status' AS drawing_status_now
FROM saves s
JOIN acts a ON a.order_id = s.order_id AND a.acted_at >= :deploy_at AND a.acted_at < s.saved_at
JOIN orders o ON o.id = s.order_id
GROUP BY s.order_id, o.erp_stage_code, o.structured_data->>'drawing_status'
ORDER BY s.order_id;
-- 읽는 법: 후보 주문마다 C1·C2 규칙(상태 == 마지막 동작, 마지막 전달 파일 ⊂ 현재본)을 사람이 확인한다.
-- C3b: 같은 기간 폼 전체 저장이 도면 담당을 바꾼 기록(담당 되돌림 후보)
SELECT c.order_id, c.before_value, c.after_value, c.created_at, c.actor_user_id
FROM order_field_changes c
JOIN security_logs l ON l.detail->>'change_set' = c.change_set_id
WHERE c.path_template = 'assignments.drawing_assignee_user_ids'
  AND c.created_at >= :deploy_at
  AND l.action = 'ORDER_STRUCTURED_SAVED' AND l.detail->>'mode' = 'full'
ORDER BY c.created_at;

-- D1: 수정 중/수령 전인데 고객확인이 남은 주문
SELECT o.erp_stage_code, upper(o.structured_data->>'drawing_status') AS drawing_status, count(*) AS orders
FROM orders o
WHERE o.deleted_at IS NULL AND o.status <> 'DELETED'
  AND o.structured_data->'blueprint'->>'customer_confirmed' = 'true'
  AND upper(coalesce(o.structured_data->>'drawing_status', '')) IN ('RETURNED', 'TRANSFERRED')
GROUP BY 1, 2;

-- E1: 저장된 파일 항목 중 key 가 자기 주문 경로가 아니거나 URL 이 서버 모양이 아닌 것(출처별, 측정만)
WITH hist AS (
  SELECT o.id AS order_id, x.e
  FROM orders o
  CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(o.structured_data->'drawing_transfer_history') = 'array'
                                               THEN o.structured_data->'drawing_transfer_history' ELSE '[]'::jsonb END) x(e)
  WHERE o.deleted_at IS NULL),
src AS (
  SELECT o.id AS order_id, 'CURRENT' AS source, f AS file
  FROM orders o
  CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(o.structured_data->'drawing_current_files') = 'array'
                                               THEN o.structured_data->'drawing_current_files' ELSE '[]'::jsonb END) f
  WHERE o.deleted_at IS NULL
  UNION ALL
  SELECT o.id, 'LAST_TRANSFER', f
  FROM orders o
  CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(o.structured_data->'last_drawing_transfer'->'files') = 'array'
                                               THEN o.structured_data->'last_drawing_transfer'->'files' ELSE '[]'::jsonb END) f
  WHERE o.deleted_at IS NULL
  UNION ALL
  SELECT h.order_id, 'HIST_' || (h.e->>'action') || CASE WHEN k.k = 'previous_current_files' THEN '_PREV' ELSE '' END, f
  FROM hist h
  CROSS JOIN LATERAL (VALUES ('files'), ('previous_current_files')) k(k)
  CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(h.e->k.k) = 'array' THEN h.e->k.k ELSE '[]'::jsonb END) f
  WHERE h.e->>'action' IN ('TRANSFER', 'CONFIRM_RECEIPT', 'REQUEST_REVISION'))
SELECT source, count(*) AS files,
  count(*) FILTER (WHERE jsonb_typeof(file) <> 'object') AS not_object,
  count(*) FILTER (WHERE jsonb_typeof(file) = 'object' AND coalesce(file->>'key', '') !~
        ('^orders/' || order_id || '/(drawing_wizard|drawing|drawing_gateway|attachments|measurement)/')) AS foreign_or_odd_key,
  count(*) FILTER (WHERE coalesce(file->>'key', '') ~ '[^A-Za-z0-9._/-]') AS non_ascii_key,
  count(*) FILTER (WHERE coalesce(file->>'view_url', '') <> ''
        AND file->>'view_url' <> '/api/files/view/' || coalesce(file->>'key', '')) AS odd_view_url,
  count(*) FILTER (WHERE coalesce(file->>'download_url', '') <> ''
        AND file->>'download_url' <> '/api/files/download/' || coalesce(file->>'key', '')) AS odd_download_url
FROM src GROUP BY 1 ORDER BY 1;
-- 주의: 서버 URL 이 key 를 인코딩하면(한글 등) odd_*_url 에 잡힌다 — non_ascii_key 와 함께 읽는다.

-- F1: 전달 취소 삭제 예약 중 지금 현재본이 가리키는 key
SELECT x.id, x.status, x.payload->>'order_id' AS order_id, x.payload->>'object_key' AS object_key
FROM domain_side_effect_outbox x
JOIN orders o ON o.id = (x.payload->>'order_id')::int
WHERE x.effect_type = 'STORAGE_DELETE' AND x.dedupe_key LIKE 'drawing_cancel:%'
  AND EXISTS (SELECT 1 FROM jsonb_array_elements(
                CASE WHEN jsonb_typeof(o.structured_data->'drawing_current_files') = 'array'
                     THEN o.structured_data->'drawing_current_files' ELSE '[]'::jsonb END) c
              WHERE c->>'key' = x.payload->>'object_key');

-- G1: 7/27 뒤 attachments/ 에 올라가 어떤 전달에도 안 실린 도면 행 — 세 무리(업로드 시각 대 마지막 전달 시각)
WITH lt AS (
  SELECT o.id AS order_id,
         max((t->>'transferred_at')::timestamp) FILTER (
           WHERE t->>'transferred_at' ~ '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$') AS last_transfer_at
  FROM orders o
  CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(o.structured_data->'drawing_transfer_history') = 'array'
                                               THEN o.structured_data->'drawing_transfer_history' ELSE '[]'::jsonb END) t
  WHERE t->>'action' = 'TRANSFER'
  GROUP BY o.id)
SELECT CASE
         WHEN jsonb_array_length(CASE WHEN jsonb_typeof(o.structured_data->'drawing_current_files') = 'array'
                                      THEN o.structured_data->'drawing_current_files' ELSE '[]'::jsonb END) = 0
           THEN 'C_NO_CURRENT(다시 올림 목록)'
         WHEN lt.last_transfer_at IS NOT NULL AND a.created_at > lt.last_transfer_at
           THEN 'B_AFTER_LAST_TRANSFER(도면팀 확인 — 숨기지 않음)'
         ELSE 'A_BEFORE_LAST_TRANSFER(숨김 후보)' END AS bucket,
       coalesce(u.team, '?') AS uploader_team,
       count(DISTINCT a.order_id) AS orders, count(*) AS rows,
       (array_agg(a.id ORDER BY a.id))[1:40] AS sample_attachment_ids
FROM order_attachments a
JOIN orders o ON o.id = a.order_id
LEFT JOIN lt ON lt.order_id = a.order_id
LEFT JOIN users u ON u.id = a.user_id
WHERE a.deleted_at IS NULL AND a.category = 'drawing'
  AND a.storage_key LIKE 'orders/%/attachments/%'
  AND a.created_at >= timestamp '2026-07-27'
  AND o.deleted_at IS NULL AND o.status <> 'DELETED'
  AND NOT EXISTS (
    SELECT 1
    FROM jsonb_array_elements(CASE WHEN jsonb_typeof(o.structured_data->'drawing_transfer_history') = 'array'
                                   THEN o.structured_data->'drawing_transfer_history' ELSE '[]'::jsonb END) t,
         jsonb_array_elements(CASE WHEN jsonb_typeof(t->'files') = 'array' THEN t->'files' ELSE '[]'::jsonb END) f
    WHERE t->>'action' = 'TRANSFER' AND f->>'key' = a.storage_key)
GROUP BY 1, 2 ORDER BY 1, 2;
-- 주의: 첨부 탭에서 multipart 로 일부러 올린 '도면'도 같은 경로라 섞인다. uploader_team 은 가르는 힌트일 뿐.

-- G2: 2c-1 배포 뒤 새 도면 업로드 폴더(:deploy_at 에 배포 시각)
SELECT split_part(storage_key, '/', 3) AS folder, count(*)
FROM order_attachments WHERE category = 'drawing' AND created_at >= :deploy_at GROUP BY 1;

-- H1(R5, 측정 완료·참고): 현재본이 비었는데 전달 파일이 있는 주문
SELECT o.id, o.erp_stage_code, o.structured_data->>'drawing_status' AS drawing_status
FROM orders o
WHERE o.deleted_at IS NULL AND o.status <> 'DELETED'
  AND coalesce(jsonb_array_length(CASE WHEN jsonb_typeof(o.structured_data->'drawing_current_files') = 'array'
                                       THEN o.structured_data->'drawing_current_files' END), 0) = 0
  AND EXISTS (SELECT 1 FROM jsonb_array_elements(
                CASE WHEN jsonb_typeof(o.structured_data->'drawing_transfer_history') = 'array'
                     THEN o.structured_data->'drawing_transfer_history' ELSE '[]'::jsonb END) h
              WHERE h->>'action' = 'TRANSFER' AND jsonb_typeof(h->'files') = 'array'
                AND jsonb_array_length(h->'files') > 0);

-- H2(R6, 측정 완료·참고): 06-24 이전 누적 모양 후보
SELECT o.erp_stage_code, o.structured_data->>'drawing_status' AS drawing_status, count(*) AS orders,
       (array_agg(o.id ORDER BY o.id))[1:30] AS sample_ids
FROM orders o
WHERE o.deleted_at IS NULL AND o.status <> 'DELETED'
  AND jsonb_typeof(o.structured_data->'drawing_current_files') = 'array'
  AND jsonb_array_length(o.structured_data->'drawing_current_files') >= 2
  AND EXISTS (SELECT 1 FROM jsonb_array_elements(
                CASE WHEN jsonb_typeof(o.structured_data->'drawing_transfer_history') = 'array'
                     THEN o.structured_data->'drawing_transfer_history' ELSE '[]'::jsonb END) h
              WHERE h->>'action' = 'REQUEST_REVISION')
GROUP BY 1, 2 ORDER BY 3 DESC;

-- I1: 최상위·중첩 도면 상태가 다른 주문(게이트는 최상위 우선 — 2a-2 가 전달 라우트·작업실도 맞춘다)
SELECT nullif(o.structured_data->>'drawing_status', '') AS flat,
       nullif(o.structured_data->'drawing'->>'status', '') AS nested, count(*)
FROM orders o
WHERE o.deleted_at IS NULL AND o.status <> 'DELETED'
  AND jsonb_typeof(o.structured_data->'drawing') = 'object'
  AND upper(coalesce(o.structured_data->>'drawing_status', ''))
      IS DISTINCT FROM upper(coalesce(o.structured_data->'drawing'->>'status', ''))
GROUP BY 1, 2 ORDER BY 3 DESC;

-- J1: 수정요청 취소 횟수(취소가 남긴 유일한 흔적)
SELECT date_trunc('month', timestamp) AS month, count(*)
FROM security_logs WHERE message LIKE '%도면 수정요청 취소%' GROUP BY 1 ORDER BY 1;

-- L1: 2a-2 뒤 관리자 뚫기·도면 미확정 강제 변경 빈도(:since = 2a-2 운영 배포 시각)
SELECT date_trunc('week', e.created_at) AS wk, e.payload->>'route' AS route,
       e.payload->>'drawing_status' AS drawing_status, count(*) AS n
FROM order_events e
WHERE e.event_type = 'ADMIN_OVERRIDE_USED' AND e.created_at >= :since
  AND (e.payload->'gates' ? 'DRAWING_STATUS' OR e.payload->'gates' ? 'COMMAND_REQUIRED')
GROUP BY 1, 2, 3
UNION ALL
SELECT date_trunc('week', e.created_at), 'STAGE_OVERRIDE', e.payload->>'drawing_status', count(*)
FROM order_events e
WHERE e.event_type = 'STAGE_OVERRIDE' AND e.created_at >= :since
  AND e.payload->>'to' IN ('PRODUCTION', 'CONSTRUCTION', 'CS', 'COMPLETED')
  AND upper(coalesce(e.payload->>'drawing_status', '')) <> 'CONFIRMED'
GROUP BY 1, 2, 3
ORDER BY 1, 2;
```

K1(과거 C21 발생)은 원장 누락 점검 Q0(서버 시간대 오프셋)·Q12(전이 순간의 도면 상태)를 그대로 쓴다 — 결과 읽는 법: REQUEST_REVISION = 수정 중에 생산으로 감, TRANSFER = 수령 전 수정본으로 감, NO_DRAWING_HISTORY = 도면 전달 없이 CONFIRM 을 지남(M3). CUSTOMER_CONFIRMED 만 서버 현지 시각이라 Q0 로 보정한다. 원문은 원장 원자료(누락 점검 impact_sql)에 있다. **K1 결과로 PRODUCTION→CONFIRM 강제 역행을 권할 때는 A2 처럼 진행 중 run 이 없는 주문만 권한다**(있으면 생산팀과 먼저 확인).

R2 버킷 버전 관리 확인(측정 ②): 버킷 설정 읽기와 #4080·#5177 참고사진 key 의 이전 버전 목록 조회(읽기 전용). 복구는 별도 승인.

---

## 6. 핫파일 · 래칫 · 핀 · 인벤토리

| 파일 | 지금 | 제약 | 묶음 | 주의 |
|---|---|---|---|---|
| `foms/api/drawing/erp_orders_draftsman.py` | 494줄 | py 500(목록 밖) | 2a-1②·2b | 확정 쓰기는 `drawing_receipt_command.py` 로 이동(줄 감소). M9 +1 |
| `foms/services/erp_quest_display.py` | 494줄 | py 500(목록 밖) | 2a-2 | +약 3줄. 넘치면 규칙을 `quest_approve_cta.py`(120줄)로 |
| `foms/services/orders/order_transition_service.py` | 473줄 | py 500(목록 밖) | 2a-2 | 방어선 +약 15줄 → 약 488. 판정 본문은 게이트 모듈 |
| `foms/services/orders/revision.py` | 415줄 | py 500 | 2a-1② | `lock_order_row` +약 13줄 |
| `foms/services/orders/dashboard_read_model.py` | 491줄 | py 500(목록 밖) | 2c-2 | +2~3줄 |
| `foms/services/construction_dashboard_display.py` | 499줄 | py 500(목록 밖) | 2b | 4.3.4 에서 저장 URL 우선 3줄 삭제(줄 감소만). R3 는 `construction_read_model.py`(230줄)만 |
| `foms/services/orders/stage_override.py` | 414줄 | py 500 | 2a-2 | +약 20줄(Q5 가 "막는다"면 +5) |
| `foms/services/orders/admin_override.py` | 326줄 | py 500 | 2a-2 | drawing_status 스냅샷 +약 3줄 |
| `foms/services/orders/quest_approve_authz.py` | 350줄 | py 500 | 2a-2 | +약 3줄 |
| `foms/services/orders/quest_transition_service.py` | 295줄 | py 500 | 2a-2 | 키워드 통과 +2줄 |
| `foms/services/orders/drawing_receipt_command.py` | 95줄 | py 500 | 2a-1② | 새 도우미. REV-99 allowlist CANONICAL 등재 |
| `foms/api/files/direct_upload.py` | 289줄 | py 500 | 2c-1 | |
| `foms/services/drawing_confirm_cleanup.py` | 244줄 | py 500 | 2c-2 | |
| `foms/services/storage_delete_handler.py` | 102줄 | py 500 | 2b | 공용 핸들러 — 다른 도메인 분기 무변경 |
| `foms/web/drawing/tablet_sheet.py` | 147줄 | py 500 | 2c-1·2d | |
| `static/js/foms/drawing-handoff.js` | 147줄 | js 300 | 2d | |
| `templates/drawing/partials/workbench_mobile_handoff.html` | 307줄 | `DETAIL_TOP_BLOCKS=5` | 2d | 새 section·details 금지 |
| 새 파일 3개(`confirm_drawing_gate.py`·`drawing_revision_files.py`·`drawing_key_safety.py`) | — | py 500 | 2a-2·2b | 각 150줄 이하 목표 |
| 새 테스트 도우미 `tests/support/confirm_seed.py` | — | py 500 | 2a-2 | |
| 새·바뀐 테스트 파일 | — | py 500 | 전부 | C21 파일 318줄 — 새 경우는 새 파일로 |
| known large(크기 자유) | — | — | — | erp_orders_structured.py · quest.py · production/orders.py · orders/status.py · orders/field_update.py · erp_orders_revision.py · erp_orders_drawing.py · workbench.py · order_routes.py · share.py · erp_mobile_order_display.py · erp-order-shared.js · erp-dashboard-drawing.js |

**기준값·인벤토리**
- failopen `_SWALLOW_BASELINE = 172`(`tests/domains/test_failopen_inventory.py:47`, **정확히 같아야 함** :202-211) — 2b 에서 **169**(draftsman :491 · drawing :672 · drawing :786). 여러 창 충돌 주의 — 반영 직전 origin 기준 재계산. `docs/harness/foms_failopen_inventory.json` baselines 도 같이.
- order_mutation_writer 인벤토리 baseline `{total: 74, external: 28}` — 2a-1② 에서 allowlist 2건 등재(`erp_orders_revision.py`·`drawing_receipt_command.py` CANONICAL) + `erp_orders_drawing.py` 사유 문구 수정 → 예상 `{total: 74, external: 24}`. `test_rev_99.py:221-225` 가 baseline == 목록 길이를, `:192` 가 (path, lineno, kind) 집합 일치를 단언.
- state_writer·audit_coverage·api_error_leak 인벤토리 — 새 쓰기 없음, 줄번호만 밀림. **커밋 전 `python tools/harness/refresh_inventories.py` 필수**(줄번호만 바뀐 것은 되쓰지 않으니 필요하면 `*_scan.py` 직접 실행).
- 파일 크기 래칫 `tests/harness/test_file_size_ratchet.py`(py 500 · js 300, known large 목록 `tests/harness/file_size_baseline.json`).

**핀**(같은 날 같은 글자 재사용 금지 — 구현일 날짜 + 다음 글자)
| 자산 | 지금 | 묶음 |
|---|---|---|
| `js/orders/erp-order-shared.js`(`erp_order_js.html:30`) | 20260929a | 2a-1①(보존 목록) · 2a-1②(409 문구) · 2c-2(R4) — 묶음마다 다시 올림 |
| `js/orders/erp-dashboard-entry.js`(`layout_scripts.html:1634`) + 그 안 detail-dom(:13) | 20260929a · 20260929a | 2a-2(일괄 알림) · 2b(취소 안내 문구) · 2d(죽은 코드) |
| entry 안 `erp-dashboard-gateway.js`(:9) | 핀 없음 | 2b(새로 붙임) |
| entry 안 `erp-dashboard-attachments.js`(:10) | 핀 없음 | 2c-2(새로 붙임) |
| entry 안 `erp-dashboard-drawing.js`(:11) | 20260909a | 2b(취소 확인창 문구) |
| `js/runtime/upload-progress.js`(`layout_scripts.html:113`) | 20260820a | 2c-1 |
| `js/foms/drawing-handoff.js`(`workbench_detail_body.html:3023`) | 20260929a | 2d |
| `js/foms/foms-admin-override.js` | 20260921a | 변경 없음(2a-2 에서 PC 생산 보드에 새로 싣기만) |
| `css/components/foms-drawing-mobile.css`(@import + share 2곳 + 부모 surfaces `layout_head.html:239` + ASSET_PIN_LOCK) | 20260929b | 2d |

---

## 7. 사용자가 정해야 할 질문 (5개)

> **사용자 답(2026-09-29)**: Q1 막는다 · Q2 막는다 **+ 생산이 수정요청을 알 수 있게 배지**(비목표였던 생산 보드 '도면 수정 중' 배지를 2a-2 범위로 넣음) · Q3 추천안(답 없음 → 허용+기록) · Q4 목록 확인 뒤 결정(2c-2 적용 때 따로 여쭘) · Q5 허용 + 경고·기록. 운영 측정 ① 실행 결과: C1 1건(#4058, 6월 옛 흐름 확정 — 폼 되돌림 아님) · C2 0건 · C3 1건(#5370, 전달 뒤 폼 저장 2회 — 상태·현재본 모두 정상) · C3b 0건 → **실제 피해 0건**.

**Q1. 주문 목록의 '상태 한꺼번에 바꾸기'나 상태 칸을 직접 고쳐서 '도면 → 고객컨펌', '고객컨펌 → 생산'으로 넘기는 것을 막을까요?**
- 추천: **막는다.** 정식 버튼(도면 수령 확정, 고객 컨펌 완료)으로만 넘긴다. 관리자는 주문 상세의 그 버튼에서 이유를 적고 넘길 수 있다.
- 이유: 이 길은 "도면을 받았는지", "고객이 컨펌했는지"를 전혀 확인하지 않는다. 같은 일을 하는 정식 버튼이 이미 있다. 막기 전에 최근 90일 동안 이 길을 몇 번 썼는지 먼저 세어 보여 드린다(측정 B1).

**Q2. 아직 만들기 시작하지 않은 주문(생산 대기)에 도면 수정요청이 들어오면, [제작 시작] 버튼도 막을까요?**
- 추천: **막는다**(관리자만 이유를 적고 가능). 이미 만들기 시작한 주문은 막지 않고 지금처럼 알림만 간다. 막힌 버튼에는 "영업 담당 OOO 이 새 도면을 확정하면 시작할 수 있어요"라고 보인다.
- 이유: 생산 보드에 '도면 수정요청 · 생산 중 변경' 표시는 뜨지만 [제작 시작] 버튼은 그대로 눌린다. 표시를 못 보고 누르면 옛 도면으로 가구를 만든다.

**Q3. 도면팀이 이미 "반영 완료"를 누르고 고치는 중이어도, 영업이 수정요청을 취소할 수 있게 둘까요?**
- 추천: **둔다.** 대신 취소한 사실·이유·원래 요청을 기록으로 남기고, 도면팀에 지금처럼 알린다. 참고사진도 지우지 않는다.
- 이유: 고객이 요청을 거둬들이는 일이 있다. 막으면 도면팀이 괜히 다시 보내야만 풀린다. 문제는 취소 자체보다 "기록이 사라지는 것"이었다. (이 답은 2b 를 만들기 전에 필요하다. 답이 없으면 추천대로 만든다.)

**Q4. 8~9월에 올렸지만 전달되지 못한 도면 파일 53개를 어떻게 할까요?**
- 추천: 세 무리로 나눠서 목록을 먼저 보여 드리고, 하나씩 정한다.
  - (가) 그 주문의 마지막 전달**보다 먼저** 올렸고, 이미 전달된 도면이 있는 파일 → 고객 링크·생산 화면에서 **숨긴다**(휴지통으로. 파일은 남아 언제든 되살릴 수 있다).
  - (나) 마지막 전달**보다 뒤에** 올린 파일 → **숨기지 않는다.** 도면팀이 보내려다 막힌 최신 도면일 수 있어서, 도면팀에게 "이게 보내려던 최신본인지" 확인받는다.
  - (다) 전달된 도면이 하나도 없는 주문 → 도면팀에 목록을 드려 다시 올리게 한다(고친 뒤로는 올리면 바로 전달된다).
- 이유: 대부분은 전달 창에서 올렸다가 막힌 파일이지만, 일부는 첨부 탭에서 일부러 올린 파일일 수 있다. 무작정 숨기면 최신 도면을 가려 옛 도면으로 만들 위험이 있고, 지우면 되돌릴 수 없다. 운영 데이터를 바꾸는 일이라 목록을 보고 승인받은 뒤 바꾼다.

**Q5. 팀장(MANAGER)이 '단계 강제 변경'으로, 도면이 아직 확정되지 않은 주문을 생산 단계로 넘기는 것을 허용할까요?**
- 추천: **허용하되 경고하고 기록한다.** 강제 변경 창에 "도면이 아직 확정되지 않았어요 — 옛 도면으로 생산될 수 있어요"를 띄우고, 넘긴 순간의 도면 상태를 기록으로 남긴다. 몇 번이나 이렇게 넘겼는지 나중에 세어 볼 수 있다(측정 L1).
- 이유: 급한 현장 사정(구두 컨펌 등)으로 넘겨야 할 때가 있고, 팀장은 이미 이유를 적고 한 번 더 확인해야 강제 변경을 할 수 있다. 막으면 관리자만 풀 수 있어 일이 멈출 수 있다. 다른 선택: "막는다" — 그러면 도면이 확정 안 된 주문을 생산 이후로 넘기는 것은 관리자만 할 수 있다.

---

## 8. 기본안으로 정한 것 (말씀이 없으면 이대로 간다)

- M3: 생산으로 넘어가는 조건은 **허용 목록**(수령 확정일 때만). 도면 기록이 없는 옛 주문은 관리자 뚫기 또는 **근거가 있는 경우만** 별도 승인 보정(A1).
- M16: 수정요청이 오면 고객확인 표시를 무효로, 그 요청을 취소하면 되살린다.
- M1: 폼 저장이 도면 키뿐 아니라 **도면 배정·퀘스트·고객확인(blueprint)** 도 못 바꾸게 잠근다(같은 뿌리). 2a-1① 을 긴급 묶음으로 먼저 운영에 올린다.
- M5: 이상한 파일 경로는 조용히 버리지 않고 400 으로 거절한다(files 키가 없으면 지금처럼 빈 목록).
- 화면은 어디서도 저장된 파일 URL 을 믿지 않고 key 로 다시 만든다. 옛 URL 을 지우는 운영 보정은 하지 않는다(E1 은 측정만).
- 첨부 탭에서 **지금 전달된 도면** 삭제는 409 로 막고, 교체된 옛 도면은 행만 휴지통으로 보내고 파일은 남긴다 — 휴지통에서 되살릴 수 있게 복구 API 를 함께 고친다.
- 전달 취소로 회수하는 파일은 **7일 뒤** 지우고 그때 다시 확인한다. 거둬들인 도면의 첨부 행은 지금처럼 지운다(고객·생산 화면에 안 보이게).
- 수정요청 취소는 파일을 지우지 않는다.
- **R4: ERP 주문의 '첨부' 탭에서는 교체된 옛 도면도 '교체됨' 표시로 흐리게 보인다.** 고객 링크·생산·시공 화면은 지금처럼 숨긴다.
- 관리자 뚫기는 ADMIN 만, 사유 필수, 기록 남김(그 순간의 도면 상태 포함). 관리자는 [고객 컨펌 완료]·[제작 시작] 에서 경고 모양 버튼으로 뚫는다. 일괄·상태 칸에는 관리자 재시도를 붙이지 않는다. MANAGER 긴급 오버라이드(권한 축)는 새 게이트를 풀지 못한다. MANAGER 의 단계 강제 변경은 Q5 답을 따른다.
- 새 엔드포인트는 만들지 않는다(선택 인자 `include_superseded`, 선택 본문 필드 `reason` 만 추가).
- 결정은 구현 커밋에서 `docs/harness/policy/DECISIONS.md` 에 한 줄씩 기록한다(M3 허용 목록 · Q1·Q2·Q5 결과 · 수정요청 취소 파일 보존 · 첨부 탭 현재 도면 삭제 금지 · 파일 보존 휴지통 복구 · 한글 key 표시 규칙 · 도면 상태 판정 함수 단일화).

---

## 9. 완료 기준 (검증 명령)

모두 워크트리에서 `cd <워크트리> && …` 로 시작하고, 종료 코드는 파이프 뒤에서 읽지 않는다(`> out.txt 2>&1; echo EXIT=$?`).

**공통(각 묶음마다)**
```
python -c "import app; print('APP_OK')"                                        # APP_OK
python tools/harness/refresh_inventories.py; echo EXIT=$?                      # 0, 바뀐 인벤토리는 커밋에 포함
PYTHONIOENCODING=utf-8 python -m pytest -q -p no:cacheprovider \
  tests/domains/test_failopen_inventory.py tests/domains/test_rev_99.py \
  tests/domains/test_state_guard.py tests/harness/test_file_size_ratchet.py \
  tests/harness/test_hook_log_hygiene.py > gate.txt 2>&1; echo EXIT=$?        # 0
node --check <바뀐 JS 파일마다>; echo EXIT=$?                                  # 0
python tools/perf/perf_scan.py --guard; echo EXIT=$?                            # 0
python -m pytest -q --ignore=tests/visual --ignore=tests/harness -p no:playwright \
  -n auto --dist loadfile > lane.txt 2>&1; echo EXIT=$?                        # 0 (CI 본 레인)
python -m pytest tests/harness -q > harness.txt 2>&1; echo EXIT=$?              # 0 (순서대로, xdist 금지)
powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1; echo EXIT=$?        # 0 (push 직전)
```

**2a-1①(긴급)**: 새 `test_structured_put_server_locked_keys.py` 초록((a)(a')(b)(c)(e)(f) + (d) 기존 동작) · 음성 대조(잠금 제거 시 (a)(a')(b)(c)(f) 빨강 — ② 없이 확인) · **뒤집은** `test_erp_order_shared_form_scripts.py`(`test_shared_erp_order_js_does_not_resend_server_locked_keys`) 초록 · `test_erp_orders_structured_put.py`·`test_channel_push_trace.py`·`test_drawing_revision_cancel.py`·`test_drawing_transfer_attachments.py`·`test_drawing_confirm_keeps_files.py`·`test_drawing_confirm_cleanup.py`·`test_drawing_wizard_api.py` 초록 · 스테이징: 폼을 열어 둔 채 다른 창에서 수정요청 → 폼 저장 → 도면 상태 RETURNED 유지.

**2a-1②**: 도면 라우트 5곳 버전 +1·오래된 If-Match 409 · PG 레인 `test_drawing_route_row_lock_pg.py` 초록(로컬 클러스터 — 메모리 "PG 레인 로컬 실행법") + 음성 대조 · REV-99 allowlist 2건 등재·인벤토리 재생성 뒤 `test_rev_99.py` 초록(external 값은 재생성 결과를 커밋 메시지에 적음).

**2b**: 프로브 P2·P2b·P6(두 벌)을 옮긴 테스트 초록 · 태블릿 files 없음 200 · `test_drawing_revision_cancel.py`(뒤집은 테스트 포함) · `test_upload_auth.py` · `test_drawing_mobile_revision_refs_and_cancel.py` · 핸들러 재확인 테스트 · **복구 보강 테스트(예약 없는 `file_retained` 행 → 200)** · 모바일 도면 방·시공 카드 URL 주입 렌더 테스트 · failopen **169** 잠금.

**2c-1**: 프로브 P3 을 옮긴 테스트 초록 · C9 실제 업로드 끝-끝(xfail 뗌) · M14-a 화면 == 서버 · `test_share_hides_superseded_drawings.py`·`test_construction_drawing_only_sd_filter.py` 초록 · 스테이징에서 전달 창 직접 업로드(PC·폰) → 전달 성공 · 측정 ③ G2.

**2a-2**: `test_bugrepro_c21_confirm_quest_while_returned.py` 에서 xfail 표시 0개로 **8 passed** · `test_confirm_drawing_gate.py`(한글 단계·엔진 방어선·입구 전수 가드·세 경로 관리자 뚫기·일괄 전부 차단 포함) 초록 · PG 레인 `test_confirm_gate_concurrency_pg.py` 초록 + 음성 대조 · `tests/support/confirm_seed.py` 로 고친 시드 파일 전부(PG 레인 `test_state_prod_pg.py`·`test_order_transition_service.py` 포함) 초록 · 스테이징 gstack browse: CONFIRM 수정요청 **직후 그리드 새로고침**에서 PC 그리드·모바일 상세·큐 카드·태블릿 시트에 비관리자는 이유 줄 / 관리자는 경고 버튼 → 사유 시트 → 통과, PC 생산 보드 관리자 재시도, 수령 확정 직후 막힌 이유 줄이 바로 사라짐, 타임라인 '전용 버튼 경로'·도면 상태 기록.

**2c-2**: R3 개수 == 목록 · `tests/performance/test_perf_regression_guard.py` 초록 · R4 인자 테스트·정적 계약 · `test_superseded_drawing_rows_hidden.py` 초록 · R1 스크립트 dry-run 테스트 · (운영 적용은 별도 승인 뒤) 적용 결과 목록과 복구 확인.

**2d**: `test_drawing_mobile_asset_pin_freshness.py`·`test_drawing_mobile_back_to_workbench.py`·`test_drawing_workbench_mobile.py`·`test_drawing_room_push_workbench_ui.py` 초록 · R11 보강 테스트 · 390px 실화면 캡처(반영 체크 토글·막힌 이유·도면방 보내기·관리자 바 가림 없음).

**완료 선언 조건**: push 뒤 CI green 까지(`ci_watch` 는 런 생성 뒤 확인) · `docs/AI_STATUS.md` 상단(4,000자 예산)·`docs/AI_CHANGELOG.md`·원장 판정표 "Spec" 열 갱신. production 반영은 묶음마다 사용자 명시 요청 뒤 `promote_own_to_production.py`.

---

## 10. 확인 필요 (코드·실행으로 확인하지 못한 것)

1. §5 측정값 전부 — 미측정(H1·H2·C2 는 승격 직전 0).
2. 폼 JS 밖에서 PUT 으로 `quests`·`blueprint`·도면 배정을 정당하게 새로 쓰는 길이 없는지(검색상 없음 — 전체 레인으로 확인).
3. 도면 라우트를 `execute_order_mutation` 으로 감쌀 때 receipt·캐시 intent 가 알림 흐름과 충돌하지 않는지(PG 레인).
4. R4: `order-detail-fragment.js:298` 을 쓰는 화면이 내부용인지.
5. M5 참고 파일 개수 상한(20)과 화면 업로드 상한.
6. 공용 업로드 도우미(`upload-progress.js`)와 ERP 첨부 탭 direct 경로가 세션 요청에 `category` 를 싣는지 — 서버 폴더 재작성이 이 값에 기댄다(첨부 탭 direct 는 이미 폴더에 category 를 넣어 영향 없음).
7. 현장에서 경미한 수정이 남은 채 구두 컨펌하는 관행이 있는지(있으면 관리자 뚫기·팀장 강제 변경으로 흡수 — L1 로 빈도 확인).
8. 옛 템플릿이 모르는 action(`REVISION_CANCELLED`)을 그리는 모양(되돌리기 때).
9. `quest.py` 의 `datetime.datetime.now()` 가 Railway 에서 UTC 인지 — 비목표지만 M16 `invalidated_at` 은 UTC 로 쓴다.
10. `security_logs.timestamp` 는 DB 기본 `now()`(세션 시간대) — Railway PG 가 UTC 인지(C3 의 `:deploy_at` 비교).
11. `drawing_wizard.versions` 항목이 산출 PNG key 를 가리키는지(§4.3.5 `drawing_keys_in_use` 범위).
12. 모바일 큐 카드·태블릿 시트 화면에 `foms-admin-override.js`·사유 시트가 실려 있는지(없으면 싣는다).
13. 강제 변경 창을 여는 템플릿이 도면 상태를 넘길 수 있는 위치(§4.2.8).
14. 마법사 시트 재저장이 옛 pending key 를 커밋 뒤 동기 삭제한다(`foms/api/drawing/wizard.py:1015-1019`). pending 을 비우지 않고 그 key 를 전달한 경우(API 로 files 에 직접 넣기) 현재 도면 파일이 지워질 수 있다 — 원장 밖, 코드 추정. 재현되면 공통 판정 적용 대상. → **2026-09-30 반영**: 재저장·스냅샷 가지치기의 옛 파일 삭제가 `split_deletable_keys(scope='drawing')` 를 거치고, 마법사 부가 쓰기 3곳이 행 잠금 + 버전 +1 로 바뀜(DECISIONS 2026-09-30).

---

## 11. 리뷰 반영 기록

리뷰 A(21건)·리뷰 B(17건) 전량. P0 없음. P1·P2 는 전부 반영. P3 는 반영 또는 받지 않은 이유.

| # | 등급 | 지적 | 처리 |
|---|---|---|---|
| A-1 | P1 | 1차가 이미 운영(cherry-pick 이라 조상 검사로 오판) — 순서 의존 7 이 운영에서 열림, "승격 전" 측정 시점 지남 | 반영 — §0 첫 줄, §2(production `4bc407c49`·patch-id), §3(2a-1① 긴급 단독 묶음), §4.1, §5(측정 ① 지금 · C3 새로), §10 옛 2번 삭제 |
| A-2 | P1 | 게이트가 원문 단계값을 비교해 '고객컨펌' 주문에서 뚫림, 뒤 방어선 없음 | 반영 — §4.2.2 정규화 + 전이 엔진 방어선(`drawing_gate_waived`), :563 blueprint 조건도 정규화, 한글 단계 테스트, A1 에 한글 단계 칸 |
| A-3 | P1 | 예약 없는 휴지통 행은 복구 API 가 거짓 문구로 거절 — Q4 약속 무너짐 | 반영 — §4.3.6 복구 보강(`file_retained` 이벤트 표시 + 존재 확인), R1 스크립트 같은 표시, 테스트, §3 2c-2 전제에 2b |
| A-4 | P2 | REV-99 주장 오류(allowlist 등재 상태·파일 단위 분류·새 파일 EXTERNAL·전달 쓰기 오표시) | 반영 — §4.1 ② REV-99 절 재작성(파일별 영향·예상 24·refresh 필수), §6 |
| A-5 | P2 | 감싸기만으로 lost update 못 막음(잠금 전 deepcopy·dirty 객체), C21 게이트 TOCTOU | 반영 — `lock_order_row` 로 라우트 첫 조회 잠금(§4.1 ②·§4.2.2·§4.2.3), 콜백 전 dirty 금지, 엔진 방어선, PG 두 세션 테스트 2개 |
| A-6 | P2 | 2c(M10)가 2a-2 뒤라 게이트가 주문을 CONFIRM 에 가둠 | 반영 — 2c 를 2c-1(M10·M14-a)/2c-2 로 나누고 2c-1 을 2a-2 앞에, 2a-2 전제에 "M10 운영" |
| A-7 | P2 | 잠금 테스트가 버전 올림에 가려짐, (d)는 결함 테스트 아님 | 반영 — (a) If-Match 없이·(a') 최신 버전 경우로 재작성, 음성 대조를 ② 무관하게, (d) 기존 동작 표시 |
| A-8 | P2 | 폼 JS 보존 목록에서 빼면 기존 계약 테스트 빨강 | 반영 — §4.1 ① 테스트 뒤집기(블록 잘라 not in), §9 2a-1① |
| A-9 | P2 | 폼이 도면 배정을 되돌림(전달 권한 기준값) | 반영 — `SERVER_LOCKED_SUBKEYS` 로 `assignments.drawing_assignee_user_ids`·`drawing_assignees` 잠금, 테스트 (f), 비목표 사유 수정(영업 담당은 별건 — 이유 기재), §4.10 전제 |
| A-10 | P2 | 모바일 도면 방 현재 도면·시공 카드가 저장 URL 우선 | 반영 — §4.3.4 에 `_build_handoff_files`·`_url_from_file_entry` 추가, E1 범위를 현재본·마지막 전달·이력 전부로 |
| A-11 | P2 | 공통 판정 (1)이 `drawing_wizard` 를 모름 — 회수 중단·P6 잘못된 이유로 초록 | 반영 — `is_own_order_key`(서버 폴더 전부) + scope='drawing', P6 두 벌·음성 대조 정의 |
| A-12 | P2 | 필드 경로에 뚫기 공통 기록 없음, 일괄 전부 차단이어도 success | 반영 — §4.2.4 필드 분기 안 즉시 기록, 일괄 success·메시지, 테스트 2종 |
| A-13 | P2 | files 없음 400 이면 태블릿 수정요청 전부 깨짐, 취소 본문 없음 415 | 반영 — §4.3.2 계약(없음/null → []), §4.4 `get_json(silent=True)`, 태블릿·본문 없음 회귀 테스트 |
| A-14 | P2 | 수정요청 등이 PRODUCTION family 캐시를 안 지워 화면·서버 불일치 | 반영 — §4.2.5 캐시 무효화 5 라우트(②에 기대지 않음), R3 캐시 확인 닫음, 스테이징 새로고침 확인 |
| A-15 | P3 | 취소 안내 문구 3곳이 "파일 삭제"라고 거짓 안내 | 반영 — §4.4 문구 3곳 + 핀 |
| A-16 | P3 | 입구 가드가 override 경로(PRODUCTION_UNCOMPLETE 등)를 놓침 | 반영 — to_values PRODUCTION 전 command 고정 표 + 허용 목록, state_writer 파일 집합 고정, 뚫기 이벤트에 도면 상태 자동 기록 |
| A-17 | P3 | "서버 도면 라우트는 최상위만" 근거 부분 오류 | 반영 — §4.2.1 근거를 쓰기/읽기로 나눠 사실대로, 전달 라우트·작업실·알림 게이트도 같은 함수, I1 결과 처리 |
| A-18 | P3 | 막혔을 때 팀 버튼 유지·sd 없는 호출·다른 quest 화면 누락 | 반영 — `approvable_teams` 같은 규칙, `sd=None` 막지 않음 명시, 나머지 3화면 확인 항목 |
| A-19 | P3 | 핀 표 누락(attachments·erp-order-shared 재핀), failopen 목표 불일치, import 없음 | 반영 — §6 핀 표, §4.6 169 확정·import 한 줄 |
| A-20 | P3 | 공용 시드 헬퍼가 없음, 목록 누락(PG 포함) | 반영 — `tests/support/confirm_seed.py` 신설 + 파일별 목록(누락 6개·PG 2개 추가) |
| A-21 | P3 | 타임라인 라벨 '도면 전용 경로'가 고객컨펌 뚫기를 도면 뚫기로 보이게 함 | 반영 — '전용 버튼 경로'로 변경(단언 테스트 없음 확인) |
| B-1 | P1 | 기준선 낡음(1차 운영·HEAD·R5/R6/R10 측정 완료 누락) | 반영 — A-1 과 같음 + HEAD `da99a9916`, H1·H2·C2 측정 완료 표시, C1·C2 재측정을 측정 ①·② 요청으로 묶음 |
| B-2 | P1 | (1) 판정이 뒤집혀 마법사 전달 취소 행이 남아 고객·생산에 보임 | 반영 — A-11 + §4.5 행/파일 판정 분리(`history_referenced_keys`), 마법사 key 끝-끝 테스트 |
| B-3 | P2 | 2a-2 가 M10 보다 먼저면 폰 담당 주문이 갇힘 | 반영 — A-6 과 같음 |
| B-4 | P2 | 관리자 뚫기가 화면에서 닿지 않음 | 반영 — ADMIN 경고 버튼 유지(기존 retry 연결), PC 생산 보드 retry·스크립트 싣기, 일괄·상태 칸은 전용 버튼으로 안내(표·§8·§9 수정), 화면 계약 테스트 |
| B-5 | P2 | MANAGER 강제 변경이 목표 1·§8 과 다름, 입구 가드가 raw 경로 못 잡음 | 반영 — 목표 1 문구 수정, Q5 신설, §4.2.8(경고·스냅샷, "막는다" 대안), 입구 가드에 state_writer 파일 집합, 측정 L1 |
| B-6 | P2 | 예약 없는 tombstone 은 복구 불가(Q4 근거 거짓) | 반영 — A-3 과 같음 |
| B-7 | P2 | G1 이 마지막 전달 뒤 업로드(보내려던 최신본)까지 숨김 후보로 | 반영 — G1 세 무리 SQL, §4.7 R1 세 무리, Q4 문구 |
| B-8 | P2 | Q2 이유(배지 안 뜬다)가 사실과 다름 | 반영 — Q2 이유를 "배지는 뜨지만 버튼은 눌린다"로, 비목표 배지 문장 보정 |
| B-9 | P2 | 생산팀용 차단 문구가 없음 | 반영 — `production_block_reason`(영업 담당 이름 포함), (a)(b) 공통, 풀림 알림은 비목표 한 줄 |
| B-10 | P3 | 409 증가가 견적 자동 저장·알림톡 저장에도 뜸, 문구가 "다른 사용자" | 부분 반영 — 두 흐름을 부작용에 기록, 409 확인창에 "도면·퀘스트는 서버가 지킨다" 한 줄 추가. **받지 않음**: 409 응답에 변경 종류 싣기(충돌 경로에 receipt 조회를 더해야 하고 ①이 데이터를 지키므로 이득이 작다), 견적 자동 저장의 상태 줄 전환(견적 화면 별건 — 비목표에 기록) |
| B-11 | P3 | 중첩 상태 우선 읽기로 게이트·전달·작업실이 다른 값, I1 처리 미정 | 반영 — A-17 과 같음 + I1 ≠ 0 이면 2a-2 전 보정(별도 승인)을 전제로 |
| B-12 | P3 | M3 보정 "사실대로 채움"이 없던 확정을 만들 수 있음 | 반영 — §4.2.6 근거 있는 경우만 보정, 없으면 관리자 뚫기만 |
| B-13 | P3 | E1 URL 보정 불필요, 한글 key 링크 소실 결정 미노출 | 반영 — E1 측정만(§4.3 옛 데이터·§8), 한글 key 표시 규칙 한 줄(§4.3.4) |
| B-14 | P3 | failopen 기준값 자기 모순(170 대 168) | 반영 — §4.6·§6·§9 모두 169(:741 은 이 묶음에서 안 고침) |
| B-15 | P3 | 관리자 일반 쓰기 뚫기에 도면 상태 기록 없음, 빈도 점검 없음 | 반영 — `record_admin_override_event` payload 에 drawing_status 스냅샷, 측정 ④ L1 |
| B-16 | P3 | CLAUDE.md 절차(측정 요청 단위·승격 절차·cherry-pick 순서·Q3 전제) 미기재 | 반영 — §3 승격 절차·순서, §5 측정 묶음 4개(요청 1건씩), 2b 전제에 Q3 |
| B-17 | P3 | 원장 대조 상태 줄 누락, 94px 가림·R2 버전 관리·K1 run 조건 빠짐 | 반영 — §0.1 원장 대조표, 94px → 2d(§4.12), R2 버전 관리 → 측정 ②, K1·§4.2 옛 데이터에 진행 중 run 조건 |
