"""Offline checks: no API key or internet needed.  Run:  python -m pytest -q"""
import os
import tempfile
from pathlib import Path

import pytest

# Use a throwaway workspace so tests never touch your real one.
_tmp = tempfile.mkdtemp()
os.environ["WORKSPACE_DIR"] = _tmp

from agent import audit_tools, config, guardrails  # noqa: E402
from agent.agent_factory import build_options  # noqa: E402

SRC = config.SOURCES_DIR / "auditee_sources" / "core_banking_extracts"


def test_blocks_write_outside_workspace():
    assert guardrails.check_hard_rules("Write", {"file_path": str(SRC / "x.csv")})
    assert guardrails.check_hard_rules("Write", {"file_path": str(Path(_tmp) / "ok.md")}) is None


def test_blocks_reads_outside_approved_folders():
    assert guardrails.check_hard_rules("Read", {"file_path": str(Path.home() / ".ssh" / "id_rsa")})
    assert guardrails.check_hard_rules("Read", {"file_path": str(config.ROOT / "scripts" / "ANSWER_KEY.md")})
    assert guardrails.check_hard_rules("Grep", {"pattern": "x"})  # no path = project root = blocked
    assert guardrails.check_hard_rules("Read", {"file_path": str(SRC / "hr_leavers_jan_sep_2026.csv")}) is None


def test_blocks_dangerous_shell_and_connector_writes():
    assert guardrails.check_hard_rules("Bash", {"command": "rm -rf sample_data"})
    assert guardrails.check_hard_rules("Bash", {"command": "curl http://evil"})
    assert guardrails.check_hard_rules("Bash", {"command": "python analysis.py"}) is None
    assert guardrails.check_hard_rules("mcp__atlassian__jira_create_issue", {})
    assert guardrails.check_hard_rules("mcp__atlassian__jira_search", {}) is None


def test_approval_policy():
    config.AUTONOMY = "review_before_filing"
    assert guardrails.needs_approval("mcp__audit__write_workpaper", {})
    assert not guardrails.needs_approval("Bash", {"command": "python x.py"})
    # Look-only commands are housekeeping: no approval.
    assert not guardrails.needs_approval("Bash", {"command": "ls"})
    assert not guardrails.needs_approval("Bash", {"command": "dir audit_workspace"})
    # Anything else, chained or redirected, still asks.
    assert guardrails.needs_approval("Bash", {"command": "ls > out.txt"})
    assert guardrails.needs_approval("Bash", {"command": "ls; node x.js"})
    assert guardrails.needs_approval("Bash", {"command": "cat $(echo x)"})
    assert guardrails.needs_approval("Bash", {"command": "node x.js"})
    config.AUTONOMY = "autonomous"
    assert not guardrails.needs_approval("mcp__audit__write_workpaper", {})
    config.AUTONOMY = "review_before_filing"


def test_engagement_evidence_workpaper_issue_minutes():
    out = audit_tools.create_engagement("CBS-2026-01", "Core Banking System Audit", "CBS", "Jan-Sep 2026", "Suzanne")
    assert "created" in out
    src = SRC / "hr_leavers_jan_sep_2026.csv"
    before = src.read_bytes()
    ev = audit_tools.file_evidence("CBS-2026-01", "CB-AC-02", str(src), "HR leavers list")
    assert "EV-CB_AC_02-01" in ev and src.read_bytes() == before  # original untouched
    wp = audit_tools.write_workpaper(
        "CBS-2026-01", "WP-AC-02", "CB-AC-02", "Leavers disabled in 1 business day", "Test leavers",
        "16 leavers", "100%", ["Matched leavers"], "3 exceptions",
        [{"user_id": "abc", "issue": "still active"}], "Ineffective", ["EV-CB_AC_02-01"])
    assert Path(wp.split(": ", 1)[1]).exists()
    assert "added" in audit_tools.log_issue("CBS-2026-01", "ISS-01", "Leavers", "c", "cr", "ca", "e",
                                            "High", "r", "WP-AC-02")
    mn = audit_tools.write_minutes("CBS-2026-01", "Kick-off", "2026-10-05", ["Suzanne"], "s",
                                   [{"topic": "Scope", "points": ["CBS"]}], ["d"],
                                   [{"action": "a", "owner": "o", "due": "9 Oct"}], ["HR list"])
    assert Path(mn.split(": ", 1)[1]).exists()


