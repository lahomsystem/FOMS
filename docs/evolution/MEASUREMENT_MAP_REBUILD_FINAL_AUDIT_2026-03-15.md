# 실측 지도 재구현 Spec — 최종 감리 보고서

- **감리일**: 2026-03-15
- **대상**: `docs/plans/2026-03-15-measurement-map-rebuild-spec.md` Phase 1~6 + 후속 작업
- **검증 문서**: `docs/validation/2026-03-15-measurement-map-rebuild-spec-validation.md`

---

## 1. 요약

| 항목 | 결과 | 비고 |
|------|------|------|
| Phase 1~6 구현 | ✅ 완료 | geocode_status 신뢰, map_snapshot, conversion_status UI, worker 실패 처리 |
| reset_order_geocode 확대 적용 | ✅ 완료 | order_edit, erp_measurement, erp_orders_structured, erp_map |
| Legacy 정리 스크립트 | ✅ 실행 완료 | 정리 대상 0건 (DB 일관성 양호) |
| 앱 기동 | ✅ 정상 | `python -c "import app; print('APP_OK')"` |
| **종합 판정** | **✅ 최종 감리 통과** | |

---

## 2. Phase별 검증

### Phase 1: geocode_status DB 신뢰

| 항목 | 상태 | 검증 |
|------|------|------|
| `geocode_status` DB 값 우선 사용 | ✅ | `erp_map.py` map_data에서 `getattr(order, 'geocode_status', None) or 'unknown'` |
| `geocode_failed` 제거 | ✅ | map_data 응답에 `geocode_failed` 없음, `conversion_status`만 사용 |
| 주소 수정 API 응답 통일 | ✅ | `update_address` 응답에 `conversion_status` 포함 |

### Phase 2: 서비스 레이어 + erp_map reset

| 항목 | 상태 | 검증 |
|------|------|------|
| `services/map_snapshot.py` | ✅ | `build_measurement_map_snapshot()` |
| `services/order_geocode.py` | ✅ | `reset_order_geocode_on_address_change()` |
| erp_map `update_address`에 reset 적용 | ✅ | 주소 변경 시 reset 호출 후 commit, enqueue |

### Phase 3: map_view.html conversion_status UI

| 항목 | 상태 | 검증 |
|------|------|------|
| `conversion_status` 기반 UI | ✅ | failed/pending/success 분기 |
| Poll 시 `data.orders` 전체 재구성 | ✅ | partial mutation 제거, 서버 응답 신뢰 |

### Phase 4: generate_map / map_data map_snapshot

| 항목 | 상태 | 검증 |
|------|------|------|
| `generate_map`, `map_data`에 map_snapshot 적용 | ✅ | Shared query, status=ALL |
| measurement 모드 status selector 숨김 | ✅ | `erp_measurement_dashboard.html` 직접 링크 `status=ALL` |

### Phase 5: Worker 실패 시 lat/lng 초기화

| 항목 | 상태 | 검증 |
|------|------|------|
| 실패 시 `lat/lng=None` | ✅ | `services/jobs/tasks.py` geocode 실패 분기 |

### Phase 6: Legacy 정리 스크립트

| 항목 | 상태 | 검증 |
|------|------|------|
| `scripts/fix_geocode_status_inconsistency.py` | ✅ | 작성 완료, 실행 시 정리 대상 0건 |

---

## 3. 후속 작업: reset_order_geocode 확대 적용

| 파일 | 적용 내용 | 상태 |
|------|----------|------|
| `apps/order_edit.py` | `'address' in changes` 시 reset 호출, commit 후 enqueue | ✅ |
| `apps/api/erp_measurement.py` | `field == 'address'` 시 reset 호출, structured_data 분기 처리 | ✅ |
| `apps/api/erp_orders_structured.py` | `old_addr != new_addr` 시 reset 호출, commit 전 적용 | ✅ |
| `apps/api/erp_map.py` | Phase 2에서 이미 적용 | ✅ |
| `apps/api/orders.py` | `allowed_fields`에 address 없음 → 적용 대상 아님 | N/A |
| `apps/order_pages.py` | 신규 주문 생성만, 주소 수정 경로 없음 | N/A |

---

## 4. Spec 요구사항 대비 최종 상태

| Spec 요구 | 구현 | 상태 |
|-----------|------|------|
| DB 기준 geocode_status 신뢰 | conversion_status = DB geocode_status | ✅ |
| geocode_failed 제거 | map_data 응답에서 제거 | ✅ |
| pending/success/failed 3가지 구분 | UI 및 API 모두 적용 | ✅ |
| 주소 수정 후 서버 응답 기준 갱신 | poll 시 data.orders 전체 재구성 | ✅ |
| 다른 화면 주소 수정 후 reset | order_edit, erp_measurement, erp_orders_structured | ✅ |
| measurement 모드 status=ALL 고정 | generate_map, map_data, 대시보드 링크 | ✅ |

---

## 5. 결론

- **Phase 1~6** 및 **후속 reset_order_geocode 확대 적용**이 Spec 및 검증 문서 요구사항을 충족함.
- Legacy 정리 스크립트는 배포 전 1회 실행 권장(현재 DB는 정리 대상 없음).
- **최종 감리 통과.**
