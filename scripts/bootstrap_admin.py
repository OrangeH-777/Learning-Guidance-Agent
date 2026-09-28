"""Create the configured administrator once, without promoting or resetting existing users."""

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security import hash_password
from backend.app.db.models import User
from backend.app.db.session import create_database_engine
from backend.app.schemas.inputs import RegistrationInput


def bootstrap_admin(engine, settings):
    try:
        credentials = RegistrationInput(
            username=settings.admin_username,
            password=settings.admin_password,
            password_confirmation=settings.admin_password,
        )
    except ValidationError:
        raise ValueError("Configure a valid ADMIN_USERNAME and ADMIN_PASSWORD in .env") from None
    with Session(engine) as db, db.begin():
        # Serialize bootstrap operations, including first creation before a row exists.
        from sqlalchemy import func

        db.execute(select(func.pg_advisory_xact_lock(724905184)))
        existing = db.scalar(select(User).where(User.username == credentials.username))
        if existing:
            if not existing.is_admin:
                raise ValueError("Configured username already belongs to a non-administrator")
            return "unchanged"
        db.add(
            User(
                username=credentials.username,
                password_hash=hash_password(credentials.password.get_secret_value()),
                is_admin=True,
            )
        )
    return "created"


def main():
    settings = get_settings()
    engine = create_database_engine(settings)
    if engine is None:
        raise SystemExit("DATABASE_URL is not configured")
    try:
        print("Administrator: " + bootstrap_admin(engine, settings))
    except ValueError as error:
        raise SystemExit(str(error)) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
