# Governance

How this sample maps to the enterprise agent-platform pillars — and what is deliberately out of scope.

This sample is a **single-account L2→L3 platform starter**, not an enterprise governance product. Every pillar below is covered at one of three levels:

- ✅ **Implemented** — working mechanism in this repo
- 📄 **Documented** — honest pointer to the AWS-native way, with the plug-in point identified
- 🚫 **Out of scope** — with the graduation path stated

## The two planes

Agent governance needs two planes: one to **define** controls, one to **enforce** them at runtime. This sample implements both — with git as the governance plane and the Gateway as the enforcement plane.

### Governance plane (define what's allowed)

| Enterprise concept | This sample | Level |
|---|---|---|
| Policy engine / policy-as-code | The **manifest** is the policy: `readOnly: true` enforced at synth, per-target least-privilege IAM declared in-file, versioned tool names | ✅ |
| Agent/tool registry & catalog | `capabilities/` directory **is** a lightweight catalog: every capability is a reviewable folder with an owner, a description, and a lifecycle | ✅ |
| Approval workflows & lifecycle | Git PR review = the approval workflow. Adding/retiring a capability is a reviewed commit. Retirement conditions are declared up front (`retirement:`) | ✅ |
| Identity & access | SigV4 on the Gateway; per-target IAM roles; PR agent has its own isolated credential | ✅ |
| Audit trail | CloudTrail + git history (every capability change is a commit) + DevOps Agent investigation timelines | ✅ |
| Testing & evaluation | AgentCore Evaluations as CI/CD gates — plug-in point identified, **not implemented** (faking an eval pipeline is worse than pointing at the real one) | 📄 |
| Data governance / classification | Out of scope for a cost sample (Cost Explorer data is not sensitive-classified); see AgentCore data-governance docs | 🚫 |

### Enforcement plane (apply it at runtime, every request)

| Enterprise concept | This sample | Level |
|---|---|---|
| Inbound gateway (auth, rate limits) | AgentCore Gateway: SigV4 auth, one audited entry point for **all** clients (DevOps Agent, IDEs, PR agent) | ✅ |
| Runtime orchestration | DevOps Agent (judgment) + AgentCore Runtime (PR agent) | ✅ |
| Guardrails | Model-level guardrails are DevOps Agent–managed; the structural guardrail here is **read-only tools + write-as-PR** | ✅ |
| Human-in-the-loop | The PR **is** the HITL gate: every write lands as a proposal reviewed by a human (optionally pre-reviewed by DevOps Agent release readiness) | ✅ |
| Outbound control on writes | The only write path (GitHub) is isolated in a dedicated agent with its own scoped secret — never on the shared Gateway | ✅ |

## Anti-sprawl properties

The scaling challenges this design structurally prevents, at single-account scale:

- **Integration chaos** → one Gateway, one protocol (MCP), uniform auth. No agent connects to tools "its own way".
- **Shadow AI / ownership ambiguity** → a capability exists ⇔ a folder exists in git, with an owner in the manifest and a PR that added it.
- **Agent sprawl / no reuse** → every capability added for one client is instantly available to all clients via semantic tool discovery.
- **Cost blindness** → cost-allocation tags per capability + the observability dashboard (M5) showing invocations per target and $ saved from merged PRs.

## Observability & cost

- ✅ AgentCore observability + DevOps Agent dashboards are built-in; the sample adds cost-allocation tags per capability and a small CloudWatch dashboard (M5)
- 📄 Drift detection, A/B testing, online evals: pointers to AgentCore Evaluations/Observability — not sample scope

## Explicitly out of scope (and where to graduate)

| Concern | Why not here | Graduation path |
|---|---|---|
| Multi-account topology | This sample **is** one domain account in the enterprise reference architecture | Platform account (registry, AI gateway, shared identity) + domain accounts + centralized observability — see the [Thomson Reuters pattern](https://aws.amazon.com/blogs/machine-learning/how-thomson-reuters-built-an-agentic-platform-engineering-hub-with-amazon-bedrock-agentcore/) |
| Multi-tenancy | Single team, single account by design | Tenant isolation via per-domain Gateways + FGAC |
| Cedar policy engine, SCPs | Manifest-as-policy is sufficient at this scale | AgentCore Policy + Organizations SCPs |
| Eval pipelines / quality gates | Sample would fake them | AgentCore Evaluations wired as CI/CD gates |

## Maturity positioning

On the agent-platform maturity ladder (L1 experimentation → L4 governed & optimized), this sample is the **L2→L3 accelerator**: centralize tool access behind a gateway, stand up a tool catalog and shared MCP servers, migrate your first agents onto a shared pattern, establish basic cost tracking — with the L4 concerns named, mapped, and deliberately deferred.
