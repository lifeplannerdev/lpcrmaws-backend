-- ==============================================================================
-- Independent SQL Script: Add 'admin:dashboard' Permission
-- File: lpcrmbackend-main/scripts/add_admin_dashboard_perm.sql
-- 
-- Description:
-- Registers the 'admin:dashboard' permission independently into the permissions
-- table and safely attaches it to ADMIN, CEO, and managing_director roles in the
-- role_permissions join table without clearing or modifying existing mappings.
-- ==============================================================================

BEGIN;

-- 1. Insert or update the admin:dashboard permission
INSERT INTO permissions (name, description)
VALUES (
    'admin:dashboard',
    'Full administrative access to CRM overview dashboard, metrics, analytics, and operational aggregations'
)
ON CONFLICT (name) DO UPDATE
SET description = EXCLUDED.description;

-- 2. Associate with ADMIN, CEO, and managing_director roles safely
INSERT INTO role_permissions (role_id, apppermission_id)
SELECT r.id, p.id
FROM roles r
CROSS JOIN permissions p
WHERE p.name = 'admin:dashboard'
  AND r.name IN ('ADMIN', 'CEO', 'managing_director')
ON CONFLICT (role_id, apppermission_id) DO NOTHING;

COMMIT;

-- Verify results
SELECT p.id AS permission_id, p.name AS permission_name, r.id AS role_id, r.name AS role_name
FROM permissions p
JOIN role_permissions rp ON rp.apppermission_id = p.id
JOIN roles r ON rp.role_id = r.id
WHERE p.name = 'admin:dashboard';
