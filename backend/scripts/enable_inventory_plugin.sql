-- enable_inventory_plugin.sql
-- Run this script against your omni_erp database to enable the inventory plugin
-- for your test tenant.

-- Option A: Update ALL tenants to have the inventory plugin
UPDATE public.tenants
SET active_plugins = (
    SELECT jsonb_agg(DISTINCT elem)
    FROM jsonb_array_elements_text(
        CASE 
            WHEN active_plugins IS NULL THEN '[]'::jsonb
            ELSE active_plugins::jsonb 
        END
    ) AS elem
    UNION
    SELECT 'inventory'
);

-- Option B: Update a SPECIFIC tenant (replace with your tenant ID)
-- UPDATE public.tenants
-- SET active_plugins = '["accounting", "contacts", "inventory"]'::jsonb
-- WHERE id = 'YOUR-TENANT-UUID';
