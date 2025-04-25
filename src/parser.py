import logging
from typing import Any, Iterable, Optional
from enum import Enum
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.chunking import HybridChunker, BaseChunk, DocChunk
from docling_core.types.doc.document import Uint64
from langchain_docling import DoclingLoader
from langchain_docling.loader import ExportType, BaseMetaExtractor, DoclingDocument
from langchain_core.documents import Document
import re


class IsTrailing:
    """An optional true-by-default boolean that you can store by reference. Think `BooleanValue` from Java."""

    value: Optional[bool]

    def __init__(self, value: Optional[bool]):
        self.value = value

    def __bool__(self) -> bool:
        return True if self.value is None else self.value

    def __str__(self) -> str:
        return self.__bool__().__str__()


class MetaExtractorExtras(BaseMetaExtractor):
    """
    What this adds to the metadata:
        - First and last page numbers that each chunk appears in
        - Page edge detection
    """

    prev_file_hash: Optional[Uint64] = None
    prev_max_page_no: Optional[int] = None
    prev_is_trailing: Optional[IsTrailing] = None

    def extract_chunk_meta(self, file_path: str, chunk: BaseChunk) -> dict[str, Any]:
        if type(chunk) is not DocChunk:
            logging.warning("chunk isn't a docchunk")
            return {"source": file_path}

        if chunk.meta.origin is None:
            logging.warning("chunk has no origin")
            return {"source": file_path}

        # Reset state whenever we're in a new file
        file_hash = chunk.meta.origin.binary_hash
        if file_hash != self.prev_file_hash:
            self.prev_file_hash = file_hash
            self.prev_max_page_no = None
            self.prev_is_trailing = None

        min_page_no = None
        max_page_no = None

        # Find the first and last page that the chunk appears in
        for item in chunk.meta.doc_items:
            for prov in item.prov:
                if min_page_no:
                    min_page_no = min(min_page_no, prov.page_no)
                else:
                    min_page_no = prov.page_no

                if max_page_no:
                    max_page_no = max(max_page_no, prov.page_no)
                else:
                    max_page_no = prov.page_no

        if min_page_no is None:
            min_page_no = 0
        if max_page_no is None:
            max_page_no = 0

        # True if the chunk is across two pages
        is_crossing_pages = min_page_no < max_page_no

        # On a new page if:
        # 1) The chunk doesn't start where the previous one ended
        # 2) It's the first chunk
        is_on_new_page = (self.prev_max_page_no is None) or (
            self.prev_max_page_no < min_page_no)

        # Leading if:
        # 1) The previous chunk was on a previous page or it's the first chunk
        # 2) Chunk crosses two pages
        is_leading = is_on_new_page or is_crossing_pages

        # Trailing if:
        # 1) Chunk crosses two pages
        # 2) The next iteration decides that it's trailing
        is_trailing = IsTrailing(
            is_crossing_pages if is_crossing_pages else None)

        # Previous chunk was trailing, if the previous chunk was on a previous page
        if self.prev_is_trailing is not None and self.prev_is_trailing.value is None:
            self.prev_is_trailing.value = is_on_new_page

        # Keep track of the previous iteration
        self.prev_max_page_no = max_page_no
        self.prev_is_trailing = is_trailing

        return {
            "source": file_path,
            "dl_meta": chunk.meta.export_json_dict(),
            "min_page_no": min_page_no,
            "max_page_no": max_page_no,
            # Whether the chunk has an item that is at the start of a page
            "is_leading": is_leading,
            # Whether the chunk has an item that is at the end of a page
            # The value gets updated later if this method is ever called again
            # This is an insane workaround but it works
            "is_trailing": str(is_trailing),
        }

    # No clue what this does. Copied from the default implementation.
    def extract_dl_doc_meta(
            self, file_path: str, dl_doc: DoclingDocument
    ) -> dict[str, Any]:
        return {"source": file_path}


