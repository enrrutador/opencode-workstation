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
