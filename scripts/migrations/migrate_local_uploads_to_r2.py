#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
다운타임용 마이그레이션 (A안):
  - 로컬 `static/uploads` 파일을 Cloudflare R2로 업로드 (키 유지)
  - DB의 URL을 영구 링크로 통일: `/api/files/view/<storage_key>`

대상:
  - orders.blueprint_image_url (로컬 경로인 경우만)
  (옛 chat_attachments · chat_messages 단계는 CHAT-DEL-01 2단계로 표째 지워 뺐다)

안전 장치:
  - 기본은 dry-run (업로드/DB 변경 없음)
  - 실제 반영하려면 --execute 옵션 필수

필수 환경변수 (R2 업로드 시):
  - R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME

선택 환경변수:
  - UPLOAD_FOLDER (기본: static/uploads)
  - LOCAL_DB_URL (기본: 프로젝트 로컬 기본값)
"""

from pathlib import Path
import sys

_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import argparse
import os
from typing import Optional, Tuple

from sqlalchemy import create_engine, text

from foms.services.db_url_resolver import sqlalchemy_url

from foms.services.common.table_version_counter import bump_table_versions


def normalize_postgres_url(url: str) -> str:
    if url and url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def extract_storage_key_from_url(url: Optional[str]) -> Optional[str]:
    """
    URL 형태:
      - /static/uploads/<key>
      - /api/chat/download/<key>
      - /api/files/view/<key>
      - /api/files/download/<key>
    위 두 케이스만 안정적으로 key를 추출한다.
    (presigned URL 등은 케이스가 다양하고 만료될 수 있어 여기서는 제외)
    """
    if not url or not isinstance(url, str):
        return None
    if url.startswith("/static/uploads/"):
        return url[len("/static/uploads/") :]
    if url.startswith("/api/chat/download/"):
        return url[len("/api/chat/download/") :]
    if url.startswith("/api/files/view/"):
        return url[len("/api/files/view/") :]
    if url.startswith("/api/files/download/"):
        return url[len("/api/files/download/") :]
    return None


def build_permanent_view_url(storage_key: str) -> str:
    return f"/api/files/view/{storage_key}"


def ensure_r2_env() -> None:
    missing = [k for k in ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"] if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"R2 환경변수 누락: {', '.join(missing)}")


def make_r2_client():
    import boto3

    account_id = os.getenv("R2_ACCOUNT_ID")
    endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )


def r2_object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def upload_file_to_r2(
    client,
    bucket: str,
    key: str,
    local_path: str,
    *,
    skip_if_exists: bool,
) -> Tuple[bool, str]:
    if not os.path.exists(local_path):
        return False, f"missing_local_file: {local_path}"

    if skip_if_exists and r2_object_exists(client, bucket, key):
        return True, "skip_exists"

    with open(local_path, "rb") as f:
        client.upload_fileobj(f, bucket, key)
    return True, "uploaded"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="실제 업로드 + DB 업데이트 수행 (기본은 dry-run)")
    parser.add_argument("--skip-existing", action="store_true", help="R2에 이미 존재하면 업로드 스킵(head_object)")
    parser.add_argument("--limit", type=int, default=0, help="처리 건수 제한(0=무제한)")
    args = parser.parse_args()

    upload_folder = os.getenv("UPLOAD_FOLDER", "static/uploads")
    local_db_url = normalize_postgres_url(
        os.getenv("LOCAL_DB_URL") or "postgresql://postgres:lahom@localhost/furniture_orders"
    )

    print("=" * 70)
    print("migrate_local_uploads_to_r2")
    print("=" * 70)
    print(f"mode: {'EXECUTE' if args.execute else 'DRY_RUN'}")
    print(f"upload_folder: {upload_folder}")
    print(f"local_db_url: {local_db_url}")
    print(f"skip_existing: {args.skip_existing}")
    print(f"limit: {args.limit or 'no-limit'}")
    print()

    # R2 클라이언트 준비(실행 모드에서만 필수)
    client = None
    bucket = None
    if args.execute:
        ensure_r2_env()
        client = make_r2_client()
        bucket = os.getenv("R2_BUCKET_NAME")
        if not bucket:
            raise RuntimeError("R2_BUCKET_NAME is required when --execute is set")

    engine = create_engine(sqlalchemy_url(local_db_url), pool_pre_ping=True)

    # 통계
    stats = {
        "orders_total": 0,
        "orders_uploaded_ok": 0,
        "orders_missing_files": 0,
        "orders_db_updated": 0,
        "skipped_unextractable_urls": 0,
    }

    with engine.begin() as conn:
        # orders.blueprint_image_url
        order_rows = conn.execute(
            text(
                """
                SELECT id, blueprint_image_url
                FROM orders
                WHERE blueprint_image_url IS NOT NULL AND blueprint_image_url <> ''
                ORDER BY id
                """
            )
        ).fetchall()

        if args.limit:
            order_rows = order_rows[: args.limit]

        stats["orders_total"] = len(order_rows)
        print(f"[orders.blueprint_image_url] rows={len(order_rows)}")

        for orow in order_rows:
            oid = orow.id
            url = orow.blueprint_image_url

            key = extract_storage_key_from_url(url)
            if not key:
                # presigned 등은 여기서 자동 처리 불가(원본 키를 알기 어렵다)
                stats["skipped_unextractable_urls"] += 1
                print(f"  [WARN] order#{oid} blueprint url not extractable: {url}")
                continue

            local_path = os.path.join(upload_folder, key)
            if args.execute:
                assert bucket is not None
                ok, msg = upload_file_to_r2(client, bucket, key, local_path, skip_if_exists=args.skip_existing)
                if ok:
                    if msg == "uploaded":
                        stats["orders_uploaded_ok"] += 1
                else:
                    stats["orders_missing_files"] += 1
                    print(f"  [WARN] order#{oid} blueprint upload failed: {msg}")
            else:
                if not os.path.exists(local_path):
                    stats["orders_missing_files"] += 1
                    print(f"  [WARN] order#{oid} blueprint missing local: {local_path}")

            new_url = build_permanent_view_url(key)
            if args.execute:
                conn.execute(
                    text("UPDATE orders SET blueprint_image_url = :u WHERE id = :id"),
                    {"u": new_url, "id": oid},
                )
                stats["orders_db_updated"] += 1

    # HB-S1: 이 스크립트는 Session 이 아니라 Connection(engine.begin) 으로 raw UPDATE 를
    # 낸다. 세션 훅이 볼 수 없으므로, 트랜잭션이 성공적으로 닫힌 뒤 orders 카운터를
    # 직접 올린다(mark_tables_dirty 는 Session 전용이라 여기서는 못 쓴다).
    if stats["orders_db_updated"]:
        bump_table_versions("orders")

    print()
    print("=" * 70)
    print("RESULT")
    print("=" * 70)
    for k, v in stats.items():
        print(f"{k}: {v}")
    print()
    if not args.execute:
        print("[DRY_RUN] 실제 반영하려면 --execute 옵션을 붙여 실행하세요.")


if __name__ == "__main__":
    main()

