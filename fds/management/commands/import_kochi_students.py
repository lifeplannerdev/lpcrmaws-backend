"""
Django Management Command: import_kochi_students
================================================
Bulk-imports all Kochi branch FDS students (active + inactive) with their
complete fee/payment history directly into the database.

Source: active_students.md + inactive_students.md (Kochi branch data)

Usage:
    python manage.py import_kochi_students            # live run
    python manage.py import_kochi_students --dry-run  # preview only

Data decisions applied (confirmed by user):
  - branch = 'KOCHI' for all records
  - Students with no joining_date (NOT MENTIONED / blank) are SKIPPED
  - Gender: M -> MALE, F -> FEMALE; combined (M,F / M & F) -> first token
  - Payment mode combined (ONLINE,CASH) -> first valid token; invalid ('F') -> OTHER
  - Dirty dates fixed: '09/082026' -> '09/08/2026', '19-11-0225' -> '19/11/2025',
    '14/010/2026' -> '14/01/2026', '15 Sep 2026' (typo) -> '15 Sep 2025',
    '31 Oct 2026' (typo) -> '31 Oct 2025'
  - Payment rows with unparseable dates/amounts are skipped and logged
  - batch = None (assign manually via UI)
  - created_by = None (import script)
  - 18 students skipped (no joining_date): ANJU & EVA, DRUPAD, THANOOJA,
    ELIZEBATH YESUDAS, ANUREIM THOMAS, BEENA JACOB, ELISA THERES ANTONY,
    GEETHA PREMKUMAR, ILLAKIYA, JACOB RAHUL, JOVANA ANNA JAIBIN, LATHA PRATHAP,
    LEKHA P.S, NILA NANDAGOPAN/ALAKA NANDAGOPAN, RUBY SANTHOSH, SACHITHRA SHAJI,
    SISILY P JOHN, TESS CARMEL
  - Total students imported: 115 (7 active + 108 inactive)
"""

