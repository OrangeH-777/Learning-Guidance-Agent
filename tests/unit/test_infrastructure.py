"""Infrastructure checks do not access a database or paid model service."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from backend.app.core.config import Settings
from backend.app.db.health import check_database
from backend.app.main import create_app


def test_liveness_is_independent_from_database_readiness():
    app = create_app(Settings(database_url="", _env_file=None))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["database"] == "not_configured"


def test_database_failure_does_not_expose_connection_secrets():
    engine = MagicMock()
    engine.connect.side_effect = OperationalError("", {}, Exception("secret-password-marker"))
    result = check_database(engine)
    assert result["status"] == "unavailable"
    assert "secret-password-marker" not in str(result)


def test_postgresql_without_pgvector_is_not_reported_ready():
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one_or_none.return_value = None
    assert check_database(engine) == {
        "status": "not_ready",
        "database": "ok",
        "pgvector": "missing",
    }
