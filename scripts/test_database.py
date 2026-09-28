"""Fail closed before destructive test setup; never include connection secrets in errors."""

from sqlalchemy.engine import make_url


def require_test_database(url: str | None, application_url: str | None) -> str:
    message = "A separate PostgreSQL *_test database is required; refusing destructive setup"
    try:
        if not url:
            raise ValueError
        parsed = make_url(url)
        if (
            parsed.get_backend_name() != "postgresql"
            or not parsed.database
            or not parsed.database.endswith("_test")
            or {"host", "hostaddr", "port", "dbname", "service", "servicefile"}
            & parsed.query.keys()
        ):
            raise ValueError
        # Reject matching database names even through other roles, ports or DNS aliases.
        # Tests on another server must also use a distinct name from the application DB.
        if application_url and make_url(application_url).database == parsed.database:
            raise ValueError
    except Exception:
        raise ValueError(message) from None
    return url
