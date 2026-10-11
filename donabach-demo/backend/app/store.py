"""Document store: the sample PDFs and uploads, by id. Parsing is cached."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from app.api_models import DocumentInfo
from app.docs import generate
from app.docs.models import ParsedDocument
from app.docs.parse import parse_document

BACKEND_DIR = Path(__file__).resolve().parents[1]
UPLOAD_DIR = BACKEND_DIR / "data" / "uploads"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

SAMPLE_IDS = {
    "form_1040": "sample-form-1040",
    "brokerage_statement": "sample-brokerage",
    "retirement_401k": "sample-401k",
}


class NotAPdf(ValueError):
    pass


def sample_paths() -> dict[str, Path]:
    """The three sample PDFs by document kind, generated first if any is missing."""
    paths = {kind: generate.DEFAULT_OUT_DIR / name for kind, name in generate.DOC_FILENAMES.items()}
    if not all(path.is_file() for path in paths.values()):
        generate.generate_all()
    return paths


@dataclass
class StoredDocument:
    id: str
    name: str
    path: Path
    size_bytes: int
    pages: int
    parsed: ParsedDocument | None = None

    def info(self) -> DocumentInfo:
        return DocumentInfo(
            id=self.id,
            name=self.name,
            size_bytes=self.size_bytes,
            pages=self.pages,
            kind=self.parsed.doc_kind if self.parsed else None,
        )


class DocumentStore:
    def __init__(self) -> None:
        self._docs: dict[str, StoredDocument] = {}
        self._lock = threading.Lock()

    def _register(self, doc_id: str, name: str, path: Path) -> StoredDocument:
        with pdfplumber.open(path) as pdf:
            pages = len(pdf.pages)
        doc = StoredDocument(doc_id, name, path, path.stat().st_size, pages)
        doc.parsed = parse_document(path)
        with self._lock:
            self._docs[doc_id] = doc
        return doc

    def add_samples(self) -> list[StoredDocument]:
        paths = sample_paths()
        docs = []
        for kind, path in paths.items():
            existing = self._docs.get(SAMPLE_IDS[kind])
            docs.append(existing or self._register(SAMPLE_IDS[kind], path.name, path))
        return docs

    def add_upload(self, name: str, data: bytes) -> StoredDocument:
        if len(data) > MAX_UPLOAD_BYTES:
            raise NotAPdf(f"{name} is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
        if not data.startswith(b"%PDF"):
            raise NotAPdf(f"{name} is not a PDF")
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        doc_id = uuid.uuid4().hex[:12]
        path = UPLOAD_DIR / f"{doc_id}.pdf"
        path.write_bytes(data)
        try:
            return self._register(doc_id, name, path)
        except Exception as exc:  # unreadable or malformed PDF
            path.unlink(missing_ok=True)
            raise NotAPdf(f"{name} could not be read as a PDF") from exc

    def get(self, doc_id: str) -> StoredDocument:
        with self._lock:
            doc = self._docs.get(doc_id)
        if doc is None:
            raise KeyError(doc_id)
        return doc

    def parsed(self, doc_id: str) -> ParsedDocument:
        doc = self.get(doc_id)
        if doc.parsed is None:
            doc.parsed = parse_document(doc.path)
        return doc.parsed


store = DocumentStore()
