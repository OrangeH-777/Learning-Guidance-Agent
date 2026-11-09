import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.core.errors import register_error_handlers
from backend.app.main import create_app
from backend.app.schemas.responses import SessionResponse


def test_every_business_operation_documents_success_and_safe_errors():
    schema = create_app().openapi()
    operations = 0
    for path, methods in schema["paths"].items():
        if not path.startswith("/api/"):
            continue
        for operation in methods.values():
            operations += 1
            for code, response in operation["responses"].items():
                if code.startswith("2") and code != "204":
                    assert response["content"]["application/json"]["schema"], path
                if code in {"401", "403", "404", "409", "413", "422", "429", "500", "502", "503"}:
                    assert response["content"]["application/json"]["schema"] == {
                        "$ref": "#/components/schemas/ErrorResponse"
                    }
    assert operations == 29


def test_invalid_internal_response_never_exposes_private_data(caplog):
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/invalid", response_model=SessionResponse)
    def invalid():
        return {"password": "private-password-canary", "encrypted_key": "private-key-canary"}

    result = TestClient(app).get("/invalid")
    assert result.status_code == 500
    assert result.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "canary" not in result.text + caplog.text


def test_public_model_schema_has_no_credential_fields():
    schema = create_app().openapi()["components"]["schemas"]["SavedModelResponse"]
    encoded = json.dumps(schema)
    assert "encrypted_key" not in encoded and "api_key" not in encoded
