"""Chat UI for the Virtual Auditor.  Run:  chainlit run app.py -w

The same agent can later be exposed in Microsoft Teams: Chainlit has a Teams
adapter that switches on when TEAMS_APP_ID / TEAMS_APP_PASSWORD are set
(needs an Azure Bot registration from IT).
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import chainlit as cl
from claude_agent_sdk import (AssistantMessage, ClaudeSDKClient, ResultMessage, TextBlock,
                              ToolResultBlock, ToolUseBlock, UserMessage)

from agent import config, sessions
from agent.agent_factory import build_options

FRIENDLY = {
    "Read": "Reading file", "Grep": "Searching files", "Glob": "Listing files",
    "Write": "Writing draft", "Edit": "Editing draft", "Bash": "Running analysis",
    "WebSearch": "Searching the web", "WebFetch": "Reading web page", "Skill": "Loading audit procedure",
    "TodoWrite": "Updating plan",
    "mcp__audit__create_engagement": "Creating engagement folders",
    "mcp__audit__file_evidence": "Filing evidence",
    "mcp__audit__write_workpaper": "Writing workpaper",
    "mcp__audit__log_issue": "Logging issue",
    "mcp__audit__write_minutes": "Writing minutes",
}


def _summarise_request(tool: str, data: dict) -> str:
    if tool == "Bash":
        return f"```\n{data.get('command', '')}\n```"
    if tool in ("Write", "Edit"):
        return f"File: `{data.get('file_path')}`"
    keep = {k: v for k, v in data.items() if k in (
        "engagement_id", "test_id", "wp_ref", "source_path", "description", "conclusion",
        "issue_id", "title", "rating", "meeting_title")}
    return "```json\n" + json.dumps(keep or data, indent=2)[:1500] + "\n```"


async def ask_auditor(tool: str, data: dict) -> tuple[bool, str]:
    """Shown in the chat whenever the agent needs sign-off."""
    res = await cl.AskActionMessage(
        content=f"**Approval needed: {FRIENDLY.get(tool, tool)}**\n{_summarise_request(tool, data)}",
        actions=[
            cl.Action(name="approve", payload={"ok": True}, label="Approve"),
            cl.Action(name="reject", payload={"ok": False}, label="Reject"),
        ],
        timeout=900,
    ).send()
    if res and res.get("payload", {}).get("ok"):
        return True, ""
    if res is None:
        return False, "No response within 15 minutes"
    note = await cl.AskUserMessage(content="What should it change? (optional)", timeout=300).send()
    return False, (note or {}).get("output", "")


async def agent_worker(inbox: asyncio.Queue, outbox: asyncio.Queue, resume_id: str | None) -> None:
    """Owns one long-lived agent session per chat, so it remembers the conversation.
    resume_id reloads an earlier session's transcript (conversation memory across restarts)."""
    async with ClaudeSDKClient(options=build_options(ask_auditor, resume_session=resume_id)) as client:
        while True:
            prompt = await inbox.get()
            try:
                await client.query(prompt)
                async for msg in client.receive_response():
                    await outbox.put(msg)
            except Exception as e:  # surface errors in the chat rather than dying silently
                await outbox.put(e)
            await outbox.put(None)  # end of this turn


@cl.set_starters
async def starters(user=None, language=None):
    return [
        cl.Starter(label="Set up the engagement",
                   message="Create engagement CBS-2026-01 'Core Banking System Audit' for auditable entity "
                           "'Core Banking Platform', period 1 Jan to 30 Sep 2026, lead auditor Suzanne. "
                           "Then read the audit program and give me a one-page plan of the test steps."),
        cl.Starter(label="Run test CB-AC-02 (leavers)",
                   message="Perform audit test CB-AC-02 from the audit program for engagement CBS-2026-01. "
                           "File evidence, write the workpaper and draft issues for any exceptions."),
        cl.Starter(label="Run test CB-CM-01 (changes)",
                   message="Perform audit test CB-CM-01 from the audit program for engagement CBS-2026-01."),
        cl.Starter(label="Where are we?",
                   message="Where are we on engagement CBS-2026-01? Read the engagement notes and give me the "
                           "status, tests done, open PBC items and open questions."),
        cl.Starter(label="Minute the kick-off meeting",
                   message="Write minutes for the kick-off meeting transcript in sample_data/meetings for "
                           "engagement CBS-2026-01, and list any evidence requests the auditee agreed to."),
    ]


