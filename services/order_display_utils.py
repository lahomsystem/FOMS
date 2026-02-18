"""주문 표시용 유틸리티 (format_options_for_display, _ensure_dict)."""
import json


def _ensure_dict(data):
    """Ensure data is a dict, properly parsing stringified JSON if needed (migration fix)."""
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            return json.loads(data)
        except Exception:
            return {}
    return {}


def format_options_for_display(options_json_str):
    """옵션 JSON을 한글 표시용 문자열로 변환."""
    if not options_json_str:
        return ""
    try:
        options_data = json.loads(options_json_str)
        key_to_korean = {
            'product_name': '제품명', 'standard': '규격', 'internal': '내부',
            'color': '색상', 'option_detail': '상세옵션', 'handle': '손잡이',
            'misc': '기타', 'quote': '견적내용'
        }
        korean_to_key = {v: k for k, v in key_to_korean.items()}

        if isinstance(options_data, dict):
            if options_data.get("option_type") == "direct" and "details" in options_data:
                details = options_data["details"]
                display_parts = []
                for key, kor_display_name in key_to_korean.items():
                    value = details.get(key)
                    if value:
                        display_parts.append(f"{kor_display_name}: {value}")
                return ", ".join(display_parts) if display_parts else "옵션 정보 없음"
            elif options_data.get("option_type") == "online" and "online_options_summary" in options_data:
                summary = options_data["online_options_summary"]
                return summary.replace('\n', '<br>') if summary else "온라인 옵션 요약 없음"
            elif any(key in options_data for key in key_to_korean.keys()):
                display_parts = []
                for key_eng, value in options_data.items():
                    if value and key_eng in key_to_korean:
                        display_parts.append(f"{key_to_korean[key_eng]}: {value}")
                return ", ".join(display_parts) if display_parts else "옵션 정보 없음 (구)"
            elif any(key_kor in options_data for key_kor in korean_to_key.keys()):
                display_parts = []
                for key_kor, value in options_data.items():
                    if value and key_kor in korean_to_key:
                        display_parts.append(f"{key_kor}: {value}")
                return ", ".join(display_parts) if display_parts else "옵션 정보 없음 (구-한글)"
            else:
                display_parts = []
                for key, value in options_data.items():
                    if isinstance(value, (str, int, float)):
                        display_parts.append(f"{key}: {value}")
                return ", ".join(display_parts) if display_parts else options_json_str
        else:
            return str(options_data)
    except json.JSONDecodeError:
        return options_json_str if options_json_str else "옵션 정보 없음"
    except Exception:
        return options_json_str if options_json_str else "옵션 처리 오류"
