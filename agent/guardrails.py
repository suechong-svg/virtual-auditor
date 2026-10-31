"""Controls around the agent.

Two layers, like a preventive control plus an authorisation:
1. pre_tool_guard (hook): HARD rules that run before every tool call and can
   never be overridden by the model or by a human click. Example: no writes
   outside the Audit workspace, no write actions on Confluence/JIRA.
2. approval_policy (can_use_tool): decides whether a human must approve the
   action first, based on the AUTONOMY setting.

Every decision and every tool call is written to the activity log.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

from . import config

# Tools that only read. These never need approval.
READ_ONLY_TOOLS = [
    "Read", "Grep", "Glob", "WebSearch", "WebFetch", "Skill",
    "TodoWrite",
    "mcp__audit__create_engagement",
    "mcp__audit__list_engagements",
    "mcp__audit__read_engagement_notes",
]

# Memory writes: not the audit record, so no approval unless step_by_step.
MEMORY_TOOLS = {"mcp__audit__update_engagement_notes"}

# Tools that put something on the audit record. Approval needed unless autonomous.
FILING_TOOLS = {
    "mcp__audit__file_evidence",
    "mcp__audit__write_workpaper",
    "mcp__audit__log_issue",
    "mcp__audit__write_minutes",
}

# Words in a connector tool name that mean it changes the auditee's system.
WRITE_VERBS = re.compile(
    r"(create|update|delete|add|remove|edit|transition|upload|link|move|assign|comment|batch)",
    re.I,
)

# Shell commands we never allow. A deny-list, not a sandbox: IT should replace
# this with a container sandbox before any real deployment.
BLOCKED_SHELL = re.compile(
    r"(\brm\b|\brmdir\b|\bdel\b|\berase\b|\bmv\b|\bmove\b|\bformat\b|\bshutdown\b|"
    r"\bcurl\b|\bwget\b|invoke-webrequest|\bssh\b|\bscp\b|\bpip\b|\bnpm\b|\bgit\s+push\b|"
    r"remove-item|set-content|chmod|chown|\bsudo\b)",
    re.I,
)

# Look-only shell commands (list folders, peek at a file). Auto-approved so the
# auditor is not asked about housekeeping. Anything chained, redirected or
# substituted still needs approval, and the hard rules above still apply.
SAFE_LOOKUP = re.compile(
    r"^(ls|dir|pwd|cat|head|tail|wc|type|tree|get-childitem|get-content|gci|gc)(\s|$)", re.I)
SHELL_CONTROL = re.compile(r"[;&|<>`]|\$\(")

PATH_KEYS = ("file_path", "path", "notebook_path")


def _resolve(p: str) -> Path:
    path = Path(p).expanduser()
    if not path.is_absolute():
        path = config.ROOT / path
    return path.resolve()


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.relative_to(folder.resolve())
        return True
    except ValueError:
        return False


def log_event(event: dict[str, Any]) -> None:
    event = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "user": config.AUDITOR_NAME, "agent": "virtual-auditor", **event}
    config.ACTIVITY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with config.ACTIVITY_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, default=str)[:20000] + "\n")


def check_hard_rules(tool: str, tool_input: dict[str, Any]) -> str | None:
    """Return a reason string if the call breaks a hard rule, else None."""
    readable = [config.SOURCES_DIR, config.WORKSPACE_DIR, config.ROOT / ".claude",
                config.ROOT / "templates", config.ROOT / "prompts"]

    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        target = _resolve(str(tool_input.get("file_path") or tool_input.get("notebook_path") or ""))
        if not _inside(target, config.WORKSPACE_DIR):
            return (f"Blocked: the agent may only write inside the Audit workspace "
                    f"({config.WORKSPACE_DIR}). Attempted: {target}")

    if tool in ("Read", "Grep", "Glob"):
        raw = next((tool_input[k] for k in PATH_KEYS if tool_input.get(k)), None)
        # No path means "search the project folder", which holds code and the answer key.
        target = _resolve(str(raw)) if raw else config.ROOT
        if target.name == ".env":
            return "Blocked: configuration secrets are not readable by the agent."
        if not any(_inside(target, d) for d in readable):
            return (f"Blocked: {target} is outside the approved folders. Pass an explicit path under "
                    f"{config.SOURCES_DIR} or {config.WORKSPACE_DIR}.")

    if tool == "Bash":
        cmd = str(tool_input.get("command", ""))
        if "answer_key" in cmd.lower() or ".env" in cmd:
            return "Blocked: that file is not part of the audit sources."
        if BLOCKED_SHELL.search(cmd):
            return f"Blocked shell command (deny-list): {cmd[:200]}"
        if str(config.SOURCES_DIR) in cmd and re.search(r">|\btee\b|\bcp\b|\bcopy\b", cmd):
            return "Blocked: shell output may not be written into auditee source folders."

    if tool.startswith("mcp__") and not tool.startswith("mcp__audit__"):
        action = tool.split("__")[-1]
        if WRITE_VERBS.search(action):
            return f"Blocked: auditee systems are read-only for the agent ({tool})."

    return None


async def pre_tool_guard(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict:
    tool = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {}) or {}
    reason = check_hard_rules(tool, tool_input)
    if reason:
        log_event({"type": "blocked", "tool": tool, "input": tool_input, "reason": reason})
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    return {}


async def post_tool_log(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict:
    response = input_data.get("tool_response")
    log_event({
        "type": "tool_call",
        "tool": input_data.get("tool_name"),
        "tool_use_id": tool_use_id,
        "input": input_data.get("tool_input"),
        "result_preview": str(response)[:1500],
    })
    return {}


# A function the UI supplies: shows the request to a human, returns (approved, note).
Approver = Callable[[str, dict[str, Any]], Awaitable[tuple[bool, str]]]


def needs_approval(tool: str, tool_input: dict[str, Any]) -> bool:
    mode = config.AUTONOMY
    if mode == "autonomous":
        return False
    if mode == "step_by_step":
        return tool not in READ_ONLY_TOOLS
    # review_before_filing
    if tool in FILING_TOOLS:
        return True
    if tool == "Bash":
        cmd = str(tool_input.get("command", "")).strip().lower()
        if re.match(r"^(python|python3|py)\b", cmd):
            return False
        if SAFE_LOOKUP.match(cmd) and not SHELL_CONTROL.search(cmd):
            return False
        return True
    return False


def make_permission_callback(approver: Approver):
    async def can_use_tool(tool: str, tool_input: dict[str, Any], context: Any):
        if not needs_approval(tool, tool_input):
            log_event({"type": "auto_approved", "tool": tool, "autonomy": config.AUTONOMY})
            return PermissionResultAllow()
        approved, note = await approver(tool, tool_input)
        log_event({"type": "human_decision", "tool": tool, "approved": approved, "note": note,
                   "input": tool_input})
        if approved:
            return PermissionResultAllow()
        return PermissionResultDeny(
            message=f"The auditor rejected this action. Their note: {note or 'none'}. "
                    "Ask what they want changed before trying again."
        )
    return can_use_tool
