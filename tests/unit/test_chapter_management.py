from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml
from sqlalchemy import create_engine

from backend.app.core.errors import AppError
from backend.app.db.models import Course
from backend.app.schemas.materials import CourseCreate, MaterialSave
from backend.app.services.chapters import reviewed_chapters, suggested_chapter_number
from backend.app.services.public_knowledge import PublicKnowledgeManager


@pytest.mark.parametrize(
    ("filename", "content", "number"),
    [
        ("第二十章 图.pdf", "# 第1章 回顾", 20),
        ("栈.docx", "## 第二章 栈\n正文", 2),
        ("资料.md", "这是对第3章的一段引用。", None),
    ],
)
def test_upload_suggests_number_from_filename_or_heading(filename, content, number):
    assert suggested_chapter_number(filename, content) == number


def test_individual_chapters_in_a_legacy_book_survive_edits_and_deletes(tmp_path):
    engine = create_engine("sqlite://")
    Course.__table__.create(engine)
    settings = SimpleNamespace(public_knowledge_dir=str(tmp_path))
    manager = PublicKnowledgeManager(engine, settings)
    course_id = manager.create_course(CourseCreate(name="数据结构"), "admin")["id"]
    directory = tmp_path / course_id
    catalog = directory / "course.yaml"
    manifest = yaml.safe_load(catalog.read_text(encoding="utf-8"))
    manifest["sources"].append(
        dict(
            id="book",
            title="旧教材",
            source_url="https://example.org/book",
            section="全书",
            license="原创",
            file="book.md",
            version="v1",
            review_status="approved",
        )
    )
    catalog.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    (directory / "book.md").write_text(
        "# 第十章 排序\nSORT\n# 第二章 栈\nSTACK\n# 第十一章 图\nGRAPH", encoding="utf-8"
    )
    chapters = manager.courses()[0]["sources"]
    assert [c["chapter_number"] for c in chapters] == [2, 10, 11]
    stack, sort, graph = chapters
    assert "SORT" not in manager.detail(course_id, stack["id"])["content"]
    before = catalog.read_bytes()
    files = set(directory.rglob("*.md"))
    with patch("sqlalchemy.orm.session.SessionTransaction.commit", side_effect=RuntimeError):
        with pytest.raises(RuntimeError):
            manager.delete(course_id, stack["id"], "v1")
    assert catalog.read_bytes() == before and set(directory.rglob("*.md")) == files

    result = manager.delete(course_id, stack["id"], "v1")
    with pytest.raises(AppError, match="VERSION_CONFLICT"):
        manager.delete(course_id, graph["id"], "v1")
    with pytest.raises(AppError, match="NOT_FOUND"):
        manager.detail(course_id, stack["id"])
    assert "GRAPH" in manager.detail(course_id, graph["id"])["content"]

    manager.save(
        course_id,
        MaterialSave(
            expected_version=result["version"],
            source_id=graph["id"],
            title="图的表示",
            chapter_number=3,
            description="比较两种存储方式",
            content="# 第三章 图\nGRAPH\n## 第四章 回顾\n边与点",
            section="P.12",
            source_url=graph["source_url"],
            license="原创",
            confirmed=True,
        ),
    )
    visible = list(reviewed_chapters(settings, course_id))
    assert [c["chapter_number"] for c in visible] == [3, 10]
    assert visible[0]["description"] == "比较两种存储方式" and "第四章" in visible[0]["content"]
    assert visible[1]["id"] == sort["id"] + ":v1:0"
    assert "SORT" in visible[1]["content"] and "STACK" not in visible[1]["content"]
    engine.dispose()
