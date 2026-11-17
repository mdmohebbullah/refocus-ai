"""Read-only text extraction from .docx files."""
import io

from docx import Document as DocxDocument


def paragraphs_from_docx(data: bytes) -> list[dict]:
    d = DocxDocument(io.BytesIO(data))
    out = []
    for p in d.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        style = (p.style.name if p.style is not None else "") or ""
        out.append({"index": len(out), "text": text, "style": style, "is_heading": style.lower().startswith("heading") or style == "Title"})
    return out
