"""Persistence layer for OpenCode Cloud Workstation on Kaggle.

See module docstring in repo history for architecture overview.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class RecoveryStatus(str, Enum):
    RESTORED_FROM_DATASET = "RESTORED_FROM_DATASET"
    FRESH_WORKSTATION = "FRESH_WORKSTATION"
    RESTORE_FAILED = "RESTORE_FAILED"


@dataclass
class RecoveryResult:
    status: RecoveryStatus
    dataset_id: str = ""
    message: str = ""
    details: Optional[dict] = None


class DownloadErrorKind(str, Enum):
    DATASET_NOT_FOUND = "DATASET_NOT_FOUND"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    INVALID_DATASET = "INVALID_DATASET"
    DOWNLOAD_ERROR = "DOWNLOAD_ERROR"


def classify_download_error(exc: BaseException) -> DownloadErrorKind:
    msg = str(exc).lower()
    name = type(exc).__name__.lower()
    if any(t in msg for t in ("401", "unauthorized", "authentication", "invalid credentials", "api key")):
        return DownloadErrorKind.AUTHENTICATION_ERROR
    if any(t in msg for t in ("403", "forbidden", "permission denied", "not allowed")):
        return DownloadErrorKind.AUTHORIZATION_ERROR
    if any(t in msg for t in ("429", "rate limit", "too many requests")):
        return DownloadErrorKind.RATE_LIMIT
    if any(t in msg for t in ("timeout", "timed out", "connection", "network", "dns", "unreachable", "ssl")):
        return DownloadErrorKind.NETWORK_ERROR
    if any(t in msg for t in ("404", "not found", "does not exist", "dataset does not exist", "no such dataset")):
        return DownloadErrorKind.DATASET_NOT_FOUND
    if "not found" in name or "http404" in name:
        return DownloadErrorKind.DATASET_NOT_FOUND
    return DownloadErrorKind.DOWNLOAD_ERROR
