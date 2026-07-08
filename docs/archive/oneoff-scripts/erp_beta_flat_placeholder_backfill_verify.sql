-- ERP_BETA retirement: flat placeholder backfill verification
-- Purpose:
--   Verify whether flat placeholder cleanup has removed the G-DATA blocker.
-- Safe:
--   Read-only SELECTs only.
--
-- Expected after successful auto-backfill:
--   - active_customer_name_erp_beta = 0
--   - active_product_erp_beta = 1 or 0
--   - remaining product placeholder row should only be manual follow-up candidate id 1845

-- 1) Original G-DATA summary after cleanup
SELECT
    COUNT(*) FILTER (WHERE status <> 'DELETED') AS active_orders,
    COUNT(*) FILTER (
        WHERE status <> 'DELETED'
          AND UPPER(COALESCE(customer_name, '')) = 'ERP BETA'
    ) AS active_customer_name_erp_beta,
    COUNT(*) FILTER (
        WHERE status <> 'DELETED'
          AND UPPER(COALESCE(product, '')) = 'ERP BETA'
    ) AS active_product_erp_beta,
    COUNT(*) FILTER (
        WHERE status <> 'DELETED'
          AND UPPER(COALESCE(options, '')) = 'ERP BETA'
    ) AS active_options_erp_beta,
    COUNT(*) FILTER (
        WHERE status <> 'DELETED'
          AND (
              COALESCE(structured_data::text, '') ILIKE '%ERP Beta%'
              OR COALESCE(structured_data::text, '') ILIKE '%ERP_BETA%'
          )
    ) AS active_structured_legacy_literal_rows,
    COUNT(*) FILTER (
        WHERE status <> 'DELETED'
          AND COALESCE(structured_data #>> '{meta,draft}', 'false') = 'true'
    ) AS active_structured_meta_draft_true_rows
FROM orders;

-- 2) Residual placeholder rows that still need manual review
SELECT
    id,
    status,
    customer_name,
    phone,
    product,
    address,
    COALESCE(structured_data #>> '{parties,customer,name}', '') AS structured_customer_name,
    COALESCE(structured_data #>> '{parties,customer,phone}', '') AS structured_customer_phone,
    COALESCE(structured_data #>> '{site,address_full}', structured_data #>> '{site,address_main}', '') AS structured_address,
    LEFT(COALESCE(structured_data::text, ''), 500) AS structured_data_preview
FROM orders
WHERE status <> 'DELETED'
  AND (
      UPPER(COALESCE(customer_name, '')) = 'ERP BETA'
      OR UPPER(COALESCE(product, '')) = 'ERP BETA'
      OR COALESCE(phone, '') = '000-0000-0000'
  )
ORDER BY id DESC
LIMIT 50;

-- 3) Manual follow-up row expected from current production snapshot
SELECT
    id,
    status,
    customer_name,
    phone,
    product,
    structured_data
FROM orders
WHERE id = 1845;
