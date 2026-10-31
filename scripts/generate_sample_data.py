"""Generates FAKE core banking audit data with planted exceptions.

Run: python scripts/generate_sample_data.py
Everything here is synthetic. Names are invented. Re-running gives the same data (fixed seed).
The answer key (planted exceptions) is written to scripts/ANSWER_KEY.md, OUTSIDE the
agent's source folder, so you can check whether the agent found them.
"""
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

random.seed(42)
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sample_data" / "auditee_sources"
EXTRACTS = SRC / "core_banking_extracts"
JIRA = SRC / "jira_export"
CONF = SRC / "confluence_export"
PROGRAM = ROOT / "sample_data" / "audit_program"
for d in (EXTRACTS, JIRA, CONF, PROGRAM):
    d.mkdir(parents=True, exist_ok=True)

FIRST = ["Aisha", "Omar", "Fatima", "Rahul", "Priya", "Daniel", "Mariam", "Yousef", "Sara", "Ahmed",
         "Lina", "Karim", "Noura", "Vikram", "Elena", "Hassan", "Reem", "Arjun", "Layla", "Tariq",
         "Grace", "Imran", "Hind", "Marco", "Zainab", "Faisal", "Anika", "Khalid", "Rania", "Samir"]
LAST = ["Haddad", "Rahman", "Menon", "Saleh", "Kapoor", "Farouk", "Nasser", "Iyer", "Costa", "Aziz",
        "Darwish", "Pillai", "Khoury", "Shah", "Mansour", "Fernandes", "Qasim", "Rao", "Hamdan", "Lopez"]
DEPTS = ["Retail Operations", "Payments Operations", "Treasury", "Finance", "IT Production Support",
         "Customer Service", "Credit Operations", "Compliance"]
ROLES = ["Teller Inquiry", "Account Maintenance", "Payment Maker", "Payment Approver",
         "GL Posting", "Customer Onboarding", "Limit Maintenance", "Interest Parameter Maintenance",
         "Report Viewer", "System Administrator"]

PERIOD_START, PERIOD_END = date(2026, 1, 1), date(2026, 9, 30)
answer_key = []


def rand_date(a: date, b: date) -> date:
    return a + timedelta(days=random.randint(0, (b - a).days))


