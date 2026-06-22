# Message Template Catalog (CT-B-02)

## 1. 템플릿 작성 규칙
- 가독성: 변경 핵심은 1~3줄 안에서 바로 보이게 한다.
- Prefix: manual과 automatic을 구분한다.
- Diff first: automatic push는 무엇이 어떻게 바뀌었는지 `이전 -> 이후` 형식으로 먼저 보여준다.
- CTA: 주문 상세 링크는 아래 계약을 따른다.
  - primary: `{erp_url}/channel/wam/?launch_token={launch_token}`
  - fallback: `{erp_url}/edit/{order_id}?open=erp-order`
  - legacy compatibility: `{erp_url}/erp/orders/{order_id}`는 서버에서 redirect 처리

## 2. 기본 템플릿 목록

### 2.1 상태 변경 (`stage_changed`)
```text
[알림] 주문 #{order_id} 상태 변경

- 상태: {before_stage} -> {after_stage}

변경자: {changed_by}

🔗 주문 상세 보기: {erp_url}/channel/wam/?launch_token={launch_token}
```

### 2.2 담당자 변경 (`manager_changed`)
```text
[알림] 주문 #{order_id} 담당자 변경

- 담당자: {before_manager} -> {after_manager}

변경자: {changed_by}

🔗 주문 상세 보기: {erp_url}/channel/wam/?launch_token={launch_token}
```

### 2.3 출고/시공 정보 변경 (`shipment_updated`)
```text
[알림] 주문 #{order_id} 출고/시공 정보 변경

- 시공시간: {before_time} -> {after_time}
- 시공자: {before_workers} -> {after_workers}

변경자: {changed_by}

🔗 주문 상세 보기: {erp_url}/channel/wam/?launch_token={launch_token}
```

### 2.4 결제 확인 변경 (`payment_confirmation_changed`)
```text
[알림] 주문 #{order_id} 결제 확인 변경

- 계약금 확인: 미확인 -> 확인

변경자: {changed_by}

🔗 주문 상세 보기: {erp_url}/channel/wam/?launch_token={launch_token}
```

### 2.5 긴급 알림 (`urgent`)
```text
🚨 [긴급] 주문 #{order_id} - {customer_name} 고객
{urgent_reason}
관련 담당자는 즉시 확인 바랍니다. @all

🔗 주문 상세 보기: {erp_url}/channel/wam/?launch_token={launch_token}
```

### 2.6 수동 푸시 (`manual`)
```text
{user_message}

🔗 주문 상세 보기: {erp_url}/channel/wam/?launch_token={launch_token}
```

`user_message`는 ERP 변환 텍스트(``고객명 : …``부터)만 보낸다. 재전송은 본문 앞에 ``[수정]`` 한 줄만 붙인다.
