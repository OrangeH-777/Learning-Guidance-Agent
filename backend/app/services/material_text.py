"""Bounded document-to-text conversion; no OCR, macros, remote fetches or HTML rendering."""

import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARACTERS = 500_000
ALLOWED_SUFFIXES = {".md", ".pdf", ".docx"}


class MaterialError(ValueError):
    pass


def extract_text(data: bytes, suffix: str) -> dict:
    if not data or len(data) > MAX_FILE_BYTES:
        raise MaterialError("文件为空或超过10 MB，请按章节拆分")
    warnings = []
    if suffix == ".md":
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise MaterialError("Markdown必须使用UTF-8编码") from None
    elif suffix == ".docx":
        from docx import Document
        from docx.table import Table

        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or sum(e.file_size for e in entries) > 50 * 1024 * 1024:
                raise MaterialError("Word解压后过大，请按章节拆分")
            if any("vbaproject" in e.filename.lower() for e in entries):
                raise MaterialError("不支持包含宏的Word文件")
        document = Document(BytesIO(data))
        paragraphs = []
        for block in document.iter_inner_content():
            if isinstance(block, Table):
                paragraphs.extend(" | ".join(cell.text for cell in row.cells) for row in block.rows)
            elif block.text.strip():
                text = block.text
                if block.style and block.style.name.startswith("Heading"):
                    text = "## " + text
                paragraphs.append(text)
        content = "\n\n".join(paragraphs)
        warnings.append("Word仅提取正文段落和表格文本；图片、公式、页眉页脚等需人工核对补充。")
    elif suffix == ".pdf":
        from pypdf import PdfReader

        if not data.startswith(b"%PDF-"):
            raise MaterialError("文件内容不是有效PDF")
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise MaterialError("不支持加密PDF，请先解密并另存")
        if len(reader.pages) > 500:
            raise MaterialError("PDF超过500页，请按章节拆分")
        paragraphs, missing, total = [], 0, 0
        for number, page in enumerate(reader.pages, 1):
            stream = page.get_contents()
            if stream is not None and len(stream.get_data()) > 10 * 1024 * 1024:
                raise MaterialError("PDF单页内容过大，请简化或拆分")
            text = page.extract_text() or ""
            if not text.strip():
                missing += 1
                continue
            total += len(text)
            if total > MAX_TEXT_CHARACTERS:
                raise MaterialError("提取正文超过50万字符，请按章节拆分")
            paragraphs.append(f"## 第{number}页\n\n{text}")
        content = "\n\n".join(paragraphs)
        if missing:
            warnings.append(f"有{missing}页未提取到文字，可能是扫描页或空白页，请核对并按需先OCR。")
        warnings.append("PDF文字顺序、表格和公式可能不完整，请核对预览后再保存。")
    else:
        raise MaterialError("仅支持.md、可提取文字的.pdf和.docx；旧版.doc请另存为.docx")
    content = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not content:
        raise MaterialError("没有可提取文字；扫描件请先OCR，再上传文字版")
    if len(content) > MAX_TEXT_CHARACTERS or "\x00" in content:
        raise MaterialError("正文超过50万字符或含无效字符，请整理后重试")
    return {"content": content, "warnings": warnings, "characters": len(content)}


def preview_document(data: bytes, filename: str) -> dict:
    """Isolate parsers in a disposable process; terminate them after 30 seconds."""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise MaterialError("仅支持.md、.pdf和.docx；扫描件先OCR，旧版.doc先转换")
    if not data or len(data) > MAX_FILE_BYTES:
        raise MaterialError("文件为空或超过10 MB，请按章节拆分")
    with TemporaryDirectory(prefix="lga-material-") as directory:
        source = Path(directory) / ("input" + suffix)
        source.write_bytes(data)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "backend.app.services.material_text", str(source)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            raise MaterialError("文件解析超时，请按章节拆分后重试") from None
        if result.returncode:
            raise MaterialError("文件无法解析，请检查格式或重新导出")
        parsed = json.loads(result.stdout.decode("utf-8"))
        if "error" in parsed:
            raise MaterialError(parsed["error"])
        return parsed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    source = Path(sys.argv[1])
    try:
        output = extract_text(source.read_bytes(), source.suffix)
    except MaterialError as error:
        output = {"error": str(error)}
    except Exception:
        output = {"error": "文件损坏或格式不受支持，请重新导出"}
    print(json.dumps(output, ensure_ascii=False))
