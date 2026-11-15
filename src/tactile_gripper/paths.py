"""Project-root and environment helpers (one definition for adapters, storage and UI)."""

from __future__ import annotations

import platform
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from .constants import SOFTWARE_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


@lru_cache(maxsize=1)
def git_revision() -> dict[str, str | bool | None]:
    commit = _git("rev-parse", "HEAD")
    dirty = _git("status", "--porcelain")
    return {
        "commit": commit or "UNKNOWN",
        "dirty": bool(dirty) if dirty is not None else None,
    }


def environment_snapshot() -> dict:
    revision = git_revision()
    return {
        "software_version": SOFTWARE_VERSION,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "git_commit": revision["commit"],
        "git_dirty": revision["dirty"],
    }
