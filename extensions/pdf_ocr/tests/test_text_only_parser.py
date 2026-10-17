import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deeptutor.runtime.isolated_worker import (
    DEFAULT_ISOLATED_TIMEOUT_SECONDS,
    IsolatedWorkerTimeout,
)
from deeptutor.services.parsing.engines.text_only.engine import TextOnlyParser


class KnowledgeBaseOcrDeadlineTests(unittest.TestCase):
    def test_scanned_pdf_can_finish_after_default_worker_deadline(self):
        # Exercise the KB parser caller, where OCR was killed after 120 seconds.
        def slow_ocr(_task, _source, output, *, timeout=DEFAULT_ISOLATED_TIMEOUT_SECONDS, kwargs):
            if timeout < 1800:
                raise IsolatedWorkerTimeout("scanned textbook still needs OCR")
            Path(output).write_text("--- Page 548 ---\n软件设计师", encoding="utf-8")

        with tempfile.TemporaryDirectory() as folder:
            workdir = Path(folder)
            with patch(
                "deeptutor.services.parsing.engines.text_only.engine.run_in_isolated_process_sync",
                side_effect=slow_ocr,
            ):
                TextOnlyParser().parse(Path("textbook.PDF"), workdir, config={})
            self.assertIn("Page 548", (workdir / "textbook.md").read_text(encoding="utf-8"))

    def test_non_pdf_keeps_default_worker_deadline(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch(
                "deeptutor.services.parsing.engines.text_only.engine.run_in_isolated_process_sync"
            ) as worker:
                TextOnlyParser().parse(Path("notes.txt"), Path(folder), config={})
        self.assertEqual(
            worker.call_args.kwargs.get("timeout", DEFAULT_ISOLATED_TIMEOUT_SECONDS),
            DEFAULT_ISOLATED_TIMEOUT_SECONDS,
        )


if __name__ == "__main__":
    unittest.main()
