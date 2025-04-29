from enum import StrEnum, auto
from typing import Any, List, Optional, Dict
from fastapi import Form
from pydantic import BaseModel, ConfigDict, Field
from langchain_docling.loader import ExportType


class BaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OutputFormat(StrEnum):
    MARKDOWN = auto()
    TEXT = auto()
    HTML = auto()


class ParseRequest(BaseRequest):
    include_json: bool = Field(
        False,
        description="Include a json representation of the document in the response",
    )
    output_format: OutputFormat = Field(
        OutputFormat.MARKDOWN, description="Output format of parsed text"
    )


class ParseUrlRequest(ParseRequest):
    url: str = Field(..., description="Download url for input file")


class ParseFileRequest(ParseRequest):
    @classmethod
    def from_form_data(
        cls,
        data: str = Form(..., examples=[ParseRequest().model_dump_json()]),
    ) -> "ParseFileRequest":
        return cls.model_validate_json(data)


class BaseResponse(BaseModel):
    message: str
    status: str


class ParseResponseData(BaseModel):
    output: str
    json_output: dict[str, Any] | None = None


class ParseResponse(BaseResponse):
    data: ParseResponseData


class LoadDocumentRequest(BaseModel):
    file_paths: List[str] = Field(
        ...,
        description="List of paths to document files or URLs",
        examples=[["https://example.com/doc1.pdf", "https://example.com/doc2.pdf"]]
    )
    export_type: ExportType = Field(
        ExportType.DOC_CHUNKS,
        description="Type of export to perform",
        examples=["doc_chunks"]
    )
    chunker_kwargs: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {"tokenizer": "sentence-transformers/all-MiniLM-L6-v2"},
        description="Optional arguments for the chunker"
    )
    md_export_kwargs: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional arguments for markdown export",
        examples=[{"include_metadata": True}]
    )


class DocumentChunk(BaseModel):
    """A chunk of a document with its content and metadata."""
    page_content: str
    metadata: Dict[str, Any]


class LoadDocumentResponse(BaseModel):
    """Response containing processed document chunks."""
    chunks: List[DocumentChunk]
    status: str = "success"
    message: str = "Document loaded successfully"


class ChunkUrlRequest(BaseModel):
    """Request model for chunking a single document URL."""
    url: str = Field(
        ...,
        description="URL of the document to process",
        examples=["https://example.com/document.pdf"]
    )
