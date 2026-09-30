"""Real GitHub-backed git tools.

fetch_git_diff() looks up the most recent commit touching that service's
known repo path in the sandbox repo (see scripts/seed_git_history.py) and
returns its real unified diff via the GitHub API -- no canned string.

SERVICE_PATHS is a small hardcoded service->path map. In a real company
this would come from a service catalog / CMDB, not a Python dict -- but
the *pattern* (resolve a service name to a real repo location, then query
version control for it) is the same either way.

open_remediation_pr() opens a real branch + PR on the sandbox repo
recording the incident's remediation, once a human has approved it.
"""

import os
from datetime import datetime, timezone, timedelta

from github import Auth, Github, GithubException

SERVICE_PATHS = {
    "checkout-service": "cache/lru.py",
    "orders-db-proxy": "db/pool.py",
    "auth-service": "auth/jwt_verify.py",
    "recommendation-engine": "queue/consumer.py",
    "inventory-service": "db/stock_update.py",
    "sso-gateway": "infra/cert-renewal.yaml",
    "notifications-service": "config/providers.py",
    "billing-service": "config/currency_rates.json",
    "analytics-pipeline": "jobs/cleanup.py",
    "log-aggregator": "infra/crontab",
    "api-gateway": "config/rate_limits.yaml",
    "email-service": "infra/db_quota.yaml",
    "payment-gateway": "config/timeouts.yaml",
    "search-service": "config/search_index.yaml",
    "checkout-payments-service": "config/payment_processor.py",
    "cache-invalidator": "config/cache_ttl.yaml",
    "webhook-dispatcher": "infra/tls_cert_renewal.yaml",
    "shipping-service": "config/label_api_key.py",
}


def fetch_git_diff(service_name: str) -> str:
    """Fetch the diff from the most recent commit touching this service's
    file in the sandbox repo.

    Args:
        service_name: The service whose repo history to inspect.

    Returns:
        A unified-diff formatted string, or an empty string if no path is
        known for that service, or if the GitHub lookup fails.
    """
    path = SERVICE_PATHS.get(service_name)
    if not path:
        return ""

    try:
        token = os.environ["GITHUB_PAT"]
        repo_name = os.environ["GITHUB_SANDBOX_REPO"]
        gh = Github(auth=Auth.Token(token))
        repo = gh.get_repo(repo_name)

        commits = repo.get_commits(path=path)
        latest = commits[0]  # most recent first

        diff_parts = [
            f.patch or f"(no textual patch for {f.filename})" for f in latest.files
        ]
        return "\n".join(diff_parts)

    except (GithubException, KeyError, IndexError):
        return ""


def open_remediation_pr(
    service_name: str, action: str, details: str, tool_context=None
) -> dict:
    if os.environ.get("EVAL_DRY_RUN") == "true":
        return {"status": "skipped", "reason": "EVAL_DRY_RUN=true -- no PR opened"}

    token = os.environ["GITHUB_PAT"]
    repo_name = os.environ["GITHUB_SANDBOX_REPO"]

    try:
        gh = Github(auth=Auth.Token(token))
        repo = gh.get_repo(repo_name)

        recent_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        for pr in repo.get_pulls(state="open"):
            if service_name in pr.title and pr.created_at.replace(tzinfo=timezone.utc) > recent_cutoff:
                return {
                    "status": "skipped",
                    "reason": f"an open PR for {service_name} was already created in the last 10 min (#{pr.number})",
                    "pr_url": pr.html_url,
                }

        base = repo.get_branch(repo.default_branch)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        branch_name = f"incident-fix/{service_name}-{ts}"
        repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=base.commit.sha)

        file_path = f"remediation-log/{service_name}-{ts}.md"
        content = f"# Remediation: {service_name}\n\n**Action:** {action}\n\n{details}\n"
        repo.create_file(
            path=file_path,
            message=f"incident-response-mesh: {action} for {service_name}",
            content=content,
            branch=branch_name,
        )

        pr = repo.create_pull(
            title=f"[Auto] {action} — {service_name}",
            body=f"Opened automatically by incident-response-mesh.\n\n{details}",
            head=branch_name,
            base=repo.default_branch,
        )
        return {"status": "created", "pr_url": pr.html_url, "pr_number": pr.number}

    except GithubException as e:
        return {"status": "error", "reason": str(e)}