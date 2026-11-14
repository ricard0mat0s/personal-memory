# Triage labels

| Label | Meaning |
| --- | --- |
| `needs-triage` | Scope and disposition still need evaluation. |
| `needs-info` | Required requirements, evidence, or a decision are missing. |
| `ready-for-agent` | An executable issue has approved scope, acceptance criteria, testing boundaries, and explicit blockers. |
| `ready-for-human` | The work needs human implementation or intervention. |
| `wontfix` | The owner has decided not to pursue the issue. |
| `spec` | A parent specification that organizes child issues; never eligible for implementation pickup. |

`ready-for-agent` records scope approval, not the absence of blockers or an
assignment. Selection checks those independently. An approved child can
carry the label while waiting for a blocker to close. Parent specs must
never carry it. Remove readiness when material scope changes need approval.

Claimed work remains assigned and open until its PR merges. A label cannot
authorize a merge. See [the workflow](development-workflow.md).
