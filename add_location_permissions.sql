-- Direct SQL script to add new location permissions into the permissions table
-- Safe to re-run (idempotent)

-- PostgreSQL:
INSERT INTO permissions (name, description) VALUES
('tasks:kochi', 'Assign, approve and view all tasks for staff with location Kochi (cannot approve own task)'),
('tasks:kottayam', 'Assign, approve and view all tasks for staff with location Kottayam (cannot approve own task)'),
('staff_analysis:kochi', 'View staff analysis, team members and leads for Kochi staff (no access to lead command center)'),
('staff_analysis:kottayam', 'View staff analysis, team members and leads for Kottayam staff (no access to lead command center)'),
('reports:approval-kochi', 'Approve and reject daily reports for Kochi staff (cannot approve or reject own reports)'),
('reports:approval-kottayam', 'Approve and reject daily reports for Kottayam staff (cannot approve or reject own reports)')
ON CONFLICT (name) DO NOTHING;
