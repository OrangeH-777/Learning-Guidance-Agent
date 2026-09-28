"""Export reviewable API and physical data contracts without opening a database."""

import json

from backend.app.core.config import PROJECT_ROOT
from backend.app.db.base import Base
from backend.app.main import create_app


def main():
    target = PROJECT_ROOT / "docs/design"
    (target / "openapi.json").write_text(
        json.dumps(create_app().openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# 数据字典",
        "",
        "由 `python -m scripts.export_contracts` 从当前 SQLAlchemy 模型生成。"
        "时间使用带时区 UTC，展示转换为北京时间。",
        "",
    ]
    for table in Base.metadata.sorted_tables:
        lines.extend(
            [
                f"## {table.name}",
                "",
                "| 字段 | 类型 | 可空 | 主键 | 外键 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for column in table.columns:
            references = ", ".join(f.target_fullname for f in column.foreign_keys) or "—"
            lines.append(
                f"| {column.name} | {column.type} | {column.nullable} | "
                f"{column.primary_key} | {references} |"
            )
        lines.append("")
    (target / "data-dictionary.md").write_text("\n".join(lines), encoding="utf-8")
    print("Exported API and data contracts; no database connection used.")


if __name__ == "__main__":
    main()