def add_bdays(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:  # UAE working week Mon-Fri
            n -= 1
    return d


def write_csv(path: Path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


# ------------------------------------------------------------ HR master + leavers
employees = []
used = set()
for i in range(1, 131):
    while True:
        name = f"{random.choice(FIRST)} {random.choice(LAST)}"
        if name not in used:
            used.add(name)
            break
    employees.append({"emp_id": f"E{10000 + i}", "name": name, "dept": random.choice(DEPTS),
                      "user_id": (name.split()[0][0] + name.split()[1]).lower()[:8] + str(i)})

leavers = random.sample(employees, 16)
hr_rows = []
for e in leavers:
    e["term_date"] = rand_date(date(2026, 1, 15), date(2026, 9, 20))
    hr_rows.append([e["emp_id"], e["name"], e["dept"], e["term_date"].isoformat(),
                    random.choice(["Resignation", "Resignation", "End of contract", "Termination"])])
write_csv(EXTRACTS / "hr_leavers_jan_sep_2026.csv",
          ["employee_id", "employee_name", "department", "termination_date", "leaving_reason"], hr_rows)

# ------------------------------------------------------------ CBS user access list
access_rows = []
lv = {e["emp_id"]: e for e in leavers}
planted_active, planted_late, planted_login = leavers[0], leavers[1], leavers[2]
for e in employees:
    status, disabled, last_login = "ACTIVE", "", rand_date(date(2026, 9, 1), date(2026, 9, 30))
    if e["emp_id"] in lv:
        t = e["term_date"]
        status = "DISABLED"
        disabled = add_bdays(t, random.choice([0, 0, 1])).isoformat()
        last_login = t - timedelta(days=random.randint(0, 3))
        if e is planted_active:
            status, disabled = "ACTIVE", ""
            last_login = t - timedelta(days=2)
        elif e is planted_late:
            disabled = add_bdays(t, 6).isoformat()
        elif e is planted_login:
            disabled = add_bdays(t, 4).isoformat()
            last_login = add_bdays(t, 2)
    access_rows.append([e["user_id"], e["emp_id"], e["name"], e["dept"], status,
                        date(2023, 1, 1) + timedelta(days=random.randint(0, 900)),
                        disabled, last_login.isoformat()])
# One generic account with no HR record
access_rows.append(["batchsvc01", "", "Batch Service Account", "IT Production Support", "ACTIVE",
                    "2022-03-01", "", "2026-09-30"])
write_csv(EXTRACTS / "cbs_user_access_list_30sep2026.csv",
          ["user_id", "employee_id", "user_name", "department", "account_status", "created_date",
           "disabled_date", "last_login_date"], access_rows)

answer_key += [
    f"CB-AC-02: {planted_active['user_id']} ({planted_active['name']}) left {planted_active['term_date']} but CBS account still ACTIVE.",
    f"CB-AC-02: {planted_late['user_id']} ({planted_late['name']}) left {planted_late['term_date']}, disabled 6 business days later (policy: 1).",
    f"CB-AC-02: {planted_login['user_id']} ({planted_login['name']}) left {planted_login['term_date']}, logged in AFTER termination and was disabled late (more than 1 business day).",
    "CB-AC-02 (judgement): batchsvc01 generic account has no employee owner; outside leaver test but worth flagging.",
]

# ------------------------------------------------------------ role assignments (SoD)
role_rows = []
active_staff = [e for e in employees if e["emp_id"] not in lv]
sod_conflicts = random.sample([e for e in active_staff if e["dept"] == "Payments Operations"] or active_staff, 2)
for e in employees:
    k = random.randint(1, 3)
    roles = set(random.sample(ROLES[:-1], k))
    if {"Payment Maker", "Payment Approver"} <= roles:
        roles.discard("Payment Approver")
    if e in sod_conflicts:
        roles |= {"Payment Maker", "Payment Approver"}
    for r in sorted(roles):
        role_rows.append([e["user_id"], e["name"], r, rand_date(date(2024, 1, 1), date(2026, 6, 30)).isoformat()])
role_rows.append(["batchsvc01", "Batch Service Account", "System Administrator", "2022-03-01"])
write_csv(EXTRACTS / "cbs_user_roles_30sep2026.csv", ["user_id", "user_name", "role", "assigned_date"], role_rows)
for e in sod_conflicts:
    answer_key.append(f"CB-AC-03: {e['user_id']} ({e['name']}) holds both Payment Maker and Payment Approver.")

# ------------------------------------------------------------ changes: JIRA + deployment log
tickets, deploys = [], []
for i in range(1, 43):
    key = f"CBSCHG-{1200 + i}"
    emergency = i in (7, 23, 31)
    deploy_dt = datetime.combine(rand_date(PERIOD_START, PERIOD_END), datetime.min.time()) + timedelta(hours=22)
    approved = deploy_dt - timedelta(days=random.randint(2, 6))
    pir = (deploy_dt + timedelta(days=random.randint(1, 4))).date().isoformat() if emergency else ""
    tickets.append([key, random.choice(["Patch core banking module", "Update GL mapping", "Fee table change",
                                        "Performance fix EOD batch", "Regulatory report change",
                                        "Interest accrual fix"]),
                    "Emergency" if emergency else "Normal", "Closed",
                    random.choice(["CAB-Chair: M. Nasser", "CAB-Chair: R. Iyer"]),
                    approved.isoformat(sep=" "), deploy_dt.date().isoformat(), pir])
    deploys.append([f"DEP-{5000 + i}", "CBS-PROD", deploy_dt.isoformat(sep=" "), key,
                    random.choice(["deploy_bot", "deploy_bot", "kshah12"])])

# planted: approval after deployment
tickets[10][5] = (datetime.fromisoformat(deploys[10][2]) + timedelta(hours=14)).isoformat(sep=" ")
answer_key.append(f"CB-CM-01: {tickets[10][0]} CAB approval timestamp is AFTER deployment {deploys[10][0]}.")
# planted: emergency change without PIR
tickets[22][7] = ""
answer_key.append(f"CB-CM-01: emergency change {tickets[22][0]} has no post-implementation review.")
# planted: deployment with no ticket
deploys.append(["DEP-5099", "CBS-PROD", "2026-08-14 23:40:00", "", "mfarouk57"])
answer_key.append("CB-CM-01: DEP-5099 deployed to CBS-PROD with no change ticket reference.")

write_csv(JIRA / "cbs_change_tickets_export.csv",
          ["issue_key", "summary", "change_type", "status", "approver", "approved_at",
           "planned_deploy_date", "pir_completed_date"], tickets)
write_csv(EXTRACTS / "cbs_prod_deployment_log_jan_sep_2026.csv",
          ["deployment_id", "environment", "deployed_at", "change_ticket", "deployed_by"], deploys)

# ------------------------------------------------------------ interest parameter changes
param_rows = []
makers = [e["user_id"] for e in random.sample(active_staff, 4)]
checkers = [e["user_id"] for e in random.sample(active_staff, 3)]
for i in range(1, 19):
    m, c = random.choice(makers), random.choice(checkers)
    if i == 11:
        c = m
    old = round(random.uniform(1.0, 5.5), 2)
    param_rows.append([f"PRM-{300 + i}", random.choice(["SAV-STD", "SAV-PLUS", "FD-3M", "FD-12M", "CASA-BIZ"]),
                       old, round(old + random.choice([-0.25, 0.25, 0.5]), 2),
                       rand_date(PERIOD_START, PERIOD_END).isoformat(), m, c])
write_csv(EXTRACTS / "cbs_interest_parameter_changes.csv",
          ["change_id", "product_code", "old_rate_pct", "new_rate_pct", "effective_date", "maker_id",
           "checker_id"], param_rows)
answer_key.append(f"CB-IP-01: {param_rows[10][0]} maker and checker are the same user ({param_rows[10][5]}).")

# ------------------------------------------------------------ Confluence pages (policy + review)
(CONF / "Access_Management_Policy_v3.md").write_text("""# Access Management Policy (v3.0, approved March 2025)
Owner: Head of IAM | Applies to: all production systems including the Core Banking System (CBS)

## 4. Leavers
4.1 HR notifies IAM of all leavers through the HR system on or before the termination date.
4.2 Access to CBS must be disabled within **one (1) business day** of the termination date.
4.3 Accounts belonging to leavers must not be used after the termination date.

## 5. Segregation of duties
5.1 No user may hold both **Payment Maker** and **Payment Approver** roles in CBS.
5.2 Exceptions require CISO and Head of Payments approval, recorded in the SoD exception register.

## 6. Generic and service accounts
6.1 Each generic or service account must have a named owner recorded in the account register.

## 7. Periodic review
7.1 CBS user access is recertified quarterly by line managers.
""", encoding="utf-8")

(CONF / "Change_Management_Standard_v2.md").write_text("""# Change Management Standard (v2.1, approved January 2026)
Owner: Head of IT Service Management

## 3. Normal changes
3.1 Every production change requires a JIRA change ticket (project CBSCHG).
3.2 The Change Advisory Board (CAB) must approve the ticket **before** deployment.

## 4. Emergency changes
4.1 Emergency changes may be deployed with verbal CAB-Chair approval, recorded in the ticket.
4.2 A post-implementation review (PIR) must be completed within **five (5) business days**.

## 5. Deployment
5.1 Deployments to CBS-PROD run through the deployment pipeline and must reference a ticket.
""", encoding="utf-8")

(CONF / "Interest_Parameter_Maintenance_Procedure.md").write_text("""# Interest Rate Parameter Maintenance Procedure (v1.4)
Owner: Head of Treasury Operations

1. Rate changes follow ALCO approval.
2. Each change is entered by a maker and authorised by a different checker in CBS (four-eyes).
3. Treasury Operations reconciles the CBS rate table to the ALCO minute monthly.
""", encoding="utf-8")

(CONF / "CBS_Access_Review_Q2_2026.md").write_text("""# CBS Quarterly Access Recertification - Q2 2026
Status: Completed | Launched 2 July 2026 | Closed 24 July 2026
Reviewers: 14 line managers | Accounts reviewed: 121 | Revocations requested: 6 | Revocations completed: 5
Note: One revocation (Treasury) pending at close. Sign-off by Head of IAM: 25 July 2026.
""", encoding="utf-8")

# ------------------------------------------------------------ audit program
wb = Workbook()
ws = wb.active
ws.title = "Audit Program"
header = ["Test ID", "Area", "Control ID", "Control description", "Risk", "Test procedure",
          "Source data", "Criteria"]
ws.append(header)
program = [
    ["CB-AC-01", "Access management", "IAM-C07", "CBS access is recertified quarterly by line managers.",
     "Inappropriate access persists.", "Inspect the Q2 2026 recertification for completeness, timely closure, and follow-up of revocations.",
     "confluence_export/CBS_Access_Review_Q2_2026.md", "Access Management Policy s7.1"],
    ["CB-AC-02", "Access management", "IAM-C03", "Leavers' CBS access is disabled within one business day.",
     "Ex-employees retain or use access.", "Obtain the HR leavers list for the period. Match 100% of leavers to the CBS user list. "
     "Check account status, disabled date vs termination date (business days, Mon-Fri), and any login after termination.",
     "core_banking_extracts/hr_leavers_jan_sep_2026.csv; core_banking_extracts/cbs_user_access_list_30sep2026.csv",
     "Access Management Policy s4.2, s4.3"],
    ["CB-AC-03", "Access management", "IAM-C05", "No user holds conflicting payment roles.",
     "Unauthorised payments.", "Analyse 100% of role assignments for users holding both Payment Maker and Payment Approver.",
     "core_banking_extracts/cbs_user_roles_30sep2026.csv", "Access Management Policy s5.1"],
    ["CB-CM-01", "Change management", "ITSM-C02", "CBS production changes are CAB-approved before deployment; emergency changes get a PIR in 5 business days.",
     "Unauthorised or untested changes.", "Reconcile 100% of CBS-PROD deployments to JIRA change tickets. Check approval precedes deployment, "
     "and emergency changes have a timely PIR.",
     "core_banking_extracts/cbs_prod_deployment_log_jan_sep_2026.csv; jira_export/cbs_change_tickets_export.csv",
     "Change Management Standard s3.2, s4.2, s5.1"],
    ["CB-IP-01", "Interest parameters", "TRO-C01", "Interest rate parameter changes are four-eyes authorised.",
     "Incorrect customer rates.", "Inspect 100% of rate parameter changes for maker different from checker.",
     "core_banking_extracts/cbs_interest_parameter_changes.csv", "Interest Parameter Maintenance Procedure step 2"],
]
for row in program:
    ws.append(row)
for c in ws[1]:
    c.font = Font(bold=True)
for col, width in zip("ABCDEFGH", [10, 18, 10, 45, 30, 70, 55, 35]):
    ws.column_dimensions[col].width = width
for row in ws.iter_rows(min_row=2):
    for c in row:
        c.alignment = Alignment(wrap_text=True, vertical="top")
wb.save(PROGRAM / "Core_Banking_Audit_Program_2026.xlsx")

(ROOT / "scripts" / "ANSWER_KEY.md").write_text(
    "# Planted exceptions (do not put this file in the agent's source folder)\n\n"
    + "\n".join(f"- {a}" for a in answer_key) + "\n", encoding="utf-8")
print("Sample data written to", SRC)
print("Answer key written to scripts/ANSWER_KEY.md")
