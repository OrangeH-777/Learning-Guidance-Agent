"""Read-only infrastructure check: uv run python -m scripts.check_database."""

import json

from backend.app.core.config import get_settings
from backend.app.db.health import check_database
from backend.app.db.session import create_database_engine


def main() -> int:
    engine = create_database_engine(get_settings())
    try:
        result = check_database(engine)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] == "ok" else 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
