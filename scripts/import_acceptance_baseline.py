"""Reproduce the acceptance baseline from the supplied second-cycle document.

This imports specifications only; it never marks business tests as executed.
Run with: uv run python -m scripts.import_acceptance_baseline [--check]
"""

import argparse
import hashlib
import json
import re
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "第二循环文档.docx"
TARGET = ROOT / "tests" / "fixtures" / "acceptance_baseline.json"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def extract_tables(source: Path) -> list[list[list[str]]]:
    with ZipFile(source) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    return [
        [
            [
                "".join(node.text or "" for node in cell.findall(".//w:t", NS))
                for cell in row.findall("w:tc", NS)
            ]
            for row in table.findall("w:tr", NS)
        ]
        for table in root.findall(".//w:body/w:tbl", NS)
    ]


def build_baseline(source: Path = SOURCE) -> dict:
    integration_cases = []
    system_cases = []
    course_cases = []
    traceability = []
    resource_types = {"讲解": "lecture", "练习": "exercise", "导图": "mindmap"}
    for table in extract_tables(source):
        for row in table[1:]:
            if not row:
                continue
            if match := re.fullmatch(r"(IT\d{2})\s*(.+)", row[0]):
                if len(row) != 3:
                    raise ValueError(f"Unexpected table columns for {match[1]}")
                integration_cases.append(
                    {
                        "id": match[1],
                        "interface": match[2],
                        "input": row[1],
                        "expected": row[2],
                        "execution_status": "not_run",
                    }
                )
            elif match := re.fullmatch(r"(TC\d{3})(.+)", row[0]):
                if len(row) != 5 or row[3] != "未执行":
                    raise ValueError(f"Source execution status requires review: {match[1]}")
                system_cases.append(
                    {
                        "id": match[1],
                        "action": match[2],
                        "input": row[1],
                        "expected": row[2],
                        "notes": row[4],
                        "execution_status": "not_run",
                    }
                )
            elif re.fullmatch(r"DS\d{2}", row[0]):
                if len(row) != 5:
                    raise ValueError(f"Unexpected table columns for {row[0]}")
                course_cases.append(
                    {
                        "id": row[0],
                        "course_id": "data_structure",
                        "knowledge_domain": row[1],
                        "learner_level": row[2],
                        "resource_type": resource_types[row[3]],
                        "request": row[4],
                        "execution_status": "not_run",
                    }
                )
            elif re.fullmatch(r"ST\d{2} / S\d{3}", row[0]):
                if len(row) != 5:
                    raise ValueError(f"Unexpected traceability columns for {row[0]}")
                case_range = re.fullmatch(r"TC(\d{3})—TC(\d{3})", row[3])
                if case_range is None:
                    raise ValueError(f"Unexpected test range: {row[3]}")
                traceability.append(
                    {
                        "scenario": row[0],
                        "use_cases": row[1].split(),
                        "requirements": row[2].split(),
                        "case_ids": [
                            f"TC{i:03}" for i in range(int(case_range[1]), int(case_range[2]) + 1)
                        ],
                    }
                )

    groups = [
        (integration_cases, "IT", 8, 2),
        (system_cases, "TC", 60, 3),
        (course_cases, "DS", 30, 2),
    ]
    for cases, prefix, count, width in groups:
        expected_ids = [f"{prefix}{i:0{width}}" for i in range(1, count + 1)]
        if [case["id"] for case in cases] != expected_ids:
            raise ValueError(f"Missing, duplicated or reordered {prefix} source cases")
    if len(traceability) != 12:
        raise ValueError("Expected exactly twelve ST scenarios")
    return {
        "source": "docs/第二循环文档.docx",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "scope_note": "原数据结构基线；多课程、个人模型与检索扩展另行追踪。",
        "integration_cases": integration_cases,
        "system_cases": system_cases,
        "course_cases": course_cases,
        "traceability": traceability,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check without changing the fixture")
    args = parser.parse_args()
    content = json.dumps(build_baseline(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != content:
            print("Acceptance fixture differs from the source document; review before updating.")
            return 1
        print("Acceptance baseline matches source: 8 IT, 60 TC, 30 DS, 12 ST.")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(content, encoding="utf-8", newline="\n")
    print(
        "Imported specifications only: 8 IT, 60 TC, 30 DS, 12 ST. All business cases are not_run."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