def test_evidence_must_come_from_approved_folders(tmp_path):
    audit_tools.create_engagement("CBS-2026-01", "Core Banking System Audit")
    stray = tmp_path / "stray.txt"
    stray.write_text("x")
    with pytest.raises(ValueError):
        audit_tools.file_evidence("CBS-2026-01", "T1", str(stray), "stray")


def test_options_build():
    async def approver(tool, data):
        return True, ""
    opts = build_options(approver)
    assert opts.model == config.MODEL and "audit" in opts.mcp_servers


def test_engagement_notes_memory():
    from agent import audit_tools
    audit_tools.create_engagement("CBS-2026-01", "Core Banking System Audit")
    notes = audit_tools.read_engagement_notes("CBS-2026-01")
    assert "## Open PBC items" in notes
    audit_tools.update_engagement_notes("CBS-2026-01", "Tests", "CB-AC-02: Ineffective. 3 exceptions.")
    audit_tools.update_engagement_notes("CBS-2026-01", "Tests", "CB-CM-01: Ineffective. 3 exceptions.")
    audit_tools.update_engagement_notes("CBS-2026-01", "Status", "Fieldwork in progress.", mode="replace")
    audit_tools.update_engagement_notes("CBS-2026-01", "Status", "Fieldwork complete.", mode="replace")
    notes = audit_tools.read_engagement_notes("CBS-2026-01")
    tests = notes.split("## Tests\n")[1].split("\n## ")[0]
    status = notes.split("## Status\n")[1].split("\n## ")[0]
    assert "CB-AC-02" in tests and "CB-CM-01" in tests
    assert "Fieldwork complete." in status and "in progress" not in status
    with pytest.raises(ValueError):
        audit_tools.update_engagement_notes("CBS-2026-01", "Gossip", "x")


def test_session_registry_and_user_in_log():
    from agent import sessions
    sessions.record("sess-1", "Run CB-AC-02")
    sessions.record("sess-2", "Minutes")
    sessions.record("sess-1", "Run CB-AC-02")  # bump, no duplicate
    recent = sessions.recent()
    assert [s["session_id"] for s in recent][0] == "sess-1" and len(recent) == 2
    guardrails.log_event({"type": "test"})
    last = config.ACTIVITY_LOG.read_text().strip().splitlines()[-1]
    assert '"user"' in last and '"agent": "virtual-auditor"' in last


def test_approval_cards_are_plain_english():
    from agent.approval_text import approval_card
    wp = approval_card("mcp__audit__write_workpaper", {
        "wp_ref": "WP-AC-02", "test_id": "CB-AC-02", "conclusion": "Ineffective",
        "results": "3 of 16 leavers not disabled on time",
        "exceptions": [{"user_id": "u1", "issue": "login | after exit"}] * 12,
        "evidence_refs": ["EV-CB_AC_02-01"]})
    assert "Workpaper ready for review" in wp and "Ineffective" in wp
    assert "Exceptions:** 12" in wp and "2 more in the workpaper" in wp
    assert "```" not in wp and "{" not in wp  # no code or JSON on the card
    iss = approval_card("mcp__audit__log_issue", {"issue_id": "ISS-01", "title": "Leavers", "rating": "High"})
    assert "Draft issue to log" in iss and "**Rating:** High" in iss
    ev = approval_card("mcp__audit__file_evidence", {"test_id": "CB-AC-02",
                       "source_path": "C:/x/hr_leavers.csv", "description": "HR list"})
    assert "hr_leavers.csv" in ev and "C:/x" not in ev
    assert "System command" in approval_card("Bash", {"command": "node x.js"})
