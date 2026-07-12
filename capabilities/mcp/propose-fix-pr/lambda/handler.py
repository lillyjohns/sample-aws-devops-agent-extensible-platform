"""propose_fix_pr — open a GitHub PR applying a deterministic, runbook-approved IaC fix.

Write-as-proposal: this is the platform's single external write, and it lands as
a pull request — a human reviews and merges before anything is applied. The
transform is selected from a fixed registry keyed by change_description; the
tool never performs free-form edits. Reasoning about WHAT to fix belongs to the
DevOps Agent; this tool only executes an approved, deterministic change.

The GitHub credential is a fine-grained PAT stored as an SSM SecureString
(parameter name in env GITHUB_TOKEN_PARAM); it never appears in the template or
the repo. Set dry_run=true to preview the diff without touching GitHub.

Gateway invokes this Lambda per the MCP Lambda target contract: the tool name
arrives in context.client_context.custom['bedrockAgentCoreToolName'] and the
event is the tool's input arguments.
"""

import base64
import difflib
import json
import os
import re
import time
import urllib.error
import urllib.request

import boto3

DEFAULT_REPO = os.environ.get(
    "DEFAULT_REPO", "lillyjohns/sample-aws-devops-agent-governance-blueprint"
)
TOKEN_PARAM = os.environ.get("GITHUB_TOKEN_PARAM", "/governance-blueprint/github-token")
API = "https://api.github.com"

_token_cache = None


# ---------------------------------------------------------------------------
# The transform registry — the ONLY changes this tool can make. Each entry is a
# deterministic text transform plus the PR copy that explains it. Adding a new
# fix type = adding an entry here + the enum value in the manifest, reviewed as
# a git PR like any other capability change.
# ---------------------------------------------------------------------------

def _gp2_to_gp3(text: str):
    """Replace gp2 volume types with gp3 in CFN/CDK-style IaC."""
    patterns = [
        (re.compile(r"(VolumeType:\s*)(['\"]?)gp2\2"), r"\g<1>\g<2>gp3\g<2>"),
        (re.compile(r"(volumeType:\s*)(['\"]?)gp2\2"), r"\g<1>\g<2>gp3\g<2>"),
        (re.compile(r"(EbsDeviceVolumeType\.)GP2"), r"\g<1>GP3"),
    ]
    new = text
    count = 0
    for pat, repl in patterns:
        new, n = pat.subn(repl, new)
        count += n
    return new, count


TRANSFORMS = {
    "ebs-gp2-to-gp3": {
        "apply": _gp2_to_gp3,
        "title": "Migrate EBS volume(s) from gp2 to gp3",
        "body": (
            "gp3 delivers the same baseline performance as gp2 at ~20% lower cost "
            "and decouples IOPS/throughput from volume size. This change follows the "
            "approved runbook `gp2-to-gp3-migration`."
        ),
    },
}


def handler(event, context):
    args = event if isinstance(event, dict) else {}
    repo = (args.get("repo") or DEFAULT_REPO).strip()
    file_path = (args.get("file_path") or "").strip().lstrip("/")
    change = (args.get("change_description") or "").strip()
    finding = args.get("finding")
    dry_run = bool(args.get("dry_run"))

    if not file_path:
        return {"error": "file_path is required"}
    if change not in TRANSFORMS:
        return {
            "error": f"unknown change_description '{change}'",
            "supported": sorted(TRANSFORMS.keys()),
            "hint": "Only runbook-approved deterministic transforms are supported.",
        }
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        return {"error": f"repo must be owner/name, got '{repo}'"}

    transform = TRANSFORMS[change]

    # 1. Fetch the current file from the default branch
    try:
        meta = _gh(f"/repos/{repo}")
        default_branch = meta["default_branch"]
        f = _gh(f"/repos/{repo}/contents/{file_path}?ref={default_branch}")
    except urllib.error.HTTPError as e:
        return {"error": f"could not read {repo}:{file_path}: HTTP {e.code}", "detail": e.read().decode()[:300]}
    original = base64.b64decode(f["content"]).decode("utf-8")

    # 2. Apply the deterministic transform
    updated, n_changes = transform["apply"](original)
    if n_changes == 0:
        return {
            "status": "no_change",
            "message": f"transform '{change}' matched nothing in {file_path} — "
                       f"the file may already be fixed.",
        }

    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
    )

    if dry_run:
        return {
            "status": "dry_run",
            "repo": repo,
            "file_path": file_path,
            "change_description": change,
            "replacements": n_changes,
            "diff": diff,
            "message": "Dry run — no branch or PR was created.",
        }

    # 3. Create a branch, commit the change, open the PR
    branch = f"fix/{change}-{int(time.time())}"
    base_sha = _gh(f"/repos/{repo}/git/ref/heads/{default_branch}")["object"]["sha"]
    _gh(f"/repos/{repo}/git/refs", method="POST",
        body={"ref": f"refs/heads/{branch}", "sha": base_sha})

    _gh(f"/repos/{repo}/contents/{file_path}", method="PUT", body={
        "message": f"fix: {transform['title'].lower()} in {file_path}",
        "content": base64.b64encode(updated.encode()).decode(),
        "sha": f["sha"],
        "branch": branch,
    })

    body_parts = [
        transform["body"],
        "",
        f"**File:** `{file_path}`",
        f"**Transform:** `{change}` ({n_changes} replacement(s))",
    ]
    if finding:
        body_parts += [
            "",
            "### Cost finding",
            "```json",
            json.dumps(finding, indent=2, default=str)[:3000],
            "```",
        ]
    body_parts += [
        "",
        "---",
        "_Proposed by the Governance Blueprint `propose_fix_pr` tool. The change is a "
        "deterministic, runbook-approved transform — review and merge to apply. "
        "Nothing has been changed in any environment._",
    ]

    pr = _gh(f"/repos/{repo}/pulls", method="POST", body={
        "title": transform["title"],
        "head": branch,
        "base": default_branch,
        "body": "\n".join(body_parts),
    })

    return {
        "status": "pr_opened",
        "pr_url": pr["html_url"],
        "pr_number": pr["number"],
        "branch": branch,
        "repo": repo,
        "file_path": file_path,
        "replacements": n_changes,
        "diff": diff,
        "message": f"Opened {pr['html_url']} — a human must review and merge to apply the fix.",
    }


def _github_token():
    global _token_cache
    if _token_cache is None:
        ssm = boto3.client("ssm")
        _token_cache = ssm.get_parameter(Name=TOKEN_PARAM, WithDecryption=True)[
            "Parameter"
        ]["Value"].strip()
    return _token_cache


def _gh(path, method="GET", body=None):
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Authorization": f"Bearer {_github_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "governance-blueprint-propose-fix-pr",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())