from decimal import Decimal
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from fds.models import (
    FdsStudent,
    FdsStudentFeeAccount,
    FdsFeesCollection,
    FdsFeeStructure,
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

VALID_MODES = {"CASH", "UPI", "ONLINE", "BANK_TRANSFER", "CARD", "OTHER"}

DATE_FORMATS = (
    "%d %b %Y",   # "27 Sep 2025"
    "%d/%m/%Y",   # "09/08/2026"
    "%d-%m-%Y",   # "19-11-2025"
    "%Y-%m-%d",   # "2025-09-27"
    "%d %B %Y",   # "27 September 2025"
)

SKIP_TOKENS = {"", "-", "—", "none", "#value!", "---", "-------", "not marked", "none"}


def parse_mode(raw: str) -> str:
    """Return first valid MODE_OF_PAY token from raw string; fallback OTHER."""
    for part in str(raw).upper().replace(",", " ").replace("&", " ").split():
        if part in VALID_MODES:
            return part
    return "OTHER"


def parse_amount(raw) -> Decimal:
    """Parse amount string. Returns None for unparseable or zero values."""
    cleaned = str(raw).replace("₹", "").replace(",", "").strip()
    if cleaned.lower() in SKIP_TOKENS:
        return None
    try:
        val = Decimal(cleaned)
        return val if val > 0 else None
    except Exception:
        return None


def parse_date(raw: str):
    """Try multiple date formats. Returns None if unparseable or placeholder."""
    raw = str(raw).strip()
    if raw.lower() in SKIP_TOKENS:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


# ─── Student Data ─────────────────────────────────────────────────────────────
# Format: {"name", "phone", "gender", "emergency_contact", "joining_date",
#           "is_active", "payments": [(date_str, amount_int, mode_str), ...]}
#
# All dirty data pre-cleaned inline (see module docstring).
# 18 students with no joining_date are omitted from this list entirely.

STUDENTS = [
    # ══════════════════════════════════════════════════════════════════════════
    # ACTIVE STUDENTS (is_active=True)  — 7 students
    # ══════════════════════════════════════════════════════════════════════════
    {
        "name": "DEEPA RENJITH",
        "phone": "9747234477",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "27 Sep 2025",
        "is_active": True,
        "payments": [
            ("28 Sep 2025", 1888, "ONLINE"),
            ("01 Nov 2025", 1888, "ONLINE"),
            ("04 Dec 2025", 1888, "ONLINE"),
            ("02 Jan 2026", 1888, "ONLINE"),
            ("02 Feb 2026", 1888, "ONLINE"),
            ("03 Mar 2026", 1888, "ONLINE"),
            ("07 Apr 2026", 1888, "ONLINE"),
            ("02 May 2026", 1888, "ONLINE"),
            ("04 Jun 2026", 1888, "ONLINE"),
            ("03 Jul 2026", 1888, "ONLINE"),
            ("05 Aug 2026", 1888, "ONLINE"),
            ("04 Sep 2026", 1888, "ONLINE"),
            # 13th row has "—" date → excluded here
        ],
    },
    {
        "name": "ESTHEN",
        "phone": "9037742493",
        "gender": "FEMALE",
        "emergency_contact": "9074691646",
        "joining_date": "04 Jan 2026",
        "is_active": True,
        "payments": [
            ("04 Jan 2026", 2888, "ONLINE"),  # mode was ONLINE,CASH → ONLINE
            ("03 Feb 2026", 1888, "ONLINE"),
            ("06 Mar 2026", 1888, "ONLINE"),
            ("04 Apr 2026", 1888, "ONLINE"),
            ("02 May 2026", 1888, "ONLINE"),
            ("06 Sep 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "NORA JAMES",
        "phone": "9746565383",
        "gender": "FEMALE",
        "emergency_contact": "8095711555",
        "joining_date": "08 Aug 2026",
        "is_active": True,
        "payments": [
            ("08 Aug 2026", 2888, "ONLINE"),
            ("08 Sep 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "REETA ANN THOMAS",
        "phone": "7356846458",
        "gender": "FEMALE",
        "emergency_contact": "8183899999",
        "joining_date": "15 Aug 2026",
        "is_active": True,
        "payments": [
            ("15 Aug 2026", 2000, "ONLINE"),  # mode was ONLINE,CASH → ONLINE
            ("20 Sep 2026", 1000, "ONLINE"),
            # 3rd row has "—" date → excluded
        ],
    },
    {
        "name": "REMYA SURESH",
        "phone": "7356012721",
        "gender": "FEMALE",
        "emergency_contact": "8714012721",
        # Source file says "31 Oct 2026" but source sheet is 2025-2026 and
        # first payment is 31 Oct 2025 → cleaned to 2025
        "joining_date": "31 Oct 2025",
        "is_active": True,
        "payments": [
            ("31 Oct 2025", 1888, "ONLINE"),
            ("01 Dec 2025", 1888, "ONLINE"),
            ("04 Jan 2026", 1888, "CASH"),
            ("30 Jan 2026", 1888, "ONLINE"),
            ("06 Mar 2026", 1888, "ONLINE"),
            ("06 Apr 2026", 1888, "ONLINE"),
            ("02 May 2026", 1888, "ONLINE"),
            ("03 Jun 2026", 1888, "ONLINE"),
            ("01 Jul 2026", 1888, "ONLINE"),
            ("05 Sep 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "SURYA M.S",
        "phone": "9544872879",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "08 Aug 2026",
        "is_active": True,
        "payments": [
            ("08 Aug 2026", 1000, "ONLINE"),
            ("14 Aug 2026", 1888, "ONLINE"),
            ("05 Sep 2026", 1888, "ONLINE"),
            # 12 remaining rows have "—" date → excluded
        ],
    },
    {
        "name": "TARA MARIA",
        "phone": "9895570949",
        "gender": "FEMALE",
        "emergency_contact": "9249555779",
        "joining_date": "09 Aug 2026",
        "is_active": True,
        "payments": [
            ("09/08/2026", 2888, "ONLINE"),  # cleaned from "09/082026"
            ("08 Sep 2026", 1888, "ONLINE"),
            # 3rd row has "—" date → excluded
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # INACTIVE STUDENTS (is_active=False)  — 108 students
    # ══════════════════════════════════════════════════════════════════════════
    {
        "name": "DANIEL,SARAH,JWALA",
        "phone": "9745743991",
        "gender": "MALE",         # M,F → first = MALE
        "emergency_contact": "9048451244",
        "joining_date": "22 Apr 2026",
        "is_active": False,
        "payments": [
            ("22 Feb 2026", 6164, "ONLINE"),
            ("13 Apr 2026", 5000, "ONLINE"),
            ("17 May 2026", 5664, "ONLINE"),
            ("24 Jun 2026", 3776, "ONLINE"),
        ],
    },
    {
        "name": "SHIGHIL",
        "phone": "9746343466",
        "gender": "MALE",
        "emergency_contact": "9995791846",
        "joining_date": "09 Mar 2026",
        "is_active": False,
        "payments": [
            ("09 Jun 2026", 1000, "ONLINE"),
            ("10 Mar 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "ARYA A",
        "phone": "9074553543",
        "gender": "FEMALE",
        "emergency_contact": "8129642605",
        "joining_date": "01 Apr 2026",
        "is_active": False,
        "payments": [
            ("31 Mar 2026", 2888, "ONLINE"),
            ("04 Mar 2026", 1888, "ONLINE"),
            ("05 Jun 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "NEHAL SANDEEP",
        "phone": "9388353073",
        "gender": "FEMALE",
        "emergency_contact": "9020030020",
        "joining_date": "01 Apr 2026",
        "is_active": False,
        "payments": [
            ("31 Mar 2026", 2138, "ONLINE"),
            ("04 May 2026", 1638, "ONLINE"),
            ("02 Jun 2026", 1638, "ONLINE"),
        ],
    },
    {
        "name": "NILA & ALAKA",
        "phone": "9526158999",
        "gender": "FEMALE",
        "emergency_contact": "9526158999",
        "joining_date": "28 Feb 2026",
        "is_active": False,
        "payments": [
            ("01 Mar 2026", 1000, "ONLINE"),
            ("01 Apr 2026", 3276, "ONLINE"),
            ("01 May 2026", 3276, "ONLINE"),
            ("01 Jun 2026", 3276, "ONLINE"),
        ],
    },
    {
        "name": "BENIN ROY",
        "phone": "8086179039",
        "gender": "MALE",
        "emergency_contact": "8304987275",
        "joining_date": "13 Apr 2026",
        "is_active": False,
        "payments": [
            ("13 Apr 2026", 2888, "ONLINE"),
            ("13 May 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "SRAVANTHIKA KRISHNA",
        "phone": "7591907179",
        "gender": "FEMALE",
        "emergency_contact": "9446534545",
        "joining_date": "01 Apr 2026",
        "is_active": False,
        "payments": [
            ("01 Apr 2026", 1000, "CASH"),
            ("06 Apr 2026", 1888, "ONLINE"),
            ("13 May 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "VIVEK",
        "phone": "9037592857",
        "gender": "MALE",
        "emergency_contact": None,
        "joining_date": "07 Jan 2026",
        "is_active": False,
        "payments": [
            ("07 Jan 2026", 1000, "ONLINE"),
            ("19 Jan 2026", 1888, "ONLINE"),
            ("03 Feb 2026", 1776, "ONLINE"),
            ("11 Mar 2026", 1888, "ONLINE"),
            ("14 Apr 2026", 1888, "ONLINE"),
            ("13 May 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "VIJI A",
        "phone": "9840228293",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "12 May 2026",
        "is_active": False,
        "payments": [
            ("12 May 2026", 2388, "ONLINE"),
        ],
    },
    {
        "name": "ANN MARIA",
        "phone": "8547818829",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "14/01/2026",   # cleaned from "14/010/2026"
        "is_active": False,
        "payments": [
            ("19 Jan 2026", 1888, "CASH"),
            ("19 Jan 2026", 1000, "ONLINE"),
            ("25 Feb 2026", 888, "CASH"),
            ("26 Feb 2026", 1000, "ONLINE"),
            ("18 Mar 2026", 888, "CASH"),
            ("19 Mar 2026", 1000, "CASH"),
            ("05 May 2026", 888, "CASH"),
            ("05 May 2026", 1000, "CASH"),
        ],
    },
    {
        "name": "ARADHYA ANOOP",
        "phone": "9562738638",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "07 Apr 2026",
        "is_active": False,
        "payments": [
            ("13 Apr 2026", 1000, "CASH"),
            ("05 May 2026", 1888, "CASH"),
            ("05 May 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "AAHANA ARUN",
        "phone": "9526917697",
        "gender": "FEMALE",
        "emergency_contact": "9961197495",
        "joining_date": "03 Jan 2026",
        "is_active": False,
        "payments": [
            ("03 Jan 2026", 2888, "ONLINE"),  # mode was ONLINE,CASH → ONLINE
            ("08 Feb 2026", 1888, "ONLINE"),
            ("02 May 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "DEVANANDHA",
        "phone": "9656677414",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "13 Apr 2026",
        "is_active": False,
        "payments": [
            ("13 Apr 2026", 500, "CASH"),
            ("14 Apr 2026", 1888, "CASH"),
        ],
    },
    # ANJU & EVA — SKIPPED (joining_date: NOT MENTIONED)
    {
        "name": "MOHAMMED RAZEEN",
        "phone": "9745449799",
        "gender": "MALE",
        "emergency_contact": None,
        "joining_date": "03 Feb 2026",
        "is_active": False,
        "payments": [
            ("10 Feb 2026", 1888, "ONLINE"),
            ("23 Feb 2026", 1000, "ONLINE"),
            ("04 Mar 2026", 1888, "ONLINE"),
            ("13 Apr 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "SRUTHY MOHAN",
        "phone": "6282611126",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "21 Jan 2026",
        "is_active": False,
        "payments": [
            ("21 Jan 2026", 2888, "ONLINE"),
            ("04 Mar 2026", 1888, "ONLINE"),
            ("12 Apr 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "ARUN UNNIKRISHNAN",
        "phone": "9074724117",
        "gender": "MALE",
        "emergency_contact": None,
        "joining_date": "17 Jan 2026",
        "is_active": False,
        "payments": [
            ("17 Jan 2026", 2888, "ONLINE"),
            ("22 Feb 2026", 944, "ONLINE"),
            ("10 Mar 2026", 1888, "ONLINE"),
            ("08 Apr 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "ANJITHA T K",
        "phone": "8714301975",
        "gender": "FEMALE",
        "emergency_contact": "8089683272",
        "joining_date": "01 Oct 2025",
        "is_active": False,
        "payments": [
            ("01 Oct 2025", 1888, "ONLINE"),
            ("03 Nov 2025", 1888, "ONLINE"),
            ("03 Dec 2025", 1888, "ONLINE"),
            ("05 Jan 2026", 1888, "ONLINE"),
            ("03 Mar 2026", 1888, "ONLINE"),
            ("06 Apr 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "LINIT",
        "phone": "9048835577",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "10 Mar 2026",
        "is_active": False,
        "payments": [
            ("10 Mar 2026", 2888, "ONLINE"),
            ("06 Apr 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "SURYA ANIL",
        "phone": "7591907179",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "28 Feb 2026",
        "is_active": False,
        "payments": [
            ("28 Feb 2026", 1000, "CASH"),
            # "1000 & 888" split into two rows (CASH,ONLINE)
            ("02 Mar 2026", 1000, "CASH"),
            ("02 Mar 2026", 888, "ONLINE"),
            ("06 Apr 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "BAJISH",
        "phone": "9995045172",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "02 Apr 2026",
        "is_active": False,
        "payments": [
            ("02 Apr 2026", 2888, "ONLINE"),
        ],
    },
    {
        "name": "GILBENT",
        "phone": "9745073173",
        "gender": "MALE",         # M & F → first = MALE
        "emergency_contact": "8086982924",
        "joining_date": "09 Mar 2026",
        "is_active": False,
        "payments": [
            ("07 Mar 2026", 1000, "ONLINE"),
            ("09 Mar 2026", 1888, "ONLINE"),
            ("01 Apr 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "ANEESH ANWAR",
        "phone": "9947509165",
        "gender": "MALE",
        "emergency_contact": None,
        "joining_date": "29 Mar 2026",
        "is_active": False,
        "payments": [
            ("29 Mar 2026", 2888, "ONLINE"),
        ],
    },
    {
        "name": "THOMAS RIJO JOSEPH",
        "phone": "8921627676",
        "gender": "MALE",
        "emergency_contact": None,
        "joining_date": "17 Mar 2026",
        "is_active": False,
        "payments": [
            ("17 Mar 2026", 2888, "ONLINE"),
        ],
    },
    {
        "name": "AISWARYA",
        "phone": "8547876453",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "16 Mar 2026",
        "is_active": False,
        "payments": [
            ("16 Mar 2026", 2388, "ONLINE"),
        ],
    },
    {
        "name": "ANNU M",
        "phone": "7012701513",
        "gender": "FEMALE",
        "emergency_contact": "9567868731",
        "joining_date": "03 Sep 2025",
        "is_active": False,
        "payments": [
            ("03 Sep 2025", 1888, "ONLINE"),
            ("12 Oct 2025", 1888, "ONLINE"),
            ("16 Nov 2025", 1888, "ONLINE"),
            ("15 Dec 2025", 1888, "ONLINE"),
            ("22 Jan 2026", 1888, "ONLINE"),
            ("13 Mar 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "JEROM",
        "phone": "8330870578",
        "gender": "MALE",
        "emergency_contact": "9961870578",
        "joining_date": "13 Oct 2025",
        "is_active": False,
        "payments": [
            ("13 Oct 2025", 1888, "ONLINE"),
            ("12 Nov 2025", 1888, "ONLINE"),
            ("02 Dec 2025", 1888, "ONLINE"),
            ("08 Jan 2026", 1888, "ONLINE"),
            ("20 Feb 2026", 1888, "ONLINE"),
            ("12 Mar 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "ARDRA",
        "phone": "8301840159",
        "gender": "FEMALE",
        "emergency_contact": "9747585841",
        "joining_date": "06 Jan 2026",
        "is_active": False,
        "payments": [
            ("06 Jan 2026", 2888, "ONLINE"),
            ("05 Feb 2026", 1888, "ONLINE"),
            ("10 Mar 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "HAYAS",
        "phone": "9745643024",
        "gender": "MALE",
        "emergency_contact": None,
        "joining_date": "09 Mar 2026",
        "is_active": False,
        "payments": [
            ("07 Mar 2026", 1000, "ONLINE"),
            ("10 Mar 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "ADITHYA",
        "phone": "9656319013",
        "gender": "FEMALE",
        "emergency_contact": "7025420011",
        "joining_date": "09 Mar 2026",
        "is_active": False,
        "payments": [
            ("09 Mar 2026", 2888, "ONLINE"),
        ],
    },
    {
        "name": "ARATHY P VIJAYAN",
        "phone": "8943237380",
        "gender": "FEMALE",
        "emergency_contact": "8921107797",
        "joining_date": "22 Sep 2025",
        "is_active": False,
        "payments": [
            ("22 Sep 2025", 944, "ONLINE"),
            ("07 Oct 2025", 1888, "ONLINE"),
            ("04 Nov 2025", 1888, "ONLINE"),
            ("03 Dec 2025", 1888, "ONLINE"),
            ("06 Jan 2026", 1888, "ONLINE"),
            ("04 Feb 2026", 1720, "ONLINE"),
            ("09 Mar 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "GEGARIN BABU",
        "phone": "9249825757",
        "gender": "MALE",
        "emergency_contact": "9249825757",
        "joining_date": "13 Mar 2026",
        "is_active": False,
        "payments": [
            ("09 Mar 2026", 2888, "ONLINE"),
        ],
    },
    # DRUPAD — SKIPPED (joining_date: NOT MENTIONED)
    {
        "name": "SAJITHA",
        "phone": "9526163748",
        "gender": "FEMALE",
        "emergency_contact": "9645359927",
        "joining_date": "06 Jan 2026",
        "is_active": False,
        "payments": [
            ("06 Jan 2026", 2888, "ONLINE"),
            ("04 Feb 2026", 1888, "ONLINE"),
            ("08 Mar 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "BINCY CHACKO",
        "phone": "9074204738",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "03 Nov 2025",
        "is_active": False,
        "payments": [
            ("10 Jan 2026", 1888, "ONLINE"),
            ("09 Feb 2026", 1888, "ONLINE"),
            ("07 Mar 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "RAJANI P S",
        "phone": "7012423062",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "15 Sep 2025",
        "is_active": False,
        "payments": [
            ("07 Jan 2026", 1888, "ONLINE"),
            ("06 Feb 2026", 1888, "ONLINE"),
            ("06 Mar 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "SIJO",
        "phone": "7907218863",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "06 Jan 2026",
        "is_active": False,
        "payments": [
            ("06 Jan 2026", 1000, "ONLINE"),
            ("18 Jan 2026", 1888, "ONLINE"),
            ("09 Feb 2026", 1000, "ONLINE"),
            ("05 Mar 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "SOORYA SUBRAMANIUM",
        "phone": "7034616141",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "02 Mar 2026",
        "is_active": False,
        "payments": [
            ("02 Mar 2026", 1000, "ONLINE"),
            ("04 Mar 2026", 1800, "ONLINE"),
        ],
    },
    {
        "name": "ASWATHY PILLAI",
        "phone": "8086206502",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "04 Nov 2025",
        "is_active": False,
        "payments": [
            ("04 Nov 2025", 500, "ONLINE"),
            ("05 Nov 2025", 1388, "ONLINE"),
            ("06 Dec 2025", 1888, "ONLINE"),
            ("12 Jan 2026", 1888, "ONLINE"),
            ("01 Mar 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "AVANTHIKA",
        "phone": "9074774577",
        "gender": "FEMALE",
        "emergency_contact": "8590051025",
        "joining_date": "07 Jan 2026",
        "is_active": False,
        "payments": [],   # single payment row had "NOT MARKED" amount → excluded
    },
    {
        "name": "JISMOL",
        "phone": "8593866592",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "02 Mar 2026",
        "is_active": False,
        "payments": [
            ("23 Feb 2026", 2388, "ONLINE"),
        ],
    },
    {
        "name": "DR. KAJAL",
        "phone": "7012051478",
        "gender": "FEMALE",
        "emergency_contact": "8903924927",
        "joining_date": "13 Jan 2026",
        "is_active": False,
        "payments": [
            ("13 Jan 2026", 2888, "ONLINE"),
            ("15 Feb 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "PATRICIA KIRAN",
        "phone": "9846212348",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "15 Jan 2026",
        "is_active": False,
        "payments": [
            ("14 Jan 2026", 1000, "ONLINE"),
            ("27 Jan 2026", 944, "ONLINE"),
            ("14 Feb 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "SHANA PRAVEEN",
        "phone": "8589037024",
        "gender": "FEMALE",
        "emergency_contact": "9495221196",
        "joining_date": "14 Feb 2026",
        "is_active": False,
        "payments": [
            ("14 Feb 2026", 1994, "CASH"),
        ],
    },
    {
        "name": "MADHIVADHANJ",
        "phone": "9600050105",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "06 Feb 2026",
        "is_active": False,
        "payments": [
            ("11 Feb 2026", 4276, "ONLINE"),
        ],
    },
    {
        "name": "BHUVI PRAVEEN",
        "phone": "9496602898",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "06 Jan 2025",
        "is_active": False,
        "payments": [
            ("05 Jan 2026", 1888, "ONLINE"),
            ("09 Feb 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "CICY",
        "phone": "9497283321",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "15 Jan 2026",
        "is_active": False,
        "payments": [
            ("14 Jan 2026", 1000, "ONLINE"),
            ("27 Jan 2026", 944, "ONLINE"),
            ("04 Feb 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "FIZA",
        "phone": "8129465672",
        "gender": "FEMALE",
        "emergency_contact": "9387518201",
        "joining_date": "03 Jan 2026",
        "is_active": False,
        "payments": [
            ("03 Jan 2026", 1000, "ONLINE"),
            ("06 Jan 2026", 1888, "ONLINE"),
            ("04 Feb 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "AJMAL",
        "phone": "9895872597",
        "gender": "MALE",
        "emergency_contact": None,
        "joining_date": "20 Oct 2025",
        "is_active": False,
        "payments": [
            ("15 Oct 2025", 500, "ONLINE"),
            ("20 Oct 2025", 444, "ONLINE"),
            ("03 Nov 2025", 1888, "ONLINE"),
            ("08 Dec 2025", 1888, "ONLINE"),
            ("03 Jan 2026", 1888, "ONLINE"),
            ("02 Feb 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "ANUPAMA",
        "phone": "9567718184",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "26 Jan 2026",
        "is_active": False,
        "payments": [
            ("20 Jan 2026", 1000, "ONLINE"),
            ("26 Jan 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "ANGELA",
        "phone": "8870152718",
        "gender": "FEMALE",
        "emergency_contact": "6379180341",
        "joining_date": "12 Jan 2025",
        "is_active": False,
        "payments": [
            ("08 Jan 2026", 1000, "ONLINE"),
            ("20 Jan 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "VYSAKH",
        "phone": "8136962258",
        "gender": "MALE",
        "emergency_contact": "9249527078",
        "joining_date": "20 Jan 2026",
        "is_active": False,
        "payments": [
            ("20 Jan 2026", 2888, "ONLINE"),
        ],
    },
    {
        "name": "HIMA & SAGAR",
        "phone": "8086411205",
        "gender": "MALE",         # M & F → first = MALE
        "emergency_contact": "7736903865",
        "joining_date": "19 Jan 2026",
        "is_active": False,
        "payments": [
            ("19 Jan 2026", 5776, "ONLINE"),
        ],
    },
    {
        "name": "ARUN & MARIAH",
        "phone": "9995802823",
        "gender": "MALE",         # M,F → first = MALE
        "emergency_contact": None,
        "joining_date": "17 Jan 2026",
        "is_active": False,
        "payments": [
            ("17 Jan 2026", 5776, "ONLINE"),
        ],
    },
    {
        "name": "ASRA SAYYIDATH",
        "phone": "9778368805",
        "gender": "FEMALE",
        "emergency_contact": "9526969149",
        "joining_date": "17 Jan 2026",
        "is_active": False,
        "payments": [
            ("17 Jan 2026", 2888, "ONLINE"),
        ],
    },
    {
        "name": "AJMAL O B",
        "phone": "9746479326",
        "gender": "MALE",
        "emergency_contact": None,
        "joining_date": "24 Sep 2025",
        "is_active": False,
        "payments": [
            ("24 Sep 2025", 1888, "ONLINE"),
            ("03 Nov 2025", 1888, "ONLINE"),
            ("16 Dec 2025", 1888, "ONLINE"),  # mode was ONLINE,CASH → ONLINE
            ("12 Jan 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "LIJNA",
        "phone": "9446208052",
        "gender": "FEMALE",
        "emergency_contact": "9567262310",
        "joining_date": "12 Jan 2026",
        "is_active": False,
        "payments": [
            ("12 Jan 2026", 2888, "ONLINE"),
        ],
    },
    {
        "name": "SARANYA BABU",
        "phone": "6238528698",
        "gender": "FEMALE",
        "emergency_contact": "7025323964",
        "joining_date": "12 Jan 2026",
        "is_active": False,
        "payments": [
            ("12 Jan 2026", 2888, "ONLINE"),
        ],
    },
    {
        "name": "SUNITHA",
        "phone": "8089614890",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "09 Jan 2026",
        "is_active": False,
        "payments": [
            ("09 Jan 2026", 2888, "ONLINE"),
        ],
    },
    {
        "name": "DENIS",
        "phone": "8078950759",
        "gender": "MALE",
        "emergency_contact": None,
        "joining_date": "12 Jan 2025",
        "is_active": False,
        "payments": [
            ("08 Jan 2026", 2888, "ONLINE"),
            # second row had "—" date → excluded
        ],
    },
    {
        "name": "JASEELA",
        "phone": "7592896875",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "06 Jan 2026",
        "is_active": False,
        "payments": [
            ("05 Jan 2026", 1000, "ONLINE"),
            ("07 Jan 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "ANJU PRAVEEN",
        "phone": "9496602898",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "22 Sep 2025",
        "is_active": False,
        "payments": [
            ("05 Jan 2026", 1888, "ONLINE"),
        ],
    },
    {
        "name": "ROYAL AUSTIN",
        "phone": "6282698217",
        "gender": "MALE",
        "emergency_contact": None,
        "joining_date": "06 Jan 2026",
        "is_active": False,
        "payments": [
            ("05 Jan 2026", 2388, "ONLINE"),
        ],
    },
    # THANOOJA — SKIPPED (joining_date: NOT MENTIONED)
    {
        "name": "NICE CHERIAN",
        "phone": "889388849",
        "gender": "MALE",
        "emergency_contact": "9895986684",
        "joining_date": "19 Nov 2025",
        "is_active": False,
        "payments": [
            ("19/11/2025", 2500, "CASH"),   # cleaned from "19-11-0225"
            ("19 Nov 2025", 388, "ONLINE"),
            ("22 Dec 2025", 944, "ONLINE"),
        ],
    },
    {
        "name": "MALAVIKA PRADEEP",
        "phone": "8592829901",
        "gender": "FEMALE",
        "emergency_contact": "9447255091",
        "joining_date": "22 Sep 2025",
        "is_active": False,
        "payments": [
            ("24 Sep 2025", 500, "CASH"),
            ("06 Oct 2025", 1388, "CASH"),
            ("12 Nov 2025", 1888, "ONLINE"),
            ("16 Dec 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "NIPHY",
        "phone": "6282643692",
        "gender": "FEMALE",
        "emergency_contact": "8086816891",
        "joining_date": "16 Dec 2025",
        "is_active": False,
        "payments": [
            ("16 Dec 2025", 1944, "ONLINE"),
        ],
    },
    {
        "name": "ASHLY MARIYA",
        "phone": "9061119182",
        "gender": "FEMALE",
        "emergency_contact": "7012849522",
        "joining_date": "15 Dec 2025",
        "is_active": False,
        "payments": [
            ("15 Dec 2025", 1944, "ONLINE"),
        ],
    },
    {
        "name": "ABRAM RINO",
        "phone": "7736172018",
        "gender": "MALE",
        "emergency_contact": "9567989949",
        "joining_date": "19 Oct 2025",
        "is_active": False,
        "payments": [
            ("19 Oct 2025", 500, "ONLINE"),
            ("02 Nov 2025", 1888, "ONLINE"),
            ("13 Dec 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "ATHIRA S",
        "phone": "8714217685",
        "gender": "FEMALE",
        "emergency_contact": "9656761381",
        "joining_date": "12 Dec 2025",
        "is_active": False,
        "payments": [
            ("12 Dec 2025", 2888, "ONLINE"),
        ],
    },
    {
        "name": "HABNAM",
        "phone": "9207590020",
        "gender": "FEMALE",
        "emergency_contact": "9961906242",
        "joining_date": "12 Dec 2025",
        "is_active": False,
        "payments": [
            ("12 Dec 2025", 2888, "ONLINE"),
        ],
    },
    {
        "name": "THAMJEEDHA",
        "phone": "8129552944",
        "gender": "FEMALE",
        "emergency_contact": "8129920182",
        "joining_date": "12 Dec 2025",
        "is_active": False,
        "payments": [
            ("12 Dec 2025", 1944, "ONLINE"),
        ],
    },
    {
        "name": "CHRISTINA",
        "phone": "7994755549",
        "gender": "FEMALE",
        "emergency_contact": "9947578600",
        "joining_date": "10 Dec 2025",
        "is_active": False,
        "payments": [
            ("10 Dec 2025", 2888, "ONLINE"),
        ],
    },
    {
        "name": "SHAN E H",
        "phone": "9744780317",
        "gender": "MALE",
        "emergency_contact": "8281189317",
        "joining_date": "24 Sep 2025",
        "is_active": False,
        "payments": [
            ("24 Sep 2025", 1888, "ONLINE"),
            ("03 Nov 2025", 1888, "ONLINE"),
            ("10 Dec 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "SUDHI",
        "phone": "9496809021",
        "gender": "MALE",
        "emergency_contact": "9495227796",
        "joining_date": "09 Sep 2025",
        "is_active": False,
        "payments": [
            ("10 Sep 2025", 1888, "CASH"),
            ("13 Oct 2025", 1888, "ONLINE"),
            ("10 Nov 2025", 1888, "ONLINE"),
            ("10 Dec 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "FAISAL",
        "phone": "8912663440",
        "gender": "MALE",
        "emergency_contact": None,
        "joining_date": "08 Oct 2025",
        "is_active": False,
        "payments": [
            ("08 Oct 2025", 1500, "CASH"),
            ("08 Oct 2025", 388, "ONLINE"),
            ("08 Nov 2025", 1888, "ONLINE"),
            ("08 Dec 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "C SNEHA",
        "phone": "8086244622",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "08 Aug 2025",
        "is_active": False,
        "payments": [
            ("08 Sep 2025", 1000, "ONLINE"),
            ("15 Sep 2025", 888, "CASH"),
            ("08 Oct 2025", 1888, "ONLINE"),
            ("03 Nov 2025", 1888, "ONLINE"),
            ("03 Dec 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "AMRITHA P",
        "phone": "7736292406",
        "gender": "FEMALE",
        "emergency_contact": "9495461724",
        "joining_date": "03 Nov 2025",
        "is_active": False,
        "payments": [
            ("03 Nov 2025", 2888, "ONLINE"),
            ("02 Dec 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "ATHIRA G",
        "phone": "6238196487",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "03 Nov 2025",
        "is_active": False,
        "payments": [
            ("02 Nov 2025", 1888, "ONLINE"),
            ("02 Dec 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "TONY GEORGE",
        "phone": "8891165580",
        "gender": "MALE",
        "emergency_contact": None,
        "joining_date": "01 Dec 2025",
        "is_active": False,
        "payments": [
            ("01 Dec 2025", 2888, "ONLINE"),
        ],
    },
    {
        "name": "ASIFA",
        "phone": "8606759792",
        "gender": "FEMALE",
        "emergency_contact": "9745934430",
        "joining_date": "26 Nov 2025",
        "is_active": False,
        "payments": [
            ("29 Nov 2025", 2888, "ONLINE"),
        ],
    },
    {
        "name": "SEENA",
        "phone": "9387212301",
        "gender": "FEMALE",
        "emergency_contact": "9497281740",
        "joining_date": "28 Nov 2025",
        "is_active": False,
        "payments": [
            ("28 Nov 2025", 2888, "ONLINE"),
        ],
    },
    {
        "name": "ISHI ELIZABETH",
        "phone": "9037434242",
        "gender": "FEMALE",
        "emergency_contact": "9447568191",
        "joining_date": "10 Nov 2025",
        "is_active": False,
        "payments": [
            ("08 Nov 2025", 1900, "CASH"),
            ("17 Nov 2025", 988, "CASH"),
        ],
    },
    {
        "name": "MEERA K V",
        "phone": "9895235359",
        "gender": "FEMALE",
        "emergency_contact": "8891458544",
        "joining_date": "17 Nov 2025",
        "is_active": False,
        "payments": [
            ("17 Nov 2025", 1944, "ONLINE"),
        ],
    },
    {
        "name": "LEENA THOMAS",
        "phone": "9495380740",
        "gender": "FEMALE",
        "emergency_contact": "9446135227",
        "joining_date": "20 Oct 2025",
        "is_active": False,
        "payments": [
            ("20 Oct 2025", 944, "ONLINE"),
            ("10 Nov 2025", 944, "ONLINE"),
        ],
    },
    {
        "name": "FRANCIS (baiju)",
        "phone": "9961728099",
        "gender": "MALE",
        "emergency_contact": None,
        "joining_date": "15 Oct 2025",
        "is_active": False,
        "payments": [
            ("14 Oct 2025", 1888, "ONLINE"),
            ("06 Nov 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "MINI MENON",
        "phone": "9947283446",
        "gender": "FEMALE",
        "emergency_contact": "9447609915",
        "joining_date": "01 Oct 2025",
        "is_active": False,
        "payments": [
            ("01 Oct 2025", 1888, "ONLINE"),
            ("05 Nov 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "SONIYA ROFFU",
        "phone": "7012050569",
        "gender": "FEMALE",
        "emergency_contact": "859060887",
        "joining_date": "03 Nov 2025",
        "is_active": False,
        "payments": [
            ("03 Nov 2025", 1000, "ONLINE"),
            ("05 Nov 2025", 888, "ONLINE"),
        ],
    },
    {
        "name": "ANNA MARIYA ANTONY",
        "phone": "9895691760",
        "gender": "FEMALE",
        "emergency_contact": "8129116668",
        "joining_date": "21 Sep 2025",
        "is_active": False,
        "payments": [
            ("21 Sep 2025", 649, "ONLINE"),
            ("19 Oct 2025", 1593, "CASH"),
            ("04 Nov 2025", 1593, "ONLINE"),
        ],
    },
    {
        "name": "SAJNA YOOSUF",
        "phone": "7034010923",
        "gender": "FEMALE",
        "emergency_contact": "9895080923",
        "joining_date": "22 Oct 2025",
        "is_active": False,
        "payments": [
            ("22 Oct 2025", 500, "ONLINE"),
            ("04 Nov 2025", 1388, "ONLINE"),
        ],
    },
    # ELIZEBATH YESUDAS — SKIPPED (joining_date: NOT MENTIONED)
    {
        "name": "SRUTHY BABU",
        "phone": "7902991801",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "03 Nov 2025",
        "is_active": False,
        "payments": [
            ("03 Nov 2025", 2888, "ONLINE"),
        ],
    },
    {
        "name": "PRASANTHI NATHAN",
        "phone": "9446480476",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "16 Sep 2025",
        "is_active": False,
        "payments": [
            ("16 Sep 2025", 944, "ONLINE"),
            ("06 Oct 2025", 1888, "ONLINE"),
            ("02 Nov 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "VIVEK",
        "phone": "9844191444",         # different phone from the other VIVEK (9037592857)
        "gender": "MALE",
        "emergency_contact": "9061382622",
        "joining_date": "03 Nov 2025",
        "is_active": False,
        "payments": [
            ("01 Nov 2025", 2888, "ONLINE"),
        ],
    },
    {
        "name": "ALFIYA HANEEFA",
        "phone": "8089994049",
        "gender": "FEMALE",
        "emergency_contact": "9562630804",
        "joining_date": "28 Oct 2025",
        "is_active": False,
        "payments": [
            ("28 Oct 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "RAHUL ASOK",
        "phone": "9605864933",
        "gender": "MALE",
        "emergency_contact": "9446439055",
        "joining_date": "22 Oct 2025",
        "is_active": False,
        "payments": [
            ("22 Oct 2025", 1770, "ONLINE"),
        ],
    },
    {
        "name": "SIVAHITHA",
        "phone": "9539170811",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "18 Oct 2025",
        "is_active": False,
        "payments": [
            ("18 Oct 2025", 944, "ONLINE"),
        ],
    },
    {
        "name": "DUA MEHRIN",
        "phone": "7012771602",
        "gender": "FEMALE",
        "emergency_contact": "9400903499",
        "joining_date": "10 Sep 2025",
        "is_active": False,
        "payments": [
            ("10 Sep 2025", 1000, "ONLINE"),
            ("06 Oct 2025", 888, "ONLINE"),
        ],
    },
    {
        "name": "JOANNA JILS",
        "phone": "7012719780",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "20 Sep 2025",
        "is_active": False,
        "payments": [
            ("20 Sep 2025", 944, "ONLINE"),
            ("05 Oct 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "AIBEN NEEL",
        "phone": "9656123765",
        "gender": "MALE",
        "emergency_contact": None,
        "joining_date": "04 Oct 2025",
        "is_active": False,
        "payments": [
            ("04 Oct 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "BINDHU SURESH",
        "phone": "9947000519",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "02 Oct 2025",
        "is_active": False,
        "payments": [
            ("02 Oct 2025", 1888, "OTHER"),   # original mode "F" → OTHER
            # second row had "—" date → excluded
        ],
    },
    {
        "name": "SREEJAYA V P",
        "phone": "7012064291",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "02 Oct 2025",
        "is_active": False,
        "payments": [
            ("02 Oct 2025", 1888, "CASH"),
        ],
    },
    {
        "name": "IAISA TONY",
        "phone": "9847444528",
        "gender": "FEMALE",
        "emergency_contact": "9387718877",
        "joining_date": "01 Oct 2025",
        "is_active": False,
        "payments": [
            ("01 Oct 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "FIFA FATHIMA",
        "phone": "8086172086",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "31 Aug 2025",
        "is_active": False,
        "payments": [
            ("09 Sep 2025", 500, "ONLINE"),
            ("15 Sep 2025", 300, "ONLINE"),
            ("27 Sep 2025", 588, "CASH"),
        ],
    },
    {
        "name": "ADHVIK",
        "phone": "9074807943",
        "gender": "MALE",
        "emergency_contact": "9074807943",
        "joining_date": "20 Sep 2025",
        "is_active": False,
        "payments": [
            ("20 Sep 2025", 944, "ONLINE"),
        ],
    },
    {
        "name": "BEENA TOSHY",
        "phone": "9539512039",
        "gender": "FEMALE",
        "emergency_contact": None,
        # Original says "15 Sep 2026" — obvious typo for 2025-2026 sheet
        "joining_date": "15 Sep 2025",
        "is_active": False,
        "payments": [
            ("15 Sep 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "HARIKRISHNAN T",
        "phone": "9744061248",
        "gender": "MALE",
        "emergency_contact": None,
        "joining_date": "08 Sep 2025",
        "is_active": False,
        "payments": [
            ("08 Sep 2025", 1888, "ONLINE"),
        ],
    },
    {
        "name": "BADIYA GOWTHAM",
        "phone": "9502796116",
        "gender": "MALE",
        "emergency_contact": "7993908225",
        "joining_date": "19 Aug 2025",
        "is_active": False,
        "payments": [
            ("19 Aug 2025", 2832, "ONLINE"),
        ],
    },
    {
        "name": "J AARSHITA RAO",
        "phone": "7225909889",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "19 Aug 2025",
        "is_active": False,
        "payments": [
            ("19 Aug 2025", 1000, "ONLINE"),
        ],
    },
    # ANUREIM THOMAS — SKIPPED (joining_date: —)
    # BEENA JACOB — SKIPPED (joining_date: —)
    {
        "name": "DIVYA LAKSHMI",
        "phone": "9600050105",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "04 Mar 2026",
        "is_active": False,
        "payments": [],   # all payment rows unparseable → excluded
    },
    # ELISA THERES ANTONY — SKIPPED (joining_date: —)
    # GEETHA PREMKUMAR — SKIPPED (joining_date: —)
    # ILLAKIYA — SKIPPED (joining_date: —)
    # JACOB RAHUL — SKIPPED (joining_date: —)
    {
        "name": "JINU JENSON",
        "phone": "8907683525",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "22 Jan 2025",
        "is_active": False,
        "payments": [],   # ADMISSION FORM WITHOUT FEE CARD
    },
    # JOVANA ANNA JAIBIN — SKIPPED (joining_date: —)
    # LATHA PRATHAP — SKIPPED (joining_date: —)
    # LEKHA P.S — SKIPPED (joining_date: —)
    {
        "name": "LEONATE MARIZ OJEY",
        "phone": "9847053334",
        "gender": "FEMALE",
        "emergency_contact": None,
        "joining_date": "21 Apr 2026",
        "is_active": False,
        "payments": [],   # payment date was #VALUE! → excluded
    },
    # NILA NANDAGOPAN / ALAKA NANDAGOPAN — SKIPPED (joining_date: —)
    # RUBY SANTHOSH — SKIPPED (joining_date: —)
    # SACHITHRA SHAJI — SKIPPED (joining_date: —)
    # SISILY P JOHN — SKIPPED (joining_date: —)
    # TESS CARMEL — SKIPPED (joining_date: —)
]


# ─── Management Command ────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        "Import all Kochi branch FDS students and their payment history. "
        "Safe to re-run (uses get_or_create). Use --dry-run to preview."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without touching the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN — no data will be written ===\n"))

        # ── Step 1: Ensure a generic fee structure exists ──────────────────
        # FdsFeesCollection requires a fees_type FK. We use/create a generic
        # "Kochi Import — General" structure so existing fee structures are
        # untouched and this import is self-contained.
        if not dry_run:
            fee_structure, fs_created = FdsFeeStructure.objects.get_or_create(
                name="Kochi Import — General",
                defaults={
                    "category": "MONTHLY",
                    "amount": Decimal("0"),
                    "is_active": False,   # inactive so it doesn't appear in UI dropdowns
                    "details": "Auto-created by import_kochi_students management command. "
                               "Assign students to their real fee structure via the UI.",
                },
            )
            if fs_created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created fee structure: {fee_structure}")
                )
            else:
                self.stdout.write(f"Using existing fee structure: {fee_structure}")
        else:
            fee_structure = None  # not used in dry-run

        # ── Step 2: Process each student ───────────────────────────────────
        total_students = len(STUDENTS)
        created_count = 0
        skipped_count = 0
        payment_created = 0
        payment_skipped = 0
        errors = []

        for idx, s in enumerate(STUDENTS, start=1):
            joining_date = parse_date(s["joining_date"])
            if not joining_date:
                # Should not happen (pre-filtered from STUDENTS list) but guard anyway
                self.stdout.write(
                    self.style.WARNING(
                        f"  [{idx}/{total_students}] SKIPPING {s['name']} — "
                        f"unparseable joining_date: {s['joining_date']!r}"
                    )
                )
                skipped_count += 1
                continue

            if dry_run:
                active_label = "ACTIVE" if s["is_active"] else "INACTIVE"
                self.stdout.write(
                    f"  [{idx}/{total_students}] {active_label}: {s['name']} "
                    f"(phone: {s['phone']}, joined: {joining_date}, "
                    f"payments: {len(s['payments'])})"
                )
                payment_created += len(s["payments"])
                created_count += 1
                continue

            # ── Live run: wrap each student in its own transaction ──────────
            try:
                with transaction.atomic():
                    student, stu_created = FdsStudent.objects.get_or_create(
                        name=s["name"],
                        contact_no=s["phone"],
                        defaults={
                            "branch": "KOCHI",
                            "gender": s["gender"],
                            "emergency_contact_no": s["emergency_contact"],
                            "whatsapp_no": s["phone"],
                            "joining_date": joining_date,
                            "is_active": s["is_active"],
                            "student_type": "REGULAR",
                            "created_by": None,
                        },
                    )

                    if not stu_created:
                        self.stdout.write(
                            f"  [{idx}/{total_students}] SKIP (exists): {s['name']}"
                        )
                        skipped_count += 1
                        continue

                    # Create fee account (mirrors FdsStudentViewSet.perform_create)
                    account, _ = FdsStudentFeeAccount.objects.get_or_create(
                        student=student,
                        defaults={
                            "active_package": fee_structure,
                            "plan_type": "CUSTOM",
                            "plan_name": "Kochi Import",
                        },
                    )

                    # Create payment records
                    p_ok = 0
                    p_skip = 0
                    for pay_date_str, pay_amount_raw, pay_mode_raw in s["payments"]:
                        pay_date = parse_date(str(pay_date_str))
                        pay_amount = parse_amount(pay_amount_raw)
                        if not pay_date or not pay_amount:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"    SKIP payment: date={pay_date_str!r} "
                                    f"amount={pay_amount_raw!r} mode={pay_mode_raw!r}"
                                )
                            )
                            p_skip += 1
                            payment_skipped += 1
                            continue

                        mode = parse_mode(pay_mode_raw)
                        FdsFeesCollection.objects.create(
                            account=account,
                            student=student,
                            fees_type=fee_structure,
                            pay_date=pay_date,
                            paid_amount=pay_amount,
                            total_fees=pay_amount,
                            mode_of_pay=mode,
                            status="PAID",
                            collected_by=None,
                        )
                        p_ok += 1
                        payment_created += 1

                    # Recalculate fee account totals
                    account.recalculate(save=True)

                    active_label = "ACTIVE" if s["is_active"] else "INACTIVE"
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  [{idx}/{total_students}] CREATED ({active_label}): "
                            f"{s['name']} — {p_ok} payments"
                            + (f" ({p_skip} skipped)" if p_skip else "")
                        )
                    )
                    created_count += 1

            except Exception as exc:
                msg = f"  [{idx}/{total_students}] ERROR for {s['name']}: {exc}"
                self.stdout.write(self.style.ERROR(msg))
                errors.append(msg)

        # ── Step 3: Summary ────────────────────────────────────────────────
        self.stdout.write("\n" + "=" * 60)
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN SUMMARY (nothing was written)"))
        else:
            self.stdout.write(self.style.SUCCESS("IMPORT COMPLETE"))
        self.stdout.write(f"  Students in source data : {total_students}")
        self.stdout.write(f"  Students created        : {created_count}")
        self.stdout.write(f"  Students skipped/dup    : {skipped_count}")
        self.stdout.write(f"  Payment rows created    : {payment_created}")
        self.stdout.write(f"  Payment rows skipped    : {payment_skipped}")
        if errors:
            self.stdout.write(self.style.ERROR(f"  Errors                  : {len(errors)}"))
            for e in errors:
                self.stdout.write(self.style.ERROR(e))
        self.stdout.write("=" * 60)

        if not dry_run:
            self.stdout.write(
                "\nVerification query:\n"
                "  python manage.py shell -c \"\n"
                "  from fds.models import FdsStudent, FdsStudentFeeAccount, FdsFeesCollection\n"
                "  print('Students (KOCHI):', FdsStudent.objects.filter(branch='KOCHI').count())\n"
                "  print('Active:', FdsStudent.objects.filter(branch='KOCHI', is_active=True).count())\n"
                "  print('Inactive:', FdsStudent.objects.filter(branch='KOCHI', is_active=False).count())\n"
                "  print('Fee Accounts:', FdsStudentFeeAccount.objects.filter(student__branch='KOCHI').count())\n"
                "  print('Payments:', FdsFeesCollection.objects.filter(student__branch='KOCHI').count())\n"
                "  \""
            )
