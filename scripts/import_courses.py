"""Import only course metadata. This never fabricates sources, embeddings or readiness."""

from pathlib import Path

from sqlalchemy.orm import Session

from agents.retrieval.catalog import read_course
from backend.app.core.config import PROJECT_ROOT, get_settings
from backend.app.db.models import Course
from backend.app.db.session import create_database_engine


def main():
    settings = get_settings()
    root = Path(settings.public_knowledge_dir)
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    manifests = [read_course(path.parent) for path in sorted(root.glob("*/course.yaml"))]
    engine = create_database_engine(settings)
    if engine is None:
        raise SystemExit("DATABASE_URL is not configured")
    try:
        with Session(engine) as db, db.begin():
            for manifest in manifests:
                course = db.get(Course, manifest.id)
                if course is None:
                    course = Course(id=manifest.id)
                    db.add(course)
                elif course.content_version != manifest.version:
                    course.active_index_version = None
                course.name, course.description = manifest.name, manifest.description
                course.enabled, course.content_version = manifest.enabled, manifest.version
        print(
            f"Imported {len(manifests)} course catalog entries; index readiness remains separate."
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
