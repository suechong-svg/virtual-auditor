---
name: workpaper-standards
description: House style and quality bar for audit workpapers and issue write-ups. Use before writing any workpaper, issue or audit finding.
---

# Workpaper standards

A reviewer who did not do the work must be able to re-perform it from the workpaper alone.

## Every workpaper states
- Control description and test objective, in the auditee's terms.
- Criteria: the exact policy clause, with document name and version.
- Population: source system or file, extraction date, row count, period covered, completeness checks.
- Approach: full population or sample (method, size, seed), and the business-day convention.
- Procedures: numbered, specific, past tense ("Matched 16 HR leavers to the CBS user list on employee_id").
- Results: numbers first, then the exceptions table.
- Conclusion: one of Effective / Partially effective / Ineffective / Unable to conclude, with a one-line reason.
- Evidence refs (EV-...) for every source and analysis file.

## Issues use the 5 Cs
- Condition: what we found, with counts and record IDs.
- Criteria: the clause breached.
- Cause: "To be confirmed with auditee" unless evidence shows the cause.
- Effect: the risk in business terms (for example, an ex-employee could post transactions).
- Recommendation: specific, actionable, owner-agnostic.

## Rating guide (prototype)
- High: control failure that allowed, or could directly allow, unauthorised transactions or customer impact (for example a leaver login after termination, maker equals checker on rates).
- Medium: control operated late or incompletely with no evidence of misuse.
- Low: documentation or housekeeping gap.

## Style
- Plain, active British English. No em-dashes. No adjectives like "robust" or "significant" without a number behind them.
- Never state a cause, owner or date that is not in the evidence.
