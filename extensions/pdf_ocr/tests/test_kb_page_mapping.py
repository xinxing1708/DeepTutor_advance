"""Exercise OCR serialization -> KB loader -> real text splitting, without indexing."""

import asyncio
import base64
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import pymupdf
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import MetadataMode
from llama_index.core.schema import NodeWithScore
from deeptutor_pdf_ocr.engine import PdfText


def loader_class():
    candidate = os.environ.get("PDF_PAGE_MAPPING_LOADER")
    if not candidate:
        from deeptutor.services.rag.pipelines.llamaindex.document_loader import LlamaIndexDocumentLoader
        return LlamaIndexDocumentLoader
    name = "deeptutor.services.rag.pipelines.llamaindex._candidate_page_loader"
    spec = importlib.util.spec_from_file_location(name, candidate)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.LlamaIndexDocumentLoader


class KnowledgeBasePageMappingTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.workspace.cleanup)
        self.kb = Path(self.workspace.name) / "知识库"
        self.source = self.kb / "raw" / "教材" / "软件设计师.PDF"
        self.digest = "a" * 64
        self.loader = loader_class()()

    def load_pages(self, texts, source=None):
        source = source or self.source
        parsed = PdfText(self.digest, [{"text": text} for text in texts], self.kb).chat_text()
        with patch.object(self.loader, "_parse_document", return_value=(parsed, [], "text_only")):
            return asyncio.run(self.loader.load([str(source)], kb_dir=self.kb))

    @staticmethod
    def split(documents):
        # No embedding transformation, vector index or persisted cache is created.
        splitter = SentenceSplitter(
            chunk_size=192, chunk_overlap=24,
            tokenizer=lambda value: list(value),
            chunking_tokenizer_fn=lambda value: [value],
        )
        return IngestionPipeline(transformations=[splitter], disable_cache=True).run(
            documents=documents, show_progress=False,
        )

    def test_load_assigns_physical_page_and_exact_relative_source(self):
        docs = self.load_pages(["数据库第一页", "设计模式第二页"])
        self.assertEqual(len(docs), 2)
        self.assertEqual([doc.metadata["page"] for doc in docs], [1, 2])
        for page, doc in enumerate(docs, 1):
            self.assertEqual(doc.metadata["page_label"], str(page))
            self.assertEqual(doc.metadata["source_path"], "教材/软件设计师.PDF")
            self.assertEqual(doc.metadata["file_path"], str(self.source))
            self.assertEqual(doc.metadata["pdf_ocr_id"], self.digest)
            self.assertNotIn("read_source", doc.text)

    def test_every_chunk_keeps_its_page_even_without_a_text_marker(self):
        docs = self.load_pages(["数据库规范化。" * 90, "软件设计模式。" * 90])
        nodes = self.split(docs)
        self.assertGreater(len(nodes), 4)
        for node in nodes:
            page = node.metadata["page"]
            self.assertIn(page, (1, 2))
            self.assertEqual(node.metadata["page_label"], str(page))
            self.assertEqual(node.metadata["source_path"], "教材/软件设计师.PDF")
            self.assertEqual(node.metadata["pdf_ocr_id"], self.digest)
            self.assertNotIn("--- Page", node.text)
            self.assertIn("数据库" if page == 1 else "软件", node.text)
            self.assertNotIn("软件" if page == 1 else "数据库", node.text)

    def test_empty_pages_do_not_renumber_later_pages(self):
        docs = self.load_pages(["first physical page", "", "third physical page"])
        self.assertEqual([doc.metadata["page"] for doc in docs], [1, 3])
        self.assertEqual([doc.metadata["page"] for doc in self.split(docs)], [1, 3])

    def test_repeated_page_text_has_distinct_parent_documents(self):
        docs = self.load_pages(["identical page text", "identical page text"])
        self.assertEqual(len(docs), 2)
        self.assertNotEqual(docs[0].doc_id, docs[1].doc_id)
        nodes = self.split(docs)
        self.assertEqual({node.metadata["page"] for node in nodes}, {1, 2})
        self.assertEqual(len({node.ref_doc_id for node in nodes}), 2)
        for node in nodes:
            restored = type(node).from_json(node.to_json())
            self.assertEqual(restored.metadata, node.metadata)

    def test_locator_metadata_does_not_consume_chunk_budget(self):
        source = self.kb / "raw" / ("长目录" * 50) / "book.pdf"
        docs = self.load_pages(["Long page body. " * 70], source)
        self.assertEqual(docs[0].metadata["page"], 1)
        for mode in (MetadataMode.EMBED, MetadataMode.LLM):
            value = docs[0].get_metadata_str(mode=mode)
            self.assertNotIn(str(source), value)
            self.assertNotIn(self.digest, value)
        self.assertTrue(self.split(docs))

    def test_ordinary_text_retains_original_loading_behavior(self):
        docs = []
        text = "--- Page 1 ---\nordinary markdown, not an OCR PDF"
        self.loader._append_if_nonempty(docs, self.kb / "raw" / "notes.md", text)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].text, text)
        self.assertNotIn("page", docs[0].metadata)

    def test_windows_line_endings_preserve_page_boundaries(self):
        parsed = PdfText(self.digest, [{"text": "first"}, {"text": "second"}], self.kb).chat_text()
        with patch.object(self.loader, "_parse_document", return_value=(parsed.replace("\n", "\r\n"), [], "text_only")):
            docs = asyncio.run(self.loader.load([str(self.source)], kb_dir=self.kb))
        self.assertEqual([doc.text for doc in docs], ["first", "second"])
        self.assertEqual([doc.metadata["page"] for doc in docs], [1, 2])

    def test_retrieved_chunk_can_open_exact_original_page_for_the_model(self):
        from deeptutor.services.rag.pipelines.llamaindex import ingestion
        from deeptutor.services.rag.source_visuals import page_image
        from deeptutor.tools.builtin import RAGTool

        self.source.parent.mkdir(parents=True)
        with pymupdf.open() as pdf:
            for text in ("FIRST PAGE", "", "THIRD PAGE"):
                page = pdf.new_page()
                if text:
                    page.insert_text((50, 80), text)
            data = pdf.tobytes()
        self.source.write_bytes(data)
        self.digest = hashlib.sha256(data).hexdigest()
        docs = self.load_pages(["FIRST PAGE", "", "THIRD PAGE"])
        with patch.object(ingestion, "build_ingestion_pipeline", return_value=IngestionPipeline(
            transformations=[SentenceSplitter(
                chunk_size=192, chunk_overlap=24, tokenizer=lambda value: list(value),
                chunking_tokenizer_fn=lambda value: [value],
            )], disable_cache=True,
        )):
            nodes = ingestion.documents_to_nodes(docs, show_progress=False)
        selected = next(node for node in nodes if node.metadata["page"] == 3)

        candidate = os.environ.get("PDF_PAGE_MAPPING_PIPELINE")
        if candidate:
            name = "deeptutor.services.rag.pipelines.llamaindex._candidate_page_pipeline"
            spec = importlib.util.spec_from_file_location(name, candidate)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            pipeline_class = module.LlamaIndexPipeline
        else:
            from deeptutor.services.rag.pipelines.llamaindex.pipeline import LlamaIndexPipeline
            pipeline_class = LlamaIndexPipeline
        pipeline = pipeline_class.__new__(pipeline_class)
        reference = pipeline._nodes_to_result("third page", [NodeWithScore(node=selected, score=1.0)])["sources"][0]
        self.assertEqual(reference["page"], 3)
        self.assertEqual(reference["source_hash"], self.digest)
        resource = SimpleNamespace(name="test-kb", base_dir=self.kb.parent)
        with patch("deeptutor.multi_user.knowledge_access.resolve_for_rag", return_value=resource), patch(
            "deeptutor.services.rag.kb_paths.resolve_kb_dir", return_value=self.kb,
        ):
            result = asyncio.run(RAGTool().execute(
                query="inspect original cited page", kb_name="test-kb",
                source_path=reference["source_path"], page=reference["page"],
                source_hash=reference["source_hash"], _vision_supported=True,
            ))
        self.assertTrue(result.success, result.content)
        self.assertIn("THIRD PAGE", result.content)
        pixels = next(part for part in result.model_message["content"] if part["type"] == "image_url")
        attached = base64.b64decode(pixels["image_url"]["url"].split(",", 1)[1])
        _, expected = page_image(self.kb, "教材/软件设计师.PDF", 3, expected_hash=self.digest)
        self.assertEqual(attached, expected)


if __name__ == "__main__":
    unittest.main()
