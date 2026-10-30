"""
Milestone 4 Challenger Empirical Production Workload & E2E Verification Script
Auditor: challenger_m4_2 (Empirical Challenger)
Target: Live EC2 Production Server (13.205.190.151)
Live DB: PostgreSQL with 17,502 leads, 19,820 followups, 44,956 activity logs (82,502 total records)
"""

import os
import sys
import time
import json
import statistics

# Set up Django environment on remote EC2 host
sys.path.insert(0, '/home/lpcrm/lpcrmaws-backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
import django
django.setup()

from django.db import connection, reset_queries
from django.conf import settings
from rest_framework.test import APIClient
from accounts.models import User, Role, AppPermission
from accounts.permissions import has_dynamic_permission
from accounts.dashboard_service import DashboardAggregationService
from leads.models import Lead, FollowUp
from tasks.models import Task

print("=" * 80)
print("MILENSTONE 4 EMPIRICAL VERIFICATION HARNESS — challenger_m4_2")
print("Target: EC2 Live Production Environment (PostgreSQL lpcrm)")
print("=" * 80)

# ==============================================================================
# SECTION 1: DATABASE INVENTORY & INTEGRITY AUDIT
# ==============================================================================
print("\n>>> SECTION 1: Live Production Database Record Inventory")
lead_count = Lead.objects.count()
followup_count = FollowUp.objects.count()
task_count = Task.objects.count()
user_count = User.objects.count()

print(f"[*] Verified Lead count:       {lead_count:,}")
print(f"[*] Verified FollowUp count:   {followup_count:,}")
print(f"[*] Verified Task count:       {task_count:,}")
print(f"[*] Verified User count:       {user_count:,}")

if lead_count < 17500:
    print(f"[FAIL] Expected at least 17,500 leads, found {lead_count}")
    sys.exit(1)
else:
    print(f"[PASS] Confirmed live production workload across {lead_count:,} leads (> 17,500 records)")

# Find key test users
admin_user = User.objects.filter(db_roles__name='ADMIN', is_active=True).first()
if not admin_user:
    admin_user = User.objects.filter(is_superuser=True).first()

ceo_user = User.objects.filter(db_roles__name='CEO').first()
md_user = User.objects.filter(db_roles__name='managing_director').first()

# Non-admin users across different roles
operation_user = User.objects.filter(db_roles__name='OPERATION', is_active=True).first()
trainer_user = User.objects.filter(db_roles__name='TRAINER', is_active=True).first()
counsellor_user = User.objects.filter(db_roles__name='ADM_COUNSELLOR').first()
telecaller_user = User.objects.filter(db_roles__name='ADM_EXEC').first()

print(f"[*] Admin user selected:       {admin_user.username if admin_user else 'None'}")
print(f"[*] Operations user selected:  {operation_user.username if operation_user else 'None'}")
print(f"[*] Trainer user selected:     {trainer_user.username if trainer_user else 'None'}")
print(f"[*] Counsellor user selected:  {counsellor_user.username if counsellor_user else 'None'}")

# ==============================================================================
# SECTION 2: QUERY EXECUTION TIME BENCHMARK ACROSS 17,500+ RECORDS
# ==============================================================================
print("\n>>> SECTION 2: Query Execution Time Benchmark on Live 17,500+ Records")

def benchmark_aggregation(user, runs=10, label="User"):
    timings = []
    # Warmup
    _ = DashboardAggregationService.get_dashboard_data(user)
    for i in range(runs):
        start = time.perf_counter()
        data = DashboardAggregationService.get_dashboard_data(user)
        duration_ms = (time.perf_counter() - start) * 1000.0
        timings.append(duration_ms)
    
    mean_t = statistics.mean(timings)
    median_t = statistics.median(timings)
    min_t = min(timings)
    max_t = max(timings)
    stdev_t = statistics.stdev(timings) if len(timings) > 1 else 0.0
    
    print(f"--- Benchmark Results: {label} ({runs} runs) ---")
    print(f"    Mean latency:     {mean_t:.2f} ms")
    print(f"    Median latency:   {median_t:.2f} ms")
    print(f"    Min latency:      {min_t:.2f} ms")
    print(f"    Max latency:      {max_t:.2f} ms")
    print(f"    Stdev:            {stdev_t:.2f} ms")
    print(f"    Per-run (ms):     {[round(t, 1) for t in timings]}")
    return {
        "mean": mean_t,
        "median": median_t,
        "min": min_t,
        "max": max_t,
        "stdev": stdev_t,
        "runs": timings
    }

admin_bench = benchmark_aggregation(admin_user, runs=10, label=f"ADMIN ({admin_user.username}) - Full Aggregation")

test_staff = operation_user or counsellor_user or trainer_user
staff_bench = benchmark_aggregation(test_staff, runs=10, label=f"STAFF ({test_staff.username}) - Scoped Aggregation")

# Production SLA check (< 500ms under full live 17,500+ records)
if admin_bench['mean'] < 500.0:
    print(f"[PASS] Admin aggregation mean latency {admin_bench['mean']:.2f}ms satisfies strict production SLA (<500ms)")
else:
    print(f"[FAIL] Admin aggregation mean latency {admin_bench['mean']:.2f}ms exceeds 500ms SLA threshold!")

# ==============================================================================
# SECTION 3: EMPIRICAL N+1 QUERY REGRESSION VERIFICATION
# ==============================================================================
print("\n>>> SECTION 3: Empirical N+1 Query Regression Verification")

# Enable query logging
original_debug = settings.DEBUG
settings.DEBUG = True

def profile_queries(user, label="User"):
    reset_queries()
    start_q_count = len(connection.queries)
    t0 = time.perf_counter()
    data = DashboardAggregationService.get_dashboard_data(user)
    elapsed = (time.perf_counter() - t0) * 1000.0
    executed_queries = connection.queries[start_q_count:]
    q_count = len(executed_queries)
    
    print(f"\n[*] Query Count Profile: {label}")
    print(f"    Total SQL queries executed: {q_count}")
    print(f"    Total execution time: {elapsed:.2f}ms")
    for idx, q in enumerate(executed_queries, 1):
        sql_summary = " ".join(q['sql'].split())[:120]
        print(f"    Query #{idx} ({q['time']}s): {sql_summary}...")
    
    return q_count, executed_queries

admin_q_count, admin_queries = profile_queries(admin_user, f"ADMIN ({admin_user.username})")
staff_q_count, staff_queries = profile_queries(test_staff, f"STAFF ({test_staff.username})")
counsellor_q_count, _ = profile_queries(counsellor_user, f"COUNSELLOR ({counsellor_user.username})") if counsellor_user else (None, None)

settings.DEBUG = original_debug

print(f"\n[*] Evaluating N+1 Regression Criteria:")
print(f"    Live Leads in DB:          {lead_count:,}")
print(f"    Live FollowUps in DB:      {followup_count:,}")
print(f"    Admin SQL Query Count:     {admin_q_count}")
print(f"    Staff SQL Query Count:     {staff_q_count}")
if counsellor_q_count is not None:
    print(f"    Counsellor SQL Query Count:{counsellor_q_count}")

# Rigorous N+1 check:
# If there were an N+1 query regression, query count would scale with lead_count (17,502 queries)
# An O(1) constant design will execute <= 12 queries total.
if admin_q_count <= 12 and staff_q_count <= 12:
    print(f"[PASS] ZERO N+1 QUERY REGRESSION CONFIRMED! Constant query count ({admin_q_count} admin, {staff_q_count} staff) over {lead_count:,} records.")
else:
    print(f"[FAIL] Potential N+1 query regression detected: query count {admin_q_count} is too high!")

# ==============================================================================
# SECTION 4: UNAUTHENTICATED REQUESTS REJECTED (HTTP 401)
# ==============================================================================
print("\n>>> SECTION 4: Unauthenticated Requests Rejection Verification")

# Use secure=True because EC2 production settings enforce SECURE_SSL_REDIRECT = True
client = APIClient()

# Test 1: Completely unauthenticated GET /api/dashboard/stats/
resp_unauth = client.get('/api/dashboard/stats/', secure=True)
print(f"[*] GET /api/dashboard/stats/ (secure=True) without auth -> HTTP {resp_unauth.status_code}")
if resp_unauth.status_code == 401:
    print(f"[PASS] Unauthenticated request correctly rejected with HTTP 401 Unauthorized")
else:
    print(f"[FAIL] Expected HTTP 401, got {resp_unauth.status_code}")

# Test 2: Unauthenticated with bogus Bearer token
client.credentials(HTTP_AUTHORIZATION='Bearer invalid_bogus_token_12345')
resp_bogus = client.get('/api/dashboard/stats/', secure=True)
print(f"[*] GET /api/dashboard/stats/ with invalid Bearer token -> HTTP {resp_bogus.status_code}")
if resp_bogus.status_code == 401:
    print(f"[PASS] Invalid token correctly rejected with HTTP 401 Unauthorized")
else:
    print(f"[FAIL] Expected HTTP 401, got {resp_bogus.status_code}")

# Clear credentials
client.credentials()

# Test 3: Unauthenticated GET /api/stats/ (legacy endpoint)
resp_legacy = client.get('/api/stats/', secure=True)
print(f"[*] GET /api/stats/ (secure=True) without auth -> HTTP {resp_legacy.status_code}")
if resp_legacy.status_code == 401:
    print(f"[PASS] Legacy /api/stats/ unauthenticated correctly rejected with HTTP 401")
else:
    print(f"[FAIL] Expected HTTP 401, got {resp_legacy.status_code}")

# ==============================================================================
# SECTION 5: AUTHENTICATED NON-ADMIN PRIVILEGE ISOLATION & DATA SCOPING
# ==============================================================================
print("\n>>> SECTION 5: Non-Admin Privilege Isolation & Boundary Verification")

for candidate in [operation_user, counsellor_user, trainer_user]:
    if not candidate:
        continue
    has_admin_perm = has_dynamic_permission(candidate, 'admin:dashboard')
    print(f"\n[*] Testing non-admin candidate: {candidate.username} (Roles: {list(candidate.db_roles.values_list('name', flat=True))})")
    print(f"    has_dynamic_permission('admin:dashboard') = {has_admin_perm}")
    if has_admin_perm:
        print(f"    [FAIL] Candidate unexpectedly has admin:dashboard permission!")
        continue

    client.force_authenticate(user=candidate)
    resp = client.get('/api/dashboard/stats/', secure=True)
    print(f"    GET /api/dashboard/stats/ status code: {resp.status_code}")
    
    if resp.status_code == 200:
        cdata = resp.data
        exec_fin = cdata.get('metrics', {}).get('executive_financials')
        role_sec_fin = cdata.get('role_sections', {}).get('executive_financials')
        has_dash = cdata.get('has_admin_dashboard')
        cand_leads = cdata.get('metrics', {}).get('leads', {}).get('total', 0)
        
        print(f"    has_admin_dashboard: {has_dash}")
        print(f"    metrics.executive_financials: {exec_fin}")
        print(f"    role_sections.executive_financials: {role_sec_fin}")
        print(f"    scoped total leads: {cand_leads} (out of {lead_count:,} live leads)")
        
        if exec_fin is None and role_sec_fin is None and has_dash is False:
            print("    [PASS] executive_financials strictly hidden (None) for staff user")
        else:
            print(f"    [FAIL] executive_financials leaked to non-admin user {candidate.username}!")
            
        if cand_leads < lead_count:
            print(f"    [PASS] Leads count scoped to assigned records ({cand_leads} < {lead_count:,})")
        else:
            print(f"    [FAIL] Staff user can see all company leads ({cand_leads})! Data scoping breached!")
            
    elif resp.status_code == 403:
        print(f"    [PASS] User without stats viewing permissions strictly rejected with HTTP 403 Forbidden")
    else:
        print(f"    [FAIL] Unexpected HTTP status: {resp.status_code}")

# 5.2 Adversarial Parameter Injection: ?company=ALL parameter tampering
print("\n[*] Testing Parameter Tampering (?company=ALL) on Non-Admin User:")
client.force_authenticate(user=test_staff)
resp_tamper = client.get('/api/dashboard/stats/?company=ALL', secure=True)
if resp_tamper.status_code == 200:
    tamper_fin = resp_tamper.data.get('metrics', {}).get('executive_financials')
    tamper_leads = resp_tamper.data.get('metrics', {}).get('leads', {}).get('total', 0)
    print(f"    Staff with ?company=ALL total leads: {tamper_leads}")
    print(f"    Staff with ?company=ALL executive_financials: {tamper_fin}")
    if tamper_fin is None and tamper_leads < lead_count:
        print("    [PASS] Tampered ?company=ALL safely guarded against privilege escalation")
    else:
        print(f"    [FAIL] Tampered ?company=ALL leaked company data to staff!")
elif resp_tamper.status_code in [400, 403]:
    print(f"    [PASS] Tampered company parameter rejected with HTTP {resp_tamper.status_code}")

# 5.3 Verify Admin User Access
print("\n[*] Testing Admin User Privileged Access:")
client.force_authenticate(user=admin_user)
resp_admin = client.get('/api/dashboard/stats/', secure=True)
print(f"    Admin GET /api/dashboard/stats/ -> HTTP {resp_admin.status_code}")
if resp_admin.status_code == 200:
    adata = resp_admin.data
    admin_fin = adata.get('metrics', {}).get('executive_financials')
    admin_leads = adata.get('metrics', {}).get('leads', {}).get('total', 0)
    has_dash_admin = adata.get('has_admin_dashboard')
    print(f"    Admin has_admin_dashboard: {has_dash_admin}")
    print(f"    Admin total leads visible: {admin_leads:,}")
    print(f"    Admin executive_financials present: {admin_fin is not None}")
    if isinstance(admin_fin, dict):
        print(f"    Executive revenue: Rs. {admin_fin.get('total_revenue', 0):,.2f}")
        print(f"    Executive receivables: Rs. {admin_fin.get('pending_receivables', 0):,.2f}")
        print(f"    Executive collections this month: Rs. {admin_fin.get('collections_this_month', 0):,.2f}")
    if has_dash_admin is True and admin_leads >= 17500 and isinstance(admin_fin, dict):
        print("    [PASS] Admin receives complete company-wide aggregates and executive financials")
    else:
        print("    [FAIL] Admin data incomplete!")

print("\n" + "=" * 80)
print("MILENSTONE 4 EMPIRICAL HARNESS EXECUTION COMPLETE — ALL CHECKS EVALUATED")
print("=" * 80)
