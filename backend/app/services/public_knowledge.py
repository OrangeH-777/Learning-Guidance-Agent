"""Administrator-managed canonical Markdown and versioned public indexes."""

import asyncio
from uuid import uuid4

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.retrieval.catalog import CourseManifest, SourceEntry, read_course
from backend.app.core.config import PROJECT_ROOT
from backend.app.core.errors import AppError
from backend.app.db.models import Course
from backend.app.schemas.materials import MaterialSave
from backend.app.services.chapters import Chapter, catalog_chapters, parse_chapter_number


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
                directory = self.directory(course.id)
                manifest = read_course(directory)
                result.append(
                    {
                        "id": course.id,
                        "name": manifest.name,
                        "version": manifest.version,
                        "active_index_version": course.active_index_version,
                        "sources": [
                            self.entry(c.entry) for c in catalog_chapters(directory, manifest)
                        ],
                    }
                )
            return result

    @staticmethod
    def entry(source):
        return source.model_dump(exclude={"file", "version"})

    def detail(self, course_id, source_id):
        directory = self.directory(course_id)
        manifest = read_course(directory)
        chapter = self.find_chapter(catalog_chapters(directory, manifest), source_id)
        return {
            **self.entry(chapter.entry),
            "content": chapter.content,
            "version": manifest.version,
        }

    @staticmethod
    def find_chapter(chapters, source_id):
        for chapter in chapters:
            if chapter.entry.id == source_id:
                return chapter
        raise AppError(404, "NOT_FOUND", "教材章节不存在，请刷新目录")

    def load_for_edit(self, course_id, expected_version):
        directory = self.directory(course_id)
        manifest = read_course(directory)
        if manifest.version != expected_version:
            raise AppError(409, "VERSION_CONFLICT", "课程教材已更新，请重新加载后保存")
        return directory, manifest, catalog_chapters(directory, manifest)

    def save(self, course_id, payload: MaterialSave):
        directory, manifest, chapters = self.load_for_edit(course_id, payload.expected_version)
        previous = self.find_chapter(chapters, payload.source_id) if payload.source_id else None
        token = uuid4().hex
        source_id = payload.source_id or "upload_" + token
        number = payload.chapter_number
        if number is None:
            number = (
                previous.entry.chapter_number
                if previous
                else (
                    parse_chapter_number(payload.title)
                    or parse_chapter_number(payload.section)
                    or max((c.entry.chapter_number for c in chapters), default=0) + 1
                )
            )
        if number > 999999:
            raise AppError(422, "INVALID_INPUT", "请填写 1 到 999999 之间的章号")
        source = SourceEntry(
            id=source_id,
            title=payload.title,
            chapter_number=number,
            description=(
                previous.entry.description
                if previous and "description" not in payload.model_fields_set
                else payload.description
            ),
            file=f"content/admin_{token}.md",
            source_url=payload.source_url,
            section=payload.section,
            license=payload.license,
            version=token,
            review_status="approved",
        )
        updated = Chapter(source, payload.content, False, "")
        if previous:
            chapters[chapters.index(previous)] = updated
        else:
            chapters.append(updated)
        self.publish(directory, manifest, chapters, {source.file: payload.content})
        return {"source_id": source_id, "version": manifest.version}

    def delete(self, course_id, source_id, expected_version):
        directory, manifest, chapters = self.load_for_edit(course_id, expected_version)
        chapters.remove(self.find_chapter(chapters, source_id))
        self.publish(directory, manifest, chapters, {})
        return {"source_id": source_id, "version": manifest.version}

    def publish(self, directory, manifest, chapters, new_files):
        expected_version = manifest.version
        token = uuid4().hex
        manifest.version = "materials-" + token
        manifest.sources = []
        for chapter in sorted(chapters, key=lambda c: c.entry.chapter_number):
            entry = chapter.entry
            if chapter.split:
                # Give surviving chapters from an older, combined upload independent bodies.
                path = f"content/admin_{uuid4().hex}.md"
                entry = entry.model_copy(update={"file": path})
                new_files[path] = chapter.content
            manifest.sources.append(entry)
        catalog = directory / "course.yaml"
        before = catalog.read_bytes()
        staged = directory / f".course-{token}.tmp"
        created = []
        changed = False
        try:
            with Session(self.engine) as db, db.begin():
                course = db.scalar(select(Course).where(Course.id == manifest.id).with_for_update())
                if course is None or not course.enabled:
                    raise AppError(409, "COURSE_DISABLED", "课程未导入或未开放")
                # Browser writes are serialized; also reject an intervening CLI catalog import.
                if course.content_version != expected_version:
                    raise AppError(
                        409, "VERSION_CONFLICT", "课程目录与数据库版本不同，请先导入目录"
                    )
                content_dir = (directory / "content").resolve()
                if not content_dir.is_relative_to(directory):
                    raise AppError(409, "INVALID_CATALOG", "教材保存路径无效")
                content_dir.mkdir(exist_ok=True)
                for path, content in new_files.items():
                    target = directory / path
                    with target.open("x", encoding="utf-8") as output:
                        created.append(target)
                        output.write(content)
                encoded = yaml.safe_dump(manifest.model_dump(), allow_unicode=True, sort_keys=False)
                if len(encoded) > 1024 * 1024:
                    raise AppError(422, "INVALID_CATALOG", "课程目录已满，请缩短章节信息或拆分课程")
                staged.write_text(encoded, encoding="utf-8")
                staged.replace(catalog)
                changed = True
                course.content_version = manifest.version
                course.active_index_version = None
        except Exception:
            if changed:
                staged.write_bytes(before)
                staged.replace(catalog)
            for path in created:
                path.unlink(missing_ok=True)
            raise
        finally:
            staged.unlink(missing_ok=True)
