---
name: corebanking-fieldwork
description: Procedure for performing a Core Banking System (CBS) audit test step end to end - read the audit program, analyse the data, file evidence, write the workpaper and draft issues. Use whenever asked to perform, run or re-perform a test from the audit program.
---

# Core banking fieldwork procedure

## 1. Prepare
- Confirm the engagement exists (mcp__audit__list_engagements). If not, ask whether to create it.
- Read the engagement notes (mcp__audit__read_engagement_notes). Check whether this test was already done, any scoping decisions, and open PBC items that affect it.
- Read the audit program: `sample_data/audit_program/Core_Banking_Audit_Program_2026.xlsx` (use Python/openpyxl or pandas). Find the row for the test ID.
- Read the criteria document named in the Criteria column (Confluence export) and quote the exact clause in your workpaper.

## 2. Population and completeness
- Load each source file named in the Source data column with pandas.
- Record: file name, row count, date range covered, and any blanks or duplicates in key fields.
- If the population looks incomplete for the audit period, say so and raise an information request. Do not stop the test unless the gap makes it meaningless.

## 3. Analysis
- Write the analysis as a Python script in the engagement's `_agent_scratch` folder (for example `_agent_scratch/CB-AC-02_analysis.py`), then run it with `python <script>`.
- The script must print the counts and write an exceptions file (`_agent_scratch/CB-AC-02_exceptions.csv`).
- Business days are Monday to Friday (UAE). Use `numpy.busday_count`. State your counting convention in the workpaper.
- Test 100% of the population when the program says so. If sampling, state the method and seed.

## 4. Evaluate
- For each exception record: identifier, what the policy required, what happened, and the size of the gap.
- Note observations outside the test scope separately (for example a generic account with no owner). Do not mix them into the test result.
- Conclusion options: "Effective", "Partially effective", "Ineffective", "Unable to conclude". Explain the choice in one or two sentences.

## 5. Document (approval required at this stage)
1. mcp__audit__file_evidence for each source file used, the script, and the exceptions file.
2. mcp__audit__write_workpaper with the evidence refs returned in step 1. Follow the workpaper-standards skill.
3. mcp__audit__log_issue for each distinct finding (group exceptions that share a root cause into one issue).

## 6. Update the engagement notes
- Tests: "<test ID>: <conclusion>. <n> exceptions. WP <ref>. Evidence <refs>."
- Open PBC items / Open questions: anything you need from the auditee or auditor.
- Status: replace with the current two-line status.

## 7. Report back in chat
- Two or three sentence summary: population, exceptions, conclusion.
- A short table of exceptions.
- What still needs the auditor's judgement or auditee confirmation.
