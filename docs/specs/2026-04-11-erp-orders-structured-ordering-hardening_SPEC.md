# erp_orders_structured Ordering Hardening Spec
> 작성일: 2026-04-11 | 상태: 🟢 승인됨

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
`apps/api/erp_orders_structured.py`의 `api_put_order_structured()`가 실제 저장 여부와 일치하는 순서로 Channel outbox mark/payload와 geocode reset을 실행하도록 정리한다. `structured_data`가 없는 요청에서는 channel side effect가 발생하지 않고, 주소를 빈 값으로 바꾸는 경우에도 geocode reset이 누락되지 않게 한다.

### 1.2 기능 요구사항
1. `structured_data`가 요청에 없으면 `build_structured_update_payload()`와 `mark_order_updated_for_channel()`는 실행되지 않는다.
2. `structured_data`가 있을 때만 channel payload/mark/enqueue가 같은 조건 경계 안에서 동작한다.
3. 주소 변경 판정은 truthy/falsy가 아니라 정규화된 이전/새 주소 비교로 수행한다.
4. 새 주소가 빈 문자열이어도 실제 변경이면 `reset_order_geocode_on_address_change()`가 호출된다.
5. 기존 API 응답 형식과 public route contract는 유지한다.

### 1.3 예외/제약 조건
- `channel_delivery.py`, `channel_event_payloads.py`, `order_geocode.py` 내부 로직은 이번 배치에서 변경하지 않는다.
- 대형 ERP Beta 템플릿/프론트엔드 저장 로직은 이번 배치에 섞지 않는다.
- 구조 분해나 별도 리팩터링 없이 `api_put_order_structured()`와 focused regression test만 다룬다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `apps/api/erp_orders_structured.py` | channel payload/mark 조건과 geocode reset 조건을 실제 저장 경계에 맞게 정렬 |
| `tests/*` (신규 focused test) | `structured_data` 미전달, 주소 클리어, channel side effect negative case를 고정 |
| `docs/specs/2026-04-11-erp-orders-structured-ordering-hardening_SPEC.md` | 이번 품질 배치의 승인된 범위를 기록 |
| `docs/ARCHIVE_INDEX.md` | 신규 spec 문서 인덱스 추가 |

### 2.2 아키텍처 방향
- 현재 route-level orchestration은 유지하되, side effect trigger 경계만 바로잡는다.
- channel 관련 helper와 geocode helper는 기존 canonical service를 그대로 사용한다.
- 참고 패턴:
  - `foms/services/order_geocode.py`의 빈 문자열 허용 reset contract
  - `docs/plans/2026-04-11-quality-ops-separation-plan.md` Track B

### 2.3 의존성 및 영향 범위
- 영향 범위:
  - ERP structured PUT API
  - Channel outbox / enqueue path
  - geocode reset / enqueue path
- DB 마이그레이션: 없음
- 외부 API/웹훅 스키마 변경: 없음

## 3. Steps — 실행 단계
- [ ] Step 1: `api_put_order_structured()`에서 channel payload/mark 생성 범위를 `structured_data` 저장 경계와 일치시킨다.
- [ ] Step 2: 주소 변경 판정을 정규화 비교로 바꾸고 빈 주소 reset 누락을 제거한다.
- [ ] Step 3: negative/edge case focused regression test를 추가한다.
- [ ] Step 4: app import, focused pytest, channel/geocode 회귀 smoke를 재검증한다.

## 4. 검증 기준
- [ ] `python -c "import app; print('APP_OK')"` 통과
- [ ] 해당 focused pytest 통과
- [ ] `structured_data` 미전달 요청에서 channel side effect가 발생하지 않음을 테스트로 확인
- [ ] 주소 삭제 시 geocode reset이 반영됨을 테스트로 확인

## 5. 참고 자료
- 관련 상태: `docs/AI_STATUS.md`의 `erp_orders_structured.py` 알려진 이슈
- 관련 계획: `docs/plans/2026-04-11-quality-ops-separation-plan.md`
- 관련 서비스:
  - `foms/services/order_geocode.py`
  - `foms/services/channel_delivery.py`
  - `foms/services/channel_event_payloads.py`
