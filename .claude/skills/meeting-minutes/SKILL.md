---
name: meeting-minutes
description: Turn a Teams meeting transcript (.vtt, .docx or text) into audit meeting minutes, actions and evidence requests, and cross-check what was said against the engagement's evidence. Use when given a transcript or asked to minute a meeting.
---

# Meeting minutes procedure

The value is not the transcription (Teams already does that). The value is linking what was said to the engagement.

1. Read the transcript. Identify attendees and roles from the speaker labels. Do not add attendees who did not speak unless the auditor lists them.
2. Write minutes with: summary (3 to 5 lines), discussion by topic, decisions, actions (action, owner, due date as stated), and evidence requests (PBC) the auditee agreed to.
3. Cross-check against the engagement and sources:
   - For each PBC item, check whether the file already exists in the sources or the evidence folder. Mark it "Received" or "Outstanding".
   - Flag any statement that the evidence contradicts or that changes the test approach (for example "the deployment log format changed in July" means a completeness check across both formats is needed). Cite the file.
4. Call mcp__audit__write_minutes (approval required).
5. Update the engagement notes: Open PBC items (one line per request with owner and due date), Decisions, Open questions.
6. In chat, list: outstanding PBC items with owners and due dates, and statements that need follow-up.
7. Use only what the transcript says for owners and dates. If a due date is vague ("this week"), keep the auditee's words.
