import re
import datetime


def _clean(s: str | None) -> str | None:
    if s is None:
        return None
    v = str(s).strip()
    return v if v else None


def _normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"[^0-9]", "", phone)
    if len(digits) == 11:
        return f"{digits[0:3]}-{digits[3:7]}-{digits[7:11]}"
    if len(digits) == 10:
        return f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}"
    return phone.strip()


def _parse_amount(text: str | None) -> int | None:
    if not text:
        return None
    digits = re.sub(r"[^0-9]", "", text)
    try:
        return int(digits) if digits else None
    except Exception:
        return None


def _extract_first(patterns: list[str], blob: str) -> str | None:
    for pat in patterns:
        m = re.search(pat, blob, re.MULTILINE | re.IGNORECASE)
        if m:
            # 패턴에 캡처 그룹이 없을 수도 있으므로 안전 처리
            if m.lastindex and m.lastindex >= 1:
                return _clean(m.group(1))
            return _clean(m.group(0))
    return None


def _split_items(text: str) -> tuple[str, list[str]]:
    """
    예시 형태:
      1)
      제품명: ...
      ...
      2)
      ...
    """
    lines = text.splitlines()
    idxs: list[int] = []
    for i, line in enumerate(lines):
        if re.match(r"^\s*\d+\)\s*$", line.strip()):
            idxs.append(i)

    if not idxs:
        return text, []

    header = "\n".join(lines[: idxs[0]])
    blocks: list[str] = []
    for j, start in enumerate(idxs):
        end = idxs[j + 1] if j + 1 < len(idxs) else len(lines)
        block = "\n".join(lines[start:end]).strip()
        blocks.append(block)
    return header, blocks


def _extract_url_after_label(blob: str, label: str) -> str | None:
    """
    '추가결제링크'처럼 라벨만 한 줄에 있고, 다음 줄에 URL이 오는 형태를 안정적으로 처리.
    - 정규식/인코딩/공백 변형에 강하게 라인 스캔으로 찾는다.
    """
    if not blob:
        return None
    lines = blob.splitlines()
    label_norm = re.sub(r"\s+", "", label)
    url_re = re.compile(r"(https?://\S+)", re.IGNORECASE)
    for i, line in enumerate(lines):
        line_norm = re.sub(r"\s+", "", str(line))
        if label_norm and label_norm in line_norm:
            # 다음 라인들에서 첫 URL 찾기
            for j in range(i + 1, min(i + 5, len(lines))):
                m = url_re.search(str(lines[j]).strip())
                if m:
                    return m.group(1).strip()
    # 라벨을 못 찾았더라도 URL만 있는 케이스가 있어 전체에서 첫 URL을 폴백으로 추출
    m = url_re.search(blob)
    return m.group(1).strip() if m else None


