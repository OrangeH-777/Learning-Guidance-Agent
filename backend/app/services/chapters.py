"""Approved public material entries are the selectable course chapters."""

import re

from agents.retrieval.catalog import read_course, read_source
from backend.app.core.config import PROJECT_ROOT


def reviewed_chapters(settings, course_id):
    root = (PROJECT_ROOT / settings.public_knowledge_dir).resolve()
    directory = (root / course_id).resolve()
    if directory.parent != root or not (directory / "course.yaml").is_file():
        return
    manifest = read_course(directory)
    for entry in manifest.sources:
        if entry.review_status == "approved":
            content = read_source(directory, entry)
            headings = list(
                re.finditer(
                    r"(?m)^[ \t]*(?:#{1,6}[ \t]+)?(第[零〇一二三四五六七八九十百千两0-9]+章[^\n]{0,100})[ \t]*$",
                    content,
                )
            )
            sections = [(entry.section, content)]
            if headings:
                ends = [match.start() for match in headings[1:]] + [len(content)]
                sections = [
                    (match[1].strip(), content[match.start() : end])
                    for match, end in zip(headings, ends, strict=True)
                ]
                prefix = content[: headings[0].start()].strip()
                if prefix:
                    sections.insert(0, ("章前内容", prefix))
            for number, (section, body) in enumerate(sections):
                yield {
                    "id": f"{entry.id}:{entry.version}:{number}",
                    "title": f"{entry.title} · {section}",
                    "content": body,
                    "source": entry.source_url,
                    "version": entry.version,
                    "license": entry.license,
                }
