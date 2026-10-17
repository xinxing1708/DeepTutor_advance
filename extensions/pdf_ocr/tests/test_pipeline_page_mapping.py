"""Exercise retrieval formatting with in-memory nodes, without loading the app."""

import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
import unittest


CANDIDATE = Path(os.environ.get(
    "PDF_PAGE_MAPPING_PIPELINE",
    str(Path(__file__).resolve().parents[1]
        / "patched-1.6.14/services/rag/pipelines/llamaindex/pipeline.py"),
))
tree = ast.parse(CANDIDATE.read_text(encoding="utf-8"), filename=str(CANDIDATE))
pipeline = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "LlamaIndexPipeline")
formatter = next(node for node in pipeline.body if isinstance(node, ast.FunctionDef) and node.name == "_nodes_to_result")
namespace = {"json": json, "Any": Any, "Dict": Dict}
exec(compile(ast.Module(body=[formatter], type_ignores=[]), str(CANDIDATE), "exec"), namespace)
nodes_to_result = namespace["_nodes_to_result"]


def result_for(*nodes):
    return nodes_to_result(None, "test query", list(nodes))


def node(text, metadata, *, node_id="chunk-1", score=0.123456):
    return SimpleNamespace(
        node=SimpleNamespace(text=text, metadata=metadata, node_id=node_id),
        score=score,
    )


class PageMappingFormattingTests(unittest.TestCase):
    def test_ocr_reference_reaches_body_and_sources(self):
        metadata = {
            "file_name": "教材.pdf",
            "file_path": "D:/fake/raw/章节/教材.pdf",
            "source_path": "章节/教材.pdf",
            "page": 7,
            "page_label": "7",
            "pdf_ocr_id": "a" * 64,
        }
        result = result_for(node("OCR page seven", metadata))
        self.assertIn("[PDF page source: ", result["content"])
        reference = json.loads(result["content"].split("[PDF page source: ", 1)[1].split("; page is", 1)[0])
        self.assertEqual(reference, {key: metadata[key] for key in ("source_path", "page", "page_label", "pdf_ocr_id")})
        self.assertIn("Use rag with this source_path and page", result["content"])
        self.assertTrue(result["content"].endswith("OCR page seven"))
        self.assertEqual(result["answer"], result["content"])
        source = result["sources"][0]
        for key in ("source_path", "page", "page_label", "pdf_ocr_id"):
            self.assertEqual(source[key], metadata[key])
        self.assertEqual(source["source_hash"], metadata["pdf_ocr_id"])
        self.assertEqual(source["source"], metadata["file_path"])
        self.assertEqual(source["content"], "OCR page seven")
        self.assertEqual(source["score"], 0.1235)

    def test_physical_page_wins_over_display_label_for_mapped_source(self):
        result = result_for(node("passage", {"source_path": "book.pdf", "page": 9, "page_label": "printed-3"}))
        self.assertEqual(result["sources"][0]["page"], 9)
        self.assertEqual(result["sources"][0]["page_label"], "printed-3")
        self.assertIn('"page": 9', result["content"])

    def test_each_retrieved_page_keeps_its_reference(self):
        result = result_for(
            node("first page", {"source_path": "book.pdf", "page": 1, "page_label": "1"}, node_id="one"),
            node("late page", {"source_path": "book.pdf", "page": 555, "page_label": "555"}, node_id="late"),
        )
        self.assertEqual([source["page"] for source in result["sources"]], [1, 555])
        self.assertEqual(result["content"].count("[PDF page source:"), 2)
        self.assertIn('"page": 555', result["content"])
        self.assertIn("\nfirst page\n\n[PDF page source:", result["content"])

    def test_pdf_mapping_does_not_require_an_ocr_cache_id(self):
        result = result_for(node("native PDF text", {"source_path": "book.pdf", "page": 2, "page_label": "2"}))
        self.assertNotIn("pdf_ocr_id", result["sources"][0])
        self.assertNotIn("source_hash", result["sources"][0])
        self.assertNotIn("pdf_ocr_id", result["content"])
        self.assertIn('"source_path": "book.pdf"', result["content"])

    def test_legacy_text_and_page_label_are_unchanged(self):
        result = result_for(node("legacy content", {"file_name": "legacy.pdf", "file_path": "legacy/path.pdf", "page_label": "iv", "page": 4}))
        self.assertEqual(result["content"], "legacy content")
        self.assertEqual(result["sources"][0]["page"], "iv")
        self.assertNotIn("source_path", result["sources"][0])
        self.assertNotIn("pdf_ocr_id", result["sources"][0])

    def test_visual_asset_fields_are_preserved(self):
        metadata = {
            "visual_asset_id": "v" * 64,
            "source_document_id": "s" * 64,
            "bbox": [1, 2, 3, 4],
            "caption": "Figure 2.1",
            "source_locator": "blocks.json#/2",
            "page_label": 7,
        }
        result = result_for(node("visual context", metadata))
        for key, value in metadata.items():
            if key != "page_label":
                self.assertEqual(result["sources"][0][key], value)
        self.assertEqual(result["sources"][0]["page"], 7)
        self.assertEqual(result["content"], "visual context")

    def test_empty_result_remains_empty(self):
        result = result_for()
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["answer"], "")
        self.assertEqual(result["content"], "")


if __name__ == "__main__":
    unittest.main()
