# loadOrderDetail 계약

## 상태 플래그
- `container.dataset.loaded === '1'`
  의미: 첨부 2단 패치까지 완료된 최종 상태다.
- `container.dataset.shellLoaded === '1'`
  의미: `structured_data` 기반 1단 셸 렌더는 끝났고, 첨부 2단 패치만 남아 있다.
- `container.dataset.attachPhase`
  의미: 첨부 패치 진행 상태다. 값은 `'loading' | 'done' | 'error'` 중 하나다.
- `container.dataset.attachError === '1'`
  의미: 첨부 API 실패가 발생해 재펼침 시 첨부만 재시도해야 한다.
- `container.dataset.itemCount`
  의미: 첨부 에러 후 재시도 시 제품 행 개수를 복원하기 위한 보조 값이다.

## await 의미
`await loadOrderDetail(orderId)` 는 셸 렌더만 끝나면 resolve 되는 함수가 아니다.

- 프리로드 payload만으로 끝나는 경우:
  셸 렌더 + 즉시 첨부 반영까지 완료한 뒤 resolve 된다.
- 첨부 2단 패치가 필요한 경우:
  셸 렌더 후 `patchOrderDetailAttachments()` 성공 또는 에러 처리까지 완료한 뒤 resolve 된다.
- 첨부 로드 실패 시에도:
  promise는 reject 대신 resolve 되며, 컨테이너에는 셸과 에러 슬롯이 남는다.

## 호출부 (현재)
- [templates/orders/partials/dashboard_grid.html](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/templates/orders/partials/dashboard_grid.html)
  collapse `show.bs.collapse` 이벤트에서 `loadOrderDetail(orderId)` 호출

추가 호출부를 발견하면 이 목록을 갱신한다.

## 캐시 무효화
`window.invalidateOrderDetailAttachments(orderId)` 는 아래 상태를 모두 초기화한다.

- `__attachmentsCache[orderId]`
- `__attachmentsCacheAt[orderId]`
- `__orderDetailLoadGen[orderId]`
- `loaded / shellLoaded / attachPhase / attachError / itemCount`

첨부 업로드/삭제 API 성공 콜백에서는 이 함수를 호출해 같은 브라우저 세션의 stale 첨부 상태를 비운다.

주의:
- 이 무효화는 현재 브라우저 탭 기준이다.
- 다른 사용자나 다른 탭에서 일어난 변경은 별도 실시간 동기화 대상이 아니다.

## TTL (선택 확장)
`__attachmentsCacheAt[orderId]` 는 마지막 첨부 fetch 시각(ms)을 기록한다.

향후 비용 없이 아래 확장을 넣을 수 있다.

- `Date.now() - __attachmentsCacheAt[orderId] > 60_000`
- 조건 만족 시 캐시를 무효화하고 첨부를 다시 fetch

현재 구현은 타임스탬프만 기록하고, TTL 강제 재조회는 아직 적용하지 않는다.
