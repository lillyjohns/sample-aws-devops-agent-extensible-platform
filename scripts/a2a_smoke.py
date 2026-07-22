#!/usr/bin/env python3
"""Direct A2A smoke test against the remediation agent runtime.

Speaks the A2A protocol (JSON-RPC ``message/send``) to the AgentCore Runtime
data plane with SigV4 auth — the same wire format DevOps Agent uses for a
``remoteagentsigv4`` service. Proves the agent card + message handling work
end-to-end without going through an orchestrator.

Usage:
    python3 scripts/a2a_smoke.py [--runtime-arn ARN] [--message TEXT]

Credentials come from the ambient AWS environment/config.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
import uuid

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


def _signed(url, method="GET", body=None, region="ap-northeast-1", session_id=None):
    creds = boto3.Session().get_credentials()
    headers = {"Content-Type": "application/json"} if body else {}
    if session_id:
        headers["X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"] = session_id
    req = AWSRequest(method=method, url=url, data=body, headers=headers)
    SigV4Auth(creds, "bedrock-agentcore", region).add_auth(req)
    http_req = urllib.request.Request(url, data=body, headers=dict(req.headers), method=method)
    with urllib.request.urlopen(http_req, timeout=90) as resp:
        return resp.status, json.loads(resp.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--runtime-arn",
        default="arn:aws:bedrock-agentcore:ap-northeast-1:813180854139:runtime/remediation_pr_agent-vOJXm7DNfe",
    )
    ap.add_argument("--region", default="ap-northeast-1")
    ap.add_argument(
        "--message",
        default='Dry run: propose fix for scenarios/demo-workload/template.yaml with finding '
        '{"resource": "vol-demo", "issue": "gp2 EBS volume", "change": "ebs-gp2-to-gp3"}',
    )
    args = ap.parse_args()

    esc = urllib.parse.quote(args.runtime_arn, safe="")
    base = f"https://bedrock-agentcore.{args.region}.amazonaws.com/runtimes/{esc}/invocations"

    # 1. A2A discovery: fetch the agent card (same URL DevOps Agent registers).
    status, card = _signed(f"{base}/.well-known/agent-card.json", region=args.region)
    print(f"--- agent card ({status}) ---")
    print(json.dumps({k: card[k] for k in ("name", "description", "url", "skills") if k in card}, indent=2))

    # 2. A2A message/send (JSON-RPC 2.0) to the endpoint from the card.
    rpc = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": args.message}],
                "messageId": uuid.uuid4().hex,
            }
        },
    }
    session_id = uuid.uuid4().hex + uuid.uuid4().hex[:8]  # >= 33 chars required
    status, reply = _signed(
        base, method="POST", body=json.dumps(rpc).encode(), region=args.region, session_id=session_id
    )
    print(f"--- message/send response ({status}) ---")
    print(json.dumps(reply, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
