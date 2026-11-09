"""Use the same chapter boundaries and numeric order in the editor and workspace."""

import re
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from agents.retrieval.catalog import SourceEntry, read_course, read_source
from backend.app.core.config import PROJECT_ROOT

NUMBER = r"第[ \t]*([零〇一二三四五六七八九十百千两0-9]+)[ \t]*章"
HEADING = re.compile(r"^[ \t]*(?:#{1,6}[ \t]+)?(" + NUMBER + r"[^\n]{0,100})[ \t]*$", re.M)


def parse_chapter_number(text):
    match = re.search(NUMBER, text)
    if not match:
        return None
    value = match[1]
    if len(value) > 12:
        return None
    if value.isdecimal():
        return int(value) if len(value) <= 6 and int(value) > 0 else None
    digits = dict(zip("零〇一二两三四五六七八九", "001223456789", strict=True))
    units = {"十": 10, "百": 100, "千": 1000}
    total, digit = 0, 0
    for ch in value:
        if ch in units:
            total += (digit or 1) * units[ch]
            digit = 0
        else:
            digit = digit * 10 + int(digits.get(ch, ch))
    return total + digit if 0 < total + digit <= 999999 else None


@dataclass
class Chapter:
    entry: SourceEntry
    content: str
    split: bool
    legacy_id: str


def suggested_chapter_number(filename, content):
    number = parse_chapter_number(filename)
    if number:
        return number
    heading = HEADING.search(content)
    return parse_chapter_number(heading[1]) if heading else None


def catalog_chapters(directory, manifest):
    chapters = []
    for source in manifest.sources:
        content = read_source(directory, source)
        # Explicitly numbered uploads represent one chapter, including their internal headings.
        headings = [] if source.chapter_number else list(HEADING.finditer(content))
        sections = [(source.title, content)]
        if headings:
            ends = [h.start() for h in headings[1:]] + [len(content)]
            sections = [(h[1].strip(), content[h.start() : end]) for h, end in zip(headings, ends)]
            prefix = content[: headings[0].start()].strip()
            if prefix:
                sections.insert(0, ("章前内容", prefix))
        split = len(sections) > 1
        for index, (heading, body) in enumerate(sections):
            title = heading if split else source.title
            number = (
                source.chapter_number
                or parse_chapter_number(heading)
                or parse_chapter_number(source.section)
                or len(chapters) + 1
            )
            source_id = source.id
            if index:
                source_id = (
                    "chapter_" + uuid5(NAMESPACE_URL, f"{manifest.id}/{source.id}/{index}").hex
                )
            entry = source.model_copy(
                update={"id": source_id, "title": title, "chapter_number": number}
            )
            chapters.append(Chapter(entry, body, split, f"{source.id}:{source.version}:{index}"))
    return sorted(chapters, key=lambda c: c.entry.chapter_number)


def reviewed_chapters(settings, course_id):
    root = (PROJECT_ROOT / settings.public_knowledge_dir).resolve()
    directory = (root / course_id).resolve()
    if directory.parent != root or not (directory / "course.yaml").is_file():
        return
    for chapter in catalog_chapters(directory, read_course(directory)):
        entry = chapter.entry
        if entry.review_status == "approved":
            yield {
                "id": f"{entry.id}:{entry.version}:0",
                "legacy_id": chapter.legacy_id,
                "title": entry.title,
                "description": entry.description,
                "chapter_number": entry.chapter_number,
                "content": chapter.content,
                "source": entry.source_url,
                "version": entry.version,
                "license": entry.license,
            }
