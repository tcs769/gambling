"""Document store: the sample PDFs and uploads, by id. Parsing is cached."""

from __future__ import annotations

import copy
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from app.api_models import DocumentInfo
from app.docs import generate, smith
from app.docs.models import ParsedDocument
from app.docs.parse import parse_bundle, parse_document

BACKEND_DIR = Path(__file__).resolve().parents[1]
UPLOAD_DIR = BACKEND_DIR / "data" / "uploads"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

SAMPLE_IDS = {
    "form_1040": "sample-form-1040",
    "brokerage_statement": "sample-brokerage",
    "retirement_401k": "sample-401k",
}


BUNDLE_SAMPLE_ID = "smith-bundle"


class NotAPdf(ValueError):
    pass


class NoRecognisedDocuments(NotAPdf):
    """A readable PDF that contains none of the document types the app knows."""


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
    bundle: list[ParsedDocument] | None = None  # every document found in a multi-document PDF

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

    def _save_upload(self, name: str, data: bytes) -> tuple[str, Path]:
        if len(data) > MAX_UPLOAD_BYTES:
            raise NotAPdf(f"{name} is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
        if not data.startswith(b"%PDF"):
            raise NotAPdf(f"{name} is not a PDF")
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        doc_id = uuid.uuid4().hex[:12]
        path = UPLOAD_DIR / f"{doc_id}.pdf"
        path.write_bytes(data)
        return doc_id, path

    def add_upload(self, name: str, data: bytes) -> StoredDocument:
        doc_id, path = self._save_upload(name, data)
        try:
            return self._register(doc_id, name, path)
        except Exception as exc:  # unreadable or malformed PDF
            path.unlink(missing_ok=True)
            raise NotAPdf(f"{name} could not be read as a PDF") from exc

    # -- a PDF holding several documents (the Smith bundle) ----------------------------------
    def _register_bundle(self, doc_id: str, name: str, path: Path) -> StoredDocument:
        with pdfplumber.open(path) as pdf:
            pages = len(pdf.pages)
        documents = parse_bundle(path)
        if all(d.doc_kind == "unknown" for d in documents):
            raise NoRecognisedDocuments(
                f"We could not find a tax return, brokerage statement, 401(k) statement or Roth IRA "
                f"statement in {name}."
            )
        doc = StoredDocument(doc_id, name, path, path.stat().st_size, pages, documents[0], documents)
        with self._lock:
            self._docs[doc_id] = doc
        return doc

    def add_sample_bundle(self) -> StoredDocument:
        """The John Smith bundle, under the same id every time (generated first if it is missing)."""
        with self._lock:
            existing = self._docs.get(BUNDLE_SAMPLE_ID)
        if existing is not None:
            return existing
        path = smith.DEFAULT_OUT
        if not path.is_file():
            smith.generate()
        return self._register_bundle(BUNDLE_SAMPLE_ID, path.name, path)

    def add_bundle_upload(self, name: str, data: bytes) -> StoredDocument:
        doc_id, path = self._save_upload(name, data)
        try:
            return self._register_bundle(doc_id, name, path)
        except NotAPdf:
            path.unlink(missing_ok=True)
            raise
        except Exception as exc:  # unreadable or malformed PDF
            path.unlink(missing_ok=True)
            raise NotAPdf(f"{name} could not be read as a PDF") from exc

    def bundle(self, doc_id: str) -> list[ParsedDocument]:
        """A private copy of the bundle's parsed documents (callers may edit values and re-check)."""
        doc = self.get(doc_id)
        return copy.deepcopy(doc.bundle if doc.bundle is not None else [self.parsed(doc_id)])

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
