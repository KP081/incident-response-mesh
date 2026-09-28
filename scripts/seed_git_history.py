"""One-time setup: seeds the sandbox repo with two commits per service
(a 'before' and 'after' state) so tools/git_tools.py's fetch_git_diff()
has a real commit to fetch instead of a canned string.

Run once:
    uv run python scripts/seed_git_history.py

Safe to re-run -- adds fresh commits on top each time (harmless, just
noisy history). For a clean slate, delete + recreate the sandbox repo.
"""

import os
import time

from dotenv import load_dotenv
from github import Auth, Github

load_dotenv()

# service_name -> (repo_path, before_content, after_content)
SERVICE_CHANGES = {
    "checkout-service": (
        "cache/lru.py",
        "self.max_size = 10_000\n",
        "self.max_size = None  # unbounded cache, never evicts\n",
    ),
    "orders-db-proxy": (
        "db/pool.py",
        "POOL_SIZE = 5\n",
        "POOL_SIZE = 5  # unchanged -- flash sale traffic exceeded this\n",
    ),
    "auth-service": (
        "auth/jwt_verify.py",
        "key = load_key('prod.pem')\n",
        "key = load_key('prod-rotated.pem')  # bad rotation, old tokens fail\n",
    ),
    "recommendation-engine": (
        "queue/consumer.py",
        "MAX_QUEUE_SIZE = 5000\n",
        "MAX_QUEUE_SIZE = None  # backpressure limit removed\n",
    ),
    "inventory-service": (
        "db/stock_update.py",
        "lock_order = ['sku', 'warehouse']\n",
        "lock_order = ['warehouse', 'sku']  # inconsistent across call sites\n",
    ),
    "sso-gateway": (
        "infra/cert-renewal.yaml",
        "renew_before_expiry_days: 30\n",
        "renew_before_expiry_days: 30  # cron job silently disabled, unrelated to this diff\n",
    ),
    "notifications-service": (
        "config/providers.py",
        "TWILIX_TIMEOUT_MS = 4000\n",
        "TWILIX_TIMEOUT_MS = 4000  # unchanged, provider-side slowdown\n",
    ),
    "billing-service": (
        "config/currency_rates.json",
        '{"EUR_USD": 1.08, "GBP_USD": 1.27}\n',
        '{"GBP_USD": 1.27}\n',
    ),
    "analytics-pipeline": (
        "jobs/cleanup.py",
        "cleanup_intermediate_files(older_than_hours=24)\n",
        "# cleanup_intermediate_files call removed during refactor\n",
    ),
    "log-aggregator": (
        "infra/crontab",
        "0 2 * * * /usr/sbin/logrotate /etc/logrotate.d/aggregator\n",
        "# logrotate cron entry accidentally removed during infra migration\n",
    ),
    "api-gateway": (
        "config/rate_limits.yaml",
        'per_ip_limit: "10/sec"\n',
        'per_ip_limit: "10/min"  # unit typo introduced in build 771\n',
    ),
    "email-service": (
        "infra/db_quota.yaml",
        "delivery_log_volume_gb: 100\n",
        "delivery_log_volume_gb: 100  # quota unchanged, growth outpaced it\n",
    ),
    "payment-gateway": (
        "config/timeouts.yaml",
        "downstream_timeout_seconds: 5\n",
        "downstream_timeout_seconds: 5  # unchanged -- no retry/backoff, downstream just went unresponsive\n",
    ),
    "search-service": (
        "config/search_index.yaml",
        'index_alias: "products-v3"\n',
        'index_alias: "products-v4-staging"  # alias doesn\'t exist yet, deploy shipped early\n',
    ),
    "checkout-payments-service": (
        "config/payment_processor.py",
        "RATE_LIMIT_PER_KEY = 100\n",
        "RATE_LIMIT_PER_KEY = 100  # unchanged since launch, never revisited as traffic grew\n",
    ),
}


def main():
    token = os.environ["GITHUB_PAT"]
    repo_name = os.environ["GITHUB_SANDBOX_REPO"]
    gh = Github(auth=Auth.Token(token))
    repo = gh.get_repo(repo_name)
    branch = repo.default_branch

    for service, (path, before, after) in SERVICE_CHANGES.items():
        print(f"Seeding {service} -> {path}")
        try:
            existing = repo.get_contents(path, ref=branch)
            repo.update_file(
                path=path,
                message=f"seed: initial state for {service}",
                content=before,
                sha=existing.sha,
                branch=branch,
            )
        except Exception:
            repo.create_file(
                path=path,
                message=f"seed: initial state for {service}",
                content=before,
                branch=branch,
            )

        time.sleep(1)  # distinct commit timestamps, easier to eyeball in GitHub UI

        existing = repo.get_contents(path, ref=branch)
        repo.update_file(
            path=path,
            message=f"seed: incident-causing change for {service}",
            content=after,
            sha=existing.sha,
            branch=branch,
        )
        print(f"  done -- 2 commits on {path}")


if __name__ == "__main__":
    main()
