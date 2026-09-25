"""Mock git/GitHub tools.

Day 1-3 scope: return a simulated local diff so the agent mesh is fully
testable offline. The scope doc's stretch option -- a real test repo via
PyGithub opening an actual PR -- can replace `fetch_git_diff`'s body later
without touching its signature or any caller.
"""

import os
from datetime import datetime, timezone
from github import Github, Auth, GithubException

def open_remediation_pr(
    service_name: str, action: str, details: str, tool_context=None
) -> dict:
    """Opens a real branch + PR on the sandbox repo recording this
    incident's remediation. Returns pr_url on success, or an error dict
    the agent/UI can surface without crashing the run."""
    token = os.environ["GITHUB_PAT"]
    repo_name = os.environ["GITHUB_SANDBOX_REPO"]
    
    try:
        gh = Github(auth=Auth.Token(token))
        repo = gh.get_repo(repo_name)
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
            branch=branch_name
        )
        
        pr = repo.create_pull(
            title=f"[Auto] {action} — {service_name}",
            body=f"Opened automatically by incident-response-mesh.\n\n{details}",
            head=branch_name,
            base=repo.default_branch
        )
        
        return {"status": "created", "pr_url": pr.html_url, "pr_number": pr.number}
    
    except GithubException as e:
        return {"status": "error", "reason": str(e)}
    
_MOCK_DIFFS = {
    "checkout-service": (
        "diff --git a/cache/lru.py b/cache/lru.py\n"
        "- self.max_size = 10_000\n"
        "+ self.max_size = None  # unbounded cache, never evicts\n"
    ),
    "orders-db-proxy": (
        "diff --git a/db/pool.py b/db/pool.py\n"
        "- POOL_SIZE = 5\n"
        "+ POOL_SIZE = 5  # unchanged -- flash sale traffic exceeded this\n"
    ),
    "auth-service": (
        "diff --git a/auth/jwt_verify.py b/auth/jwt_verify.py\n"
        "- key = load_key('prod.pem')\n"
        "+ key = load_key('prod-rotated.pem')  # bad rotation, old tokens fail\n"
    ),
    "recommendation-engine": (
        "diff --git a/queue/consumer.py b/queue/consumer.py\n"
        "- MAX_QUEUE_SIZE = 5000\n"
        "+ MAX_QUEUE_SIZE = None  # backpressure limit removed\n"
    ),
    "inventory-service": (
        "diff --git a/db/stock_update.py b/db/stock_update.py\n"
        "- lock_order = ['sku', 'warehouse']\n"
        "+ lock_order = ['warehouse', 'sku']  # inconsistent across call sites\n"
    ),
    "sso-gateway": (
        "diff --git a/infra/cert-renewal.yaml b/infra/cert-renewal.yaml\n"
        "- renew_before_expiry_days: 30\n"
        "+ renew_before_expiry_days: 30  # cron job silently disabled, unrelated to this diff\n"
    ),
    "notifications-service": (
        "diff --git a/config/providers.py b/config/providers.py\n"
        "- TWILIX_TIMEOUT_MS = 4000  # unchanged, provider-side slowdown\n"
        "+ TWILIX_TIMEOUT_MS = 4000\n"
    ),
    "billing-service": (
        "diff --git a/config/currency_rates.json b/config/currency_rates.json\n"
        '- {"EUR_USD": 1.08, "GBP_USD": 1.27}\n'
        '+ {"GBP_USD": 1.27}  # EUR_USD entry dropped during config migration\n'
    ),
    "analytics-pipeline": (
        "diff --git a/jobs/cleanup.py b/jobs/cleanup.py\n"
        "- cleanup_intermediate_files(older_than_hours=24)\n"
        "+ # cleanup_intermediate_files call removed during refactor\n"
    ),
    "log-aggregator": (
        "diff --git a/infra/crontab b/infra/crontab\n"
        "- 0 2 * * * /usr/sbin/logrotate /etc/logrotate.d/aggregator\n"
        "+ # logrotate cron entry accidentally removed during infra migration\n"
    ),
    "api-gateway": (
        "diff --git a/config/rate_limits.yaml b/config/rate_limits.yaml\n"
        '- per_ip_limit: "10/sec"\n'
        '+ per_ip_limit: "10/min"  # unit typo introduced in build 771\n'
    ),
    "email-service": (
        "diff --git a/infra/db_quota.yaml b/infra/db_quota.yaml\n"
        "- delivery_log_volume_gb: 100\n"
        "+ delivery_log_volume_gb: 100  # quota unchanged, growth outpaced it\n"
    ),
}


def fetch_git_diff(service_name: str, commit_sha: str) -> str:
    """Fetch the diff for a given service's most recent suspect commit.

    Args:
        service_name: The service whose repo to inspect.
        commit_sha: The commit SHA to diff (mock data ignores the exact SHA
            and returns the scenario's canned diff for that service).

    Returns:
        A unified-diff formatted string, or an empty string if no diff is
        known for that service.
    """
    return _MOCK_DIFFS.get(service_name, "")
