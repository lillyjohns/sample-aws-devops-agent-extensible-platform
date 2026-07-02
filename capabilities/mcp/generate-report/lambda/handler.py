"""generate_cost_report — CSV report from Cost Explorer, uploaded to S3, presigned URL back.

Behind the Gateway so every client benefits: chat, IDE, scheduled agents.
CSV (openpyxl-free) keeps the Lambda dependency-less; xlsx upgrade lands in M2.
"""

import csv
import datetime
import io
import os

import boto3

BUCKET = os.environ["ARTIFACT_BUCKET"]


def handler(event, context):
    args = event if isinstance(event, dict) else {}
    days = min(int(args.get("days") or 30), 365)
    group_by = args.get("group_by") or "SERVICE"

    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)

    ce = boto3.client("ce", region_name="us-east-1")
    resp = ce.get_cost_and_usage(
        TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": group_by}],
    )

    totals = {}
    for day in resp.get("ResultsByTime", []):
        for group in day.get("Groups", []):
            key = group["Keys"][0]
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            totals[key] = totals.get(key, 0.0) + amount

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([group_by.title(), f"Cost last {days} days (USD)"])
    for key, amount in sorted(totals.items(), key=lambda kv: -kv[1]):
        if amount >= 0.005:
            writer.writerow([key, f"{amount:.2f}"])
    writer.writerow(["TOTAL", f"{sum(totals.values()):.2f}"])

    key = f"reports/cost-report-{end.isoformat()}-{days}d-{group_by.lower()}.csv"
    s3 = boto3.client("s3")
    s3.put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue().encode(), ContentType="text/csv")
    url = s3.generate_presigned_url(
        "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=3600
    )

    return {
        "report_url": url,
        "expires_in_seconds": 3600,
        "rows": len(totals),
        "total_usd": round(sum(totals.values()), 2),
        "period": {"start": start.isoformat(), "end": end.isoformat()},
    }
