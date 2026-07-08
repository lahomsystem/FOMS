-- ERP_BETA retirement G-DATA read-only probe
-- Purpose:
--   1) Find active orders still carrying legacy "ERP Beta" literals
--   2) Find draft/placeholder rows that still look like ERP form bootstrap data
-- Safe:
--   Read-only SELECTs only. No INSERT/UPDATE/DELETE.

-- 1) Summary counts
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
          AND COALESCE(customer_name, '') = 'ERP Order'
          AND COALESCE(phone, '') = '000-0000-0000'
    ) AS active_canonical_placeholder_rows,
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
    ) AS active_structured_meta_draft_true_rows;

-- 2) Sample rows to inspect manually
SELECT
    id,
    status,
    customer_name,
    phone,
    product,
    LEFT(COALESCE(options, ''), 120) AS options_preview,
    COALESCE(structured_data #>> '{meta,draft}', '') AS structured_meta_draft,
    COALESCE(structured_data #>> '{parties,customer,name}', '') AS structured_customer_name,
    COALESCE(structured_data #>> '{items,0,product_name}', '') AS structured_first_product
FROM orders
WHERE status <> 'DELETED'
  AND (
      UPPER(COALESCE(customer_name, '')) = 'ERP BETA'
      OR UPPER(COALESCE(product, '')) = 'ERP BETA'
      OR UPPER(COALESCE(options, '')) = 'ERP BETA'
      OR (
          COALESCE(customer_name, '') = 'ERP Order'
          AND COALESCE(phone, '') = '000-0000-0000'
      )
      OR COALESCE(structured_data #>> '{meta,draft}', 'false') = 'true'
      OR COALESCE(structured_data::text, '') ILIKE '%ERP Beta%'
      OR COALESCE(structured_data::text, '') ILIKE '%ERP_BETA%'
  )
ORDER BY id DESC
LIMIT 50;
