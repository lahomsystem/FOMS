-- ERP_BETA retirement: flat placeholder backfill apply
-- Purpose:
--   Backfill active ERP order flat columns from structured_data so we can
--   retire runtime placeholder suppressors and legacy ERP_BETA aliases safely.
--
-- Scope:
--   - status <> 'DELETED'
--   - is_erp_order = true
--   - only rows whose flat columns are blank / placeholder values
--   - only fields with trustworthy structured_data replacements are updated
--
-- Current production dry-run baseline on 2026-04-18:
--   - any backfill candidates: 564
--   - customer_name: 564
--   - phone: 559
--   - product: 564
--   - address: 558
--   - expected unresolved product placeholder rows after auto-backfill: 1 (order id 1845)
--
-- Product fallback policy:
--   1) first non-empty item.product_name or item.name
--   2) if missing and first item represents AS/consulting ("상담"), use '상담'
--   3) otherwise leave product untouched for manual follow-up

BEGIN;

WITH base AS (
    SELECT
        o.id,
        BTRIM(COALESCE(o.customer_name, '')) AS current_customer_name,
        BTRIM(COALESCE(o.phone, '')) AS current_phone,
        BTRIM(COALESCE(o.product, '')) AS current_product,
        BTRIM(COALESCE(o.address, '')) AS current_address,
        BTRIM(COALESCE(o.structured_data #>> '{parties,customer,name}', '')) AS structured_customer_name,
        BTRIM(COALESCE(o.structured_data #>> '{parties,customer,phone}', '')) AS structured_customer_phone,
        BTRIM(COALESCE(o.structured_data #>> '{site,address_full}', o.structured_data #>> '{site,address_main}', '')) AS structured_address,
        BTRIM(COALESCE(
            (
                SELECT candidate.product_value
                FROM (
                    SELECT
                        item.ord,
                        BTRIM(COALESCE(item.elem->>'product_name', item.elem->>'name', '')) AS product_value
                    FROM jsonb_array_elements(COALESCE(o.structured_data->'items', '[]'::jsonb)) WITH ORDINALITY AS item(elem, ord)
                ) AS candidate
                WHERE candidate.product_value <> ''
                  AND UPPER(candidate.product_value) NOT IN ('ERP BETA', 'ERP ORDER')
                ORDER BY candidate.ord
                LIMIT 1
            ),
            ''
        )) AS structured_first_product,
        BTRIM(COALESCE(
            o.structured_data #>> '{items,0,option_detail}',
            o.structured_data #>> '{items,0,handle}',
            o.structured_data #>> '{items,0,misc}',
            o.structured_data #>> '{items,0,internal}',
            ''
        )) AS structured_consulting_label
    FROM orders o
    WHERE o.status <> 'DELETED'
      AND o.is_erp_order = true
),
final AS (
    SELECT
        *,
        CASE
            WHEN structured_first_product <> '' THEN structured_first_product
            WHEN structured_consulting_label = '상담' THEN '상담'
            ELSE ''
        END AS structured_product_fallback,
        (current_customer_name = '' OR UPPER(current_customer_name) IN ('ERP BETA', 'ERP ORDER'))
            AND structured_customer_name <> ''
            AND UPPER(structured_customer_name) NOT IN ('ERP BETA', 'ERP ORDER') AS needs_customer_backfill,
        (current_phone = '' OR current_phone = '000-0000-0000')
            AND structured_customer_phone <> ''
            AND structured_customer_phone <> '000-0000-0000' AS needs_phone_backfill,
        (current_product = '' OR UPPER(current_product) IN ('ERP BETA', 'ERP ORDER'))
            AND (
                structured_first_product <> ''
                OR structured_consulting_label = '상담'
            ) AS needs_product_backfill,
        (current_address = '' OR current_address = '-')
            AND structured_address <> ''
            AND structured_address <> '-' AS needs_address_backfill
    FROM base
)
UPDATE orders AS o
SET
    customer_name = CASE
        WHEN final.needs_customer_backfill THEN final.structured_customer_name
        ELSE o.customer_name
    END,
    phone = CASE
        WHEN final.needs_phone_backfill THEN final.structured_customer_phone
        ELSE o.phone
    END,
    product = CASE
        WHEN final.needs_product_backfill THEN final.structured_product_fallback
        ELSE o.product
    END,
    address = CASE
        WHEN final.needs_address_backfill THEN final.structured_address
        ELSE o.address
    END
FROM final
WHERE o.id = final.id
  AND (
      final.needs_customer_backfill
      OR final.needs_phone_backfill
      OR final.needs_product_backfill
      OR final.needs_address_backfill
  )
RETURNING
    o.id,
    final.current_customer_name AS old_customer_name,
    o.customer_name AS new_customer_name,
    final.current_phone AS old_phone,
    o.phone AS new_phone,
    final.current_product AS old_product,
    o.product AS new_product,
    final.current_address AS old_address,
    o.address AS new_address;

COMMIT;