async def choose_session() -> tuple[str | None, str | None]:
    """Offer to resume one of the last few sessions. Returns (session_id, title)."""
    past = sessions.recent(5)
    if not past:
        return None, None
    actions = [cl.Action(name="resume", payload={"id": s["session_id"], "title": s["title"]},
                         label=f"Resume: {s['title'][:50]} ({s['last_used'][:10]})") for s in past]
    actions.append(cl.Action(name="new", payload={"id": None, "title": None}, label="Start a new session"))
    res = await cl.AskActionMessage(
        content="Resume a previous session, or start a new one? Engagement notes carry over either way.",
        actions=actions, timeout=180).send()
    if not res:
        return None, None
    return res["payload"].get("id"), res["payload"].get("title")


@cl.on_chat_start
async def start():
    resume_id, title = await choose_session()
    cl.user_session.set("title", title)
    inbox, outbox = asyncio.Queue(), asyncio.Queue()
    task = asyncio.create_task(agent_worker(inbox, outbox, resume_id))
    cl.user_session.set("inbox", inbox)
    cl.user_session.set("outbox", outbox)
    cl.user_session.set("task", task)


@cl.on_message
async def on_message(message: cl.Message):
    inbox: asyncio.Queue = cl.user_session.get("inbox")
    outbox: asyncio.Queue = cl.user_session.get("outbox")

    prompt = message.content
    # Files dropped into the chat go to the Audit workspace inbox (never into auditee folders).
    if message.elements:
        drop = config.WORKSPACE_DIR / "_inbox"
        drop.mkdir(exist_ok=True)
        saved = []
        for el in message.elements:
            if getattr(el, "path", None):
                dest = drop / el.name
                shutil.copy(el.path, dest)
                saved.append(str(dest))
        if saved:
            prompt += "\n\nFiles the auditor attached:\n" + "\n".join(f"- {p}" for p in saved)

    if not cl.user_session.get("title"):
        cl.user_session.set("title", message.content.strip().splitlines()[0] if message.content.strip() else "Untitled")
    await inbox.put(prompt)
    steps: dict[str, cl.Step] = {}

    while True:
        msg = await outbox.get()
        if msg is None:
            break
        if isinstance(msg, Exception):
            await cl.Message(content=f"Agent error: `{msg}`").send()
            continue
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    await cl.Message(content=block.text).send()
                elif isinstance(block, ToolUseBlock):
                    step = cl.Step(name=FRIENDLY.get(block.name, block.name), type="tool")
                    step.input = json.dumps(block.input, indent=2)[:4000]
                    await step.send()
                    steps[block.id] = step
        elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
            for block in msg.content:
                if isinstance(block, ToolResultBlock) and block.tool_use_id in steps:
                    out = block.content
                    if isinstance(out, list):
                        out = "\n".join(str(c.get("text", c)) for c in out if isinstance(c, dict))
                    step = steps[block.tool_use_id]
                    step.output = str(out)[:4000]
                    await step.update()
        elif isinstance(msg, ResultMessage):
            sessions.record(msg.session_id, cl.user_session.get("title") or "Untitled")
            cost = f"${msg.total_cost_usd:.2f}" if msg.total_cost_usd is not None else "n/a"
            await cl.Message(content=f"_Turn complete. Cost: {cost}. Activity log: "
                                     f"`{config.ACTIVITY_LOG}`_").send()


@cl.on_chat_end
async def end():
    task = cl.user_session.get("task")
    if task:
        task.cancel()
