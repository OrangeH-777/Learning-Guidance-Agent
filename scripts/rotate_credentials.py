"""Re-encrypt stored model keys with the first configured Fernet key, atomically."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models import ModelConfiguration
from backend.app.db.session import create_database_engine
from backend.app.services.models import cipher


def main():
    settings = get_settings()
    crypto = cipher(settings)
    engine = create_database_engine(settings)
    if engine is None:
        raise SystemExit("DATABASE_URL is not configured")
    try:
        with Session(engine) as db, db.begin():
            rows = list(
                db.scalars(
                    select(ModelConfiguration)
                    .where(ModelConfiguration.encrypted_key != "")
                    .with_for_update()
                )
            )
            for row in rows:
                row.encrypted_key = crypto.rotate(row.encrypted_key)
        print(f"Rotated {len(rows)} encrypted credential records; no keys displayed.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
