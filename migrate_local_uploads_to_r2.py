#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
다운타임용 마이그레이션 (A안):
  - 로컬 `static/uploads` 파일을 Cloudflare R2로 업로드 (키 유지)
  - DB의 URL을 영구 링크로 통일: `/api/files/view/<storage_key>`

대상:
  - chat_attachments (storage_key, storage_url, thumbnail_url)
  - chat_messages.file_info (url/storage_url/thumbnail_url)  ※ 일부 UI/호환성용
  - orders.blueprint_image_url (로컬 경로인 경우만)

안전 장치:
  - 기본은 dry-run (업로드/DB 변경 없음)
  - 실제 반영하려면 --execute 옵션 필수

필수 환경변수 (R2 업로드 시):
  - R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME

선택 환경변수:
  - UPLOAD_FOLDER (기본: static/uploads)
  - LOCAL_DB_URL (기본: 프로젝트 로컬 기본값)
"""

import argparse
import json
import os
from typing import Optional, Tuple

from sqlalchemy import create_engine, text


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
        os.getenv("LOCAL_DB_URL") or "postgresql+psycopg2://postgres:lahom@localhost/furniture_orders"
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

    engine = create_engine(local_db_url, pool_pre_ping=True)

    # 통계
    stats = {
        "attachments_total": 0,
        "attachments_uploaded_ok": 0,
        "attachments_missing_files": 0,
        "attachments_db_updated": 0,
        "messages_total": 0,
        "messages_db_updated": 0,
        "orders_total": 0,
        "orders_uploaded_ok": 0,
        "orders_missing_files": 0,
        "orders_db_updated": 0,
        "skipped_unextractable_urls": 0,
    }

    with engine.begin() as conn:
        # 1) chat_attachments
        rows = conn.execute(
            text(
                """
                SELECT id, storage_key, storage_url, thumbnail_url
                FROM chat_attachments
                ORDER BY id
                """
            )
        ).fetchall()

        if args.limit:
            rows = rows[: args.limit]

        stats["attachments_total"] = len(rows)
        print(f"[chat_attachments] rows={len(rows)}")

        for r in rows:
            att_id = r.id
            storage_key = r.storage_key

            # 업로드(원본)
            local_path = os.path.join(upload_folder, storage_key)
            if args.execute:
                assert bucket is not None
                ok, msg = upload_file_to_r2(client, bucket, storage_key, local_path, skip_if_exists=args.skip_existing)
                if ok:
                    if msg == "uploaded":
                        stats["attachments_uploaded_ok"] += 1
                else:
                    stats["attachments_missing_files"] += 1
                    print(f"  [WARN] attachment#{att_id} original upload failed: {msg}")
            else:
                # dry-run: 파일 존재만 체크
                if not os.path.exists(local_path):
                    stats["attachments_missing_files"] += 1
                    print(f"  [WARN] attachment#{att_id} missing original: {local_path}")

            # 썸네일 업로드(있으면)
            thumb_key = extract_storage_key_from_url(r.thumbnail_url)
            if thumb_key:
                thumb_path = os.path.join(upload_folder, thumb_key)
                if args.execute:
                    assert bucket is not None
                    ok2, msg2 = upload_file_to_r2(client, bucket, thumb_key, thumb_path, skip_if_exists=args.skip_existing)
                    if not ok2:
                        stats["attachments_missing_files"] += 1
                        print(f"  [WARN] attachment#{att_id} thumb upload failed: {msg2}")
                else:
                    if not os.path.exists(thumb_path):
                        stats["attachments_missing_files"] += 1
                        print(f"  [WARN] attachment#{att_id} missing thumb: {thumb_path}")

            # DB URL 통일 (미리보기용)
            new_storage_url = build_permanent_view_url(storage_key)
            new_thumb_url = build_permanent_view_url(thumb_key) if thumb_key else None

            if args.execute:
                conn.execute(
                    text(
                        """
                        UPDATE chat_attachments
                        SET storage_url = :storage_url,
                            thumbnail_url = :thumbnail_url
                        WHERE id = :id
                        """
                    ),
                    {"storage_url": new_storage_url, "thumbnail_url": new_thumb_url, "id": att_id},
                )
                stats["attachments_db_updated"] += 1

        # 2) chat_messages.file_info (호환성/일관성)
        msg_rows = conn.execute(
            text(
                """
                SELECT id, file_info
                FROM chat_messages
                WHERE file_info IS NOT NULL
                ORDER BY id
                """
            )
        ).fetchall()

        if args.limit:
            msg_rows = msg_rows[: args.limit]

        stats["messages_total"] = len(msg_rows)
        print(f"[chat_messages.file_info] rows={len(msg_rows)}")

        for mr in msg_rows:
            mid = mr.id
            fi = mr.file_info
            if not isinstance(fi, dict):
                continue

            key = fi.get("key") or fi.get("storage_key")
            if not key:
                continue

            thumb_key = extract_storage_key_from_url(fi.get("thumbnail_url"))
            fi["url"] = build_permanent_view_url(key)
            fi["storage_url"] = fi["url"]
            if thumb_key:
                fi["thumbnail_url"] = build_permanent_view_url(thumb_key)

            if args.execute:
                conn.execute(
                    text("UPDATE chat_messages SET file_info = CAST(:fi AS jsonb) WHERE id = :id"),
                    {"fi": json.dumps(fi, ensure_ascii=False), "id": mid},
                )
                stats["messages_db_updated"] += 1

        # 3) orders.blueprint_image_url
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

