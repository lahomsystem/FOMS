# 2026-09-03 AS 상태 증발 2건 — 축 투영 ERP 게이트 이탈 + 열린 AS 건 status 봉인

> 유형: 데이터 사고  ·  상태: 종결
> 작성 2026-09-07. 사후 등재 문서 — 사고 당시 기록이 아니라 저장소 근거로 재구성했다.

이 사고는 **2026-08-14 사고의 재발 계열**이다. 08-14 는 목록 술어가 파생값 `orders.status`
단독이라 났고(`docs/incidents/2026-08-14-as-dashboard-bulk-complete-vanish.md`), 그 구조적 원인을
없애려고 2026-08-18 AS-AXIS-01 이 축 투영 `as_axis_status` 를 만들었다(`docs/AI_CHANGELOG.md:49`).
이번 두 건은 **그 새 사본이 게이트 밖으로 새고**(①), **옛 컬럼이 여전히 무방비로 덮이는**(②)
두 자리에서 났다.

## 1. 요약 5축

| 축 | 내용 |
|---|---|
| 유형 | 데이터 사고 — AS 상태가 두 화면에서 증발(운영 5건 복구) |
| 원인 축 | ① `as_axis_status` 투영만 `sync_erp_flat_columns` 의 `is_erp_order` 게이트 **안**에 있어 비ERP AS 주문의 축이 옛 값으로 동결 ② 지방 보드 체크리스트 자동 승격이 쏜 `status=SCHEDULED` 를 서버가 **열린 AS 건을 안 보고** 덮음(`docs/AI_CHANGELOG.md:10`) |
| 복구 | 운영 데이터 **5건 복구 완료**(백업 `C:/tmp/as_recovery_backup_20260903.json`, 사후 잔여 결함 0)(`docs/AI_CHANGELOG.md:10`, `docs/AI_STATUS.md:18`) |
| 구조 변경 여부 | 있음. `sync_as_axis_column()` 분리(게이트 앞 호출) + `as_overlay_outranks_status_write()` 신설 + 프런트 `checkAllCompleted` 가 AS 행 3종 제외. 계약 테스트 13종 신규 |
| 재발 여부 | **회귀 커밋 없음(잠복)** — 이 사고는 새로 생긴 것이 아니라 오래 잠복해 있던 자리다(`docs/AI_STATUS.md:18`, `docs/AI_CHANGELOG.md:10`) |

## 2. 증상

사용자 제보 2건이다(`docs/AI_CHANGELOG.md:10`).

