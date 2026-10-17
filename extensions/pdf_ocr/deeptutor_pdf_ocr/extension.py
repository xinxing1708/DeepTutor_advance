from deeptutor.capabilities.protocol import PromptBlock
from .tools import GUIDANCE


def direct_pdf_reading(context):
    index = context.metadata.get("source_index") or {}
    return bool(context.metadata.get("reading_material_id")) or any(
        str(text).startswith("[PDF-OCR:") for text in index.values()
    )


class PdfOcrExtension:
    name = "pdf_ocr"
    owned_tools = ("read_source",)

    def is_active(self, context):
        return direct_pdf_reading(context)

    def system_block(self, context, *, language, prompts):
        return PromptBlock("pdf_ocr", "Read attached documents with read_source and the open reader with read_material. "
                           "Use the attached source IDs exactly; use physical PDF page numbers, not printed book page numbers. "
                           "Retrieve relevant text before making claims about it. " + GUIDANCE)

    def augment_kwargs(self, tool_name, kwargs, context):
        if tool_name == "read_source" and self.is_active(context):
            return {**kwargs, "source_index": context.metadata.get("source_index") or {}}
        return kwargs

    def pre_loop_seed(self, context):
        return ""
