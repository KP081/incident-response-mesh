"""Integration tests that hit the real GitHub API against the sandbox
repo. Skipped automatically if GITHUB_PAT isn't set (e.g. CI without
secrets configured). Kept separate from test_tools.py on purpose --
real network calls to an external service are a slower, flakier tier
than the offline/local-DB unit tests.
"""

import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from tools.git_tools import fetch_git_diff

requires_github = pytest.mark.skipif(
    not os.environ.get("GITHUB_PAT"),
    reason="GITHUB_PAT not set -- skipping real GitHub integration test",
)


@requires_github
def test_fetch_git_diff_known_service_returns_real_diff():
    assert "max_size" in fetch_git_diff("checkout-service")


@requires_github
def test_fetch_git_diff_unknown_service_returns_empty():
    assert fetch_git_diff("totally-unknown-service") == ""
