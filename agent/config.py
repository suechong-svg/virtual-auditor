"""Central settings. Change paths and autonomy here or in .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _path(env_name: str, default: Path) -> Path:
    value = os.getenv(env_name)
    return Path(value).expanduser().resolve() if value else default.resolve()


# Where auditee material lives. The agent may READ here but never write.
SOURCES_DIR = _path("SOURCES_DIR", ROOT / "sample_data")

# Internal Audit's own space. The ONLY place the agent may write.
# Later: point this at a OneDrive/SharePoint-synced Audit folder.
WORKSPACE_DIR = _path("WORKSPACE_DIR", ROOT / "audit_workspace")

MODEL = os.getenv("MODEL", "claude-opus-5-5")

# How much the agent may do before a human approves:
#   step_by_step        every write or command needs approval
#   review_before_filing analysis runs freely; filing workpapers, evidence,
#                        issues and minutes needs approval   (default)
#   autonomous          no approvals; guardrails and logging still apply
AUTONOMY = os.getenv("AUTONOMY", "review_before_filing")

# Cost ceiling per chat session, in USD. The run stops if exceeded.
MAX_BUDGET_USD = float(os.getenv("MAX_BUDGET_USD", "5"))

# Who is instructing the agent. Prototype: set in .env. Production: from Entra ID sign-in.
AUDITOR_NAME = os.getenv("AUDITOR_NAME", "Auditor")

ACTIVITY_LOG = WORKSPACE_DIR / "_agent_activity_log.jsonl"
SESSIONS_FILE = WORKSPACE_DIR / "_agent_sessions.json"
ENGAGEMENT_TEMPLATE = ROOT / "templates" / "engagement_structure.json"

WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
