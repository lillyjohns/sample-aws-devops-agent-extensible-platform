# Design Deep-Dive

This document contains the full design rationale for the platform. For the overview, quick start, and demo flow, see the [README](../README.md).

## Table of Contents

- [Design principles](#design-principles)
- [The Gateway as a contract](#the-gateway-as-a-contract)
- [Manifest schema](#manifest-schema)
- [Contract rules](#contract-rules)
- [Gateway routing vs direct MCP registration](#gateway-routing-vs-direct-mcp-registration)
- [MCP target selection](#mcp-target-selection)
- [Entry points and IDE wiring](#entry-points-and-ide-wiring)
- [Decision log](#decision-log)
- [Terraform notes](#terraform-notes)
- [Open items](#open-items)

## Design principles

1. **Gateway is for tools. DevOps Agent is for judgment.**
   Dumb capabilities (Cost Explorer queries, report generation, IaC lookups) live behind a single AgentCore Gateway. The reasoning loop — what to investigate, what to recommend, when to delegate — stays in DevOps Agent. Every client (agents *and* humans) is a consumer of the same Gateway.

2. **Designed to shrink.**
   Every custom component declares its **retirement condition** — the native DevOps Agent capability that makes it obsolete. Decommissioning is a config change (`enabled: false` or deregistering an A2A connection), never a re-architecture. Custom glue should never become legacy debt.

3. **Read-only by default. Writes are isolated.**
   All Gateway targets are read-only (enforced at synth time). The only write path — GitHub PRs — lives in a dedicated agent with its own credentials, and every write lands as a *proposal* (a PR) gated by human review.

## The Gateway as a contract

The Gateway endpoint is the **stable contract** between DevOps Agent and your tooling. DevOps Agent is registered to the Gateway **once**; everything behind it is pluggable.

```
DevOps Agent ──(registered once: AWS::DevOpsAgent::Service, never changes)──► AgentCore Gateway
                                                                                │
                                              targets added/removed/upgraded freely
                                              (no DevOps Agent change, no console click)
```

1. **One-time binding (CDK):** a single `AWS::DevOpsAgent::Service` resource (`ServiceType: mcpserversigv4`) points DevOps Agent at the Gateway URL. This resource never changes after first deploy.
2. **Pluggable targets — config-driven:** each MCP is a folder + manifest under `mcp-targets/`. CDK scans the directory and synthesizes one Gateway target per manifest. **Adding an MCP = drop a folder, `cdk deploy`.**
3. **Discovery is handled by the platform:** the Gateway's semantic tool search means DevOps Agent (and every other client) finds new tools automatically. The tool *list* is not part of the contract — only the endpoint + auth are.

## Manifest schema

```yaml
# mcp-targets/find-cost-waste/manifest.yaml
name: find-cost-waste
description: Detect idle/oversized resources (Compute Optimizer, Trusted Advisor, heuristics)
type: lambda                # lambda | awslabs-reuse | mcp-passthrough
enabled: true
handler: lambda/handler.py  # for type: lambda
# ref: <container/package ref>   # for type: awslabs-reuse
# endpoint + auth               # for type: mcp-passthrough
retirement: >               # the "designed to shrink" clause
  Decommission if AWS DevOps Agent gains native idle-resource detection.
tools:
  - name: find_cost_waste
    version: 1              # breaking change ⇒ new tool name (find_cost_waste_v2)
permissions:                # least-privilege IAM synthesized per target
  - compute-optimizer:Get*
  - trustedadvisor:Describe*
  - ec2:Describe*
readOnly: true              # write tools are rejected on the shared Gateway
```

## Contract rules

- **Tool names + schemas are the API surface.** Additive changes are fine; breaking changes require a versioned tool name (`find_cost_waste_v2`).
- **Every Gateway target is read-only by default.** `readOnly: true` is enforced at synth time — write capabilities never join the shared Gateway.
- **Per-target least-privilege IAM**, declared in the manifest and synthesized by CDK.
- **Every target declares a retirement condition** in its manifest — the native capability that would make it obsolete.

## Gateway routing vs direct MCP registration

DevOps Agent *can* register MCP servers directly — but per-MCP registration scales badly:

| | Direct registration | Gateway as contract |
|---|---|---|
| Adding an MCP | Touches DevOps Agent config every time (N `DevOpsAgent::Service` resources) | Drop a folder, `cdk deploy` — DevOps Agent untouched |
| Other clients (Kiro/Claude, PR agent, future agents) | Get nothing — benefits DevOps Agent only | Get every new tool for free |
| Auth, throttling, audit | Per-MCP, scattered | One place |
| OAuth-backed services | `AWS::DevOpsAgent::Service` **cannot** register them (console-only) | Gateway absorbs whatever auth each backend needs, presents uniform SigV4 upstream |

## MCP target selection

Selection criteria for what belongs behind the Gateway:
(a) not already native to DevOps Agent, (b) needed by multiple clients, (c) safe to expose to *every* Gateway client.

| MCP target | Type | Purpose | Retirement condition |
|---|---|---|---|
| Cost Explorer MCP | awslabs, reused | Spend data, anomalies, forecasts | — (upstream-maintained) |
| AWS Pricing MCP | awslabs, reused | Price lookups so PRs state *"saves ~$47/month"* | — (upstream-maintained) |
| `find_cost_waste` | custom Lambda | One purposeful tool wrapping Compute Optimizer + Trusted Advisor cost checks + idle-resource heuristics (NAT GW bytes, unattached EBS, gp2 inventory) | Native idle-resource detection |
| `locate_iac_source` | custom Lambda | **Resource ARN → owning IaC block** (tags + Resource Explorer + scoped read-only repo search). The hardest problem in the sample, promoted to a first-class tool | Native IaC state awareness |
| `generate_cost_report` | custom Lambda | xlsx (openpyxl) → S3 → presigned URL, available to every client | Native artifact generation |
| *(optional)* DevOps Agent MCP endpoint | passthrough | `start_investigation` / `get_investigation_status` for the single-endpoint IDE story | — |

**Deliberately NOT behind the Gateway:**

- **CloudWatch / CloudTrail / logs MCPs** — DevOps Agent investigates with these natively; duplicating them adds cost and tool-selection confusion for zero new capability.
- **GitHub write access** — write credentials on a shared Gateway would let any connected IDE client silently open PRs. Write stays a *private* capability of the Remediation-PR Agent (own runtime, own secret). Least privilege by architecture; the Gateway exposes read-only `locate_iac_source` instead.

**Curated tools over raw API mirrors:** fewer, purposeful tools (`find_cost_waste` vs three raw APIs) improve LLM tool selection. Reusing awslabs MCP servers (Cost Explorer, Pricing) shows composition over reinvention.

## Entry points and IDE wiring

Kiro/Claude → Gateway alone gets **raw tools only** — no DevOps Agent judgment. Two documented wiring options:

- **Option 1 (simplest):** the IDE connects to *both* the Gateway (tools) and DevOps Agent's own headless MCP endpoint (judgment) — e.g. the Kiro power for AWS DevOps Agent.
- **Option 2 (single endpoint):** register DevOps Agent's MCP endpoint as one more Gateway target (`start_investigation`, `get_investigation_status`) so the Gateway is the only connection the IDE needs. The *client's* LLM decides when to offload to DevOps Agent.

## Decision log

| Decision | Alternatives considered | Why |
|---|---|---|
| DevOps Agent as orchestrator (console = primary UX) | Custom frontend + Gateway fronting everything (Thomson Reuters pattern); putting DevOps Agent *behind* the Gateway | A custom frontend demotes DevOps Agent to just-another-tool and forces rebuilding Agent Spaces, timelines, dashboards, incident-skip, memories. TR's pattern fits a multi-team enterprise hub, not a single-account sample. It also muddies the decommission story — the sample only reads cleanly if DevOps Agent is the brain. |
| A2A sub-agent for PR work (not EventBridge handoff) | Structured recommendation events on EventBridge | A2A makes decommissioning literally "remove one connection". EventBridge handoff would work but is a weaker upgrade story. |
| Excel reporting as a Gateway MCP tool | Client-side generation in Claude cowork | Behind the Gateway, *every* client gets it (scheduled agents included); client-side means reports only exist when a human with Claude asks. |
| Curated MCP tools over raw API mirrors | One MCP target per AWS API | Fewer, purposeful tools improve LLM tool selection; awslabs reuse shows composition over reinvention. |
| GitHub write creds private to PR agent | GitHub read/write MCP on the shared Gateway | Anyone connected to the Gateway could open PRs. Read-only IaC lookup is shared; the write path is isolated with its own secret. |
| CDK-only (no parallel Terraform implementation) | CDK + Terraform dual-ship; platform CDK + workload Terraform | One language, one toolchain, one `deploy.sh`. The manifest-driven Gateway construct is a CDK construct — that's where the effort belongs. Mixed-IaC repos confuse the clone-and-deploy experience. Terraform is a documented extension path (see below). |
| CLI break/fix instead of web dashboard | Interactive dashboard like the networking demo | Less code to maintain, fits the DevOps audience, keeps focus on the agent pattern rather than UI. |
| Platform-first framing, cost as reference implementation | Pure cost-optimization sample; pure generic framework | A pure cost sample buries the reusable machinery; a pure framework isn't demoable. Cost is the "demo cartridge" that proves the platform in 15 minutes. |

## Terraform notes

**Using Terraform for your IaC?** Two facts worth knowing:

1. **Provisioning DevOps Agent via Terraform works** through the [AWS Cloud Control (`awscc`) provider](https://registry.terraform.io/providers/hashicorp/awscc/latest) — the `AWS::DevOpsAgent::*` types are in the CloudFormation registry, which `awscc` is generated from. The OAuth-service limitation and post-deploy steps carry over identically.
2. **DevOps Agent reads Terraform** (repo learning, PR reviews on `.tf` diffs) but has no state-file/backend awareness today — which is exactly why `locate_iac_source` exists. The shipped resolver targets CDK; a Terraform resolver (HCL block lookup) is a natural community extension point in the same manifest.

## Open items

- [ ] Verify A2A delegation payload supports full finding context (resource ARNs, repo hints) or define a thin structured contract
- [ ] Check APIs for webhook/HMAC + A2A registration → wrap as CFN custom resources if possible (June 2026 releases added API-key webhook auth and Asset APIs — likely yes)
- [ ] Verify scheduled SRE agent can be defined via Git-managed skills (June 22 release: skills importable from a repo via SDK/CLI — promising)
- [ ] Confirm exact scope of DevOps Agent native PR capability (which finding types) — affects Phase 2 timeline
- [ ] Redraw diagram with official AWS architecture icons
- [ ] Build the manifest-driven CDK construct (directory scan → Gateway targets + per-target IAM)
- [ ] Ship `examples/s3-storage-class` disabled target as the extensibility demo
- [ ] Constrain Phase 1 IaC mapping to a known repo structure with tagged resources
- [ ] Enable DevOps Agent release readiness reviews on the demo repo so it reviews the PR agent's PRs (agent proposes → agent reviews → human merges)
