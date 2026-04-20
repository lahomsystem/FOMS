# ERP_BETA Placeholder Backfill Runbook

## 목적
- active ERP 주문의 flat columns(`customer_name`, `phone`, `product`, `address`)에 남아 있는 placeholder 값을 `structured_data` 기준 실값으로 채운다.
- 이 정리가 끝나야 `ERP_BETA` placeholder suppressor와 runtime alias를 안전하게 제거할 수 있다.

## 현재 production 기준선
- active ERP orders: `565`
- auto backfill candidates: `564`
- customer_name backfill: `564`
- phone backfill: `559`
- product backfill: `564`
- address backfill: `558`
- auto backfill 후에도 남는 manual follow-up: `1` row
  - `orders.id = 1845`
  - 상태: `DRAWING`
  - flat `product='ERP Beta'`
  - `structured_data`에 상품/아이템 정보가 없어 자동 치환 불가

## product fallback 정책
1. `structured_data.items[*].product_name` 또는 `name`의 첫 번째 실값을 사용한다.
2. 상품명이 비었지만 첫 아이템이 AS/상담 패턴이면 `상담`으로 backfill 한다.
3. 둘 다 없으면 자동 수정하지 않고 manual follow-up으로 남긴다.

## 실행 순서
### 권장 롤아웃 순서 (staging → production)

이 backfill은 **배포된 코드가 해당 환경에 올라간 뒤** 실행하는 1회성 command다.  
따라서 권장 순서는 아래와 같다.

1. **staging 코드 완결**
   - repo에서 `ERP_BETA` active-runtime 제거 배치를 완료한다.
   - 최소 범위: inbound alias(`open=erp-beta`, `create_mode=ERP_BETA`) 제거, placeholder suppressor 정리, 가능하면 P3 canonical-only startup/bootstrap까지 반영한다.

2. **staging 배포**
   - staging Railway 프로젝트/서비스에 새 코드를 배포한다.

3. **staging backfill + verify**
   - staging에서 이 문서의 dry-run → execute → verify 순서로 실제 데이터를 정리한다.
   - 수동 smoke(`/add`, `/edit/<id>`, measurement/shipment/CS, attachment/payment/draft`)까지 끝낸다.

4. **production 배포**
   - staging 확인이 끝난 동일 코드를 production에 배포한다.

5. **production backfill + verify**
   - production에서 dry-run → execute → verify를 다시 수행한다.
   - production 결과는 evidence JSON과 SPEC에 반영한다.

### Railway 1회성 command

실 production Railway 프로젝트가 `FOMS-PRODUCTION`이고 project id가 `cbe0af66-875b-460c-88f6-780dd705f45c`라면, 가장 안전한 방식은 `railway run`으로 **앱 환경변수를 주입한 상태에서 이 스크립트를 1회 실행**하는 것이다.

앱 서비스명이 `FOMS`일 때 기준 command:

```powershell
railway run -p cbe0af66-875b-460c-88f6-780dd705f45c -e production -s FOMS python scripts/maintenance/erp_beta_placeholder_backfill.py
```

실제 반영 command:

```powershell
railway run -p cbe0af66-875b-460c-88f6-780dd705f45c -e production -s FOMS python scripts/maintenance/erp_beta_placeholder_backfill.py --execute
```

검증 command:

```powershell
railway run -p cbe0af66-875b-460c-88f6-780dd705f45c -e production -s FOMS python scripts/maintenance/erp_beta_placeholder_backfill.py --verify-only
```

서비스명이 `FOMS`가 아니면 `-s` 값만 실제 앱 서비스명으로 바꾼다.

PowerShell 래퍼로 더 안전하게 실행하려면:

```powershell
powershell -NoProfile -File tools/harness/run_erp_beta_placeholder_backfill.ps1 -Mode dry-run
```

```powershell
powershell -NoProfile -File tools/harness/run_erp_beta_placeholder_backfill.ps1 -Mode execute
```

```powershell
powershell -NoProfile -File tools/harness/run_erp_beta_placeholder_backfill.ps1 -Mode verify
```

추가 옵션 예시:

```powershell
powershell -NoProfile -File tools/harness/run_erp_beta_placeholder_backfill.ps1 -Mode dry-run -OrderId 1845 -Json
```

1. Dry-run
   - 추천: [erp_beta_placeholder_backfill.py](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/scripts/maintenance/erp_beta_placeholder_backfill.py) 1회성 command의 기본 dry-run 사용
   - 대안: [erp_beta_flat_placeholder_backfill_dryrun.sql](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/tools/harness/erp_beta_flat_placeholder_backfill_dryrun.sql)
   - 기대값:
     - `any_backfill_candidates = 564`
     - `unresolved_placeholder_product_rows = 1`

2. Apply
   - 추천: [erp_beta_placeholder_backfill.py](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/scripts/maintenance/erp_beta_placeholder_backfill.py) + `--execute`
   - 대안: [erp_beta_flat_placeholder_backfill_apply.sql](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/tools/harness/erp_beta_flat_placeholder_backfill_apply.sql)
   - production write다.
   - 반환 row 수가 대략 `564`건인지 확인한다.

3. Verify
   - 추천: [erp_beta_placeholder_backfill.py](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/scripts/maintenance/erp_beta_placeholder_backfill.py) + `--verify-only`
   - 대안: [erp_beta_flat_placeholder_backfill_verify.sql](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/tools/harness/erp_beta_flat_placeholder_backfill_verify.sql)
   - 기대값:
     - `active_customer_name_erp_beta = 0`
     - `active_product_erp_beta = 1` 또는 `0`
     - 남는 row가 있다면 `id = 1845`인지 확인

4. Manual follow-up
   - `id = 1845`를 운영에서 직접 판단한다.
   - 선택지는 보통 둘 중 하나다:
     - 실제 테스트/불완전 데이터면 정정 또는 정리
     - 실주문이면 올바른 상품명/structured_data를 수동 보완

5. Codex 후속
   - placeholder blocker가 사실상 해제되면 P2를 시작한다.
   - 다음 배치:
     - `ERP_BETA_ENABLED` env/js fallback 제거
     - `open=erp-beta` / `create_mode=ERP_BETA` alias 제거
     - placeholder suppressor 제거

## 주의
- 이 backfill은 **자동 배포에 연결되어 있지 않다**. `git push`만으로 자동 실행되지 않는다.
- 실제 운영 반영이 필요할 때만 `railway run ... python scripts/maintenance/erp_beta_placeholder_backfill.py --execute`를 수동으로 1회 실행한다.
- 자동 수정 범위는 `status <> 'DELETED' AND is_erp_order = true`로 고정한다.
- `structured_data`에 신뢰할 실값이 없는 row는 자동 수정하지 않는다.
- production apply 전후 결과는 캡처해서 [2026-04-18-erp-beta-retirement-gate-evidence.json](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/docs/harness/evidence/2026-04-18-erp-beta-retirement-gate-evidence.json)와 SPEC에 반영한다.
