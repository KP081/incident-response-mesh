"""Mock git/GitHub tools — returns a canned diff per service."""

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
}


def fetch_git_diff(service_name: str, commit_sha: str) -> str:
    """Fetch the diff for a given service's most recent suspect commit."""
    return _MOCK_DIFFS.get(service_name, "")
