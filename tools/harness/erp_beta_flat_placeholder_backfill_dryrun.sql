-- ERP_BETA retirement: flat placeholder backfill dry-run
-- Purpose:
--   Preview which active ERP orders can be safely backfilled from structured_data
--   before removing runtime placeholder suppressors / legacy aliases.
-- Safe:
--   Read-only SELECTs only.
--
-- Current production snapshot on 2026-04-18 (read-only probe):
--   - active ERP orders: 565
--   - any backfill candidates: 564
--   - customer_name candidates: 564
--   - phone candidates: 559
--   - product candidates: 564 (includes 43 "상담" fallback rows)
--   - address candidates: 558
--   - unresolved placeholder product rows after auto-backfill: 1 (order id 1845)

WITH base AS (
    SELECT
        o.id,
        o.status,
        o.is_erp_order,
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
SELECT
    COUNT(*) AS active_erp_orders,
    COUNT(*) FILTER (WHERE needs_customer_backfill) AS customer_backfill_candidates,
    COUNT(*) FILTER (WHERE needs_phone_backfill) AS phone_backfill_candidates,
    COUNT(*) FILTER (WHERE needs_product_backfill) AS product_backfill_candidates,
    COUNT(*) FILTER (WHERE needs_address_backfill) AS address_backfill_candidates,
    COUNT(*) FILTER (
        WHERE needs_customer_backfill OR needs_phone_backfill OR needs_product_backfill OR needs_address_backfill
    ) AS any_backfill_candidates,
    COUNT(*) FILTER (
        WHERE UPPER(current_product) IN ('ERP BETA', 'ERP ORDER')
          AND NOT needs_product_backfill
    ) AS unresolved_placeholder_product_rows
FROM final;

WITH base AS (
    SELECT
        o.id,
        o.status,
        o.is_erp_order,
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
        END AS suggested_product,
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
SELECT
    id,
    status,
    current_customer_name,
    structured_customer_name AS suggested_customer_name,
    current_phone,
    structured_customer_phone AS suggested_phone,
    current_product,
    suggested_product,
    current_address,
    structured_address AS suggested_address,
    structured_consulting_label,
    needs_customer_backfill,
    needs_phone_backfill,
    needs_product_backfill,
    needs_address_backfill
FROM final
WHERE needs_customer_backfill
   OR needs_phone_backfill
   OR needs_product_backfill
   OR needs_address_backfill
   OR (
       UPPER(current_product) IN ('ERP BETA', 'ERP ORDER')
       AND NOT needs_product_backfill
   )
ORDER BY id DESC
LIMIT 100;
