# Idle NAT Gateway Remediation

**Severity:** medium · **Owner:** platform-team · **Last reviewed:** 2026-06

A NAT gateway costs ~$45/month (ap-northeast-1) even when it processes zero
bytes. This runbook covers confirming a NAT gateway is idle and removing it
safely.

## Confirm it is actually idle

1. Check `BytesOutToDestination` over **14 days**, not 7 — some workloads are
   bi-weekly. Less than 1 MB total is idle; less than 1 GB is a candidate for
   review with the owning team.
2. Check the route tables: `aws ec2 describe-route-tables` filtered on the NAT
   gateway ID. If private subnets still route `0.0.0.0/0` through it, find out
   what lives in those subnets before touching anything.
3. Check for periodic workloads (monthly batch jobs, disaster-recovery drills)
   with the owning team via the `Team` tag.

## Decide the fix

- **Nothing needs egress** → delete the NAT gateway and the routes that point
  at it.
- **Only AWS API traffic** (S3, DynamoDB, ECR, CloudWatch) → replace with VPC
  gateway/interface endpoints; delete the NAT gateway afterwards. Endpoints for
  S3/DynamoDB are free.
- **Rare egress** (e.g. monthly job) → discuss with the owner: either keep it,
  or move the job to a public-subnet task with a security-group lockdown.

## Execute (through IaC only)

1. Locate the owning IaC block (CDK construct or Terraform resource) — search
   the repo for the NAT gateway's subnet or the `natGateways:` setting.
2. In CDK: set `natGateways: 0` on the VPC (or remove the `NatProvider`), and
   remove dependent routes. In Terraform: remove the `aws_nat_gateway` and
   `aws_route` resources.
3. Open a PR titled `cost: remove idle NAT gateway <id>` including:
   - the 14-day traffic evidence,
   - estimated monthly savings (~$45/month per gateway),
   - rollback note (NAT gateway can be recreated in ~2 minutes if needed).
4. Merge only after the owning team approves. Deleting is reversible but causes
   an egress outage for anything silently depending on it.

## Rollback

Recreate via IaC revert. Allocation of a new Elastic IP is automatic; expect
~2 minutes of provisioning. Update any hardcoded EIP allowlists downstream.
