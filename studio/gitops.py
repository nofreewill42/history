"""Committing sessions to git. Never pushes."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .paths import REPO


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=check)


def lfs_problem(audio_file: Path) -> str | None:
    """Why audio_file would NOT go through Git LFS, or None if it would."""
    if _git("lfs", "version", check=False).returncode != 0:
        return "git-lfs is not installed"
    if not _git("config", "--get", "filter.lfs.clean", check=False).stdout.strip():
        return "Git LFS is not set up on this machine; run: git lfs install"
    rel = audio_file.relative_to(REPO).as_posix()
    attr = _git("check-attr", "filter", "--", rel, check=False).stdout.strip()
    if not attr.endswith(": lfs"):
        return f"{rel} is not tracked by Git LFS (check .gitattributes)"
    return None


def commit(paths: list[Path], message: str) -> str:
    """Commit exactly these paths. Returns the new commit hash.

    Uses the machine's own git identity. Only the listed paths are committed,
    so anything else staged or modified in the repo is left alone.
    """
    rels = [p.relative_to(REPO).as_posix() for p in paths if p.exists()]
    _git("add", "--", *rels)
    _git("commit", "-m", message, "--", *rels)
    return _git("rev-parse", "--short", "HEAD").stdout.strip()
