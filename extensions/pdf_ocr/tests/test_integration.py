import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pymupdf

from deeptutor.reading.extract import extract_material
from deeptutor.tools.builtin import ReadSourceTool
from deeptutor.utils.document_extractor import extract_text_from_bytes


def scanned_pdf():
    source = pymupdf.open()
    page = source.new_page(width=600, height=800)
    page.insert_text((50, 100), "ORIGINAL VALUE 7392", fontsize=26)
    page.insert_text((50, 150), "Read this page only when exact wording is needed.", fontsize=16)
    pixels = page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png")
    scan = pymupdf.open()
    scan.new_page(width=600, height=800).insert_image(page.rect, stream=pixels)
    scan.new_page(width=600, height=800).insert_text((50, 100), "Digital page unchanged.")
    data = scan.tobytes()
    scan.close()
    source.close()
    return data


class UploadTests(unittest.TestCase):
    def test_direct_pdf_routing_and_source_scope(self):
        from types import SimpleNamespace
        from deeptutor_pdf_ocr.extension import PdfOcrExtension
        from deeptutor.capabilities.explore_context.capability import ExploreContextCapability
        extension = PdfOcrExtension()
        explorer = ExploreContextCapability()
        for metadata, direct in [
            ({"source_index": {"at-1": "[PDF-OCR:" + "a" * 64 + "]"}}, True),
            ({"reading_material_id": "book"}, True),
            ({"source_index": {"at-1": "ordinary text"}}, False),
        ]:
            context = SimpleNamespace(metadata=metadata)
            self.assertEqual(extension.is_active(context), direct)
            self.assertEqual(explorer.is_active(context), not direct)
            if direct:
                kwargs = extension.augment_kwargs("read_source", {"source_index": {"forged": "text"}}, context)
                self.assertEqual(kwargs["source_index"], metadata.get("source_index", {}))

    def test_chat_recognizes_scanned_page_and_preserves_page_numbers(self):
        text = extract_text_from_bytes("scan.pdf", scanned_pdf(), max_chars=None)
        self.assertIn("7392", text)
        self.assertIn("--- Page 1 ---", text)
        self.assertIn("--- Page 2 ---", text)
        self.assertIn("Digital page unchanged.", text)

    def test_immersive_reading_uses_same_ocr(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scan.pdf"
            path.write_bytes(scanned_pdf())
            result = extract_material(path)
            self.assertIn("7392", result.units[0])
            self.assertEqual(len(result.units), 2)

    def test_chat_tool_can_read_one_page_without_visual_verification(self):
        text = "--- Page 1 ---\nfirst\n\n--- Page 2 ---\nsecond"
        result = asyncio.run(ReadSourceTool().execute(
            source_id="at-test", source_index={"at-test": text}, page=2,
        ))
        self.assertIn("second", result.content)
        self.assertNotIn("first", result.content)

    def test_verification_requires_specific_page_and_focus(self):
        result = asyncio.run(ReadSourceTool().execute(
            source_id="at-test", source_index={"at-test": "plain text"},
            verify_original=True,
        ))
        self.assertFalse(result.success)

    def test_cached_page_read_does_not_call_vision(self):
        text = extract_text_from_bytes("scan.pdf", scanned_pdf(), max_chars=None)
        with patch("deeptutor_pdf_ocr.tools.verify_page", new_callable=AsyncMock) as vision:
            result = asyncio.run(ReadSourceTool().execute(
                source_id="at-test", source_index={"at-test": text}, page=1,
            ))
        vision.assert_not_awaited()
        self.assertIn("7392", result.content)

    def test_specific_page_can_be_retrieved_after_preview_truncation(self):
        text = extract_text_from_bytes("scan.pdf", scanned_pdf(), max_chars=150)
        result = asyncio.run(ReadSourceTool().execute(
            source_id="at-test", source_index={"at-test": text}, page=2,
        ))
        self.assertTrue(result.success)
        self.assertIn("Digital page unchanged.", result.content)

    def test_unknown_source_cannot_access_cached_document(self):
        result = asyncio.run(ReadSourceTool().execute(
            source_id="at-other", source_index={"at-test": "text"},
            page=1, verify_original=True, focus="number",
        ))
        self.assertFalse(result.success)

    def test_keyword_search_finds_pages_outside_preview_without_vision(self):
        text = extract_text_from_bytes("scan.pdf", scanned_pdf(), max_chars=150)
        with patch("deeptutor_pdf_ocr.tools.verify_page", new_callable=AsyncMock) as vision:
            result = asyncio.run(ReadSourceTool().execute(
                source_id="at-test", source_index={"at-test": text}, query="Digital page",
            ))
        vision.assert_not_awaited()
        self.assertEqual(result.metadata["matched_pages"], [2])
        self.assertIn("Page 2", result.content)

    def test_empty_keyword_search_is_explicit(self):
        text = extract_text_from_bytes("scan.pdf", scanned_pdf(), max_chars=150)
        result = asyncio.run(ReadSourceTool().execute(
            source_id="at-test", source_index={"at-test": text}, query="no such passage",
        ))
        self.assertEqual(result.metadata["matched_pages"], [])
        self.assertIn("No exact OCR match", result.content)

    def test_cached_ocr_is_not_repeated(self):
        from deeptutor_pdf_ocr.engine import extract_pdf
        data = scanned_pdf()
        first = extract_pdf(data)
        with patch("deeptutor_pdf_ocr.engine._recognize", side_effect=AssertionError("must not rescan")):
            second = extract_pdf(data)
        self.assertEqual(first.units, second.units)

    def test_digital_page_does_not_run_ocr(self):
        from deeptutor_pdf_ocr.engine import extract_pdf
        with pymupdf.open() as doc:
            doc.new_page().insert_text((50, 80), "Native text only")
            data = doc.tobytes()
        with patch("deeptutor_pdf_ocr.engine._recognize", side_effect=AssertionError("must not OCR")):
            result = extract_pdf(data)
        self.assertEqual(result.pages[0]["method"], "native")
        self.assertIn("Native text only", result.units[0])

    def test_reading_view_remains_visually_identical_and_selectable(self):
        from deeptutor.reading.store import ReadingStore
        data = scanned_pdf()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scan.pdf"
            path.write_bytes(data)
            store = ReadingStore(Path(folder) / "reading")
            manifest = store.ingest(path)
            with pymupdf.open(stream=data, filetype="pdf") as original, pymupdf.open(store.raw_path(manifest.material_id)) as view:
                self.assertEqual(original[0].get_pixmap().samples, view[0].get_pixmap().samples)
                self.assertIn("7392", view[0].get_text())
                self.assertTrue(view[0].search_for("7392"))
            self.assertEqual(path.read_bytes(), data)

    def test_pdf_ocr_upgrade_preserves_reading_position(self):
        import json
        from deeptutor.reading.store import ReadingStore
        from deeptutor.reading.models import ReadingPosition
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scan.pdf"
            path.write_bytes(scanned_pdf())
            store = ReadingStore(Path(folder) / "reading")
            manifest = store.ingest(path)
            store.save_position(manifest.material_id, ReadingPosition(locator=2))
            manifest_path = store._dir(manifest.material_id) / "manifest.json"
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            old["extractor"] = "pymupdf"
            manifest_path.write_text(json.dumps(old), encoding="utf-8")
            store.ingest(path)
            self.assertEqual(store.position(manifest.material_id).locator, 2)

    def test_visual_verification_sends_one_image_without_text_fallback(self):
        from deeptutor_pdf_ocr.tools import verify_page
        with patch("deeptutor.services.llm.config.get_llm_config", return_value=object()), patch("deeptutor.services.llm.factory.complete_with_config", new_callable=AsyncMock, return_value="7392") as vision:
            result = asyncio.run(verify_page(scanned_pdf(), 1, "the original number"))
        vision.assert_awaited_once()
        self.assertFalse(vision.call_args.kwargs["allow_image_fallback"])
        self.assertTrue(vision.call_args.kwargs["image_data"])
        self.assertTrue(result.metadata["visual_verification"])

    def test_visual_failure_is_not_reported_as_verified(self):
        text = extract_text_from_bytes("scan.pdf", scanned_pdf(), max_chars=None)
        with patch("deeptutor.services.llm.config.get_llm_config", return_value=object()), patch("deeptutor.services.llm.factory.complete_with_config", new_callable=AsyncMock, side_effect=RuntimeError("provider failed")) as vision:
            result = asyncio.run(ReadSourceTool().execute(
                source_id="at-test", source_index={"at-test": text}, page=1,
                verify_original=True, focus="number",
            ))
        self.assertFalse(result.success)
        self.assertNotIn("Original-image check", result.content)
        vision.assert_awaited_once()

    def test_reading_rejects_bulk_visual_verification(self):
        from deeptutor_pdf_ocr.tools import verify_reading
        result = asyncio.run(verify_reading(None, "test", "1-100", {"verify_original": True, "focus": "all text"}))
        self.assertFalse(result.success)
        self.assertIn("ONE", result.content)

    def test_crop_and_page_bounds_are_checked(self):
        from deeptutor_pdf_ocr.engine import render_page
        data = scanned_pdf()
        for page, crop in [(0, None), (3, None), (1, [0, 0, 2, 1]), (1, [0.5, 0, 0.2, 1])]:
            with self.assertRaises(ValueError):
                render_page(data, page, crop)


if __name__ == "__main__":
    unittest.main()