class RepetitionPosition(Enum):
    START = 1
    """Remove repeating headers"""
    END = 2
    """Remove repeating footers"""


def remove_generic_repetitions(docs: list[Document], pos: RepetitionPosition):
    """
    Remove any lines of text that appear on at least two pages in a row.
    Use `pos` to specify whether to look at headers or footers.
    """

    prev_docs = []
    prev_lines = None
    needle = None

    if pos == RepetitionPosition.START:
        metadata_key = "is_leading"
    elif pos == RepetitionPosition.END:
        metadata_key = "is_trailing"

    for doc in docs:
        if not doc.metadata[metadata_key]:
            continue

        curr_lines = doc.page_content.splitlines()

        if needle is not None and needle in curr_lines:
            doc.page_content = doc.page_content.replace(needle, "")
        elif prev_lines is not None:
            overlap = prev_lines.intersection(curr_lines)

            # Remove the needle if:
            # 1) There is an overlap
            # 2) We have a streak of at least 3 pages
            if len(overlap) != 0:
                if len(prev_docs) >= 2:
                    # Maybe want to consider multiple needles
                    needle = overlap.pop()
                    for prev_doc in prev_docs:
                        prev_doc.page_content = prev_doc.page_content.replace(
                            needle, "")
                    doc.page_content = doc.page_content.replace(needle, "")
            # If there's no overlap, drop the streak of docs
            else:
                prev_docs.clear()
                needle = None

        prev_docs.append(doc)
        prev_lines = set(curr_lines)


page_number_pattern = re.compile(r"Seite\s*\d+(\s*von\s*\d+)")


def remove_page_numbers(docs: list[Document]):
    """Remove any lines that go "Seite ... [von ...]" from footers."""

    for doc in docs:
        if not doc.metadata["is_trailing"]:
            continue

        doc.page_content = page_number_pattern.sub("", doc.page_content)


double_space_pattern = re.compile(r"\s{2,}")
trailing_space_pattern = re.compile(r"\s\n")
double_newline_pattern = re.compile(r"\n{2,}")


def remove_whitespace(docs: list[Document]):
    """Remove any repeating and hanging newline and spaces."""

    for doc in docs:
        doc.page_content = double_space_pattern.sub(" ", doc.page_content)
        doc.page_content = trailing_space_pattern.sub("\n", doc.page_content)
        doc.page_content = double_newline_pattern.sub("\n", doc.page_content)

        doc.page_content = doc.page_content.removeprefix("\n")
        doc.page_content = doc.page_content.removesuffix("\n")
        doc.page_content = doc.page_content.removeprefix(" ")
        doc.page_content = doc.page_content.removesuffix(" ")


def remove_prelude(docs: list[Document]) -> list[Document]:
    """
    Remove the table of contents and anything that comes before.
    This returns a new list.
    """

    last_doc = None

    for i, doc in enumerate(docs):
        if doc.page_content == "Inhaltsverzeichnis":
            last_doc = i
            break

    if last_doc is None:
        return docs
    else:
        return docs[last_doc + 1:]


def parse_files(file_paths: Iterable[str]) -> list[Document]:
    """
    Parses files into RAG documents (AKA chunks) and trims their layout content.
    File paths can be remote URLs.
    """

    # setting up Converter pipeline
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options.do_cell_matching = True

    loader = DoclingLoader(
        file_path=file_paths,
        export_type=ExportType.DOC_CHUNKS,
        chunker=HybridChunker(
            tokenizer="sentence-transformers/all-MiniLM-L6-v2"),
        converter=DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options
                )
            }
        ),
        meta_extractor=MetaExtractorExtras()
    )

    docs = loader.load()

    remove_generic_repetitions(docs, RepetitionPosition.START)
    remove_generic_repetitions(docs, RepetitionPosition.END)
    remove_page_numbers(docs)
    remove_whitespace(docs)
    docs = remove_prelude(docs)

    return docs
