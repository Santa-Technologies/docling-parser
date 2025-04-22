from pathlib import Path
from contextlib import asynccontextmanager
from io import BytesIO
from typing import AsyncIterator, Callable
import logging
import asyncio

from docling.datamodel.base_models import (
    ConversionStatus,
    DoclingComponentType,
    InputFormat,
)
from docling.datamodel.document import ConversionResult
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.io import DocumentStream
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import uvicorn

from src.models import (
    OutputFormat,
    ParseFileRequest,
    ParseResponse,
    ParseResponseData,
    ParseUrlRequest,
)
from src.config import Config, get_log_config
from src.model_manager import ModelManager

logger = logging.getLogger(__name__)

# Initialize configuration
config = Config()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize app state on startup and cleanup on shutdown"""
    logger.info("Starting application initialization...")
    app.state.ready = False
    app.state.config = config

    # Start model initialization in background
    asyncio.create_task(initialize_models())

    yield

    # Cleanup on shutdown
    logger.info("Shutting down application...")
    if hasattr(app.state, "model_manager"):
        app.state.model_manager = None
    app.state.ready = False

# Create FastAPI app instance with lifespan
app = FastAPI(lifespan=lifespan)

async def initialize_models():
    """Initialize models in background"""
    try:
        logger.info("Initializing model manager...")
        config = app.state.config

        # Initialize model manager with GCP bucket if configured
        model_manager = ModelManager(cache_bucket=config.cache_bucket)

        # Sync models from bucket if available
        model_manager.sync_with_bucket()

        # Load OCR models based on configuration
        if config.ocr_languages:
            model_manager.load_ocr_models(config.ocr_languages.split(","))

        # Load enrichment models based on configuration
        if config.do_code_enrichment:
            model_manager.load_enrichment_models("code")
        if config.do_formula_enrichment:
            model_manager.load_enrichment_models("formula")
        if config.do_picture_classification:
            model_manager.load_enrichment_models("picture_classification")
        if config.do_picture_description:
            model_manager.load_enrichment_models("picture_description")

        app.state.model_manager = model_manager
        app.state.ready = True
        logger.info("Model initialization complete")
    except Exception as e:
        logger.error(f"Error during model initialization: {e}")
        raise

@app.get("/health")
async def health_check():
    """Health check endpoint that responds immediately"""
    return {"status": "healthy"}

@app.get("/ready")
async def readiness_check():
    """Readiness check that verifies models are loaded"""
    if not getattr(app.state, "ready", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application is not ready yet"
        )
    return {"status": "ready"}

bearer_auth = HTTPBearer(auto_error=False)

async def authorize_header(
    request: Request, bearer: HTTPAuthorizationCredentials | None = Depends(bearer_auth)
) -> None:
    # Do nothing if config is not initialized or AUTH_KEY is not set
    if not hasattr(request.app.state, "config") or request.app.state.config is None:
        return
    auth_token: str | None = request.app.state.config.auth_token
    if auth_token is None:
        return

    # Validate auth bearer
    if bearer is None or bearer.credentials != auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Unauthorized"},
        )

@app.exception_handler(Exception)
async def ingestion_error_handler(_, exc: Exception) -> None:
    detail = {"message": str(exc)}
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail
    )

ConvertData = str | Path | DocumentStream
ConvertFunc = Callable[[ConvertData], ConversionResult]


def convert(request: Request) -> ConvertFunc:
    def convert_func(data: ConvertData) -> ConversionResult:
        try:
            result = request.app.state.model_manager.converter.convert(data, raises_on_error=False)
            _check_conversion_result(result)
            return result
        except FileNotFoundError as exc:
            logger.error(f"File not found error: {str(exc)}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "Input not found"},
            ) from exc

    return convert_func


@app.post("/parse/url", response_model=ParseResponse)
def parse_document_url(
    payload: ParseUrlRequest,
    convert: ConvertFunc = Depends(convert),
    _=Depends(authorize_header),
) -> ParseResponse:
    result = convert(payload.url)
    output = _get_output(result.document, payload.output_format)

    json_output = result.document.export_to_dict() if payload.include_json else None

    return ParseResponse(
        message="Document parsed successfully",
        status="Ok",
        data=ParseResponseData(output=output, json_output=json_output),
    )


@app.post("/parse/file", response_model=ParseResponse)
def parse_document_stream(
    file: UploadFile,
    convert: ConvertFunc = Depends(convert),
    payload: ParseFileRequest = Depends(ParseFileRequest.from_form_data),
    _=Depends(authorize_header),
) -> ParseResponse:
    binary_data = file.file.read()
    data = DocumentStream(
        name=file.filename or "unset_name", stream=BytesIO(binary_data)
    )

    result = convert(data)
    output = _get_output(result.document, payload.output_format)

    json_output = result.document.export_to_dict() if payload.include_json else None

    return ParseResponse(
        message="Document parsed successfully",
        status="Ok",
        data=ParseResponseData(output=output, json_output=json_output),
    )


def _check_conversion_result(result: ConversionResult) -> None:
    if result.status != ConversionStatus.SUCCESS:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"Conversion failed: {result.error_message}"},
        )


def _get_output(document: DoclingDocument, format: OutputFormat) -> str:
    if format == OutputFormat.MARKDOWN:
        return document.export_to_markdown()
    if format == OutputFormat.TEXT:
        return document.export_to_text()
    if format == OutputFormat.HTML:
        return document.export_to_html()


if __name__ == "__main__":
    config = Config()
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=config.port,
        log_config=get_log_config(config.log_level),
        reload=config.dev_mode,
        workers=config.get_num_workers(),
    )
