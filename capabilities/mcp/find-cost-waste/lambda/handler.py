"""find_cost_waste — one purposeful tool consolidating idle/oversized resource checks.

Gateway invokes this Lambda per the MCP Lambda target contract:
the tool name arrives in context.client_context.custom['bedrockAgentCoreToolName']
and the event is the tool's input arguments.
"""

import datetime
import json
import os

import boto3

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")

ALL_CHECKS = ["idle_nat_gateways", "unattached_ebs", "gp2_volumes", "overprovisioned_ec2"]

# Rough monthly price anchors (USD, ap-northeast-1) — findings state estimates, PRs refine via Pricing MCP
NAT_GW_MONTHLY = 0.062 * 730
GP2_PER_GB = 0.12
GP3_PER_GB = 0.096


def handler(event, context):
    args = event if isinstance(event, dict) else {}
    checks = args.get("checks") or ALL_CHECKS
    region = args.get("region") or REGION

    ec2 = boto3.client("ec2", region_name=region)
    cw = boto3.client("cloudwatch", region_name=region)

    findings = []

    if "idle_nat_gateways" in checks:
        findings += check_idle_nat_gateways(ec2, cw, region)
    if "unattached_ebs" in checks:
        findings += check_unattached_ebs(ec2, region)
    if "gp2_volumes" in checks:
        findings += check_gp2_volumes(ec2, region)
    if "overprovisioned_ec2" in checks:
        findings += check_overprovisioned_ec2(region)

    total = round(sum(f["estimated_monthly_waste_usd"] for f in findings), 2)
    return {
        "findings": findings,
        "summary": {
            "count": len(findings),
            "total_estimated_monthly_waste_usd": total,
            "checks_run": checks,
            "region": region,
        },
    }


def check_idle_nat_gateways(ec2, cw, region):
    out = []
    now = datetime.datetime.utcnow()
    for gw in ec2.describe_nat_gateways(
        Filters=[{"Name": "state", "Values": ["available"]}]
    ).get("NatGateways", []):
        stats = cw.get_metric_statistics(
            Namespace="AWS/NATGateway",
            MetricName="BytesOutToDestination",
            Dimensions=[{"Name": "NatGatewayId", "Value": gw["NatGatewayId"]}],
            StartTime=now - datetime.timedelta(days=7),
            EndTime=now,
            Period=86400,
            Statistics=["Sum"],
        )
        total_bytes = sum(p["Sum"] for p in stats.get("Datapoints", []))
        if total_bytes < 1_000_000:  # < 1 MB in a week = idle
            out.append(finding(
                resource_arn=f"arn:aws:ec2:{region}:{account_id()}:natgateway/{gw['NatGatewayId']}",
                resource_type="AWS::EC2::NatGateway",
                issue=f"Idle NAT gateway: {int(total_bytes)} bytes out in last 7 days",
                recommendation="Delete the NAT gateway (or replace with VPC endpoints if only reaching AWS APIs)",
                monthly=NAT_GW_MONTHLY,
                tags=gw.get("Tags", []),
            ))
    return out


def check_unattached_ebs(ec2, region):
    out = []
    for vol in ec2.describe_volumes(
        Filters=[{"Name": "status", "Values": ["available"]}]
    ).get("Volumes", []):
        gb = vol["Size"]
        rate = GP2_PER_GB if vol.get("VolumeType") == "gp2" else GP3_PER_GB
        out.append(finding(
            resource_arn=f"arn:aws:ec2:{region}:{account_id()}:volume/{vol['VolumeId']}",
            resource_type="AWS::EC2::Volume",
            issue=f"Unattached {vol.get('VolumeType')} volume, {gb} GiB",
            recommendation="Snapshot then delete, or delete if data is disposable",
            monthly=gb * rate,
            tags=vol.get("Tags", []),
        ))
    return out


def check_gp2_volumes(ec2, region):
    out = []
    for vol in ec2.describe_volumes(
        Filters=[{"Name": "volume-type", "Values": ["gp2"]}, {"Name": "status", "Values": ["in-use"]}]
    ).get("Volumes", []):
        gb = vol["Size"]
        out.append(finding(
            resource_arn=f"arn:aws:ec2:{region}:{account_id()}:volume/{vol['VolumeId']}",
            resource_type="AWS::EC2::Volume",
            issue=f"gp2 volume ({gb} GiB) — gp3 is ~20% cheaper at equal baseline performance",
            recommendation="Migrate volume type to gp3 in the owning IaC",
            monthly=gb * (GP2_PER_GB - GP3_PER_GB),
            tags=vol.get("Tags", []),
        ))
    return out


def check_overprovisioned_ec2(region):
    out = []
    try:
        co = boto3.client("compute-optimizer", region_name=region)
        recs = co.get_ec2_instance_recommendations(
            filters=[{"name": "Finding", "values": ["Overprovisioned"]}]
        )
        for r in recs.get("instanceRecommendations", []):
            opts = r.get("recommendationOptions", [])
            best = opts[0] if opts else {}
            savings = (
                best.get("savingsOpportunity", {})
                .get("estimatedMonthlySavings", {})
                .get("value", 0.0)
            )
            out.append(finding(
                resource_arn=r["instanceArn"],
                resource_type="AWS::EC2::Instance",
                issue=f"Over-provisioned: {r.get('currentInstanceType')} -> suggested {best.get('instanceType', 'n/a')}",
                recommendation="Change instance type in the owning IaC",
                monthly=savings,
                tags=[],
            ))
    except Exception as exc:  # Compute Optimizer may not be enrolled
        out.append({
            "resource_arn": None,
            "resource_type": "ComputeOptimizer",
            "issue": f"Compute Optimizer unavailable: {exc.__class__.__name__}",
            "recommendation": "Enroll the account in AWS Compute Optimizer for rightsizing findings",
            "estimated_monthly_waste_usd": 0.0,
            "tags": {},
        })
    return out


def finding(resource_arn, resource_type, issue, recommendation, monthly, tags):
    return {
        "resource_arn": resource_arn,
        "resource_type": resource_type,
        "issue": issue,
        "recommendation": recommendation,
        "estimated_monthly_waste_usd": round(monthly, 2),
        "tags": {t["Key"]: t["Value"] for t in tags} if isinstance(tags, list) else tags,
    }


_ACCOUNT_ID = None


def account_id():
    global _ACCOUNT_ID
    if _ACCOUNT_ID is None:
        _ACCOUNT_ID = boto3.client("sts").get_caller_identity()["Account"]
    return _ACCOUNT_ID
