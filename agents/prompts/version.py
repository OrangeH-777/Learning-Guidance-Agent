"""Fingerprint prompt implementation and structured contracts for immutable task snapshots."""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("nodes/model_nodes.py", "schemas/resources.py", "schemas/workflow.py")
PROMPT_VERSION = (
    "learning-v1-"
    + hashlib.sha256(
        b"\n".join((ROOT / name).read_bytes().replace(b"\r\n", b"\n") for name in FILES)
    ).hexdigest()[:24]
)
