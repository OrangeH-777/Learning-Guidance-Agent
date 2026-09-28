import argparse
import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

from agents.retrieval.indexing import index_course
from backend.app.core.config import PROJECT_ROOT, get_settings
from backend.app.db.session import create_database_engine
from backend.app.services.knowledge import embedder_for


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("course")
    parser.add_argument("--allow-unreviewed-preview", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    root = (PROJECT_ROOT / settings.public_knowledge_dir).resolve()
    directory = (root / args.course).resolve()
    if directory.parent != root:
        raise SystemExit("Course must be a direct child of the knowledge directory")
    engine = create_database_engine(settings)
    if engine is None:
        raise SystemExit("DATABASE_URL is not configured")
    record = {
        "course": args.course,
        "index_version": settings.embedding_index_version,
        "model": settings.embedding_model,
        "dimensions": settings.embedding_dimensions,
        "started_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "unreviewed_preview": args.allow_unreviewed_preview,
    }
    output = PROJECT_ROOT / "var/index-runs" / f"{uuid4()}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    try:
        result = await index_course(
            engine,
            directory,
            embedder_for(settings),
            index_version=settings.embedding_index_version,
            chunk_characters=settings.knowledge_chunk_characters,
            allow_unreviewed=args.allow_unreviewed_preview,
        )
        print(json.dumps(result))
        record.update(result)
    except Exception as error:
        record.update(status="failed", error_type=type(error).__name__)
        raise SystemExit(
            "Index build failed; inspect configuration and the local run record"
        ) from None
    finally:
        record["finished_at"] = datetime.now(UTC).isoformat()
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
