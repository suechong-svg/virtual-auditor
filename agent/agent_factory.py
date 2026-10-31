"""Builds the agent: model, tools, guardrails, skills and connectors in one place."""
from __future__ import annotations

import os
import warnings

from claude_agent_sdk import CanUseToolShadowedWarning, ClaudeAgentOptions, HookMatcher

# Intended: read-only tools skip the approval callback. The PreToolUse hook still checks them.
warnings.filterwarnings("ignore", category=CanUseToolShadowedWarning)

from . import config
from .audit_tools import audit_server
from .guardrails import READ_ONLY_TOOLS, Approver, make_permission_callback, post_tool_log, pre_tool_guard

BUILT_IN_TOOLS = ["Read", "Grep", "Glob", "Write", "Edit", "Bash", "WebSearch", "WebFetch", "TodoWrite"]


def _system_prompt() -> str:
    text = (config.ROOT / "prompts" / "virtual_auditor.md").read_text(encoding="utf-8")
    return text.format(
        SOURCES_DIR=config.SOURCES_DIR,
        WORKSPACE_DIR=config.WORKSPACE_DIR,
        AUTONOMY=config.AUTONOMY,
        AUDITOR_NAME=config.AUDITOR_NAME,
    )


def _connectors() -> dict:
    servers: dict = {"audit": audit_server}
    # Phase 2: Confluence + JIRA, read-only. Turns on when the .env values are filled in.
    if os.getenv("JIRA_URL") or os.getenv("CONFLUENCE_URL"):
        servers["atlassian"] = {
            "type": "stdio",
            "command": "uvx",
            "args": ["mcp-atlassian"],
            "env": {
                "CONFLUENCE_URL": os.getenv("CONFLUENCE_URL", ""),
                "CONFLUENCE_USERNAME": os.getenv("ATLASSIAN_EMAIL", ""),
                "CONFLUENCE_API_TOKEN": os.getenv("ATLASSIAN_API_TOKEN", ""),
                "JIRA_URL": os.getenv("JIRA_URL", ""),
                "JIRA_USERNAME": os.getenv("ATLASSIAN_EMAIL", ""),
                "JIRA_API_TOKEN": os.getenv("ATLASSIAN_API_TOKEN", ""),
                "READ_ONLY_MODE": "true",  # connector-side control; our hook is the second line
            },
        }
    return servers


def build_options(approver: Approver, resume_session: str | None = None) -> ClaudeAgentOptions:
    connectors = _connectors()
    auto_allowed = list(READ_ONLY_TOOLS)
    if "atlassian" in connectors:
        auto_allowed.append("mcp__atlassian")  # reads auto-allowed; writes blocked by the hook

    return ClaudeAgentOptions(
        model=config.MODEL,
        system_prompt={"type": "preset", "preset": "claude_code", "append": _system_prompt()},
        cwd=str(config.ROOT),
        add_dirs=[str(config.SOURCES_DIR), str(config.WORKSPACE_DIR)],
        tools=BUILT_IN_TOOLS,
        allowed_tools=auto_allowed,
        mcp_servers=connectors,
        skills="all",                    # loads .claude/skills/* from this project
        setting_sources=["project"],     # ignore personal ~/.claude settings
        permission_mode="default",
        can_use_tool=make_permission_callback(approver),
        hooks={
            "PreToolUse": [HookMatcher(matcher=None, hooks=[pre_tool_guard])],
            "PostToolUse": [HookMatcher(matcher=None, hooks=[post_tool_log])],
        },
        max_budget_usd=config.MAX_BUDGET_USD,
        resume=resume_session,
    )