**① AS완료인데 미완료 탭.** 초록 `AS완료` 뱃지를 단 채 미완료 탭에 남았다. 탭 술어는 축을,
뱃지는 `status` 를 보기 때문에 한 화면 안에서 두 값이 어긋난 채로 보였다.
운영 정확히 **3건**(#1315·#1119·#1706), **전부 `is_erp_order=False`**.

**② AS 접수했는데 지방 AS 섹션에서 사라짐.** 지방 AS 섹션 술어와 ERP `AS: 접수` 뱃지·재접수 버튼이
모두 같은 컬럼을 읽어 **두 화면에서 동시에 증발**했다. 그리고 재접수는 409(열린 cycle)라
**화면에서 복구가 불가능**했다 — 사용자가 스스로 되돌릴 길이 없는 모양이다.

## 3. 타임라인

| 시각 | 사건 | 근거 |
|---|---|---|
| 2026-07-13 | AS 행이 체크박스 섹션에 들어감(`0b4ab4546`) — ②의 잠복 시작 조건 | `docs/AI_CHANGELOG.md:10` |
| `e23fe359a` 이전 | 덮어쓰기 코드는 그 전부터 존재 | `docs/AI_CHANGELOG.md:10` |
| 2026-08-31 | 주문 #4816 AS 접수 — 이후 09-03 06:27 까지 정상이었다 | `docs/AI_CHANGELOG.md:10` |
| 2026-09-03 06:27 | #4816 증발(②). 감사 원장에 체크박스 저장 **+0.18~0.22초 뒤** `ORDER_STATUS_CHANGED: AS_RECEIVED -> SCHEDULED` | `docs/AI_CHANGELOG.md:10` |
| 2026-09-03 | 사용자 제보 2건 → CEO 총괄 멀티 에이전트(각 9에이전트) 조사, 운영 실데이터로 원인 확정 | `docs/AI_CHANGELOG.md:10` |
| 2026-09-03 | 수정·검증·운영 반영(PR #288, production `ac23a6c16`), 운영 5건 복구 | `docs/AI_STATUS.md:18`, `docs/AI_CHANGELOG.md:10` |

①이 언제부터 동결돼 있었는지(첫 발생 시각) — `미상(근거 없음)`.
②의 06:27 과 +0.18~0.22초는 감사 원장이 남긴 실측값이다.

## 4. 근본 원인

### ① 축 투영이 ERP 게이트 안에만 있었다

AS 완료 커맨드(`_reproject_and_sync`)는 `order.status`·`as_completed_date` 를 **게이트 밖에서
무조건** 쓰는데, `as_axis_status` 투영만 `sync_erp_flat_columns` 의 `is_erp_order` 게이트 **안**에
있었다. 그래서 비ERP AS 주문은 축이 옛 `RECEIVED` 로 **동결**됐다(`docs/AI_CHANGELOG.md:10`).

- 탭 술어는 축을, 뱃지는 `status` 를 본다 → 한 화면에서 두 값이 갈렸다.
- **음성 대조군으로 확정했다**: 같은 분·같은 `AS_COMPLETE` 를 탄 ERP 주문 2건은 정상이었다.
  갈림 변수가 `is_erp_order` **하나**임을 이 대조로 못박았다.
- **자가 회복 경로도 없었다**: 부팅 백필은 `is_erp_order=True` 만 보고, models 훅은 `before_insert`
  전용이다. 즉 한 번 동결되면 스스로 풀리지 않는다.

### ② 열린 AS 건 위로 물류 코드가 그대로 얹혔다

지방 보드 체크리스트 자동 승격(`checkAllCompleted`)이 `status=SCHEDULED` 를 쏘면, 서버가
**열린 AS 건을 안 보고 덮었다**. `SCHEDULED` 는 물류 보드 코드라 stage-override 엔진과 canonical
엔진을 **둘 다 건너뛰고 `setattr` 직행**이었다(`docs/AI_CHANGELOG.md:10`).

- 지방 AS 섹션 술어와 ERP `AS: 접수` 뱃지·재접수 버튼이 모두 그 컬럼을 읽어 두 화면 동시 증발.
- 재접수는 409(열린 cycle) → 화면에서 복구 불가.
- 인과는 감사 원장이 그대로 담았다: 체크박스 저장 **+0.18~0.22초 뒤** `ORDER_STATUS_CHANGED:
  AS_RECEIVED -> SCHEDULED`.
- **회귀 커밋은 없다(잠복).** 덮어쓰기 코드는 `e23fe359a` 이전부터, AS 행이 체크박스 섹션에 들어간
  것은 `0b4ab4546`(2026-07-13)부터다. 즉 새 변경이 깨뜨린 것이 아니라 **두 조건이 만나기를 기다리던
  자리**였다.

### 두 건의 공통 축

08-14 사고와 같다 — **AS 의 정본이 아닌 파생 사본을 화면이 읽고, 그 사본을 다른 축의 쓰기 경로가
덮는다.** 08-14 는 사본이 `orders.status` 였고, 이번 ①은 그 대안으로 만든 사본
`as_axis_status` 가 **동기화 규약(호출)에서 새어** 같은 증상을 만들었다
(`docs/plans/2026-09-06-foms-system-review-report.md:37`, `:107`).

## 5. 복구

- 운영 데이터 **5건 복구 완료**. 백업 `C:/tmp/as_recovery_backup_20260903.json`,
  **사후 잔여 결함 0**(`docs/AI_CHANGELOG.md:10`). `docs/AI_STATUS.md:18` 도 "운영 5건 복구" 로 적는다.
- 5건의 내역(①의 3건 + ②의 몇 건)이 어떻게 나뉘는지는 두 줄만으로 갈리지 않는다 —
  ①은 운영 3건(#1315·#1119·#1706)으로 명시돼 있고, ②는 #4816 이 실사례로 나온다.
  나머지 배분 — `미상(근거 없음)`.
- 백업 파일은 **저장소 밖 로컬 임시 경로**라 이 문서로는 현재 존재 여부를 확인할 수 없다.

## 6. 구조 변경

**수정 ①(서버)**: `sync_as_axis_column()` 을 **분리해 게이트 앞에서 호출**한다.
이때 **"값 없으면 안 지움" 규약은 유지**했다 — 그것이 2026-08-14 사고의 방어선이라 무변경이다
(`docs/AI_CHANGELOG.md:10`). blast radius 운영 실측 **0행**.

**수정 A(서버, ②)**: `as_overlay_outranks_status_write()` 신설 —
`legacy_status_projection` 의 우선순위(DELETED > ON_HOLD > AS_* > logistics > main)를
**쓰기 경로에도 적용**하고 `field_update`·`update_order_status` 를 대칭으로 맞췄다.
거부 방식은 **403 이 아니라 무시**다 — 실패 배너는 `.alert` 자동닫힘에 지워져 무음 실패가 되고,
체크리스트 저장 자체는 정상 업무이기 때문이다. 의도적 본공정 전이·보류·삭제·AS 코드는 통과시키고
**음성 대조군 4종으로 잠갔다**(`docs/AI_CHANGELOG.md:10`).

**수정 B(클라, ②)**: `checkAllCompleted` 가 AS 행 표식 **3종**을 제외한다.
행 클래스가 섹션마다 달라(`as-order-row` vs `regional-as-shipping-row`) **기존 가드가 사고 난 쪽에
안 걸려 있었다**(`docs/AI_CHANGELOG.md:10`).

**검증**(`docs/AI_CHANGELOG.md:10`): 승격 트리(`origin/production` 기준)
`tests/domains`+`tests/contracts` **6695 passed·5 skipped**, `pre_push_smoke exit 0`, `APP_OK`,
deploy·PR 검사 각 4/4 green, cherry-pick 충돌 0. **계약 테스트 13종 신규.**

**반영**: deploy `370e2f689`·`fe112d765` · production `ac23a6c16`(PR #288).

**미해결로 남긴 것(버그 아님으로 판정)**: ERP 본공정 드롭다운이 AS 접수 후에도 `MEASURE` 로 남는 것은
STATE-AS-01 설계(`8829079a9`)다 — 정상 동작 중인 수도권 AS 47건도 전부 그렇다
(`docs/AI_CHANGELOG.md:10`).

## 7. 재발 여부·남은 것

- 이 사고 자체는 종결이다(`docs/AI_STATUS.md:18` "회귀 없음(잠복). 운영 5건 복구").
- **계열로 보면 재발이다.** 08-14 → AS-AXIS-01 로 사본 하나 더 → 09-03 그 사본 이탈 → 봉인 가드.
  검토 보고서의 판정: **매 수정이 '가드 하나 더' 였고 사본 구조는 그대로다**
  (`docs/plans/2026-09-06-foms-system-review-report.md:107`, `:37`).
- 남은 것 ①: 사본을 맞추는 주체가 생성 컬럼·트리거가 아니라 `sync_erp_flat_columns` **호출 규약**
  (27곳/19파일)이다. 쓰기 경로가 늘면 '부른 경로' 와 '안 부른 경로' 가 또 갈린다
  (`docs/plans/2026-09-06-foms-system-review-report.md:37`).
- 남은 것 ②: 드리프트 감사 도구(`tools/ops/audit_as_axis_drift.py`)는 있으나 **자동 실행 배선이 0**
  이었다(같은 근거 줄의 D3 워커 grep: `.github/workflows/*.yml start.sh predeploy.sh` 에
  `audit_as_axis_drift|audit_erp_flat_columns` 0건). 그 배선은 별 task 로 진행 중이다.
- 남은 것 ③: `status` 는 여전히 overlay projection 이고 그 위에 봉인 가드가 얹힌 형태다
  (`models.py:109-111`).

## 8. 근거 앵커

- `docs/AI_STATUS.md:18` — 운영 반영(PR #288 · `ac23a6c16`) · 원인 2종 함수명 · "회귀 없음(잠복)" · 운영 5건 복구
- `docs/AI_CHANGELOG.md:10` — 전문: ① `_reproject_and_sync` 게이트 밖 write vs `is_erp_order` 게이트 안 투영 · 운영 3건(#1315·#1119·#1706) 전부 `is_erp_order=False` · 대조군 ERP 2건 정상 · 자가 회복 부재 · ② `checkAllCompleted`→`status=SCHEDULED`·`setattr` 직행 · 재접수 409 · 감사 원장 +0.18~0.22초 · 회귀 커밋 없음(`e23fe359a`·`0b4ab4546`·#4816 08-31~09-03 06:27) · 수정 3벌 · 검증 6695 passed·13종 신규 · 복구 5건·백업 파일 · 커밋 `370e2f689`·`fe112d765`·`ac23a6c16`
- `docs/AI_CHANGELOG.md:49` — AS-AXIS-01(이번 ①이 새어 나온 그 축의 도입)
- `models.py:109-112` — `as_axis_status` 컬럼 주석(08-14 사고 기록)
- `docs/incidents/2026-08-14-as-dashboard-bulk-complete-vanish.md` — 같은 계열 선행 사고
- `docs/plans/2026-09-06-foms-system-review-report.md:37` · `:107` — R1·R8, 사본 동기화 규약과 "같은 유형 4건" 판정
