# Message Template Catalog (CT-B-02)

## 1. 템플릿 작성 규칙
- **가독성 (Readability)**: 길고 복잡한 텍스트보다 불릿(Bullet) 위주의 간결한 요약.
- **Prefix**: 모든 자동화 메시지는 `[시스템 알림]` 또는 `[긴급]`과 같은 Prefix를 달아 사람이 직접 보낸 메시지와 구분한다.
- **링크 (Call-to-Action)**: 주문번호/고객명을 클릭하면 ERP의 해당 주문 상세 페이지로 이동하는 링크를 포함한다.

## 2. 기본 템플릿 목록

### 2.1. 실측 완료 (`measurement_completed`)
```text
[실측완료] 주문 #{order_id} - {customer_name} 고객님
실측이 완료되어 보고서가 업로드되었습니다.
도면팀은 확인 후 도면 작업을 진행해 주세요.

📍 주소: {address}
⏰ 실측일: {measurement_date}
🔗 주문 상세 보기: {erp_url}/erp/orders/{order_id}
```

### 2.2. 도면 확정 (`drawing_approved`)
```text
[도면확정] 주문 #{order_id} - {customer_name} 고객님
도면이 최종 확정되었습니다. 생산/시공 일정을 확인해 주세요.

🔗 주문 상세 보기: {erp_url}/erp/orders/{order_id}
```

### 2.3. 긴급 알림 (`urgent_notice`)
```text
🚨 [긴급] 주문 #{order_id} - {customer_name} 고객님
{urgent_reason}
관련 담당자는 즉시 확인 바랍니다. @all

🔗 주문 상세 보기: {erp_url}/erp/orders/{order_id}
```

### 2.4. 수동 푸시 (`manual_push`)
```text
[ERP 푸시] 주문 #{order_id} - {customer_name}
{user_message}

🔗 주문 상세 보기: {erp_url}/erp/orders/{order_id}
```
*(재전송 시 `[수정]` Prefix 추가됨)*
