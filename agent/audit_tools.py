"""Audit-specific tools the agent can call.

Each tool is a plain Python function (easy to test and to reuse in another
agent framework later), wrapped as an MCP tool for the Claude Agent SDK.
All outputs land inside config.WORKSPACE_DIR.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Pt
from openpyxl import Workbook, load_workbook

from claude_agent_sdk import create_sdk_mcp_server, tool

from . import config

PREPARER = "Virtual Auditor (AI) - draft pending human review"
EVIDENCE_HEADER = ["evidence_ref", "test_id", "file_name", "description", "source_path",
                   "sha256", "retrieved_utc"]
ISSUE_HEADER = ["issue_id", "title", "condition", "criteria", "cause", "effect", "rating",
                "recommendation", "related_workpaper", "status", "raised_by", "raised_utc"]


# ---------------------------------------------------------------- helpers
def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:60]


def _engagement_dir(engagement_id: str) -> Path:
    matches = [p for p in config.WORKSPACE_DIR.iterdir()
               if p.is_dir() and p.name.startswith(_slug(engagement_id))]
    if not matches:
        raise ValueError(f"No engagement folder for '{engagement_id}'. Create it first.")
    return matches[0]


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _heading_table(doc: Document, rows: list[tuple[str, str]]) -> None:
    table = doc.add_table(rows=0, cols=2)
    table.style = "Light Grid Accent 1"
    for label, value in rows:
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = value or ""
        cells[0].paragraphs[0].runs[0].bold = True


# ---------------------------------------------------------------- core functions
def create_engagement(engagement_id: str, name: str, auditable_entity: str = "",
                      period: str = "", lead_auditor: str = "") -> str:
    template = json.loads(config.ENGAGEMENT_TEMPLATE.read_text(encoding="utf-8"))
    root = config.WORKSPACE_DIR / f"{_slug(engagement_id)}_{_slug(name)}"
    existed = root.exists()
    for folder in template["folders"]:
        (root / folder).mkdir(parents=True, exist_ok=True)

    meta_path = root / "00_Admin" / "engagement.json"
    if not meta_path.exists():
        meta_path.write_text(json.dumps({
            "engagement_id": engagement_id, "name": name, "auditable_entity": auditable_entity,
            "period": period, "lead_auditor": lead_auditor, "created_utc": _now(),
            "created_by": "Virtual Auditor (AI)"}, indent=2), encoding="utf-8")
        (root / "README.txt").write_text(template.get("readme", ""), encoding="utf-8")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not _notes_path(root).exists():
        _notes_path(root).write_text(_new_notes(meta), encoding="utf-8")

    index = root / "02_Fieldwork" / "Evidence" / "Evidence_Index.csv"
    if not index.exists():
        with index.open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow(EVIDENCE_HEADER)

    issues = root / "03_Issues" / "Issue_Log.xlsx"
    if not issues.exists():
        wb = Workbook()
        wb.active.title = "Issues"
        wb.active.append(ISSUE_HEADER)
        wb.save(issues)

    status = "already existed; missing folders added" if existed else "created"
    tree = "\n".join(f"  {f}" for f in template["folders"])
    return f"Engagement folder {status}: {root}\n{tree}"


def list_engagements() -> str:
    items = []
    for p in sorted(config.WORKSPACE_DIR.iterdir()):
        meta = p / "00_Admin" / "engagement.json"
        if meta.exists():
            m = json.loads(meta.read_text(encoding="utf-8"))
            items.append(f"- {m['engagement_id']}: {m['name']} ({p})")
    return "\n".join(items) or "No engagements yet."


NOTES_SECTIONS = ["Status", "Scope and key facts", "Decisions", "Tests", "Open PBC items",
                  "Open questions", "Session log"]


def _notes_path(root: Path) -> Path:
    return root / "00_Admin" / "engagement_notes.md"


def _new_notes(meta: dict) -> str:
    head = (f"# Engagement notes: {meta['engagement_id']} {meta['name']}\n\n"
            "Working memory for the Virtual Auditor and the team. The agent reads this before working on "
            "the engagement and updates it after each meaningful step. Humans can edit it too.\n")
    return head + "".join(f"\n## {sec}\n" for sec in NOTES_SECTIONS)


def read_engagement_notes(engagement_id: str) -> str:
    root = _engagement_dir(engagement_id)
    path = _notes_path(root)
    if not path.exists():
        meta = json.loads((root / "00_Admin" / "engagement.json").read_text(encoding="utf-8"))
        path.write_text(_new_notes(meta), encoding="utf-8")
    return path.read_text(encoding="utf-8")


def update_engagement_notes(engagement_id: str, section: str, entry: str, mode: str = "append") -> str:
    if section not in NOTES_SECTIONS:
        raise ValueError(f"Unknown section '{section}'. Use one of: {', '.join(NOTES_SECTIONS)}")
    if mode not in ("append", "replace"):
        raise ValueError("mode must be 'append' or 'replace'")
    text = read_engagement_notes(engagement_id)
    path = _notes_path(_engagement_dir(engagement_id))
    stamp = f"[{_now()[:10]} | {config.AUDITOR_NAME} via Virtual Auditor]"
    new_lines = "\n".join(f"- {stamp} {line.strip()}" for line in entry.strip().splitlines() if line.strip())

    marker = f"\n## {section}\n"
    start = text.index(marker) + len(marker)
    nxt = text.find("\n## ", start)
    end = len(text) if nxt == -1 else nxt
    body = text[start:end].rstrip("\n")
    body = new_lines if (mode == "replace" or not body.strip()) else body + "\n" + new_lines
    text = text[:start] + body + "\n" + text[end:]
    path.write_text(text, encoding="utf-8")
    return f"Updated '{section}' in {path}"


def file_evidence(engagement_id: str, test_id: str, source_path: str, description: str) -> str:
    root = _engagement_dir(engagement_id)
    src = Path(source_path).expanduser()
    if not src.is_absolute():
        src = config.ROOT / src
    src = src.resolve()
    if not src.is_file():
        raise ValueError(f"Source file not found: {src}")
    if not (_inside(src, config.SOURCES_DIR) or _inside(src, config.WORKSPACE_DIR)):
        raise ValueError("Evidence must come from the approved source folders or the Audit workspace.")

    dest_dir = root / "02_Fieldwork" / "Evidence" / _slug(test_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    n = len(list(dest_dir.glob("EV-*"))) + 1
    ref = f"EV-{_slug(test_id)}-{n:02d}"
    dest = dest_dir / f"{ref}_{src.name}"
    shutil.copy2(src, dest)  # copy, never move: the auditee's original is untouched
    digest = _sha256(dest)

    with (root / "02_Fieldwork" / "Evidence" / "Evidence_Index.csv").open("a", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow([ref, test_id, dest.name, description, str(src), digest, _now()])
    return f"Filed {ref} -> {dest}\nSHA-256: {digest}"


def write_workpaper(engagement_id: str, wp_ref: str, test_id: str, control_description: str,
                    test_objective: str, population_and_source: str, approach: str,
                    procedures: list[str], results: str, exceptions: list[dict[str, str]],
                    conclusion: str, evidence_refs: list[str]) -> str:
    root = _engagement_dir(engagement_id)
    meta = json.loads((root / "00_Admin" / "engagement.json").read_text(encoding="utf-8"))

    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(10)
    doc.add_heading(f"Workpaper {wp_ref}: {test_id}", level=1)
    _heading_table(doc, [
        ("Engagement", f"{meta['engagement_id']} {meta['name']}"),
        ("Auditable entity", meta.get("auditable_entity", "")),
        ("Period", meta.get("period", "")),
        ("Workpaper ref", wp_ref),
        ("Test ID", test_id),
        ("Prepared by", PREPARER),
        ("Prepared on (UTC)", _now()),
        ("Reviewed by", ""),
        ("Review date", ""),
    ])
    sections = [
        ("1. Control description", control_description),
        ("2. Test objective", test_objective),
        ("3. Population and source", population_and_source),
        ("4. Approach and sampling", approach),
    ]
    for title, body in sections:
        doc.add_heading(title, level=2)
        doc.add_paragraph(body)

    doc.add_heading("5. Procedures performed", level=2)
    for step in procedures:
        doc.add_paragraph(step, style="List Number")

    doc.add_heading("6. Results", level=2)
    doc.add_paragraph(results)

    doc.add_heading("7. Exceptions", level=2)
    if exceptions:
        keys = list(dict.fromkeys(k for e in exceptions for k in e))
        table = doc.add_table(rows=1, cols=len(keys))
        table.style = "Light Grid Accent 1"
        for i, k in enumerate(keys):
            table.rows[0].cells[i].text = k.replace("_", " ").title()
        for e in exceptions:
            cells = table.add_row().cells
            for i, k in enumerate(keys):
                cells[i].text = str(e.get(k, ""))
    else:
        doc.add_paragraph("No exceptions noted.")

    doc.add_heading("8. Conclusion", level=2)
    doc.add_paragraph(conclusion)

    doc.add_heading("9. Evidence references", level=2)
    for ref in evidence_refs or ["None filed"]:
        doc.add_paragraph(ref, style="List Bullet")

    doc.add_heading("10. Reviewer sign-off", level=2)
    doc.add_paragraph("Reviewer comments:\n\n\nSigned: ____________________   Date: ____________")

    out = root / "02_Fieldwork" / "Workpapers" / f"{_slug(wp_ref)}_{_slug(test_id)}.docx"
    doc.save(out)
    return f"Workpaper saved: {out}"


def log_issue(engagement_id: str, issue_id: str, title: str, condition: str, criteria: str,
              cause: str, effect: str, rating: str, recommendation: str,
              related_workpaper: str) -> str:
    root = _engagement_dir(engagement_id)
    path = root / "03_Issues" / "Issue_Log.xlsx"
    wb = load_workbook(path)
    ws = wb["Issues"]
    ws.append([issue_id, title, condition, criteria, cause, effect, rating, recommendation,
               related_workpaper, "Draft - pending auditor review", PREPARER, _now()])
    wb.save(path)
    return f"Issue {issue_id} added to {path}"


def write_minutes(engagement_id: str, meeting_title: str, meeting_date: str, attendees: list[str],
                  summary: str, discussion: list[dict[str, Any]], decisions: list[str],
                  actions: list[dict[str, str]], pbc_requests: list[str]) -> str:
    root = _engagement_dir(engagement_id)
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(10)
    doc.add_heading(f"Minutes: {meeting_title}", level=1)
    _heading_table(doc, [("Date", meeting_date), ("Attendees", "; ".join(attendees)),
                         ("Prepared by", PREPARER)])
    doc.add_heading("Summary", level=2)
    doc.add_paragraph(summary)
    doc.add_heading("Discussion", level=2)
    for item in discussion:
        doc.add_paragraph(str(item.get("topic", "")), style="List Number")
        for point in item.get("points", []):
            doc.add_paragraph(str(point), style="List Bullet 2")
    doc.add_heading("Decisions", level=2)
    for d in decisions or ["None recorded"]:
        doc.add_paragraph(d, style="List Bullet")
    doc.add_heading("Action items", level=2)
    table = doc.add_table(rows=1, cols=3)
    table.style = "Light Grid Accent 1"
    for i, h in enumerate(["Action", "Owner", "Due"]):
        table.rows[0].cells[i].text = h
    for a in actions:
        cells = table.add_row().cells
        cells[0].text, cells[1].text, cells[2].text = a.get("action", ""), a.get("owner", ""), a.get("due", "")
    doc.add_heading("Evidence / information requests (PBC)", level=2)
    for r in pbc_requests or ["None"]:
        doc.add_paragraph(r, style="List Bullet")

    out = root / "05_Meetings" / f"{_slug(meeting_date)}_{_slug(meeting_title)}_Minutes.docx"
    doc.save(out)
    return f"Minutes saved: {out}"


# ---------------------------------------------------------------- MCP wrappers
def _ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _err(e: Exception) -> dict:
    return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}


def _wrap(fn, args: dict) -> dict:
    try:
        return _ok(fn(**args))
    except Exception as e:  # report back to the agent instead of crashing
        return _err(e)


STR = {"type": "string"}
STR_LIST = {"type": "array", "items": {"type": "string"}}


@tool("create_engagement", "Create (or repair) the standard Internal Audit engagement folder "
      "structure in the Audit workspace.",
      {"type": "object", "properties": {
          "engagement_id": STR, "name": STR, "auditable_entity": STR, "period": STR,
          "lead_auditor": STR}, "required": ["engagement_id", "name"]})
async def t_create_engagement(args):
    return _wrap(create_engagement, args)


@tool("list_engagements", "List engagements that exist in the Audit workspace.",
      {"type": "object", "properties": {}})
async def t_list_engagements(args):
    return _wrap(list_engagements, {})


@tool("read_engagement_notes", "Read the engagement's working-memory notes (status, decisions, tests, "
      "open PBC items, open questions, session log). Call this before working on an engagement.",
      {"type": "object", "properties": {"engagement_id": STR}, "required": ["engagement_id"]})
async def t_read_engagement_notes(args):
    return _wrap(read_engagement_notes, args)


@tool("update_engagement_notes", "Record what changed in the engagement's working-memory notes. "
      "Append by default; use replace only to rewrite a section such as Status. One fact per line.",
      {"type": "object", "properties": {
          "engagement_id": STR,
          "section": {"type": "string", "enum": NOTES_SECTIONS},
          "entry": STR,
          "mode": {"type": "string", "enum": ["append", "replace"]}},
       "required": ["engagement_id", "section", "entry"]})
async def t_update_engagement_notes(args):
    return _wrap(update_engagement_notes, args)


@tool("file_evidence", "Copy a source file into the engagement's evidence folder for a test, "
      "hash it, and record it in the Evidence Index. Never moves or edits the original.",
      {"type": "object", "properties": {
          "engagement_id": STR, "test_id": STR, "source_path": STR, "description": STR},
       "required": ["engagement_id", "test_id", "source_path", "description"]})
async def t_file_evidence(args):
    return _wrap(file_evidence, args)


@tool("write_workpaper", "Write a structured test workpaper (.docx) into the engagement's "
      "Workpapers folder.",
      {"type": "object", "properties": {
          "engagement_id": STR, "wp_ref": STR, "test_id": STR, "control_description": STR,
          "test_objective": STR, "population_and_source": STR, "approach": STR,
          "procedures": STR_LIST, "results": STR,
          "exceptions": {"type": "array", "items": {"type": "object",
                                                    "additionalProperties": {"type": "string"}}},
          "conclusion": STR, "evidence_refs": STR_LIST},
       "required": ["engagement_id", "wp_ref", "test_id", "control_description", "test_objective",
                    "population_and_source", "approach", "procedures", "results", "exceptions",
                    "conclusion", "evidence_refs"]})
async def t_write_workpaper(args):
    return _wrap(write_workpaper, args)


@tool("log_issue", "Add a draft audit issue (condition, criteria, cause, effect, rating, "
      "recommendation) to the engagement Issue Log.",
      {"type": "object", "properties": {
          "engagement_id": STR, "issue_id": STR, "title": STR, "condition": STR, "criteria": STR,
          "cause": STR, "effect": STR,
          "rating": {"type": "string", "enum": ["High", "Medium", "Low"]},
          "recommendation": STR, "related_workpaper": STR},
       "required": ["engagement_id", "issue_id", "title", "condition", "criteria", "cause",
                    "effect", "rating", "recommendation", "related_workpaper"]})
async def t_log_issue(args):
    return _wrap(log_issue, args)


@tool("write_minutes", "Write meeting minutes (.docx) into the engagement's Meetings folder.",
      {"type": "object", "properties": {
          "engagement_id": STR, "meeting_title": STR, "meeting_date": STR, "attendees": STR_LIST,
          "summary": STR,
          "discussion": {"type": "array", "items": {"type": "object", "properties": {
              "topic": STR, "points": STR_LIST}}},
          "decisions": STR_LIST,
          "actions": {"type": "array", "items": {"type": "object", "properties": {
              "action": STR, "owner": STR, "due": STR}}},
          "pbc_requests": STR_LIST},
       "required": ["engagement_id", "meeting_title", "meeting_date", "attendees", "summary",
                    "discussion", "decisions", "actions", "pbc_requests"]})
async def t_write_minutes(args):
    return _wrap(write_minutes, args)


audit_server = create_sdk_mcp_server(
    name="audit", version="0.1.0",
    tools=[t_create_engagement, t_list_engagements, t_read_engagement_notes, t_update_engagement_notes,
           t_file_evidence, t_write_workpaper,
           t_log_issue, t_write_minutes],
)
