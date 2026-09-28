"""Administrator-managed canonical Markdown and versioned public indexes."""

import asyncio
from contextlib import suppress
from uuid import uuid4

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.retrieval.catalog import SourceEntry, read_course, read_source
from agents.retrieval.indexing import index_course
from backend.app.core.config import PROJECT_ROOT
from backend.app.core.errors import AppError
from backend.app.db.models import Course
from backend.app.schemas.materials import IndexJob, MaterialSave
from backend.app.services.knowledge import web_index_prefix


class PublicKnowledgeManager:
    def __init__(self, engine, settings, embedder_factory):
        self.engine, self.settings, self.embedder_factory = engine, settings, embedder_factory
        self.root = (PROJECT_ROOT / settings.public_knowledge_dir).resolve()
        self.lock = asyncio.Lock()
        self.preview_lock = asyncio.Lock()
        self.task = None
        self.job = None
        self.state_file = self.root / ".admin-index-job.json"
        if self.state_file.exists():
            try:
                self.job = IndexJob.model_validate_json(self.state_file.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self.job = None
            if self.job and self.job.status == "running":
                self.job.status = "interrupted"
                self.job.error = "后端已重启，请核对课程状态后重新建立索引"
                self.persist_job()

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

    def persist_job(self):
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(self.job.model_dump_json(), encoding="utf-8")
        temporary.replace(self.state_file)

    async def start_index(self, course_id, payload):
        if self.lock.locked():
            raise AppError(409, "KNOWLEDGE_BUSY", "教材正在保存或建立索引，请稍后重试")
        await self.lock.acquire()
        try:
            directory = self.directory(course_id)
            manifest = read_course(directory)
            if manifest.version != payload.expected_version:
                raise AppError(409, "VERSION_CONFLICT", "课程教材已更新，请重新加载")
            if not manifest.sources or (
                not payload.allow_unreviewed
                and any(s.review_status != "approved" for s in manifest.sources)
            ):
                raise AppError(
                    409, "REVIEW_REQUIRED", "请先检查并确认全部教材，或明确选择本地未复核测试"
                )
            with Session(self.engine) as db:
                course = db.get(Course, course_id)
                if not course or not course.enabled or course.content_version != manifest.version:
                    raise AppError(409, "VERSION_CONFLICT", "请先同步课程目录与数据库")
            embedder = self.embedder_factory(self.settings)
            self.job = IndexJob(
                id=uuid4().hex,
                course_id=course_id,
                index_version=web_index_prefix(self.settings) + uuid4().hex,
                status="running",
            )
            self.persist_job()
            self.task = asyncio.create_task(
                self.build(directory, embedder, payload.allow_unreviewed)
            )
            return self.job.model_copy()
        except BaseException:
            self.lock.release()
            raise

    async def build(self, directory, embedder, allow_unreviewed):
        try:
            async with asyncio.timeout(600):
                result = await index_course(
                    self.engine,
                    directory,
                    embedder,
                    index_version=self.job.index_version,
                    chunk_characters=self.settings.knowledge_chunk_characters,
                    allow_unreviewed=allow_unreviewed,
                )
            self.job.status, self.job.chunks = result["status"], result["chunks"]
        except asyncio.CancelledError:
            self.job.status, self.job.error = "interrupted", "后端停止，索引未确认完成，请重新检查"
        except Exception:
            self.job.status = "failed"
            self.job.error = "索引失败，请检查嵌入配置、网络、维度及课程版本后重试"
        finally:
            try:
                self.persist_job()
            finally:
                self.lock.release()

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
