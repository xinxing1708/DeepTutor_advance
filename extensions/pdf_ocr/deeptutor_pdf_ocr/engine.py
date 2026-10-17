"""Page-preserving OCR. Rendering stays on one thread; OCR workers use ONNX."""

from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass
import hashlib
import json
import logging
import os
from pathlib import Path
import threading
import time
import uuid

from filelock import FileLock
import pymupdf

LOG = logging.getLogger(__name__)
ENGINE_VERSION = "rapidocr-v3-1"
_LOCAL = threading.local()
_INIT_LOCK = threading.Lock()
_RENDER_LOCK = threading.RLock()
_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="pdf-ocr")


def cache_root():
    from deeptutor.services.path_service import get_path_service
    return get_path_service().get_runtime_state_dir() / "pdf-ocr" / ENGINE_VERSION


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@dataclass
class PdfText:
    document_id: str
    pages: list[dict]
    directory: Path

    @property
    def units(self):
        return tuple(page["text"] for page in self.pages)

    def chat_text(self):
        notice = (
            f"[PDF-OCR:{self.document_id}]\n"
            f"PDF physical pages: {len(self.pages)}. OCR is approximate, not visually verified. "
            "Use this text for ordinary reading. For an exact quotation, ambiguous character, "
            "or important number, call read_source with page=N, verify_original=true and a "
            "specific focus. Verify only the relevant page, never the whole document. "
            "Use page=N to retrieve pages omitted by preview truncation.\n"
        )
        return notice + "\n\n".join(
            f"--- Page {i} ---\n{p['text']}" for i, p in enumerate(self.pages, 1)
        )


def _ocr_engine():
    if getattr(_LOCAL, "engine", None) is None:
        # RapidOCR v1 uses importlib and defaults to all CPU cores per session.
        # Initialize serially and bound each worker to two inference threads.
        with _INIT_LOCK:
            import onnxruntime as ort
            import rapidocr_onnxruntime
            engine = rapidocr_onnxruntime.RapidOCR()
            model_root = Path(rapidocr_onnxruntime.__file__).parent / "models"
            models = (
                ("text_detector", "infer", "ch_PP-OCRv3_det_infer.onnx"),
                ("text_recognizer", "session", "ch_PP-OCRv3_rec_infer.onnx"),
                ("text_cls", "infer", "ch_ppocr_mobile_v2.0_cls_infer.onnx"),
            )
            for part, attr, filename in models:
                options = ort.SessionOptions()
                options.intra_op_num_threads = 2
                options.inter_op_num_threads = 1
                options.log_severity_level = 3
                wrapper = getattr(getattr(engine, part), attr)
                wrapper.session = ort.InferenceSession(
                    str(model_root / filename), sess_options=options,
                    providers=["CPUExecutionProvider"],
                )
            _LOCAL.engine = engine
    return _LOCAL.engine


def _recognize(png, width, height):
    rows, _ = _ocr_engine()(png)
    lines = [
        {"box": [[float(x), float(y)] for x, y in box], "text": text,
         "confidence": float(score)}
        for box, text, score in (rows or []) if text.strip()
    ]
    return {"text": "\n".join(line["text"] for line in lines), "method": "ocr",
            "lines": lines, "width": width, "height": height}


def needs_ocr(page, text):
    if len(text.strip()) >= 250:
        return False
    images = page.get_image_info()
    if not images:
        return False
    area = max(1, page.rect.get_area())
    coverage = sum((pymupdf.Rect(img["bbox"]) & page.rect).get_area() for img in images) / area
    return len(text.strip()) < 8 or coverage >= 0.5


