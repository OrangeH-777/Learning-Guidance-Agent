"""Administrator-managed canonical Markdown and versioned public indexes."""

import asyncio
from uuid import uuid4

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.retrieval.catalog import CourseManifest, SourceEntry, read_course, read_source
from backend.app.core.config import PROJECT_ROOT
from backend.app.core.errors import AppError
from backend.app.db.models import Course
from backend.app.schemas.materials import MaterialSave


class PublicKnowledgeManager:
    def __init__(self, engine, settings):
        self.engine = engine
        self.root = (PROJECT_ROOT / settings.public_knowledge_dir).resolve()
        self.lock = asyncio.Lock()
        self.preview_lock = asyncio.Lock()

    def create_course(self, payload, maintainer):
        course_id = "course_" + uuid4().hex
        manifest = CourseManifest(
            id=course_id,
            name=payload.name,
            description=payload.description or payload.name,
            maintainer=maintainer,
            enabled=True,
            version="v1",
            topics=[payload.name],
            prerequisites=[],
            sources=[],
        )
        directory = self.root / course_id
        directory.mkdir(parents=True, exist_ok=False)
        catalog = directory / "course.yaml"
        try:
            with Session(self.engine) as db, db.begin():
                if db.scalar(select(Course.id).where(Course.name == payload.name).limit(1)):
                    raise AppError(409, "COURSE_EXISTS", "已有同名课程，请直接选择")
                db.add(
                    Course(
                        id=course_id,
                        name=manifest.name,
                        description=manifest.description,
                        enabled=True,
                        content_version=manifest.version,
                    )
                )
                db.flush()
                catalog.write_text(
                    yaml.safe_dump(manifest.model_dump(), allow_unicode=True, sort_keys=False),
                    encoding="utf-8",
                )
        except Exception:
            catalog.unlink(missing_ok=True)
            directory.rmdir()
            raise
        return {
            "id": course_id,
            "name": manifest.name,
            "version": manifest.version,
            "active_index_version": None,
            "sources": [],
        }

    def directory(self, course_id):
        directory = (self.root / course_id).resolve()
        if directory.parent != self.root or not (directory / "course.yaml").is_file():
            raise AppError(404, "NOT_FOUND", "课程资料目录不存在")
        if not (directory / "course.yaml").resolve().is_relative_to(directory):
            raise AppError(409, "INVALID_CATALOG", "课程配置路径无效")
        return directory

    def courses(self):
        with Session(self.engine) as db:
            records = db.scalars(select(Course).where(Course.enabled).order_by(Course.id)).all()
            result = []
            for course in records:
                manifest = read_course(self.directory(course.id))
                result.append(
                    {
                        "id": course.id,
                        "name": manifest.name,
                        "version": manifest.version,
                        "active_index_version": course.active_index_version,
                        "sources": [self.entry(source) for source in manifest.sources],
                    }
                )
            return result

    @staticmethod
    def entry(source):
        return source.model_dump(exclude={"file", "version"})

    def detail(self, course_id, source_id):
        directory = self.directory(course_id)
        manifest = read_course(directory)
        source = next((s for s in manifest.sources if s.id == source_id), None)
        if source is None:
            raise AppError(404, "NOT_FOUND", "教材条目不存在")
        return {
            **self.entry(source),
            "content": read_source(directory, source),
            "version": manifest.version,
        }

    def save(self, course_id, payload: MaterialSave):
        directory = self.directory(course_id)
        manifest = read_course(directory)
        if manifest.version != payload.expected_version:
            raise AppError(409, "VERSION_CONFLICT", "课程教材已更新，请重新加载后保存")
        if payload.source_id and not any(s.id == payload.source_id for s in manifest.sources):
            raise AppError(404, "NOT_FOUND", "原教材条目不存在")
        token = uuid4().hex
        source_id = payload.source_id or "upload_" + token
        content_dir = (directory / "content").resolve()
        if not content_dir.is_relative_to(directory):
            raise AppError(409, "INVALID_CATALOG", "教材保存路径无效")
        content_dir.mkdir(exist_ok=True)
        target = content_dir / f"admin_{token}.md"
        source = SourceEntry(
            id=source_id,
            title=payload.title,
            file=f"content/{target.name}",
            source_url=payload.source_url,
            section=payload.section,
            license=payload.license,
            version=token,
            review_status="approved",
        )
        manifest.sources = [source if s.id == source_id else s for s in manifest.sources]
        if not payload.source_id:
            manifest.sources.append(source)
        manifest.version = "materials-" + token
        catalog = directory / "course.yaml"
        before = catalog.read_bytes()
        staged = directory / f".course-{token}.tmp"
        changed = False
        try:
            with Session(self.engine) as db, db.begin():
                course = db.scalar(select(Course).where(Course.id == course_id).with_for_update())
                if course is None or not course.enabled:
                    raise AppError(409, "COURSE_DISABLED", "课程未导入或未开放")
                # Browser writes are serialized; also reject an intervening CLI catalog import.
                if course.content_version != payload.expected_version:
                    raise AppError(
                        409, "VERSION_CONFLICT", "课程目录与数据库版本不同，请先导入目录"
                    )
                target.write_text(payload.content, encoding="utf-8")
                staged.write_text(
                    yaml.safe_dump(manifest.model_dump(), allow_unicode=True, sort_keys=False),
                    encoding="utf-8",
                )
                staged.replace(catalog)
                changed = True
                course.content_version = manifest.version
                course.active_index_version = None
        except Exception:
            if changed:
                staged.write_bytes(before)
                staged.replace(catalog)
            target.unlink(missing_ok=True)
            raise
        finally:
            staged.unlink(missing_ok=True)
        return {"source_id": source_id, "version": manifest.version}
