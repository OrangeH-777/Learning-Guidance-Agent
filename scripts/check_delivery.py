"""Inspect shareable files/builds for configured secrets and write a content fingerprint."""

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
from datetime import UTC, datetime

from dotenv import dotenv_values

from backend.app.core.config import PROJECT_ROOT

TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".js",
    ".vue",
    ".html",
    ".css",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".lock",
    ".ini",
    ".example",
    ".txt",
    ".log",
}
SECRET_NAMES = (
    "DATABASE_URL",
    "TEST_DATABASE_URL",
    "MODEL_CREDENTIAL_ENCRYPTION_KEY",
    "EMBEDDING_API_KEY",
)


def audit_files(paths, secrets):
    fingerprints, findings = {}, []
    for path in sorted(set(paths)):
        if not path.is_file() or not path.resolve().is_relative_to(PROJECT_ROOT):
            continue
        if path.suffix not in TEXT_SUFFIXES:
            continue
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        raw = path.read_bytes()
        fingerprints[relative] = hashlib.sha256(raw).hexdigest()
        if any(secret.encode() in raw for secret in secrets if secret):
            findings.append(relative)  # Never expose the matching value or source line.
    return fingerprints, findings


def main():
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
    )
    paths = [PROJECT_ROOT / name for name in result.stdout.decode("utf-8").split("\0") if name]
    paths.extend((PROJECT_ROOT / "frontend/dist").rglob("*"))
    paths.extend((PROJECT_ROOT / "var").rglob("*.log"))
    paths.extend((PROJECT_ROOT / "tests/results").rglob("*.log"))
    values = {**dotenv_values(PROJECT_ROOT / ".env"), **os.environ}
    secrets = [values.get(name, "") for name in SECRET_NAMES]
    fingerprints, findings = audit_files(paths, secrets)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "base_commit": head,
        "artifact_kind": "unreleased_working_tree",
        "python": platform.python_version(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("fastapi", "sqlalchemy", "langgraph", "pydantic", "psycopg", "pgvector")
        },
        "sha256": fingerprints,
        "configured_secret_findings": findings,
        "scope": "Text sources, frontend build and existing text logs; not binary trace archives",
    }
    target = PROJECT_ROOT / "tests/results/delivery-manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "files_checked": len(fingerprints),
                "secret_findings": len(findings),
                "frontend_build_present": (PROJECT_ROOT / "frontend/dist/index.html").exists(),
            }
        )
    )
    if findings:
        raise SystemExit("Configured secret detected; inspect the local report, do not publish")


if __name__ == "__main__":
    main()
