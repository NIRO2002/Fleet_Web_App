"""Fix Pass 2 item E: reproducibility primitives.

Without a recorded seed, git commit, and environment snapshot, a Phase 6
evaluation result cannot be tied back to the code that produced it. This
module is deliberately small and dependency-free of the rest of the
optimization/evaluation code, so it can be imported from anywhere (the
harness, `optimize_load`, a notebook) without pulling in the GA.
"""
import hashlib
import importlib.metadata
import json
import platform
import random
import subprocess
from pathlib import Path

import numpy as np

from app.core.config import settings
from app.utils_datetime import utcnow

#: Package distribution names (as registered with pip/PyPI), not import
#: names -- e.g. "scikit-learn" the distribution provides the `sklearn`
#: import. Version lookup below is guarded per-package so one
#: missing/renamed distribution never crashes the whole manifest.
_TRACKED_PACKAGES = ["pymoo", "hdbscan", "scikit-learn", "numpy", "scipy", "pandas"]

#: Settings fields never written into a manifest, however it's read.
_REDACTED_SETTINGS_KEYS = {"jwt_secret_key"}


def set_seeds(seed: int) -> int:
    """Seeds every source of randomness this codebase actually uses
    (`random` for the synthetic-data/harness layer, `numpy.random` for
    everything numeric including pymoo's default RNG plumbing). Returns
    `seed` so a caller can log it inline: `logger.info(set_seeds(42))`."""
    random.seed(seed)
    np.random.seed(seed)
    return seed


def _run_git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def git_commit_sha() -> str | None:
    return _run_git("rev-parse", "HEAD")


def is_git_dirty() -> bool:
    """True if there are uncommitted changes (staged, unstaged, or
    untracked) in the working tree. A results set produced from an
    uncommitted tree can't be reproduced against any commit, so the harness
    (item B) refuses to run against a dirty tree unless overridden."""
    status = _run_git("status", "--porcelain")
    return bool(status)


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in _TRACKED_PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _redacted_settings() -> dict:
    return {
        key: ("***REDACTED***" if key in _REDACTED_SETTINGS_KEYS else value)
        for key, value in settings.model_dump().items()
    }


def _catalog_digest(catalog) -> str | None:
    """`catalog` is a `tuple[VehicleTypeSpec, ...]` (a frozen dataclass) --
    the same shape `LoadPlan.catalog_snapshot` already stores via
    `dataclasses.asdict`."""
    if catalog is None:
        return None
    from dataclasses import asdict

    serializable = [asdict(v) for v in catalog]
    encoded = json.dumps(serializable, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_manifest(catalog=None) -> dict:
    """Full reproducibility snapshot for one run: settings (secrets
    redacted), git commit + dirty flag, Python version, tracked package
    versions, a UTC timestamp, and (when `catalog` is passed) a digest of
    the exact vehicle catalog snapshot the run used."""
    return {
        "settings": _redacted_settings(),
        "git_commit_sha": git_commit_sha(),
        "git_dirty": is_git_dirty(),
        "python_version": platform.python_version(),
        "package_versions": _package_versions(),
        "timestamp_utc": utcnow().isoformat(),
        "catalog_snapshot_digest": _catalog_digest(catalog),
    }


def write_manifest(path: str | Path, *, catalog=None) -> dict:
    manifest = run_manifest(catalog=catalog)
    Path(path).write_text(json.dumps(manifest, indent=2))
    return manifest