def parse_order_text(raw_text: str) -> dict:
    """
    Palantir-style (ERP Beta) v1 구조화 파서
    - 멀티 아이템(1..n) 지원
    - 날짜는 '상담/미정/확정' 같은 값이 들어올 수 있으므로 상태+원문 중심으로 저장
    """
    raw_text = raw_text or ""
    now_iso = datetime.datetime.now().isoformat()

    header_text, item_blocks = _split_items(raw_text)
    blob = raw_text

    customer_name = _extract_first([r"^\s*고객명\s*:\s*(.+)$"], blob)
    orderer = _extract_first([r"^\s*발주사\s*:\s*(.+)$"], blob)
    manager_name = _extract_first([r"^\s*담당자\s*:\s*(.+)$"], blob)

    address = _extract_first([
        r"^\s*주\s*소\s*:\s*(.+)$",
        r"^\s*주소\s*:\s*(.+)$",
    ], blob)

    phone = _extract_first([
        r"^\s*연락처\s*:\s*(.+)$",
        r"^\s*전화번호\s*:\s*(.+)$",
    ], blob)
    phone = _normalize_phone(phone)

    measurement_date = _extract_first([r"^\s*실측일\s*:\s*(.+)$"], blob)
    measurement_time = _extract_first([r"^\s*시\s*간\s*:\s*(.+)$", r"^\s*실측시간\s*:\s*(.+)$"], blob)

    construction_raw = _extract_first([r"^\s*시공일\s*:\s*(.+)$"], blob)
    construction_status = None
    construction_date = None
    if construction_raw:
        if any(k in construction_raw for k in ["상담", "미정"]):
            construction_status = "CONSULT"
        else:
            construction_status = "DATE"
            construction_date = construction_raw

    deposit_raw = _extract_first([r"^\s*예약금\s*:\s*(.+)$"], blob)
    balance_raw = _extract_first([r"^\s*잔\s*금\s*:\s*(.+)$", r"^\s*잔금\s*:\s*(.+)$"], blob)
    prepay_raw = _extract_first([r"^\s*선결제금액\s*:\s*(.+)$"], blob)
    cash_receipt = _extract_first([r"^\s*현금영수증\s*:\s*(.+)$"], blob)

    additional_payment_status = _extract_first([r"^\s*추가\s*결제\s*필\s*-\s*$", r"^\s*추가\s*결제\s*필\s*:\s*(.+)$"], blob)
    # 링크는 라벨 다음 줄에 오는 케이스가 많아서 라인 스캔으로 추출 (가장 안정적)
    additional_payment_link = _extract_url_after_label(blob, "추가결제링크")

    promotions: list[dict] = []
    promo_block = re.search(r"-\s*(.+프로모션.+)\s*-\s*([\s\S]*?)(?=\n\s*-\s*추가|\Z)", blob)
    if promo_block:
        title = _clean(promo_block.group(1))
        details_blob = promo_block.group(2) or ""
        details = []
        for line in details_blob.splitlines():
            line = line.strip()
            if not line:
                continue
            details.append(line.lstrip("*").strip())
        promotions.append({"title": title, "details": details})

    # items
    items: list[dict] = []
    if item_blocks:
        for idx, block in enumerate(item_blocks, start=1):
            # 블록의 첫 줄은 "1)" 같은 번호
            product_name = _extract_first([r"^\s*제품명\s*:\s*(.+)$"], block)
            spec = _extract_first([r"^\s*규\s*격\s*:\s*(.+)$", r"^\s*규격\s*:\s*(.+)$"], block)
            internal = _extract_first([r"^\s*내\s*부\s*:\s*(.+)$", r"^\s*내부\s*:\s*(.+)$"], block)
            color = _extract_first([r"^\s*색\s*상\s*:\s*(.+)$", r"^\s*색상\s*:\s*(.+)$"], block)
            option_detail = _extract_first([r"^\s*옵\s*션\s*:\s*(.+)$", r"^\s*옵션\s*:\s*(.+)$"], block)
            handle = _extract_first([r"^\s*손잡이\s*:\s*(.+)$"], block)
            misc = _extract_first([r"^\s*기\s*타\s*:\s*(.+)$", r"^\s*기타\s*:\s*(.+)$"], block)
            price_raw = _extract_first([r"^\s*견적가\s*:\s*(.+)$"], block)

            items.append({
                "index": idx,
                "product_name": product_name,
                "spec": spec,
                "internal": internal,
                "color": color,
                "option_detail": option_detail,
                "handle": handle,
                "misc": misc,
                "price": _parse_amount(price_raw),
                "raw_price": price_raw,
            })
    else:
        # 단일 아이템(번호가 없는 경우) - 최소한 기존 1개 제품으로 수용
        product_name = _extract_first([r"^\s*제품명\s*:\s*(.+)$"], blob)
        spec = _extract_first([r"^\s*규\s*격\s*:\s*(.+)$", r"^\s*규격\s*:\s*(.+)$"], blob)
        internal = _extract_first([r"^\s*내\s*부\s*:\s*(.+)$", r"^\s*내부\s*:\s*(.+)$"], blob)
        color = _extract_first([r"^\s*색\s*상\s*:\s*(.+)$", r"^\s*색상\s*:\s*(.+)$"], blob)
        option_detail = _extract_first([r"^\s*옵\s*션\s*:\s*(.+)$", r"^\s*옵션\s*:\s*(.+)$"], blob)
        handle = _extract_first([r"^\s*손잡이\s*:\s*(.+)$"], blob)
        misc = _extract_first([r"^\s*기\s*타\s*:\s*(.+)$", r"^\s*기타\s*:\s*(.+)$"], blob)
        price_raw = _extract_first([r"^\s*견적가\s*:\s*(.+)$"], blob)
        if any([product_name, spec, internal, color, option_detail, handle, misc, price_raw]):
            items.append({
                "index": 1,
                "product_name": product_name,
                "spec": spec,
                "internal": internal,
                "color": color,
                "option_detail": option_detail,
                "handle": handle,
                "misc": misc,
                "price": _parse_amount(price_raw),
                "raw_price": price_raw,
            })

    # confidence (간단 기준: 고객명/연락처/주소 + 아이템1 제품명 채움)
    score = 0
    score += 1 if customer_name else 0
    score += 1 if phone else 0
    score += 1 if address else 0
    score += 1 if items and items[0].get("product_name") else 0
    if score >= 4:
        confidence = "high"
    elif score >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    structured = {
        "entity_type": "order_structured",
        "schema_version": 1,
        "parsed_at": now_iso,
        "confidence": confidence,
        "parties": {
            "customer": {"name": customer_name, "phone": phone},
            "orderer": {"name": orderer, "type": "individual" if (orderer and orderer.strip() == "개인") else "company"},
            "manager": {"name": manager_name},
        },
        "site": {"address_full": address},
        "schedule": {
            "measurement": {"date": measurement_date, "time": measurement_time},
            "construction": {"raw": construction_raw, "status": construction_status, "date": construction_date},
        },
        "payments": {
            "deposit": {"raw": deposit_raw, "amount": _parse_amount(deposit_raw)},
            "balance": {"raw": balance_raw, "amount": _parse_amount(balance_raw)},
            "prepayment": {"raw": prepay_raw, "amount": _parse_amount(prepay_raw)},
            "cash_receipt": {"raw": cash_receipt, "value": cash_receipt},
            "additional_payment": {"status": additional_payment_status, "link": additional_payment_link},
        },
        "promotions": promotions,
        "items": items,
        "raw": {"text": raw_text},
        "header_raw": _clean(header_text),
    }
    return structured

