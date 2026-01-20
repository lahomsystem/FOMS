from db import engine
from sqlalchemy import text
from pprint import pprint

with engine.begin() as conn:
    print("users:")
    pprint(conn.execute(text("SELECT id, username, name, role FROM users ORDER BY id LIMIT 10")).fetchall())

    print("\norders:")
    pprint(conn.execute(text("SELECT id, customer_name, blueprint_image_url FROM orders ORDER BY id DESC LIMIT 3")).fetchall())

    print("\nchat_attachments:")
    pprint(conn.execute(text("SELECT id, storage_key, storage_url, thumbnail_url FROM chat_attachments ORDER BY id DESC LIMIT 5")).fetchall())

    print("\norder_attachments:")
    try:
        pprint(conn.execute(text("SELECT id, order_id, storage_key, thumbnail_key FROM order_attachments ORDER BY id DESC LIMIT 5")).fetchall())
    except Exception as e:
        print("order_attachments query failed:", e)

