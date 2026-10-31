# Virtual Auditor: build plan

The full design (architecture, identity, memory, controls, data, deployment) is in the Agent Design Specification doc. This file is the short working plan.

## 1. The idea in one line
One AI staff auditor that the team instructs through chat (browser now, Teams later), which reads auditee systems, performs test steps, and files draft work into Audit's own space for human review.

## 2. Architecture

```
 Channels            Agent core                      Tools (MCP)                 Data
 ----------          ----------------------          -------------------------   ----------------------
 Browser chat  --->  Claude Agent SDK                Audit tools (write)  -----> Audit workspace
 (Chainlit)          - model: Claude Opus 5.5        - engagement folders        (local now; SharePoint
                     - skills: audit procedures      - evidence + hash index      or OneDrive later)
 Teams bot     --->  - guardrails (hook)             - workpaper / issue / minutes
 (Phase 3)           - approvals (callback)          Built-in: read, search,     Auditee sources
                     - activity log                    python analysis, web  ---> (read only)
                                                     Atlassian (Phase 2) ------> Confluence / JIRA
```

Design choices and why:
- **Skills as plain English procedures.** Auditors own the method, not developers. A new audit area is a new markdown file.
- **Tools as MCP servers.** The same tools work with other models and frameworks later, so the bank is not locked in.
- **Two layers of control.** A hard rule layer the model cannot override, and a human approval layer set by the autonomy level. Both log to one activity file.
- **Memory attached to the engagement, not the person.** Anyone on the team can pick up where the agent left off.

## 3. Your design question: shared agent or one per person?
Recommendation: **one shared agent platform, with engagement-scoped memory and task-specific skill packs.**

| Option | Verdict |
|---|---|
| One personal agent per auditor | No. Knowledge stays with the person; the team cannot see what the agent did on an engagement. |
| Separate agents per task (fieldwork, risk assessment) | Later, only where they need different permissions or data. Same code, different skill pack and tool list. |
| One agent, many skills, memory per engagement | Yes for now. Build effort is the same as a single-user prototype. |

What "memory" means here:
- Engagement memory: the engagement folder, Evidence Index, Issue Log, minutes and activity log. Shared.
- Conversation memory: the current chat session.
- Personal memory: only preferences (format, tone). Small and optional.

In Teams this maps cleanly: one bot, added to each engagement's channel, with channel = engagement.

## 4. Autonomy: how hard is it to go fully autonomous later?
Technically it is one setting (`AUTONOMY=autonomous`). The hard rules and logging stay on. The real work is evidence that it is safe:
- Accuracy record: run each skill against seeded data with an answer key and track hit rate and false positives.
- Reviewer sign-off still required on every workpaper (IIA Standards: humans own conclusions).
- Model risk management sign-off for the use case, and IT controls (sandbox, identity, data loss prevention).

Suggested path: step_by_step (first runs on a new skill) > review_before_filing (default) > autonomous for low-risk, repeatable tests with a good record (for example continuous monitoring of leavers).

## 5. Meetings: where the value actually is
You are right that transcription alone adds little; Teams already does it. The value is connecting the meeting to the engagement:
- Turn agreed requests into a PBC tracker and check what has already arrived.
- Flag statements that change the test approach or contradict the evidence (the sample transcript has one).
- Answer questions during the meeting from the engagement workspace ("what did we find on leavers?").

| Phase | What | Who builds | Effort |
|---|---|---|---|
| Now | Feed the Teams transcript; agent writes minutes, PBC list, flags | You (built) | Done |
| 3 | Bot in the meeting chat / channel; HoIA @mentions it with a question | You + IT (Azure Bot registration, Teams app) | Days of IT time |
| 4 | Agent pulls transcripts automatically after meetings (Graph API) | IT (admin consent for transcript access) | Days |
| Not recommended | Bot that joins the call and listens or speaks live | Specialist vendor or heavy Azure media build | High cost, high risk for a bank |

Pitch to your boss: "It does not just take notes. It updates the engagement from the meeting and answers questions from our working papers."

## 6. Tools you asked about
- **Claude Code**: use it to change this code by describing what you want. Best value for a non-engineer.
- **Orca** (onorca.dev): a free, open-source desktop app for running several coding agents (Claude Code, Codex and others) in parallel. Useful when you are making several changes at once. Not needed to start; it is a tool for building the agent, not part of the agent.
- **Cursor**: an AI code editor. Optional alternative to VS Code + Claude Code.
- **GitHub**: private repo, so IT can review, fork and deploy.

## 7. Timeline (8 hours Sat and Sun, 2 to 3 hours on weekdays)

| When | Goal | Done when |
|---|---|---|
| Sat AM (3h) | Install, run tests, start the chat | Engagement folder created from chat |
| Sat PM (5h) | Run CB-AC-02 and CB-CM-01; compare with answer key; tune the skill | Both tests match the answer key |
| Sun AM (4h) | Replace folder template and workpaper layout with Wio's (sanitised) | Workpaper looks like a real Wio WP |
| Sun PM (4h) | Phase 2: free Atlassian Cloud site with fake pages and tickets; connect read-only | Agent reads a Confluence page and JIRA tickets |
| Weekdays wk1 | Remaining tests (CB-AC-01, CB-AC-03, CB-IP-01), minutes, question answering | All 5 tests and minutes run end to end |
| End of wk1 | Rehearse demo, record a backup video, one-page brief for boss | Ready to demo (about 7 to 8 Nov) |
| After demo | IT: Teams bot, Azure hosting, SSO, model choice | Phase 3 starts |

## 8. What IT will need to decide (handover list)
1. **Model hosting.** Options: Claude via Microsoft Foundry on the bank's Azure subscription (keeps this code; check data residency, as Foundry currently offers Global and US Data Zone deployments), or the bank's own models (Qwen, G42). For a self-hosted model, IT swaps the agent runtime for an open framework and keeps the tools (MCP), skills (markdown), guardrail rules and tests.
2. **Hosting the app.** Azure Container Apps or App Service, inside the bank network.
3. **Identity.** Entra ID sign-in; per-user identity passed to the activity log.
4. **Connectors.** Service accounts with read-only scopes for Confluence and JIRA; write access only to the Audit SharePoint library.
5. **Sandbox.** Run the analysis shell in an isolated container with no network.
6. **Logging.** Ship the activity log to the SIEM; retain per audit record-keeping policy.
7. **Teams.** Azure Bot registration and Teams app package. Chainlit's Teams adapter switches on with `TEAMS_APP_ID` / `TEAMS_APP_PASSWORD`.
8. **Model risk and DLP sign-off** for the use case.
