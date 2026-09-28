"""Create local secrets and isolated development/test databases with an existing Docker.

No remote deployment or system PostgreSQL service is configured. Existing .env is preserved.
"""

import secrets
import subprocess

from cryptography.fernet import Fernet

from backend.app.core.config import PROJECT_ROOT

IMAGE = (
    "pgvector/pgvector:pg17@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f"
)


def main() -> None:
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        raise SystemExit(".env already exists; refusing to overwrite local settings")
    password = secrets.token_urlsafe(32)
    runtime = PROJECT_ROOT / "var" / "local-database"
    runtime.mkdir(parents=True, exist_ok=True)
    postgres_env = runtime / "postgres.env"
    postgres_env.write_text(
        f"POSTGRES_USER=lga\nPOSTGRES_PASSWORD={password}\nPOSTGRES_DB=lga_dev\n", encoding="utf-8"
    )
    subprocess.run(
        [
            "docker",
            "run",
            "--detach",
            "--name",
            "lga-postgres-dev",
            "--publish",
            "127.0.0.1:55432:5432",
            "--env-file",
            str(postgres_env),
            "--mount",
            "type=volume,source=lga-postgres-data,target=/var/lib/postgresql/data",
            IMAGE,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    # Only store the password in ignored local files; never echo it to the terminal.
    url = f"postgresql+psycopg://lga:{password}@127.0.0.1:55432/"
    env_path.write_text(
        f"DATABASE_URL={url}lga_dev\nTEST_DATABASE_URL={url}lga_test\n"
        f"MODEL_CREDENTIAL_ENCRYPTION_KEY={Fernet.generate_key().decode()}\n"
        "SESSION_TTL_SECONDS=7200\nCOOKIE_SECURE=false\n",
        encoding="utf-8",
    )
    print("Local container created; .env written without displaying secrets.")
    print("Wait for pg_isready, then create lga_test and enable vector in both databases.")


if __name__ == "__main__":
    main()
