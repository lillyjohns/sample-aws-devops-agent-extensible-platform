# Unattached EBS Volume Cleanup

**Severity:** low · **Owner:** platform-team · **Last reviewed:** 2026-06

Unattached (`available`) EBS volumes accumulate from terminated instances whose
volumes had `DeleteOnTermination: false`, from manual detachments, and from
abandoned experiments. gp3 costs $0.096/GB-month in ap-northeast-1 — a forgotten
500 GB volume is ~$48/month for nothing.

## Identify

1. Run `find_cost_waste` with `checks: [unattached_ebs]`, or list volumes in
   state `available` directly.
2. For each volume, gather: size, type, creation time, tags, and the last
   attachment (CloudTrail `DetachVolume` events if recent).

## Classify before deleting

| Signal | Action |
|---|---|
| Tagged `Keep`, `Backup`, or attached < 30 days ago | Leave; ask the owner |
| Has a `Team`/`Project` tag | Notify the team, 7-day grace period |
| Untagged, older than 90 days | Snapshot then delete |
| Created by an autoscaling group that no longer exists | Snapshot then delete |

## Execute

1. **Snapshot first, always:** `aws ec2 create-snapshot --volume-id <id>
   --description "pre-cleanup <date>"`. Tag the snapshot with the original
   volume ID and a `DeleteAfter` date 30 days out.
2. Delete the volume after the snapshot completes.
3. If volumes are IaC-managed, fix the source: set `DeleteOnTermination: true`
   or add explicit retention, and open a PR rather than deleting by hand.
4. Record the monthly savings (size × $0.096 for gp3, × $0.12 for gp2).

## Prevention

- Enforce `DeleteOnTermination: true` for non-data volumes in launch templates.
- Add a recurring monthly waste scan (the alert-to-investigation scenario in
  this repo automates exactly this).
