"""Runs before any test module is imported, so core.config picks this up.

Tests must never touch the real (Neon) database: seed_telemetry() deletes
rows for a service before inserting, which would wipe live demo data.
A throwaway local sqlite file keeps them fast, offline, and isolated.
"""

import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + str(
    Path(tempfile.gettempdir()) / "incident_mesh_test.db"
)
