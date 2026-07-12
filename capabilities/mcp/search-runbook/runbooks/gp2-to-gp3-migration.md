# gp2 to gp3 EBS Volume Migration

**Severity:** Low (cost optimization) · **Owner:** platform-team

## When this applies

`find_cost_waste` reports a gp2 EBS volume (check: `gp2_volumes`), or a gp2
volume type is found in IaC review. gp3 delivers the same baseline performance
(3,000 IOPS / 125 MB/s) at ~20% lower cost per GB and decouples IOPS and
throughput from volume size. Virtually every gp2 volume should be gp3.

## Approved procedure

**Fix it in the IaC, never in the console.** A console `ModifyVolume` drifts
from the source of truth and will be reverted by the next deploy.

1. **Locate the owning IaC** for the flagged volume (repo + file). For blueprint
   demo resources this is `scenarios/demo-workload/template.yaml` in
   `lillyjohns/sample-aws-devops-agent-governance-blueprint`.
2. **Open a pull request** with the `propose_fix_pr` tool:
   - `file_path`: the IaC file containing the gp2 volume
   - `change_description`: `ebs-gp2-to-gp3`
   - `finding`: pass the finding JSON from `find_cost_waste` so reviewers see
     the evidence and estimated savings
3. **Do not merge the PR yourself.** The PR is the approval gate — a human
   owner reviews and merges. The deployment pipeline applies the change.

## Verification (post-merge)

- `aws ec2 describe-volumes --volume-ids <id> --query 'Volumes[0].VolumeType'`
  returns `gp3`
- Re-run `find_cost_waste` with `checks: ["gp2_volumes"]` — the finding is gone

## Notes

- Volumes >1 TB or with provisioned IOPS bursts above gp3 baseline need an IOPS/
  throughput review before migration — flag these in the PR body instead of
  assuming defaults.
- Migration is online and non-disruptive (elastic volumes); no detach needed.
