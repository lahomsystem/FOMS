"""signing key slot inspect — key-ID/encoding only artifact (SESSION-SIGNING-STATE-00).

    python tools/ops/inspect_signing_key_slot.py --slot CURRENT --output <redacted.json>

env slot(``FOMS_SIGNING_KEY_CURRENT`` / ``FOMS_SIGNING_KEY_NEXT``)의 root 를 strict decode
해 **key ID 와 encoding 메타데이터만** artifact 로 남긴다. root/subkey 등 비밀 bytes 는
stdout·artifact 어디에도 넣지 않는다. 이 CLI 는 읽기 전용이며 approval 토큰을 소비하지
않는다(DB 도 건드리지 않는다).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.datetime_kst import now_utc_naive  # noqa: E402
from foms.services.security.signing.signing_key_format import (  # noqa: E402
    ROOT_KEY_BYTES,
    SigningKeyFormatError,
    decode_root_key,
    key_id_from_root,
)

_SLOT_ENV = {
    "CURRENT": "FOMS_SIGNING_KEY_CURRENT",
    "NEXT": "FOMS_SIGNING_KEY_NEXT",
}


def build_artifact(slot: str, env_value: str) -> dict:
    """slot env 값을 decode 해 key-ID/encoding only artifact dict 를 만든다(비밀 0)."""
    root = decode_root_key(env_value)  # strict decode; length 검증
    return {
        "schema_version": 1,
        "slot": slot,
        "key_id": key_id_from_root(root),
        "encoding": "base64url-nopad",
        "byte_length": ROOT_KEY_BYTES,
        "captured_at": now_utc_naive().isoformat(),
    }


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect a signing key slot and emit a key-ID/encoding-only artifact.")
    parser.add_argument("--slot", required=True, choices=sorted(_SLOT_ENV))
    parser.add_argument("--output", required=True, help="redacted artifact 출력 경로")
    args = parser.parse_args(argv)

    env_name = _SLOT_ENV[args.slot]
    env_value = os.environ.get(env_name, "").strip()
    if not env_value:
        raise SystemExit(f"env {env_name} is not set (slot {args.slot} unavailable).")

    try:
        artifact = build_artifact(args.slot, env_value)
    except SigningKeyFormatError as exc:
        # 예외 메시지에도 비밀은 없다(format helper 계약).
        raise SystemExit(f"slot {args.slot} key format error: {exc}")

    out_path = Path(args.output)
    out_path.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    # stdout 에는 key ID 만(비밀 0).
    print(json.dumps({"slot": args.slot, "key_id": artifact["key_id"], "output": str(out_path)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
