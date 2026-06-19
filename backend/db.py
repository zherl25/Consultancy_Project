"""Shared database path used by all storage modules."""

from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "store.db"
