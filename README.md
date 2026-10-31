# Virtual Auditor: prototype

An AI staff auditor you chat with in a browser. It reads auditee sources (read only), runs audit test steps from the audit program, files evidence, writes workpapers and draft issues, and minutes meetings, all inside the Audit workspace. It pauses for your approval before anything goes on the audit record, and logs every action.

**Synthetic data only.** Do not put bank data on a personal laptop.

## What is in the box

| Part | File | What it does |
|---|---|---|
| Chat UI | `app.py` | Browser chat (Chainlit). Approve/Reject buttons. Shows each tool step. |
| Agent | `agent/agent_factory.py` | Claude Opus 5.5 via the Claude Agent SDK, with tools, skills and connectors. |
| Controls | `agent/guardrails.py` | Hard rules (write only to the Audit workspace, auditee systems read only, shell deny-list), approval policy, activity log. |
| Audit tools | `agent/audit_tools.py` | Create engagement folders, file evidence (copy + SHA-256 + index), write workpaper (.docx), log issue (.xlsx), write minutes (.docx). |
| Memory | `agent/audit_tools.py` (notes), `agent/sessions.py` | Engagement notes the agent reads and updates; list of past chats to resume after a restart. |
| Audit procedures | `.claude/skills/*/SKILL.md` | Plain-English procedures the agent follows. Auditors can edit these without coding. |
| Persona and rules | `prompts/virtual_auditor.md` | Role, folders, how to work a test step, rules. |
| Folder standard | `templates/engagement_structure.json` | Your engagement folder structure. |
| Fake data | `sample_data/` | Core banking extracts, JIRA export, Confluence pages, audit program, Teams transcript. |
| Answer key | `scripts/ANSWER_KEY.md` | Planted exceptions. The agent is blocked from reading it. Use it to score the agent. |
| Tests | `tests/test_offline.py` | Checks controls and tools without an API key. |

Full design: the **Agent Design Specification** doc (shared separately; export it to Word or Markdown and save it as `docs/SPECIFICATION.md` when you hand over to IT). Diagrams: `docs/architecture.png`, `docs/roadmap.png`.

## Setup (about 1 to 2 hours, once)

### 1. Install the tools
- **Python 3.12**: https://www.python.org/downloads/ (Windows: tick "Add python.exe to PATH").
- **Git**: https://git-scm.com/downloads
- **VS Code**: https://code.visualstudio.com/
- Optional, to have an AI change the code for you: **Claude Code** (https://claude.com/claude-code) in the VS Code terminal, or Cursor. Use a personal account on a personal laptop; check bank policy before signing in with the enterprise account here.

### 2. Get a model API key
1. Go to https://console.anthropic.com, create an account, add a card.
2. **Settings > Limits**: set a monthly spend limit you are comfortable with.
3. **API keys > Create key**. Copy it.

Note: this is separate from your Claude Enterprise seat. Custom agents need an API key.

### 3. Get the code running
Open a terminal (Windows: PowerShell; Mac: Terminal) in the unzipped `virtual-auditor` folder.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac:
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env        # Mac: cp .env.example .env
```

Open `.env` in VS Code, paste your API key after `ANTHROPIC_API_KEY=`, and put your name after `AUDITOR_NAME=`.

```bash
python scripts/generate_sample_data.py   # rebuilds the fake data
python -m pytest -q                      # should say 9 passed
chainlit run app.py -w                   # opens http://localhost:8000
```

### 4. Put it on GitHub (private)
1. Create a **private** repo on https://github.com (no README).
2. In the folder:
```bash
git init
git add .
git commit -m "Virtual Auditor prototype"
git branch -M main
git remote add origin https://github.com/<you>/virtual-auditor.git
git push -u origin main
```
`.env` and `audit_workspace/` are excluded by `.gitignore`, so your key and outputs stay local.

## Demo script (15 minutes)
1. **Set up the engagement** (starter button). Show the folder tree it creates in `audit_workspace/`.
2. **Run test CB-AC-02 (leavers)**. Watch it read the program and policy, write a Python script, find exceptions, then ask for approval before filing evidence and the workpaper. Reject one action with a note to show the human control.
3. Open the workpaper (.docx), the Evidence Index (with SHA-256 hashes) and the Issue Log.
4. Ask a Head-of-IA style question in chat: "Which leavers logged in after they left, and what's our evidence?"
5. **Minute the kick-off meeting**. Show the PBC list and the flag that the deployment log format changed mid-year.
6. **Show memory**: stop the app (Ctrl+C), start it again, pick "Start a new session", click **Where are we?**. The agent rebuilds the status from `00_Admin/engagement_notes.md`. Or pick "Resume" to continue the earlier chat itself.
7. Open `audit_workspace/_agent_activity_log.jsonl`: every tool call, approval, rejection and block.
8. Compare results with `scripts/ANSWER_KEY.md`.

## Changing how it behaves
| You want to | Change |
|---|---|
| Different folder structure | `templates/engagement_structure.json` |
| Different test method or wording | `.claude/skills/corebanking-fieldwork/SKILL.md` |
| Workpaper layout | `write_workpaper` in `agent/audit_tools.py` |
| Fewer or more approval prompts | `AUTONOMY` in `.env` |
| Point at another folder (e.g. a synced Audit OneDrive) | `WORKSPACE_DIR` in `.env` |
| A new audit area | Copy a skill folder, rename, edit the procedure |

Tip: open the folder in VS Code, start Claude Code in the terminal, and ask it, for example: "Add a field 'Risk rating' to the workpaper header and update the test".

## Troubleshooting
- **Authentication error**: the API key in `.env` is missing or wrong. Restart `chainlit` after editing `.env`.
- **"Blocked: ..." in a step**: a guardrail stopped the action. This is expected; the reason is in the step and the activity log.
- **Approval prompt never appears**: refresh the browser tab; prompts time out after 15 minutes.
- **Cost**: each turn shows its cost. `MAX_BUDGET_USD` caps a chat session.

## Known limits (be upfront about these in the demo)
- The shell guard is a deny-list, not a sandbox. Production needs a container sandbox.
- No login: anyone who can reach localhost can use it. Production needs Entra ID sign-in.
- Chat transcripts for "Resume" are stored by the agent runtime on this laptop only. Production needs a shared store.
- Tested offline (controls, tools, memory, UI start-up). Agent quality must be checked on your machine against the answer key.