def extract_pdf(data: bytes) -> PdfText:
    document_id = hashlib.sha256(data).hexdigest()
    directory = cache_root() / document_id
    directory.mkdir(parents=True, exist_ok=True)
    with FileLock(str(directory / "ocr.lock"), timeout=3600):
        completed = _load(directory / "complete.json")
        if completed and (directory / "source.pdf").exists():
            return PdfText(document_id, completed["pages"], directory)
        with _RENDER_LOCK:
            doc = pymupdf.open(stream=data, filetype="pdf")
        pending = {}
        pages = [None] * len(doc)
        try:
            if doc.is_encrypted and not doc.authenticate(""):
                raise ValueError("PDF is encrypted; unlock it before OCR.")
            if len(doc) > 2000:
                raise ValueError("PDF exceeds 2000 pages; split it before OCR.")
            source = directory / "source.pdf"
            if not source.exists():
                temp = directory / "source.tmp"
                temp.write_bytes(data)
                os.replace(temp, source)

            def save_page(index, result):
                pages[index] = result
                atomic_json(directory / f"page-{index + 1:05}.json", result)
                count = sum(p is not None for p in pages)
                atomic_json(directory / "progress.json", {
                    "completed": count, "total": len(pages), "status": "processing",
                    "updated_at": time.time(),
                })
                if count % 25 == 0 or count == len(pages):
                    LOG.info("PDF OCR %s: %d/%d pages", document_id[:12], count, len(pages))

            def collect():
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    index = pending.pop(future)
                    save_page(index, future.result())

            for index in range(len(doc)):
                cached = _load(directory / f"page-{index + 1:05}.json")
                if cached is not None:
                    pages[index] = cached
                    continue
                with _RENDER_LOCK:
                    page = doc[index]
                    text = page.get_text(sort=True) or ""
                    scan = needs_ocr(page, text)
                    if scan:
                        scale = min(2.5, 2000 / max(page.rect.width, page.rect.height))
                        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                        png, width, height = pix.tobytes("png"), pix.width, pix.height
                if not scan:
                    save_page(index, {"text": text, "method": "native", "lines": []})
                    continue
                pending[_POOL.submit(_recognize, png, width, height)] = index
                if len(pending) >= 3:
                    collect()
            while pending:
                collect()
            atomic_json(directory / "complete.json", {"engine": ENGINE_VERSION, "pages": pages})
            atomic_json(directory / "progress.json", {
                "completed": len(pages), "total": len(pages), "status": "ready",
            })
            return PdfText(document_id, pages, directory)
        except Exception as exc:
            for future in pending:
                future.cancel()
            atomic_json(directory / "progress.json", {
                "completed": sum(p is not None for p in pages), "total": len(pages),
                "status": "error", "error": type(exc).__name__,
            })
            raise
        finally:
            with _RENDER_LOCK:
                doc.close()


def cached_pdf(document_id):
    import re
    if not re.fullmatch(r"[0-9a-f]{64}", document_id):
        raise ValueError("Invalid PDF identifier.")
    directory = cache_root() / document_id
    complete = _load(directory / "complete.json")
    if complete is None or not (directory / "source.pdf").exists():
        raise ValueError("OCR cache is unavailable; re-upload the PDF.")
    return PdfText(document_id, complete["pages"], directory)


def searchable_pdf(data):
    """Invisible OCR text enables selection/highlights without changing page pixels."""
    result = extract_pdf(data)
    if not any(page["method"] == "ocr" for page in result.pages):
        return data
    target = result.directory / "searchable.pdf"
    with FileLock(str(result.directory / "overlay.lock"), timeout=3600):
        if target.exists():
            return target.read_bytes()
        with _RENDER_LOCK, pymupdf.open(stream=data, filetype="pdf") as doc:
            font = pymupdf.Font("china-s")
            for page, recognized in zip(doc, result.pages):
                if recognized["method"] != "ocr":
                    continue
                sx = page.rect.width / recognized["width"]
                sy = page.rect.height / recognized["height"]
                for line in recognized["lines"]:
                    box = line["box"]
                    rect = pymupdf.Rect(min(p[0] for p in box) * sx, min(p[1] for p in box) * sy,
                                        max(p[0] for p in box) * sx, max(p[1] for p in box) * sy)
                    text = line["text"]
                    size = min(rect.height * 0.8, rect.width / max(0.01, font.text_length(text, fontsize=1)))
                    point = pymupdf.Point(rect.x0, rect.y1 - rect.height * 0.1)
                    # Raster coordinates follow the displayed, possibly rotated page.
                    point = point * page.derotation_matrix
                    page.insert_text(point, text, fontsize=max(0.5, size), fontname="china-s",
                                     render_mode=3, rotate=(360 - page.rotation) % 360)
            temp = target.with_name("searchable.tmp.pdf")
            try:
                doc.save(temp, garbage=3, deflate=True)
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)
        return target.read_bytes()


def render_page(data, page_number, crop=None):
    with _RENDER_LOCK, pymupdf.open(stream=data, filetype="pdf") as doc:
        if page_number < 1 or page_number > len(doc):
            raise ValueError(f"Page must be between 1 and {len(doc)}.")
        page = doc[page_number - 1]
        rect = page.rect
        if crop is not None:
            if len(crop) != 4 or not all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in crop):
                raise ValueError("crop must contain four normalized coordinates between 0 and 1.")
            x0, y0, x1, y1 = crop
            if x0 >= x1 or y0 >= y1:
                raise ValueError("crop must have positive width and height.")
            rect = pymupdf.Rect(rect.x0 + x0 * rect.width, rect.y0 + y0 * rect.height,
                                rect.x0 + x1 * rect.width, rect.y0 + y1 * rect.height)
        scale = min(4, 2400 / max(rect.width, rect.height))
        return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=rect, alpha=False).tobytes("png")
