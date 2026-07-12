# Cost Anomaly Response

**Severity:** high · **Owner:** platform-team · **Last reviewed:** 2026-06

Use this runbook when a cost anomaly alert fires (AWS Cost Anomaly Detection,
budget alarm, or a spend spike reported by finance).

## Triage (first 15 minutes)

1. **Scope the anomaly.** Identify the service, region, and linked account driving
   the spike. Use Cost Explorer grouped by SERVICE, then by USAGE_TYPE:
   - `generate_cost_report` with `group_by: SERVICE` for the last 7 days
   - Compare against the previous 7-day window
2. **Rule out expected causes.** Check for: recent deployments, scheduled batch
   jobs, marketing events, new environments spun up by teams.
3. **Run the waste scan.** `find_cost_waste` with all checks — idle NAT gateways,
   unattached EBS volumes, gp2 volumes, and over-provisioned EC2 are the most
   common self-inflicted causes.

## Common causes and fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| EC2-Other spike | NAT gateway data processing | See "Idle NAT Gateway" runbook; consider VPC endpoints |
| EBS cost creep | Unattached volumes accumulating | Snapshot then delete; add lifecycle policy |
| Sudden EC2 jump | Instances left running from a test | Stop/terminate; enforce auto-stop tags |
| Data transfer spike | Cross-AZ or cross-region traffic | Review architecture; co-locate chatty services |

## Remediation rules

- **Never delete data-bearing resources directly.** Snapshot first, delete after
  7 days of no complaints.
- All fixes go through IaC (CDK/Terraform) as a pull request — no console
  changes. Include the estimated monthly savings in the PR description.
- If the anomaly exceeds $500/day, page the on-call engineer and open an
  incident; do not wait for the PR cycle.

## Escalation

- Anomaly unexplained after triage → escalate to the owning team via the
  resource's `Team` tag.
- No `Team` tag → escalate to platform-team and file a tagging-compliance issue.
