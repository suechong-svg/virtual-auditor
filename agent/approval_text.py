"""Turns an approval request into a plain-English card for the auditor.

The auditor decides on audit content (conclusion, exceptions, issue wording),
not on code or JSON. Raw tool inputs stay visible in the step details and in
the activity log for anyone who wants to re-perform the work.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

MAX_ROWS = 10  # exceptions shown on the card; the full list is in the workpaper


def _cell(value: Any) -> str:
    """Make a value safe for a one-line markdown table cell."""
    return str(value).replace("|", "/").replace("\n", " ").strip()


def _field(label: str, value: Any) -> str:
    value = "" if value is None else str(value).strip()
    return f"**{label}:** {value}" if value else ""


def _bullets(items: list[Any] | None, empty: str = "None") -> str:
    items = [str(i).strip() for i in (items or []) if str(i).strip()]
    return "\n".join(f"- {i}" for i in items) if items else f"- {empty}"


def _table(rows: list[dict[str, Any]], limit: int = MAX_ROWS) -> str:
    if not rows:
        return "No exceptions."
    keys = list(dict.fromkeys(k for r in rows for k in r))
    head = "| " + " | ".join(k.replace("_", " ").title() for k in keys) + " |"
    rule = "|" + "---|" * len(keys)
    body = ["| " + " | ".join(_cell(r.get(k, "")) for k in keys) + " |" for r in rows[:limit]]
    more = f"\n\n_...and {len(rows) - limit} more in the workpaper._" if len(rows) > limit else ""
    return "\n".join([head, rule, *body]) + more


def _join(*parts: str) -> str:
    return "\n\n".join(p for p in parts if p)


def _evidence(d: dict) -> tuple[str, str]:
    name = Path(str(d.get("source_path", ""))).name or "(no file named)"
    body = _join(
        f"File **{name}** as evidence for test **{d.get('test_id', '')}**.",
        _field("What it is", d.get("description")),
        "A copy is filed with a SHA-256 hash and added to the Evidence Index. "
        "The auditee's original is not changed.",
    )
    return "File evidence", body


def _workpaper(d: dict) -> tuple[str, str]:
    exc = d.get("exceptions") or []
    body = _join(
        f"**{d.get('wp_ref', '')}** for test **{d.get('test_id', '')}**",
        _field("Conclusion", d.get("conclusion")),
        _field("Exceptions", len(exc)),
        _field("Control", d.get("control_description")),
        _field("Population", d.get("population_and_source")),
        _field("Approach", d.get("approach")),
        _field("Results", d.get("results")),
        _table(exc) if exc else "",
        "**Evidence referenced:**\n" + _bullets(d.get("evidence_refs"), "None filed"),
        "_Approve to save the workpaper for your review and sign-off. "
        "Reject and add a note if the conclusion or exceptions need changing._",
    )
    return "Workpaper ready for review", body


def _issue(d: dict) -> tuple[str, str]:
    body = _join(
        f"**{d.get('issue_id', '')}: {d.get('title', '')}**",
        _field("Rating", d.get("rating")),
        _field("Condition", d.get("condition")),
        _field("Criteria", d.get("criteria")),
        _field("Cause", d.get("cause")),
        _field("Effect", d.get("effect")),
        _field("Recommendation", d.get("recommendation")),
        _field("Related workpaper", d.get("related_workpaper")),
        "_Approve to add this to the Issue Log as a draft pending your review._",
    )
    return "Draft issue to log", body


def _minutes(d: dict) -> tuple[str, str]:
    actions = [f"{a.get('action', '')} (owner: {a.get('owner', '?')}, due: {a.get('due', '?')})"
               for a in (d.get("actions") or []) if isinstance(a, dict)]
    body = _join(
        f"**{d.get('meeting_title', '')}** on {d.get('meeting_date', '')}",
        _field("Attendees", "; ".join(d.get("attendees") or [])),
        _field("Summary", d.get("summary")),
        "**Decisions:**\n" + _bullets(d.get("decisions")),
        "**Actions:**\n" + _bullets(actions),
        "**Evidence requests (PBC):**\n" + _bullets(d.get("pbc_requests")),
    )
    return "Meeting minutes ready", body


def _shell(d: dict) -> tuple[str, str]:
    body = _join(
        "The agent wants to run a system command that is not one of its analysis scripts.",
        f"Command: `{_cell(d.get('command', ''))[:300]}`",
        _field("Why", d.get("description")),
        "_Approve only if this looks like a harmless step. Reject if unsure; "
        "the agent will explain or find another way._",
    )
    return "System command", body


def _generic(tool: str, d: dict) -> tuple[str, str]:
    lines = [_field(k.replace("_", " ").capitalize(), v) for k, v in d.items()
             if isinstance(v, (str, int, float)) and str(v).strip()]
    return tool.replace("mcp__audit__", "").replace("_", " ").capitalize(), _join(*lines[:12])


CARDS = {
    "mcp__audit__file_evidence": _evidence,
    "mcp__audit__write_workpaper": _workpaper,
    "mcp__audit__log_issue": _issue,
    "mcp__audit__write_minutes": _minutes,
    "Bash": _shell,
}


def approval_card(tool: str, data: dict[str, Any]) -> str:
    """Markdown shown above the Approve / Reject buttons."""
    data = data or {}
    builder = CARDS.get(tool)
    title, body = builder(data) if builder else _generic(tool, data)
    return f"### Approval needed: {title}\n\n{body}"
