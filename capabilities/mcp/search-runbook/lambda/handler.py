"""search_runbook — keyword search over markdown runbooks stored in S3.

Deliberately simple: list objects, score by keyword overlap (title hits weighted
higher), return best matches with excerpts. No OpenSearch, no embeddings — a
runbook library small enough to need those has outgrown this sample (see the
manifest's retirement clause).

Gateway invokes this Lambda per the MCP Lambda target contract: the tool name
arrives in context.client_context.custom['bedrockAgentCoreToolName'] and the
event is the tool's input arguments.
"""

import os
import re

import boto3

BUCKET = os.environ["RUNBOOK_BUCKET"]
PREFIX = os.environ.get("RUNBOOK_PREFIX", "")

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "in", "is", "it", "of", "on", "or", "that", "the", "to", "was", "what",
    "when", "where", "which", "with",
}

_s3 = boto3.client("s3")
_cache = None  # (populated per warm container) list of {key, title, text}


def handler(event, context):
    args = event if isinstance(event, dict) else {}
    query = (args.get("query") or "").strip()
    if not query:
        return {"error": "query is required", "results": []}
    max_results = max(1, min(int(args.get("max_results") or 3), 10))
    include_content = bool(args.get("include_content"))

    docs = _load_docs()
    terms = _tokenize(query)

    scored = []
    for doc in docs:
        score, excerpt = _score(doc, terms)
        if score > 0:
            scored.append((score, doc, excerpt))
    scored.sort(key=lambda t: -t[0])

    results = []
    for score, doc, excerpt in scored[:max_results]:
        item = {
            "title": doc["title"],
            "key": doc["key"],
            "score": round(score, 3),
            "excerpt": excerpt,
        }
        if include_content:
            item["content"] = doc["text"]
        results.append(item)

    return {
        "query": query,
        "results": results,
        "total_runbooks": len(docs),
        "hint": None if results else
            "No runbook matched. Try broader keywords (e.g. 'cost anomaly', 'NAT gateway').",
    }


def _load_docs():
    global _cache
    if _cache is not None:
        return _cache
    docs = []
    paginator = _s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".md"):
                continue
            text = _s3.get_object(Bucket=BUCKET, Key=key)["Body"].read().decode("utf-8")
            docs.append({"key": key, "title": _title(text, key), "text": text})
    _cache = docs
    return docs


def _title(text, key):
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return os.path.basename(key).removesuffix(".md").replace("-", " ").title()


def _tokenize(s):
    return [w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in _STOPWORDS]


def _score(doc, terms):
    """Keyword overlap: title hits count 3x, body hits count by frequency (capped)."""
    if not terms:
        return 0.0, ""
    title_tokens = set(_tokenize(doc["title"]))
    body = doc["text"].lower()
    score = 0.0
    matched = []
    for t in terms:
        if t in title_tokens:
            score += 3.0
        hits = body.count(t)
        if hits:
            score += min(hits, 5) * 0.5
            matched.append(t)
    return score / len(terms), _excerpt(doc["text"], matched)


def _excerpt(text, matched, width=240):
    """Return the first line-window containing a matched term."""
    if not matched:
        return text[:width].strip()
    lower = text.lower()
    pos = min((lower.find(t) for t in matched if t in lower), default=0)
    start = max(0, lower.rfind("\n", 0, pos) + 1)
    snippet = text[start:start + width].strip()
    return snippet + ("…" if start + width < len(text) else "")
